#!/usr/bin/env bash
# Install the timetrack focus logger locally — the VSCode analogue of the Chrome
# "load unpacked". Symlinks this folder into the extensions dir of every VSCode
# variant found, so edits here are picked up on the next window reload.
#   Usage: ./install.sh
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"

installed=0
for d in ".vscode" ".vscode-insiders" ".vscode-oss"; do
  if [ -d "$HOME/$d" ]; then
    base="$HOME/$d/extensions"
    mkdir -p "$base"
    dest="$base/timetrack-focus"
    rm -rf "$dest"
    ln -s "$SRC" "$dest"
    echo "linked -> $dest"
    installed=1
  fi
done

[ "$installed" -eq 1 ] || { echo "no VSCode install dirs found (~/.vscode etc.)"; exit 1; }
echo "verify with the command palette: 'timetrack: write a test focus tick'."
echo "installed — now reload VSCode (Cmd+Shift+P -> Developer: Reload Window) to activate."
