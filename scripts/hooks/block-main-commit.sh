#!/usr/bin/env bash
# PreToolUse hook: a guard rail against accidents, not a security boundary.
# The real control is branch protection on the remote (Q18). Design and the
# accepted false positives and bypasses: ADR-KE-001, "Decision: commit hook
# is a simple fail-safe text rule (2026-10-18)" in docs/architecture.md.
#   - on main/master: any text with the word `git` and one of commit, push,
#     merge, cherry-pick, am, rebase, revert is denied;
#   - off main: a line with `git`, then `push`, then on that line main/master,
#     --all/--mirror, a force flag or a +refspec is denied.
# The text is normalised first (CR deleted, quotes and backslashes deleted,
# lower-cased) and judged as (a) backslash-newline joined to nothing, as bash
# does for a real continuation (security M5). Only if the command contains a
# backslash-newline (security L21: no second pass otherwise) it is judged
# again as (b) backslash-newline turned into a SPACE (security M6): the next
# line joins the previous one, as after a comment ending in a backslash or an
# even run of backslashes, so a push split across the pair is still one line
# for the rules. Deny if either text matches.
# Plain bash, sed, tr and grep -E: no awk, linear cost.
# Prints nothing otherwise: printing "allow" would auto-approve every call.
set -euo pipefail

input="$(cat)"

# 1. Extract the command: jq if it works, else sed on the JSON, else raw input.
if ! text="$(printf '%s' "$input" | jq -r '.tool_input.command // .toolInput.command // .tool_input.cmd // empty' 2>/dev/null)"; then
  case "$input" in
    '{'*)
      # First "command":"..." value; \ is protected, then \r is dropped and
      # \n and \t become a newline and a space (the \ + \n pair is a line
      # continuation).
      text="$(printf '%s' "$input" |
        { grep -oE '"command"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' || true; } |
        head -n 1 |
        sed -e 's/^"command"[[:space:]]*:[[:space:]]*"//' -e 's/"$//' \
            -e 's/\\\\/\x01/g' -e 's/\\r//g' -e 's/\\n/\n/g' -e 's/\\t/ /g' -e 's/\x01/\\/g')" ;;
    *) text="$input" ;;
  esac
fi
[ -n "$text" ] || exit 0

# 2. Normalise: delete CR, delete quotes and backslashes, lower-case. Text (a)
#    joins backslash-newline to nothing (M5). Text (b), built only when the
#    command contains a backslash-newline (L21), turns it into a space (M6).
# NOTE: a test (L21) counts the `tr '[:upper:]'` call and the `for text in` loop; update it if you change them.
norm() { tr -d "\"'\\\\" | tr '[:upper:]' '[:lower:]'; }
base="$(printf '%s' "$text" | tr -d '\r')"
texts=("$(printf '%s' "$base" | sed -z 's/\\\n//g' | norm)")
case "$base" in
  *$'\\\n'*) texts+=("$(printf '%s' "$base" | sed -z 's/\\\n/ /g' | norm)") ;;
esac

# 3. Judge each text; the first match wins.
W='[^[:alnum:]_-]'
GIT="(^|$W)git$W(.*$W)?"
branch="$(git branch --show-current 2>/dev/null || echo '')"
reason=""
for text in "${texts[@]}"; do
  if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    if grep -Eq "(^|$W)git($W|\$)" <<<"$text" &&
       grep -Eq "(^|$W)(commit|push|merge|cherry-pick|am|rebase|revert)($W|\$)" <<<"$text"; then
      reason="Commits/pushes are not allowed directly on main/master. Create an agent/<slug> or feat|fix|chore/<slug> branch first."
    fi
  else
    PUSH="${GIT}push($W|\$)"
    if grep -Eq "${PUSH}((.*$W)?((main|master)($W|\$)|--mirror|--all))" <<<"$text"; then
      reason="Pushing to main/master is not allowed."
    elif grep -Eq "${PUSH}((.*$W)?--force|(.*[[:space:]])?-[[:alpha:]]*f|(.*[[:space:]:])?\+)" <<<"$text"; then
      reason="Force pushes are not allowed."
    fi
  fi
  [ -z "$reason" ] || break
done

if [ -n "$reason" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
fi
exit 0
