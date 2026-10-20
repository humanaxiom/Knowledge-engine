#!/usr/bin/env bash
# Prints the value of KE_MODEL_UPSTREAM or KE_EGRESS_ALLOWLIST, and nothing
# else (PS-2.21, architecture §2.2 "Model keys in local verify"). Used by
# verify.sh full, so the verify project can reach the model host.
#
# Precedence (ruling Q35): the caller's environment wins, even when the
# variable is set empty. Otherwise the value is what `docker compose` resolves
# from the repo-root .env; .env is never sourced or parsed here, so nothing in
# it can run. Any other name exits 2 before anything runs, so no secret in
# .env can be read through this script.
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."

if [ "$#" -ne 1 ]; then
  echo "usage: scripts/env_value.sh KE_MODEL_UPSTREAM|KE_EGRESS_ALLOWLIST" >&2
  exit 2
fi
name="$1"
case "$name" in
  KE_MODEL_UPSTREAM|KE_EGRESS_ALLOWLIST) ;;
  *) echo "env_value: refused (only KE_MODEL_UPSTREAM and KE_EGRESS_ALLOWLIST can be read)" >&2; exit 2 ;;
esac

if [ -n "${!name+x}" ]; then
  printf '%s\n' "${!name}"
  exit 0
fi
if [ ! -f .env ]; then
  printf '\n'
  exit 0
fi

# Compose's own stderr is discarded: it can echo parts of the file.
if ! resolved="$(docker compose -f docker-compose.yml --env-file .env config --format json gateway 2>/dev/null)"; then
  echo "env_value: FAIL (docker compose could not resolve .env, so $name is unknown)" >&2
  exit 1
fi
line="$(printf '%s\n' "$resolved" | grep -m1 "\"$name\":" || true)"
# A plain JSON string only: a value with an escape (a quote or backslash) is
# refused rather than guessed at.
if [[ ! "$line" =~ \"$name\":\ *\"([^\"\\]*)\"[,]?[[:space:]]*$ ]]; then
  echo "env_value: FAIL ($name in .env is missing or not a plain value)" >&2
  exit 1
fi
printf '%s\n' "${BASH_REMATCH[1]}"
