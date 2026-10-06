#!/bin/sh
# Ohara: check each new set of changes against the guidelines and docs, with a one-line reply.
input=$(cat)
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
changes=$( { git diff HEAD; git ls-files --others --exclude-standard | git hash-object --stdin-paths; } 2>/dev/null )
[ -z "$changes" ] && exit 0
hash=$(printf '%s' "$changes" | git hash-object --stdin)
marker="$(git rev-parse --git-dir)/ohara-checked"
last=$(cat "$marker" 2>/dev/null)
echo "$hash" > "$marker"
case "$input" in *'"stop_hook_active": true'* | *'"stop_hook_active":true'*) exit 0 ;; esac
[ "$last" = "$hash" ] && exit 0
echo '{"decision": "block", "reason": "Ohara check: check only the changes since the last Ohara check against the guidelines in CLAUDE.md, reusing pages already read, and fix what does not follow them. If they change what an Ohara page describes, propose the updates in one propose_change with the project and active branch. Then reply with a short summary."}'
