#!/usr/bin/env python3
"""timetrack-focus — log which git worktree you were actually LOOKING at, by
watching the focused iTerm2 tab.

timetrack's attention model is latest-wins inference: the lane you last typed in
stays "active" until your next prompt lands elsewhere. That fills the gaps with a
guess. This daemon turns the guess into a measurement — every minute it records
which Claude session was sat in front of your eyes, so reading Claude work (not
just typing) counts on the right lane.

How it hangs together (same chain claude-tab-color walks):
  - The focused iTerm2 session has a controlling tty.
  - Claude writes ~/.claude/sessions/<pid>.json mapping pid -> sessionId; the
    pid's tty (via `ps`) is the iTerm2 session's tty.
  - The session's transcript jsonl carries `cwd` + `gitBranch` on each line.
  - So: focused session --(tty)--> Claude pid --> sessionId --> transcript -->
    latest cwd/branch --> a focus tick in ~/.timetrack/focus.log.

It ticks whenever iTerm2 is the frontmost app and the focused tab resolves to a
git worktree. A Claude tab resolves via the chain above; a plain shell tab falls
back to its own working directory (from iTerm2 shell integration) and is only
counted if that directory is inside a git worktree — so reviewing commits in a
bare terminal counts, but a tab parked in ~/ or /tmp ticks nothing. iTerm2 in the
background ticks nothing either way.

Cadence: it polls every POLL_INTERVAL but logs the same tab at most once per
MIN_LOG_GAP (~30s). So a parked tab heartbeats every ~30s, while a *switch* to a
different tab logs immediately (caught within one poll, so segment boundaries are
sharp). The timetrack builder keeps a run only if it spans >= ~30s of dwell, so a
quick flick gives one lone tick and gets dropped.

This is an AutoLaunch daemon. It never writes to the terminal stream, so it can't
glitch Claude's full-screen TUI — it only reads iTerm2 state via the Python API.
"""

import asyncio
import glob
import json
import os
import subprocess
import time

import iterm2

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HOME = os.path.expanduser("~")
SESSIONS_DIR = os.path.join(HOME, ".claude", "sessions")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")

FOCUS_LOG = os.path.join(HOME, ".timetrack", "focus.log")
LOG_PATH = os.path.join(HOME, ".timetrack", "focus-daemon.log")

POLL_INTERVAL = 10               # seconds between focus polls (switch detection latency)
MIN_LOG_GAP = 30                 # seconds; debounce — same tab logs at most this often
TRANSCRIPT_TAIL_BYTES = 262144   # how much of the tail to scan for cwd/branch


def log(msg):
    try:
        with open(LOG_PATH, "a") as f:
            f.write(msg + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Reading Claude state  (the tty -> session -> cwd/branch chain)
# ---------------------------------------------------------------------------

def _tty_basename(value):
    """Normalise '/dev/ttys003' or 'ttys003' -> 'ttys003'. '' / '??' -> None."""
    if not value:
        return None
    value = value.strip()
    if value in ("?", "??", "-"):
        return None
    return os.path.basename(value)


def _pid_tty(pid):
    """Controlling tty basename for a pid, or None."""
    try:
        out = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(pid)],
            capture_output=True, text=True, timeout=2,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    return _tty_basename(out)


def _worktree_branch(cwd):
    """If cwd is inside a git worktree, return its branch name ('HEAD' when
    detached); otherwise return False. The bool-vs-str result is the gate: a
    plain shell tab only ticks when this returns a string, so directories that
    aren't repos (~/, /tmp, …) are silently skipped."""
    try:
        res = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    if res.returncode != 0:
        return False
    return res.stdout.strip() or "HEAD"


def _transcript_for_session(session_id):
    """Find the transcript jsonl for a Claude sessionId, or None."""
    matches = glob.glob(os.path.join(PROJECTS_DIR, "*", session_id + ".jsonl"))
    return matches[0] if matches else None


