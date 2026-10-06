#!/bin/sh
# Ohara: once per new set of changes, check them against the guidelines, then update the docs.
input=$(cat)
case "$input" in *'"stop_hook_active": true'* | *'"stop_hook_active":true'*) exit 0 ;; esac
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
changes=$( { git diff HEAD; git ls-files --others --exclude-standard; } 2>/dev/null )
[ -z "$changes" ] && exit 0
hash=$(printf '%s' "$changes" | git hash-object --stdin)
marker="$(git rev-parse --git-dir)/ohara-checked"
[ "$(cat "$marker" 2>/dev/null)" = "$hash" ] && exit 0
echo "$hash" > "$marker"
echo '{"decision": "block", "reason": "Ohara: 1. Check the current changes against the Ohara guidelines listed in CLAUDE.md, and fix what does not follow them. 2. Then propose updates to every Ohara page these changes affect in one propose_change, or say that none are needed."}'
