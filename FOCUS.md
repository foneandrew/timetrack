# Terminal focus daemon

Logs which git worktree you were actually **looking at**, by watching the
focused iTerm2 tab. A standalone iTerm2 AutoLaunch daemon — runs on its own, the
`timetrack` builder picks up its log if it's there and ignores it if it isn't.

## Why

timetrack's attention model is **latest-wins inference**: the lane you last
typed in stays active until your next prompt lands elsewhere. That fills the gaps
between events with a guess. Focus turns the guess into a **measurement** — every
minute it records which Claude session was on screen, so *reading* Claude work
(not just typing) counts on the right lane. Worktrees you only ever looked at
still show up.

## How it works

The daemon walks the chain from the focused tab to the Claude session running in
it, reading `cwd`/branch. For the focused iTerm2 session it:

1. reads the session's tty,
2. finds the Claude pid on that tty, hence its `sessionId`
   (`~/.claude/sessions/<pid>.json`),
3. reads the latest `cwd` + `gitBranch` from that session's transcript
   (`~/.claude/projects/<cwd>/<sessionId>.jsonl`),
4. appends a tick `epoch ⇥ cwd ⇥ branch` to `~/.timetrack/focus.log`.

It only ticks when **iTerm2 is the frontmost app** *and* the focused tab holds a
Claude session — a plain shell tab, or iTerm2 sitting in the background, ticks
nothing. It reads iTerm2 state via the Python API and never writes to the
terminal stream, so it can't corrupt Claude's full-screen TUI.

It polls every 10s but logs a parked tab at most once every ~30s — so a tab you
sit on heartbeats ~30s apart, while a **switch** to a different tab logs
immediately (caught within one poll, so segment boundaries stay sharp).

The builder's `collect_focus` groups consecutive ticks on the same worktree into
a **dwell run**, broken by any signal on a *different* lane — a prompt, checkout
or PR review elsewhere is proof you'd moved on, so it ends the run (which resumes
on the next tick). There is **no max time gap**: if nothing else fired, two
same-lane ticks bridge however far apart they are — no competing signal means
"you were on that ticket" is the best guess. A run is kept only if it spans **at
least 30s** of dwell, so a single fly-by glance (one tick, zero span) is dropped.
Raw ticks stay in the log, so the thresholds can be retuned in the builder later.

## Setup

One-time, in iTerm2 (GUI — can't be scripted):

1. **Settings → General → Magic → tick "Enable Python API"**
2. **Scripts → Manage → Install Python Runtime** (provides the `iterm2` module)

Then:

```sh
./bin/install-focus-daemon.sh
```

Start it from **Scripts → AutoLaunch → timetrack-focus.py**, or relaunch iTerm2.
It auto-starts with iTerm2 from then on.

## Verify

Sit on a Claude tab for a couple of minutes, then:

```sh
tail ~/.timetrack/focus.log          # tick lines: epoch  cwd  branch
tail ~/.timetrack/focus-daemon.log   # daemon status / errors
```

Run `./bin/timetrack` and the worktree lanes fill in denser and truer.

## Tweaking

- Poll rate / heartbeat debounce: `POLL_INTERVAL` / `MIN_LOG_GAP` in `bin/timetrack-focus.py`.
- Min dwell to count a run: `MIN_DWELL_SEC` in `bin/timetrack`.
- Transcript tail scanned for cwd/branch: `TRANSCRIPT_TAIL_BYTES`.