def _latest_cwd_branch(transcript_path):
    """(cwd, gitBranch) from the last transcript line that carries a cwd, else
    (None, None). Both live together on each user/assistant entry."""
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as f:
            if size > TRANSCRIPT_TAIL_BYTES:
                f.seek(size - TRANSCRIPT_TAIL_BYTES)
                f.readline()  # drop the partial first line
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return None, None

    cwd = branch = None
    for line in data.splitlines():
        if '"cwd"' not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("cwd"):
            cwd = obj["cwd"]
            branch = obj.get("gitBranch")  # may be absent on the line
    return cwd, branch


def build_tty_claude_map():
    """Map tty basename -> (cwd, branch), for every live Claude session."""
    mapping = {}
    for path in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(path) as f:
                info = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        pid = info.get("pid")
        session_id = info.get("sessionId")
        if not pid or not session_id:
            continue

        tty = _pid_tty(pid)
        if not tty:
            continue

        transcript = _transcript_for_session(session_id)
        if not transcript:
            continue

        cwd, branch = _latest_cwd_branch(transcript)
        if cwd:
            mapping[tty] = (cwd, branch)
    return mapping


def write_tick(cwd, branch):
    """Append `epoch \\t cwd \\t branch \\t source` to the focus log (never fatal).
    The source tags who logged it, so iTerm and VSCode ticks are tellable apart."""
    try:
        os.makedirs(os.path.dirname(FOCUS_LOG), exist_ok=True)
        with open(FOCUS_LOG, "a") as f:
            f.write(f"{int(time.time())}\t{cwd}\t{branch or ''}\titerm\n")
    except OSError as e:
        log(f"write_tick failed: {e}")


# ---------------------------------------------------------------------------
# Watching iTerm2 focus
# ---------------------------------------------------------------------------

async def _focused_session_info(app):
    """(tty, cwd) for the session in the current tab of the key window. Either
    field may be None. cwd comes from iTerm2 shell integration's `path`."""
    win = app.current_terminal_window
    if win is None:
        return None, None
    tab = win.current_tab
    if tab is None:
        return None, None
    session = tab.current_session
    if session is None:
        return None, None
    tty = _tty_basename(await session.async_get_variable("tty"))
    path = await session.async_get_variable("path")
    return tty, (path or None)


async def watch_app_active(connection, state):
    """Keep state['active'] in step with whether iTerm2 is the frontmost app."""
    async with iterm2.FocusMonitor(connection) as monitor:
        while True:
            update = await monitor.async_get_next_update()
            if update.application_active is not None:
                state["active"] = update.application_active.application_active


async def heartbeat(connection, state):
    """Poll the focused tab every POLL_INTERVAL. Log a tick when focus is on a
    Claude tab AND either the tab just changed (sharp switch boundary) or it's
    been >= MIN_LOG_GAP since we last logged it (steady heartbeat)."""
    app = await iterm2.async_get_app(connection)
    last_tty = None
    last_time = 0.0
    while True:
        try:
            tty, path = (await _focused_session_info(app)) if state["active"] else (None, None)
            if tty:
                cwd, branch = build_tty_claude_map().get(tty, (None, None))
                if not cwd and path:
                    # No Claude session on this tab — fall back to the shell's own
                    # cwd, but only count it when that cwd is a git worktree.
                    wb = _worktree_branch(path)
                    if wb is not False:
                        cwd, branch = path, wb
                if cwd:
                    now = time.time()
                    if tty != last_tty or (now - last_time) >= MIN_LOG_GAP:
                        write_tick(cwd, branch)
                        last_tty, last_time = tty, now
        except Exception as e:  # never let a transient API hiccup kill the loop
            log(f"heartbeat error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


async def main(connection):
    log("timetrack-focus started")
    # Assume frontmost at launch (iTerm2 is active when it starts us); the focus
    # monitor corrects this the first time focus changes.
    state = {"active": True}
    await asyncio.gather(
        watch_app_active(connection, state),
        heartbeat(connection, state),
    )


iterm2.run_forever(main)
