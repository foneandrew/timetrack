# timetrack

Reconstructs a rough, **visual** picture of where *your* attention went each day
across parallel git worktrees — so you can fill in timesheets without remembering
a fortnight of context-switching.

Rough beats precise. You stay in the loop: it shows you the picture, you read it.

## Run

```bash
./bin/timetrack            # last 4 weeks, opens the view in your browser
./bin/timetrack -w 6       # last 6 weeks
./bin/timetrack --json     # dump the raw JSON blob to stdout (debugging)
```

### Serve mode (live Regenerate button)

Opening the built file as `file://` is fine, but to re-scan your signals without
going back to the terminal, run a tiny local server instead. Served over
`http://localhost`, the view grows a **Regenerate** button that re-greps the
sources in place (and localStorage is rock-solid over a real origin, unlike
`file://`). It also gains a **⚙ Settings** panel (edit the preferences above) and
a **🔌 Setup** panel — live status of the iTerm-focus and GitHub-review
integrations, plus one-click buttons for the scriptable install steps (the
iTerm/Chrome GUI steps still have to be done by hand, and are spelled out there).

```bash
./bin/timetrack --daemon   # serve in the background
./bin/timetrack --open     # open the running server in your browser
./bin/timetrack --status   # is it running, and where?
./bin/timetrack --stop     # stop the background server
./bin/timetrack --serve    # foreground instead — opens the browser, Ctrl-C to stop
./bin/timetrack --daemon --port 9000   # pick a port (default 8765)
```

State lives in `~/.timetrack/serve.pid`; background output in `~/.timetrack/serve.log`.

## How it works

Dumb builder, smart template. `bin/timetrack` greps the durable signal sources,
normalises everything to **local time**, and injects a JSON blob into
`template.html` → `out/timetrack.html`. All timeline maths lives in the template's JS.

