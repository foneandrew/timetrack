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
  wrapper (see below). Closes the gap where bare `gcod` (fzf) loses the branch name.

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
- `ics_url` — Outlook published-calendar `.ics` link (meetings, not yet wired).
- `skip_meetings` — title substrings that default to OFF.

## Not yet wired (fast-follows)
- Meeting lane from the ICS feed (incl. RRULE expansion for recurring meetings).
- Per-JIRA totals in the week view; days-as-rows table shell.
- Clockify project mapping; Chrome PR-view signal; shell-heartbeat + commit signals.
