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
scripts/test.sh "$mode"
if [ "$mode" = "full" ]; then
  scripts/smoke.sh
fi
echo "== verify $mode: PASS =="
