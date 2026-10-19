#!/usr/bin/env bash
# The single verification entry point for humans, agents and CI.
#
#   scripts/verify.sh fast   unit tests (pure functions, docs)
#   scripts/verify.sh full   fast + integration + smoke (everything CI runs)
#
# On the host it only orchestrates Docker (ADR-KE-009, architecture §2.2):
#   fast: re-runs itself in the one-shot `gates` compose service (no network).
#   full: builds, launches a `ke-verify-<suffix>` project that publishes
#         nothing, re-runs itself in the one-shot `gates-it` service on the
#         internal backend network, then runs the live smoke, and always tears
#         the project down with its volumes.
# Inside either container it only calls the real gate scripts; never list
# their commands here.
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-full}"
case "$mode" in
  fast|full) ;;
  *) echo "usage: scripts/verify.sh [fast|full]" >&2; exit 2 ;;
esac

if [ "${KE_IN_GATES:-}" != "1" ]; then
  # MSYS_NO_PATHCONV stops Git Bash on Windows rewriting the container path.
  export MSYS_NO_PATHCONV=1
  if [ "$mode" = fast ]; then
    exec docker compose --env-file .env.example --profile gates run --rm --build gates \
      scripts/verify.sh fast
  fi
  # Only the two model keys come from the caller's environment or the
  # repo-root .env (PS-2.21); both or neither, so a half-set pair cannot leave
  # the model host reachable by the gateway but refused by the engine.
  model_upstream="$(bash scripts/env_value.sh KE_MODEL_UPSTREAM)"
  egress_allowlist="$(bash scripts/env_value.sh KE_EGRESS_ALLOWLIST)"
  # Compose lets the process environment outrank --env-file, so every other
  # caller KE_* variable is dropped here: the verify project runs on the
  # placeholder values of .env.example, never real secrets (security L-11).
  while IFS= read -r name; do
    unset "$name"
  done < <(compgen -e | grep '^KE_' || true)
  started="$(date +%s)"
  export COMPOSE_PROJECT_NAME="ke-verify-${RANDOM}${RANDOM}"
  export COMPOSE_FILE="docker-compose.yml:docker-compose.verify.yml"
  export COMPOSE_PATH_SEPARATOR=":"
  export KE_ENV_FILE=".env.example"
  # This project is verify's own: smoke may stop and restart a store in it and
  # leaves the teardown to the trap below (ruling Q37).
  export KE_SMOKE_OWNS_PROJECT=1
  if [ -n "$model_upstream" ] && [ -n "$egress_allowlist" ]; then
    export KE_MODEL_UPSTREAM="$model_upstream" KE_EGRESS_ALLOWLIST="$egress_allowlist"
  else
    export KE_MODEL_UPSTREAM="" KE_EGRESS_ALLOWLIST=""
    echo "verify full: KE_MODEL_UPSTREAM and KE_EGRESS_ALLOWLIST must both be set to reach the model host; running without it (model-calling tests skip)"
  fi
  echo "== verify full: project $COMPOSE_PROJECT_NAME =="
  # Teardown runs once on every exit path. A failed teardown after a green
  # run still fails verify (N7): a leaked project is not a pass.
  # shellcheck disable=SC2317  # runs from the EXIT trap
  cleanup() {
    local rc=$?
    trap - EXIT
    if ! scripts/teardown.sh --volumes; then
      echo "verify full: FAIL (teardown of project $COMPOSE_PROJECT_NAME failed; remove it by hand: docker compose -p $COMPOSE_PROJECT_NAME down --volumes)" >&2
      [ "$rc" -eq 0 ] && rc=1
    elif [ "$rc" -eq 0 ]; then
      echo "== verify full: PASS ($(( $(date +%s) - started ))s) =="
    fi
    exit "$rc"
  }
  trap cleanup EXIT
  scripts/build.sh
  scripts/launch.sh
  docker compose --env-file "$KE_ENV_FILE" --profile gates-it run --rm gates-it \
    scripts/verify.sh full
  scripts/smoke.sh
  exit 0
fi

echo "== verify $mode: $(git rev-parse --short HEAD 2>/dev/null || echo no-git)$(git diff --quiet 2>/dev/null || echo '+dirty') =="
scripts/lint.sh || { echo "verify $mode: FAIL (lint.sh exited non-zero)" >&2; exit 1; }
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
