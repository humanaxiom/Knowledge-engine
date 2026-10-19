#!/usr/bin/env bash
# Smoke test entrypoint, two-sided like verify.sh and keyed on KE_IN_GATES.
#
# In the gates container: exports real OTLP traces to a stub collector and
# checks they arrive, proving the Phoenix export path works end to end.
#
# On the host: the live-stack smoke (PS-2.1, PS-2.4, PS-2.8). It checks that
# every stack service reports healthy, that the gateway proxies /healthz to
# api, that /readyz turns ready, and that stopping and restarting postgres is
# seen by /readyz. Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
#
# Who owns the project (rulings S1, Q37):
# - Nothing of the project is running: smoke launches it through launch.sh and
#   tears it down (without --volumes) when it ends, pass or fail. Run by hand
#   against a project of your own that is stopped, it takes that project down.
# - A project is already running (the operator's live stack): smoke checks it
#   and leaves it up. It does NOT stop postgres there, and says so.
# - KE_SMOKE_OWNS_PROJECT=1 (set only by verify.sh, for its own throwaway
#   project): the project must be running; smoke stops and restarts postgres in
#   it and leaves the teardown to verify.sh. With nothing running it fails.
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
launched=0
project=""
# Runs once on every exit path. A project smoke launched is torn down even
# when a check failed; a failed teardown fails smoke, naming the project.
# shellcheck disable=SC2317  # runs from the EXIT trap
cleanup() {
  local rc=$?
  trap - EXIT
  rm -f "$empty_env"
  if [ "$launched" -eq 1 ] && ! scripts/teardown.sh; then
    echo "smoke: FAIL (teardown of project $project failed; remove it by hand: docker compose -p $project down)" >&2
    [ "$rc" -eq 0 ] && rc=1
  fi
  exit "$rc"
}
trap cleanup EXIT
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

# Ruling S1: decide before launching whether this project is already running.
running="$(compose ps -q)"
if [ -z "$running" ]; then
  if [ "${KE_SMOKE_OWNS_PROJECT:-}" = 1 ]; then
    echo "smoke: FAIL (KE_SMOKE_OWNS_PROJECT=1 says verify.sh launched project $project, but nothing of it is running)" >&2
    exit 1
  fi
  launched=1
  scripts/launch.sh
  echo "smoke: launched project $project"
else
  echo "smoke: project $project is already running"
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

# Run before the proxy checks and again after the final ready.
check_healthy() {
  for service in gateway api worker postgres neo4j valkey phoenix; do
    health="$(compose ps --format '{{.Health}}' "$service")"
    if [ "$health" != healthy ]; then
      echo "smoke: FAIL ($service is '${health:-not running}', want healthy)" >&2
      exit 1
    fi
    echo "smoke: $service healthy"
  done
}
check_healthy

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

# Readiness, then a real store outage (PS-2.8). The CLI runs inside api: the
# verify project publishes nothing and api already has the settings.
readiness() { compose exec -T api python -m engine.readiness "$@"; }
if ! readiness --wait-for ready --within 60; then
  echo "smoke: FAIL (/readyz never became ready)" >&2
  exit 1
fi
echo "smoke: /readyz ready"

if [ "$launched" -eq 1 ] || [ "${KE_SMOKE_OWNS_PROJECT:-}" = 1 ]; then
  compose stop postgres
  if ! readiness --wait-for not-ready:postgres --within 30; then
    echo "smoke: FAIL (/readyz did not report postgres down after it was stopped)" >&2
    exit 1
  fi
  echo "smoke: /readyz reports postgres down"
  compose up -d --no-build --wait postgres
  if ! readiness --wait-for ready --within 60; then
    echo "smoke: FAIL (/readyz did not recover after postgres was started again)" >&2
    exit 1
  fi
  echo "smoke: /readyz ready again after postgres restart"
else
  echo "smoke: SKIPPED the postgres stop/start (project $project was already running; smoke does not stop an operator's stores)"
fi
# Every service healthy again, checked after the final ready (PS-2.8): a store
# the restart left unhealthy must fail here.
check_healthy
echo "smoke: PASS"
