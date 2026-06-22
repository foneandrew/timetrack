#!/usr/bin/env bash
# Register the native messaging host so the extension can write review ticks.
# Usage: ./install-host.sh <extension-id>
#   (load the extension unpacked first, copy its ID from chrome://extensions)
set -euo pipefail

ID="${1:-}"
if [ -z "$ID" ]; then
  echo "usage: $0 <extension-id>"
  echo "  load extension/ unpacked, then copy the ID from chrome://extensions"
  exit 1
fi

HOST_NAME="com.timetrack.review"
HOST_PATH="$(cd "$(dirname "$0")/.." && pwd)/bin/timetrack-review-host"
chmod +x "$HOST_PATH"

MANIFEST=$(cat <<EOF
{
  "name": "$HOST_NAME",
  "description": "timetrack review logger host",
  "path": "$HOST_PATH",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$ID/"]
}
EOF
)

installed=0
for d in "Google/Chrome" "Google/Chrome Canary" "Arc/User Data" "BraveSoftware/Brave-Browser" "Microsoft Edge" "Chromium"; do
  base="$HOME/Library/Application Support/$d"
  if [ -d "$base" ]; then
    dir="$base/NativeMessagingHosts"
    mkdir -p "$dir"
    printf '%s\n' "$MANIFEST" > "$dir/$HOST_NAME.json"
    echo "installed -> $dir/$HOST_NAME.json"
    installed=1
  fi
done

[ "$installed" -eq 1 ] || { echo "no Chromium-family browser dirs found"; exit 1; }
echo "done — reload the extension if it was already loaded."
