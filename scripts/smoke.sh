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
CDPATH='' cd -- "$(dirname -- "$0")/.."

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
if ! scripts/net_isolated.sh "$backend"; then
  echo "smoke: FAIL (network $backend is not internal and isolated: see the line above)" >&2
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

# PSC-25 (N0): the api runs psycopg-c on Debian's libpq5, not a vendored libpq.
# bookworm is merged-usr: ldd may print /lib/<triplet>/ or /usr/lib/<triplet>/.
# Checks: no psycopg_binary* in the venv; dpkg libpq5 owns the loaded libpq;
# the libpq5 version is validated before any arithmetic.
echo "== smoke: psycopg =="
pq_out="$(compose exec -T api python -I -c 'import importlib.util as u, os, sys, psycopg
p = psycopg.pq
s = u.find_spec("psycopg_c.pq") if u.find_spec("psycopg_c") else None
b = sorted(os.path.relpath(os.path.join(d, n), sys.prefix) for d, ds, fs in os.walk(sys.prefix)
           for n in ds + fs if n.startswith("psycopg_binary"))
if u.find_spec("psycopg_binary") and not b:
    b = ["psycopg_binary (importable)"]
print(p.__impl__, p.version(), p.__build_version__, s.origin if s else "-", ",".join(b).replace(" ", "_") or "-")')" || {
  echo "smoke: FAIL (psycopg: the check in api failed)" >&2
  exit 1
}
read -r pq_impl pq_version pq_build pq_ext pq_bin <<< "$pq_out"
if [ "$pq_impl" != c ]; then
  echo "smoke: FAIL (psycopg: api uses the '$pq_impl' implementation, want c)" >&2
  exit 1
fi
if [ "${pq_bin:--}" != - ]; then
  echo "smoke: FAIL (psycopg: psycopg_binary is installed in api beside psycopg-c: $pq_bin)" >&2
  exit 1
fi
# shellcheck disable=SC2016  # dpkg-query expands ${Version}
deb="$(compose exec -T api dpkg-query -W -f='${Version}' libpq5)" || {
  echo "smoke: FAIL (libpq: dpkg-query libpq5 failed in api)" >&2
  exit 1
}
# M-1: container output never reaches $(( )) unvalidated.
if ! [[ "$deb" =~ ^([0-9]+)\.([0-9]+)-[0-9A-Za-z.+~]+$ ]]; then
  echo "smoke: FAIL (libpq: libpq5 version in api is '$deb', not <major>.<minor>-<revision>)" >&2
  exit 1
