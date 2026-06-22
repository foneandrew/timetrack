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
signal to your last signal + 30min idle tail, framed 8am–5pm.

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

## GitHub review (browser extension)

`extension/` is an MV3 browser extension that logs **active** PR-review time —
it emits a heartbeat tick every ~75s only while a GitHub PR page is the genuine
foreground tab (visible + focused), so a parked tab doesn't count. Ticks land in
`~/.timetrack/review.log` and the builder stitches them into review intervals on
a synthetic `GitHub review` lane.

Review time attaches to the PR's JIRA (inferred from branch/title, re-inferred in
the builder from the logged title/url if the scrape missed). If that JIRA has no
worktree activity that day, the row is badged **review** (you reviewed someone
else's ticket); otherwise it folds into your own work on it.

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

## Not yet wired (fast-follows)
- Per-JIRA totals in the week view; days-as-rows table shell.
- Clockify project mapping; Jira page-view signal; shell-heartbeat + commit signals.
- RRULE edge cases beyond WEEKLY/DAILY/MONTHLY; all-day events on the timeline.
