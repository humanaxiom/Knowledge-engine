#!/usr/bin/env bash
# Builds the images (ke-app, ke-gateway, ke-gates) and pulls the digest-pinned
# ones (PS-2.9). The only step that needs the network; `launch.sh` does not
# build. Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."

args=()
[ -n "${KE_ENV_FILE:-}" ] && args+=(--env-file "$KE_ENV_FILE")
docker compose ${args[@]+"${args[@]}"} --profile '*' build
docker compose ${args[@]+"${args[@]}"} --profile '*' pull --ignore-buildable