fi
want=$((10#${BASH_REMATCH[1]} * 10000 + 10#${BASH_REMATCH[2]}))
if [ "$pq_version" != "$want" ] || [ "$pq_build" != "$want" ]; then
  echo "smoke: FAIL (psycopg: libpq version() $pq_version, __build_version__ $pq_build; libpq5 $deb is $want)" >&2
  exit 1
fi
ldd_out="$(compose exec -T api ldd "$pq_ext")" || {
  echo "smoke: FAIL (libpq: ldd $pq_ext failed in api)" >&2
  exit 1
}
libpq="$(printf '%s\n' "$ldd_out" | sed -n 's/^[[:space:]]*libpq\.so\.5 => \([^ ]*\).*/\1/p')"
if ! [[ "$libpq" =~ ^(/usr)?/lib/(x86_64|aarch64)-linux-gnu/libpq\.so\.5(\.[0-9]+)*$ ]] || [[ "$ldd_out" == *psycopg_binary* ]]; then
  echo "smoke: FAIL (libpq: the psycopg_c extension loads '${libpq:-nothing}', not Debian's libpq5)" >&2
  exit 1
fi
libpq_real="$(compose exec -T api realpath -e "$libpq")" || {
  echo "smoke: FAIL (libpq: realpath $libpq failed in api)" >&2
  exit 1
}
libpq_owner="$(compose exec -T api dpkg-query -S "$libpq_real")" || {
  echo "smoke: FAIL (libpq: dpkg owns no file $libpq_real in api, so it is not Debian's libpq5)" >&2
  exit 1
}
if ! [[ "$libpq_owner" =~ ^libpq5(:[a-z0-9]+)?:\ (.+)$ ]] || [ "${BASH_REMATCH[2]}" != "$libpq_real" ]; then
  echo "smoke: FAIL (libpq: $libpq_real belongs to '${libpq_owner%%: *}', not libpq5)" >&2
  exit 1
fi
echo "smoke: psycopg c on Debian libpq5 $deb ($libpq -> $libpq_real)"
# PSC-14 (N10a, human 2026-10-23): ke-app ships no pip. The base interpreter,
# since the venv's sys.path omits the system site-packages. The whole container
# output is compared only as a string with `-` (M-1, I-6): never evaluated.
echo "== smoke: no pip =="
pip_out="$(compose exec -T api /usr/local/bin/python3 -I -c 'import importlib.util as u, os, re
h = sorted(os.path.join(d, n) for r in ("/usr", "/opt") for d, ds, fs in os.walk(r)
           for n in ds + fs if re.fullmatch(r"pip(3(\.[0-9]+)?)?|pip-.+\.(dist-info|whl)", n))
if u.find_spec("pip") and not h:
    h = ["pip (importable)"]
print(",".join(h).replace(" ", "_") or "-")')" || {
  echo "smoke: FAIL (no pip: the check in api failed)" >&2
  exit 1
}
[ "$pip_out" = - ] || {
  echo "smoke: FAIL (no pip: the check in api printed '$pip_out', want '-' (pip in api, or no answer))" >&2
  exit 1
}
echo "smoke: no pip in api"
# PSC-26 (Q67, N16): neo4j runs ke-neo4j, the official image without
# /var/lib/neo4j/products (the commercial fleet-management plugin). find
# prints any match and one control path that ke-neo4j must hold, so a find
# that answers nothing fails (fail closed); the whole output is compared only
# as a string, never evaluated (M-1 pattern). No -xdev: the walk enters the
# volumes (/data, /logs); /proc, /sys and /dev are pruned (U5, security L-1).
echo "== smoke: no fleet plugin =="
fleet_out="$(compose exec -T neo4j find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o \( -path /var/lib/neo4j/products -o -name '*fleet-management*' -o -path /var/lib/neo4j/LICENSE.txt \) -print)" || {
  echo "smoke: FAIL (fleet plugin: the check in neo4j failed)" >&2
  exit 1
}
[ "$fleet_out" = /var/lib/neo4j/LICENSE.txt ] || {
  echo "smoke: FAIL (fleet plugin: find in neo4j printed '$fleet_out', want only /var/lib/neo4j/LICENSE.txt (products/ or a fleet-management file in neo4j, or no answer))" >&2
  exit 1
}
echo "smoke: no products/ or fleet-management plugin in neo4j"

# ci/offline (PS-3.3, architecture §2.5): api and worker have no route to
# anything off the backend network. The target is the gateway's own address on
# <project>_edge: live and routable from anything on that network, and it needs
# no internet, so the result is the same in CI, on a locked-down network and
# inside the offline check's dind. The control must connect first, otherwise
# the probe proves nothing and the check is inconclusive (never a pass).
edge_ip="$(docker inspect --format "{{(index .NetworkSettings.Networks \"${project}_edge\").IPAddress}}" "$(compose ps -q gateway)")" || {
  echo "smoke: FAIL (ci/offline: cannot read the gateway's address on ${project}_edge)" >&2
  exit 1
}
is_ipv4() { # is_ipv4 VALUE: four dotted decimal octets, 0-255, nothing else
  local IFS=. octet count=0
  [[ "$1" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
  for octet in $1; do
    [ "$((10#$octet))" -le 255 ] || return 1
    count=$((count + 1))
  done
  [ "$count" -eq 4 ]
}
if ! is_ipv4 "$edge_ip"; then
  echo "smoke: FAIL (ci/offline: the gateway's address on ${project}_edge is not an IPv4 address: '$edge_ip')" >&2
  exit 1
fi
config_json="$(compose config --format json)" || {
  echo "smoke: FAIL (ci/offline: docker compose config failed)" >&2
  exit 1
}
probe_port="$(printf '%s\n' "$config_json" | grep -m 1 -o '"KE_GATEWAY_API_LISTEN": *"[0-9]*"' | sed -e 's/^[^:]*: *"//' -e 's/"$//' || true)"
if [ -z "$probe_port" ]; then
  echo "smoke: FAIL (ci/offline: cannot read the gateway's API listen port from the compose config)" >&2
  exit 1
fi
app_image="$(compose config | awk '/^  [A-Za-z0-9_-]+:$/ { svc = $1; sub(/:$/, "", svc) } svc == "api" && /^    image: / { print $2; exit }')"
if [ -z "$app_image" ]; then
  echo "smoke: FAIL (ci/offline: cannot read the api image from the compose config)" >&2
  exit 1
fi
# The control probes the port the gateway listens on; it has its own variable so
# the message below names exactly what it probed. ke-app carries compose project
# labels, so a plain `docker run` of it would look like part of this project and
# trip the project's teardown label check; the control is labelled as its own
# project instead (security I-OC1b-2).
control_port="$probe_port"
control="$(docker run --rm --pull never --label "com.docker.compose.project=${project}-probe" --network "${project}_edge" --entrypoint python "$app_image" -m engine.netprobe "$edge_ip" "$control_port" --within 5)" || true
if [ "$control" != connected ]; then
  echo "smoke: FAIL (ci/offline inconclusive: the control probe from ${project}_edge to $edge_ip:$control_port printed '${control:-nothing}', want connected)" >&2
  exit 1
fi
for service in api worker; do
  result="$(compose exec -T "$service" python -m engine.netprobe "$edge_ip" "$probe_port" --within 2)" || true
  if [ "$result" != no_route ]; then
    echo "smoke: FAIL (ci/offline: $service printed '${result:-nothing}' for $edge_ip:$probe_port, want no_route; it can leave the backend network)" >&2
    exit 1
  fi
  echo "smoke: ci/offline $service has no route to $edge_ip:$probe_port ($service cannot reach outside the stack)"
done

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
