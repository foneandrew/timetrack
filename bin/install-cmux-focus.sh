#!/usr/bin/env bash
# Install the cmux focus logger as a launchd agent (start at login, keep alive).
# cmux has no AutoLaunch-a-script hook like iTerm, so launchd is the sane way to
# keep the tailer running. Re-runnable: reloads if already installed.
set -euo pipefail

# Prefer the system python3 at its fixed path: launchd runs with a bare PATH, and
# the script is pure stdlib, so a stable interpreter beats a version-managed one
# (mise/pyenv paths move when versions are pruned). Fall back only if it's absent.
if [ -x /usr/bin/python3 ]; then PY="/usr/bin/python3"; else PY="$(command -v python3)"; fi
[ -n "$PY" ] || { echo "python3 not found"; exit 1; }
SCRIPT="$(cd "$(dirname "$0")" && pwd)/timetrack-cmux-focus.py"
LABEL="com.timetrack.cmux-focus"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/.timetrack"
mkdir -p "$(dirname "$PLIST")" "$LOGDIR"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$SCRIPT</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOGDIR/cmux-focus-daemon.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/cmux-focus-daemon.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "loaded $LABEL"
echo "focus ticks (source: cmux) will flow while a cmux window is focused on a git worktree."