**Signals (v1):**
- **Human-typed Claude prompts** — `~/.claude/projects/**/*.jsonl`, filtered to
  `promptSource: typed` (so ralph's autonomous `sdk` prompts are excluded). Each
  carries a timestamp + `cwd` (→ worktree → JIRA). These survive worktree deletion.
- **gco/gcod checkouts** — appended to `~/.timetrack/checkouts.log` by the shell
  wrapper (see *Shell logging* below). Closes the gap where bare `gcod` (fzf)
  resolves the branch to a SHA and loses the name.
- **Terminal focus** — `~/.timetrack/focus.log`, written by the iTerm2 focus
  daemon (see [FOCUS.md](FOCUS.md)). Records which worktree was on screen each
  minute, turning latest-wins inference into measurement. Optional.

## Shell logging (gco/gcod)

`gco`/`gcod` in `~/.zshrc` are wrapped to record the branch you select. A
fail-safe helper logs `epoch ⇥ cwd ⇥ branch ⇥ action`; a logging error can
never change the checkout's behaviour:

```zsh
_timetrack_log () {  # $1 = action (gco|gcod), $2 = branch
  { mkdir -p "$HOME/.timetrack" && \
    printf '%s\t%s\t%s\t%s\n' "$(date +%s)" "$PWD" "$2" "$1" >> "$HOME/.timetrack/checkouts.log"; } 2>/dev/null
  return 0
}
# ...then each checkout fn ends with:  && _timetrack_log gcod "$branch"
```

Only affects shells opened *after* the edit — run `source ~/.zshrc` or open a new
tab to start logging now. A timestamped backup of the original sits at
`~/.zshrc.bak.timetrack-*`.

**Attention model:** latest-wins, no mid-day gaps. The lane you last acted in stays
active until your next event lands in a different lane. The day runs from your first
signal to your last signal + 30min idle tail, framed 8am–5pm. Today is excluded from
the tail — it ends exactly at the last signal, so it never shows time you've not spent yet.

## Views

- **Week** (default): one vertical bar per day (morning at top), segmented by the
  JIRA that was active. Tabs switch weeks. Click a day to drill in.
- **Day drill-down:** the resolved attention bar plus a column per worktree that
  fed into it, and a rough per-JIRA breakdown.

## Config

Copy `config.example.json` → `config.json` (gitignored — it holds your secret
calendar URL). Keys:
- `app_paths` — repo(s) whose lane is pinned at the top as the "app" lane.
- `ics_url` — Outlook published-calendar `.ics` link. Meetings render as their
  own lane and overlay the resolved attention during their slot (the task
  underneath resumes after). FREE / cancelled / `skip_meetings` matches default
  to OFF; click a meeting in the drill-in to toggle (persisted in localStorage).
  Recurring meetings (WEEKLY/DAILY/MONTHLY) are expanded; times in
  `TZID=New Zealand Standard Time` are treated as local.
- `skip_meetings` — title substrings that default to OFF.
- `jira_names` — override the auto-derived JIRA names.

Personal preferences (all optional — these are the defaults):
- `day_start` / `day_end` — the framed working day (`"08:00"` / `"17:00"`).
- `full_day` — the **Fit to** timesheet target (`"07:30"`).
- `idle_tail_min` — how long your last signal of the day keeps holding (`30`).
- `round_to_min` — the **Round to** granularity (`15`).
- `weeks` — default number of weeks to scan when `-w` isn't given (`4`).

In [serve mode](#serve-mode-live-regenerate-button) these last six are also
editable from the **⚙ Settings** panel in the view — it writes them back to
`config.json` (preserving everything else) and rebuilds. `-w` on the command
line still overrides `weeks` for that run.

## GitHub review (browser extension)

`extension/` is an MV3 browser extension that logs **active** PR-review time.
Presence is interaction-driven: scroll/click/keydown/wheel on a visible PR page
emit a tick even when the browser isn't the focused window (so reading a PR on a
second monitor while you work elsewhere still counts), plus a 75s heartbeat while
the tab is focused for motionless reading. Everything is debounced to one tick
per 30s, and the builder's dwell filter needs 2 ticks, so a parked tab or a
scroll-by doesn't count. Each tick logs `epoch ⇥ jira ⇥ url ⇥ title ⇥ branch`
to `~/.timetrack/review.log`; the builder stitches them into review intervals on
a synthetic `GitHub review` lane.

Review time attaches to the PR's JIRA (inferred from branch/title, re-inferred in
the builder from the logged title/url if the scrape missed). A review-only JIRA is
named from its PR **branch** (the PR title is the fallback for older log lines that
predate branch capture); hovering its legend entry pops the full PR title and
author. If that JIRA has no worktree activity that day, the row is badged
**review** (you reviewed someone else's ticket); otherwise it folds into your own
work on it.

Wiring (a Chrome extension can't write to disk, so a native-messaging host bridges it):
1. `chrome://extensions` → enable Developer mode → **Load unpacked** → pick `extension/`.
2. Copy the extension's **ID**, then run `extension/install-host.sh <id>` (registers
   the host in every Chromium-family browser found).
3. Reload the extension. Click its toolbar icon once — it writes a `TEST-1` line to
   `~/.timetrack/review.log` to prove the bridge. Delete that line (or the file) before real use.

Test the host alone (no extension needed):
```bash
python3 -c 'import struct,sys,json; m=json.dumps({"epoch":1,"jira":"PBL-1"}).encode(); sys.stdout.buffer.write(struct.pack("<I",len(m))+m)' | bin/timetrack-review-host
```

## Terminal focus (iTerm2 daemon)

`bin/timetrack-focus.py` is a standalone iTerm2 AutoLaunch daemon that logs which
worktree was on screen each minute, turning latest-wins inference into
measurement. Setup, internals and tuning live in **[FOCUS.md](FOCUS.md)** —
short version: enable iTerm2's Python API, run `./bin/install-focus-daemon.sh`,
start it from Scripts → AutoLaunch. The builder folds `~/.timetrack/focus.log`
in automatically when it's present.

## Not yet wired (fast-follows)
- Per-JIRA totals in the week view; days-as-rows table shell.
- Clockify project mapping; Jira page-view signal; shell-heartbeat + commit signals.
- RRULE edge cases beyond WEEKLY/DAILY/MONTHLY; all-day events on the timeline.
