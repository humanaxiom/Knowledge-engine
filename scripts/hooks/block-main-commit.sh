#!/usr/bin/env bash
# PreToolUse hook: deny git commit/push while checked out on main/master.
# Reads the tool-call JSON on stdin; falls back to scanning raw stdin text
# if the expected field isn't present (hook payload shapes can vary).
set -euo pipefail

input="$(cat)"

command_str="$(printf '%s' "$input" | jq -r '.tool_input.command // .toolInput.command // .tool_input.cmd // empty' 2>/dev/null || true)"
if [ -z "$command_str" ]; then
  command_str="$input"
fi

branch="$(git branch --show-current 2>/dev/null || echo '')"

if printf '%s' "$command_str" | grep -Eq 'git[^&|;]*(commit|push)' && { [ "$branch" = "main" ] || [ "$branch" = "master" ]; }; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Commits/pushes are not allowed directly on main/master. Create an agent/<slug> or feat|fix|chore/<slug> branch first."}}'
  exit 0
fi

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
