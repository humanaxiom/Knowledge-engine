#!/usr/bin/env bash
# The single verification entry point for humans, agents and CI.
#
#   scripts/verify.sh fast   unit tests (pure functions, docs)
#   scripts/verify.sh full   fast + integration + smoke (everything CI runs)
#
# On the host it re-runs itself inside the one-shot `gates` compose service,
# so every caller gets the same image, the same tools and no network. Inside,
# it only calls the real gate scripts; never list their commands here.
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-full}"
case "$mode" in
  fast|full) ;;
  *) echo "usage: scripts/verify.sh [fast|full]" >&2; exit 2 ;;
esac

if [ "${KE_IN_GATES:-}" != "1" ]; then
  # MSYS_NO_PATHCONV stops Git Bash on Windows rewriting the container path.
  MSYS_NO_PATHCONV=1 exec docker compose --profile gates run --rm --build gates \
    scripts/verify.sh "$mode"
fi

echo "== verify $mode: $(git rev-parse --short HEAD 2>/dev/null || echo no-git)$(git diff --quiet 2>/dev/null || echo '+dirty') =="
# Stream test.sh output through while keeping a copy: a run that executed no
# tests (no "Ran N tests" line, or N = 0) must not count as green.
log="$(mktemp)"
trap 'rm -f "$log"' EXIT
scripts/test.sh "$mode" 2>&1 | tee "$log" || { echo "verify $mode: FAIL (test.sh exited non-zero)" >&2; exit 1; }
if ! grep -Eq '^Ran [1-9][0-9]* tests?' "$log"; then
  echo "verify $mode: FAIL (no Ran N tests line with N > 0 in the test output)" >&2
  exit 1
fi
# The top-level unit suite must have run too: a test.sh that dropped it can
# still print Ran N > 0 from a sub-suite. Its sentinel test must report ok.
# Whole-line match (security N17/I1), optional trailing CR. No pipe: grep reads
# the file directly, so -q closing early cannot raise SIGPIPE under pipefail.
if ! grep -Pq '^test_top_level_unit_suite_ran \(tests\.test_sentinel\.TopLevelSuiteSentinelTest\.test_top_level_unit_suite_ran\) \.\.\. ok\r?$' "$log"; then
  echo "verify $mode: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run)" >&2
  exit 1
fi
if [ "$mode" = "full" ]; then
  scripts/smoke.sh
fi
echo "== verify $mode: PASS =="
