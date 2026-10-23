#!/usr/bin/env bash
# Builds the images (ke-app, ke-gateway, ke-neo4j, ke-gates) and pulls the
# digest-pinned ones (PS-2.9). ke-neo4j's base is fetched by its digest by the
# build, never pulled as a stack image (PSC-26). The only step that needs the
# network; `launch.sh` does not build. Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."

args=()
[ -n "${KE_ENV_FILE:-}" ] && args+=(--env-file "$KE_ENV_FILE")
docker compose ${args[@]+"${args[@]}"} --profile '*' build
docker compose ${args[@]+"${args[@]}"} --profile '*' pull --ignore-buildable
