#!/usr/bin/env bash
# Brings the stack up (PS-2.9, architecture §2.4 Scripts). Creates .env from
# .env.example if it is missing, checks Docker Compose >= 2.24 and Docker
# Engine >= 28 (the isolated backend bridge needs it), refuses a non-loopback
# published address outside dev (PS-2.14, Q33a), then
# `compose up -d --no-build --wait` and prints the URLs.
#
# The environment and bind address are read from `docker compose config`, the
# values compose resolves with the same --env-file it will `up` with, never
# from a parser of our own and never from .env.example. A missing or empty
# KE_ENV is not dev (fail closed).
# Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
set -euo pipefail
cd "$(dirname "$0")/.."

env_file="${KE_ENV_FILE:-.env}"
if [ ! -f "$env_file" ]; then
  if [ -n "${KE_ENV_FILE:-}" ]; then
    echo "error: KE_ENV_FILE does not exist: $env_file" >&2
    exit 1
  fi
  # .env holds the stack's secrets: private (0600) whatever the caller's umask (F12).
  # A redirect, not cp: cp would carry over the example's own mode bits.
  (umask 077; cat .env.example > .env)
  echo "created .env from .env.example (placeholder secrets; edit it before any use beyond local development)"
fi

at_least() { # at_least MINIMUM VERSION: dotted numbers, field by field (no sort -V: BSD sort lacks it)
  local IFS=. i have want
  local min=() ver=()
  read -r -a min <<< "$1"
  read -r -a ver <<< "$2"
  for i in "${!min[@]}"; do
    want="${min[$i]%%[!0-9]*}"
    have="${ver[$i]-0}"
    have="${have%%[!0-9]*}"
    want="${want:-0}"
    have="${have:-0}"
    if [ "$((10#$have))" -gt "$((10#$want))" ]; then return 0; fi
    if [ "$((10#$have))" -lt "$((10#$want))" ]; then return 1; fi
  done
  return 0
}

minimum=2.24
version="$(docker compose version --short 2>/dev/null || true)"
version="${version#v}"
if [ -z "$version" ] || ! at_least "$minimum" "$version"; then
  echo "error: Docker Compose >= $minimum is required (found: ${version:-none})" >&2
  exit 1
fi

# Older engines ignore gateway_mode_ipv4 without an error (security M-2).
engine_minimum=28
engine="$(docker version --format '{{.Server.Version}}' 2>/dev/null)" || {
  echo "error: cannot read the Docker Engine version; is the daemon running?" >&2
  exit 1
}
engine_major="${engine%%.*}"
if [[ ! "$engine" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || [ "$((10#${engine_major}))" -lt "$engine_minimum" ]; then
  echo "error: Docker Engine >= $engine_minimum is required (found: ${engine:-none})" >&2
  exit 1
fi

args=()
[ -n "${KE_ENV_FILE:-}" ] && args+=(--env-file "$KE_ENV_FILE")

if ! resolved="$(docker compose ${args[@]+"${args[@]}"} config --format json)"; then
  echo "error: docker compose config failed; cannot resolve KE_ENV and KE_BIND_ADDRESS" >&2
  exit 1
fi
pick() { # pick KEY: the first "KEY": "value" in the resolved model
  printf '%s\n' "$resolved" | grep -m 1 -o "\"$1\": *\"[^\"]*\"" | sed -e 's/^[^:]*: *"//' -e 's/"$//' || true
}
ke_env="$(pick KE_ENV)"
# One array element per match (bash 3.2 has no mapfile). The sed prefixes each
# value with "=" so an empty value is still a line.
collect() { # collect KEY: prints "=value" for each "KEY": "value" in the model
  printf '%s\n' "$resolved" | grep -o "\"$1\": *\"[^\"]*\"" | sed -e 's/^[^:]*: *"/=/' -e 's/"$//' || true
}
hosts=()
host_lines="$(collect host_ip)"
while IFS= read -r line; do
  case "$line" in =*) hosts+=("${line#=}") ;; esac
done <<< "$host_lines"
published_count="$(printf '%s\n' "$resolved" | grep -c '"published"' || true)"
published=()
published_lines="$(collect published)"
while IFS= read -r line; do
  case "$line" in =*) published+=("${line#=}") ;; esac
done <<< "$published_lines"

# IPv4 only; IPv6 is refused in every env. Same rule as the engine's startup
# refusal and docker/gateway/10-ke-bind-check.sh. A published port with no
# host_ip would listen on every interface: treated as 0.0.0.0.
octet='(0|[1-9][0-9]{0,2})'
if [ "${#hosts[@]}" -lt "$published_count" ]; then
  hosts+=("0.0.0.0")
fi
bind=127.0.0.1
for host in ${hosts[@]+"${hosts[@]}"}; do
  valid=1
  if [[ "$host" =~ ^${octet}\.${octet}\.${octet}\.${octet}$ ]]; then
    for part in "${BASH_REMATCH[@]:1}"; do
      [ "$part" -le 255 ] || valid=0
    done
  else
    valid=0
  fi
  if [ "$valid" = 0 ]; then
    echo "error: KE_BIND_ADDRESS is not an IPv4 address (IPv6 is not supported)" >&2
    exit 1
  fi
  bind="$host"
  if [ "${host%%.*}" != 127 ]; then
    if [ "$ke_env" = dev ]; then
      echo "warning: KE_BIND_ADDRESS is not loopback; the stack will be published beyond this host without authentication (dev only)" >&2
    else
      echo "error: KE_BIND_ADDRESS is not loopback and KE_ENV is not dev; refusing to launch (until auth-audit lands)" >&2
      exit 1
    fi
  fi
done

docker compose ${args[@]+"${args[@]}"} up -d --no-build --wait

echo "stack is up:"
echo "  api:     http://${bind}:${published[0]:-}"
echo "  phoenix: http://${bind}:${published[1]:-}"
