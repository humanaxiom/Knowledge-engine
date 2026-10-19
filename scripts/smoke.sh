#!/usr/bin/env bash
# Smoke test entrypoint, two-sided like verify.sh and keyed on KE_IN_GATES.
#
# In the gates container: exports real OTLP traces to a stub collector and
# checks they arrive, proving the Phoenix export path works end to end.
#
# On the host: the live-stack smoke against the running project (PS-2.1,
# PS-2.4). It checks that every stack service reports healthy and that the
# gateway proxies /healthz to api. It neither launches nor tears down; the
# caller (verify.sh) owns the project. Honors KE_ENV_FILE and
# COMPOSE_PROJECT_NAME. Readiness, the store stop/start and the standalone
# launch-and-teardown arrive with platform-stack-ready (PS-2.8).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${KE_IN_GATES:-}" = "1" ]; then
  uv run --locked python scripts/smoke_otlp.py
  exit 0
fi

args=()
[ -n "${KE_ENV_FILE:-}" ] && args+=(--env-file "$KE_ENV_FILE")
compose() { docker compose ${args[@]+"${args[@]}"} "$@"; }

# PS-2.2 "resolves without .env": the base compose file must resolve with no
# .env and no env file (the overlay is left out on purpose, so its ports are
# still there to be checked), and every published port must bind loopback.
# An empty env file stands in for "no .env" (not /dev/null, which Windows docker
# cannot open). Relative, so Git Bash path conversion does not matter.
empty_env="$(mktemp ./.env.smoke.XXXXXX)"
trap 'rm -f "$empty_env"' EXIT
resolved="$(docker compose -f docker-compose.yml --env-file "$empty_env" config --format json)" || {
  echo "smoke: FAIL (docker compose config does not resolve with no .env)" >&2
  exit 1
}
published="$(printf '%s\n' "$resolved" | grep -c '"published"' || true)"
loopback="$(printf '%s\n' "$resolved" | grep -c '"host_ip": *"127\.0\.0\.1"' || true)"
if [ "$published" -lt 1 ] || [ "$published" != "$loopback" ]; then
  echo "smoke: FAIL (a published port is not bound to 127.0.0.1 by default: $loopback of $published)" >&2
  exit 1
fi
echo "smoke: compose resolves with no .env; $published ports, all on 127.0.0.1"

# M-2 / M-4 runtime proof (ruling R1-B1): the backend network of this very
# project is internal and its bridge is isolated, so it has no route out. The
# project name is the one compose resolved, not a guess.
project="$(compose config | sed -n 's/^name: *//p' | head -n 1)"
if [ -z "$project" ]; then
  echo "smoke: FAIL (cannot read the compose project name)" >&2
  exit 1
fi
backend="${project}_backend"
mode="$(docker network inspect --format '{{index .Options "com.docker.network.bridge.gateway_mode_ipv4"}}' "$backend")" || {
  echo "smoke: FAIL (cannot inspect network $backend)" >&2
  exit 1
}
network_json="$(docker network inspect --format '{{json .}}' "$backend")" || {
  echo "smoke: FAIL (cannot inspect network $backend)" >&2
  exit 1
}
if [ "$mode" != isolated ] || ! printf '%s\n' "$network_json" | grep -Eq '"Internal": *true'; then
  echo "smoke: FAIL (network $backend is not isolated and internal: gateway_mode_ipv4='$mode')" >&2
  exit 1
fi
echo "smoke: $backend is internal with gateway_mode_ipv4=isolated"

for service in gateway api worker postgres neo4j valkey phoenix; do
  health="$(compose ps --format '{{.Health}}' "$service")"
  if [ "$health" != healthy ]; then
    echo "smoke: FAIL ($service is '${health:-not running}', want healthy)" >&2
    exit 1
  fi
  echo "smoke: $service healthy"
done

# From inside the gateway: its own listen ports come from its environment.
# shellcheck disable=SC2016  # expanded by the container's shell, not ours
body="$(compose exec -T gateway sh -c 'wget -q -O - "http://127.0.0.1:${KE_GATEWAY_API_LISTEN}/healthz"')"
if [ "$body" != '{"status":"ok"}' ]; then
  echo "smoke: FAIL (gateway -> api /healthz returned '$body')" >&2
  exit 1
fi
echo "smoke: gateway proxies api /healthz"
# shellcheck disable=SC2016
compose exec -T gateway sh -c 'wget -q -O /dev/null "http://127.0.0.1:${KE_GATEWAY_PHOENIX_LISTEN}/healthz"'
echo "smoke: gateway proxies phoenix /healthz"
echo "smoke: PASS"
