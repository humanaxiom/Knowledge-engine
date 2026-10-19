#!/usr/bin/env bash
# Stops and removes the project's containers and networks (PS-2.9). Named
# volumes are kept unless --volumes is given. Honors KE_ENV_FILE and
# COMPOSE_PROJECT_NAME.
set -euo pipefail
cd "$(dirname "$0")/.."

args=()
[ -n "${KE_ENV_FILE:-}" ] && args+=(--env-file "$KE_ENV_FILE")
down=()
for arg in "$@"; do
  case "$arg" in
    --volumes) down+=(--volumes) ;;
    *) echo "usage: scripts/teardown.sh [--volumes]" >&2; exit 2 ;;
  esac
done
docker compose ${args[@]+"${args[@]}"} down "${down[@]}"
