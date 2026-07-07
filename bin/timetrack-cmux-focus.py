#!/usr/bin/env python3
"""timetrack-cmux-focus — log which cmux workspace you were looking at, by
tailing cmux's event log.

cmux appends model-lifecycle events to ~/.cmuxterm/events.jsonl as
newline-delimited JSON. Two of them give us everything, no socket or auth
needed (the event log is a plain readable file):

  - window.keyed / window.unkeyed  → is a cmux window the key (focused) window
                                      (drops when you switch to another app)
  - workspace.selected             → the selected workspace (id)

The workspace's own `cwd` in the event is just the shell's cwd — often ~, so
useless for attribution. Instead we resolve the focused workspace's *Claude
session* cwd from ~/.cmuxterm/claude-hook-sessions.json — the real project dir
the agent runs in, exactly like the iTerm daemon reads it from the transcript.
Plain (non-agent) tabs fall back to the workspace shell cwd.

We hold (key, selected-workspace) as state and, while cmux is the key window and
the resolved cwd is a git worktree, heartbeat a tick to ~/.timetrack/focus.log — the
same file and format the iTerm2 daemon writes, tagged source `cmux`, so the
report stitches cmux, iTerm and VSCode ticks into one dwell timeline.

Because the event log only carries edges (no heartbeat), a poll loop supplies
the steady ticks the report's dwell filter needs, exactly like the iTerm daemon.

Run with --status to print the current derived focus state and exit.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
EVENTS = HOME / ".cmuxterm" / "events.jsonl"
SESSIONS = HOME / ".cmuxterm" / "claude-hook-sessions.json"
FOCUS_LOG = HOME / ".timetrack" / "focus.log"
LOG_PATH = HOME / ".timetrack" / "cmux-focus-daemon.log"

POLL_INTERVAL = 10   # seconds between beats (mirrors the iTerm daemon)
MIN_LOG_GAP = 30     # seconds; same-lane debounce


def log(msg):
    try:
        with open(LOG_PATH, "a") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, just not ours to signal
    except OSError:
        return False
    return True


def worktree_branch(cwd):
    """Branch name if cwd is inside a git worktree ('HEAD' when detached), else
    False. The bool-vs-str result is the gate: a non-repo dir (~/, /tmp, …)
    returns False and never ticks."""
    if not cwd:
        return False
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    if r.returncode != 0:
        return False
    return r.stdout.strip() or "HEAD"


class FocusState:
    """Derived from the cmux event stream: is cmux the key window, and what is
    the cwd of the selected workspace."""

    def __init__(self):
        self.key = False
        self.current_ws = None
        self.ws_cwd = {}        # workspace_id -> cwd
        self._offset = 0        # bytes consumed from the event log

    def cwd(self):
        """Working directory of the focused workspace. Prefer the cwd of the
        Claude session running in it (its real project dir) over the workspace's
        shell cwd, which is often just ~."""
        ws = self.current_ws
        if not ws:
            return None
        try:
            data = json.loads(SESSIONS.read_text())
        except (OSError, json.JSONDecodeError):
            data = {}
        # Scan for a live Claude session in this workspace (the "active" shortcut
        # map only tracks the most-recent one), preferring the most recent.
        best = None  # (updatedAt, cwd)
        for s in (data.get("sessions") or {}).values():
            if s.get("workspaceId") != ws:
                continue
            if not _pid_alive(s.get("pid")):
                continue
            c = s.get("cwd") or s.get("workingDirectory")
            if not c:
                continue
            u = s.get("updatedAt") or 0
            if best is None or u > best[0]:
                best = (u, c)
        return best[1] if best else self.ws_cwd.get(ws)

    def _apply(self, ev):
        name = ev.get("name")
        p = ev.get("payload") or {}
        if name == "workspace.selected":
            ws, cwd = p.get("workspace_id"), p.get("cwd")
            if ws and cwd:
                self.ws_cwd[ws] = cwd
            if p.get("selected", True) and ws:
                self.current_ws = ws
        elif name == "window.keyed":
            self.key = bool(p.get("is_key_window", True))
            if p.get("workspace_id"):
                self.current_ws = p["workspace_id"]
        elif name == "window.unkeyed":
            self.key = False

    def drain(self):
        """Consume new event-log lines since last drain, updating state. Handles
        the log being truncated/rotated by reseeding from the top."""
        try:
            size = EVENTS.stat().st_size
        except OSError:
            return
        if size < self._offset:      # truncated → start over
            self.__init__()
        try:
            with open(EVENTS, "r", errors="replace") as f:
                f.seek(self._offset)
                data = f.read()
                self._offset = f.tell()
        except OSError:
            return
        for line in data.splitlines():
            if not line.strip():
                continue
            try:
                self._apply(json.loads(line))
            except json.JSONDecodeError:
                continue


def write_tick(cwd, branch):
    """Append `epoch \\t cwd \\t branch \\t cmux` to the focus log (never fatal)."""
    try:
        os.makedirs(os.path.dirname(FOCUS_LOG), exist_ok=True)
        with open(FOCUS_LOG, "a") as f:
            f.write(f"{int(time.time())}\t{cwd}\t{branch or ''}\tcmux\n")
    except OSError as e:
        log(f"write_tick failed: {e}")


def run():
    log("timetrack-cmux-focus started")
    state = FocusState()
    last_cwd = None
    last_time = 0.0
    while True:
        try:
            state.drain()
            cwd = state.cwd() if state.key else None
            branch = worktree_branch(cwd) if cwd else False
            if cwd and branch is not False:
                now = time.time()
                if cwd != last_cwd or (now - last_time) >= MIN_LOG_GAP:
                    write_tick(cwd, branch)
                    last_cwd, last_time = cwd, now
        except Exception as e:   # never let a transient hiccup kill the loop
            log(f"beat error: {e}")
        time.sleep(POLL_INTERVAL)


def status():
    state = FocusState()
    state.drain()
    cwd = state.cwd()
    print(json.dumps({
        "eventsLog": str(EVENTS),
        "eventsLogExists": EVENTS.exists(),
        "keyWindow": state.key,
        "currentWorkspace": state.current_ws,
        "cwd": cwd,
        "branch": worktree_branch(cwd) if cwd else False,
        "wouldTick": bool(state.key and cwd and worktree_branch(cwd) is not False),
        "knownWorkspaces": len(state.ws_cwd),
    }, indent=2))


if __name__ == "__main__":
    if "--status" in sys.argv:
        status()
    else:
        run()
