#!/usr/bin/env bash
# PreToolUse hook: a guard rail against accidents, not a security boundary.
# The real control is branch protection on the remote (Q18). Design and the
# accepted false positives and bypasses: ADR-KE-001, "Decision: commit hook
# is a simple fail-safe text rule (2026-10-18)" in docs/architecture.md.
#   - on main/master: any text with the word `git` and one of commit, push,
#     merge, cherry-pick, am, rebase, revert is denied;
#   - off main: a line with `git`, then `push`, then on that line main/master,
#     --all/--mirror, a force flag or a +refspec is denied.
# The text is normalised first (quotes and backslashes deleted, lower-cased).
# Plain bash, sed, tr and grep -E: no awk, linear cost.
# Prints nothing otherwise: printing "allow" would auto-approve every call.
set -euo pipefail

input="$(cat)"

# 1. Extract the command: jq if it works, else sed on the JSON, else raw input.
if ! text="$(printf '%s' "$input" | jq -r '.tool_input.command // .toolInput.command // .tool_input.cmd // empty' 2>/dev/null)"; then
  case "$input" in
    '{'*)
      # First "command":"..." value; \ is protected, then \n and \t become
      # a newline and a space (the \ + \n pair is a line continuation).
      text="$(printf '%s' "$input" |
        { grep -oE '"command"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' || true; } |
        head -n 1 |
        sed -e 's/^"command"[[:space:]]*:[[:space:]]*"//' -e 's/"$//' \
            -e 's/\\\\/\x01/g' -e 's/\\n/\n/g' -e 's/\\t/ /g' -e 's/\x01/\\/g')" ;;
    *) text="$input" ;;
  esac
fi
[ -n "$text" ] || exit 0

# 2. Normalise: join continuations, delete quotes and backslashes, lower-case.
text="$(printf '%s' "$text" | sed -z 's/\\\n/ /g' | tr -d "\"'\\\\" | tr '[:upper:]' '[:lower:]')"

# 3. Judge.
W='[^[:alnum:]_-]'
GIT="(^|$W)git$W(.*$W)?"
branch="$(git branch --show-current 2>/dev/null || echo '')"
reason=""
if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
  if grep -Eq "(^|$W)git($W|\$)" <<<"$text" &&
     grep -Eq "(^|$W)(commit|push|merge|cherry-pick|am|rebase|revert)($W|\$)" <<<"$text"; then
    reason="Commits/pushes are not allowed directly on main/master. Create an agent/<slug> or feat|fix|chore/<slug> branch first."
  fi
else
  PUSH="${GIT}push($W|\$)"
  if grep -Eq "${PUSH}((.*$W)?((main|master)($W|\$)|--mirror|--all))" <<<"$text"; then
    reason="Pushing to main/master is not allowed."
  elif grep -Eq "${PUSH}((.*$W)?--force|(.*[[:space:]])?-[[:alpha:]]*f|(.*[[:space:]:])?\\+)" <<<"$text"; then
    reason="Force pushes are not allowed."
  fi
fi

if [ -n "$reason" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
fi
exit 0
