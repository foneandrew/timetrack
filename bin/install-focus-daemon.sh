#!/bin/bash
# Symlink the focus daemon into iTerm2's AutoLaunch dir so it starts with iTerm2.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOLAUNCH="$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch"
SCRIPT="timetrack-focus.py"

mkdir -p "$AUTOLAUNCH"
ln -sf "$REPO/$SCRIPT" "$AUTOLAUNCH/$SCRIPT"

echo "Linked $AUTOLAUNCH/$SCRIPT -> $REPO/$SCRIPT"
echo
echo "Prerequisites (one-time, in iTerm2):"
echo "  1. Settings -> General -> Magic -> tick 'Enable Python API'"
echo "  2. Scripts -> Manage -> Install Python Runtime"
echo
echo "Then start it without restarting iTerm2:"
echo "  Scripts -> AutoLaunch -> $SCRIPT"
echo "(or just relaunch iTerm2)"
echo
echo "Ticks land in ~/.timetrack/focus.log; daemon log at ~/.timetrack/focus-daemon.log"
