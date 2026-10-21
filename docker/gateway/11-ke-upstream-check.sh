#!/bin/sh
# Gateway entrypoint check (security M-3 and L-3, ADR-KE-009 F-A).
#
# The gateway's model forward is the stack's one way off the machine. Before
# nginx renders its config, KE_MODEL_UPSTREAM must be empty (no forward) or a
# strict host:port whose host is on KE_EGRESS_ALLOWLIST (comma-separated; exact,
# case-folded match, as the engine reads it). The strict character set also
# keeps the value from changing the rendered nginx config. The message names
# the variable and never echoes its value.
set -eu
name=KE_MODEL_UPSTREAM
value="${KE_MODEL_UPSTREAM:-}"

refuse() {
  echo "error: $name $1; refusing to start" >&2
  exit 1
}

[ -n "$value" ] || exit 0

case "$value" in
  *[!A-Za-z0-9.:-]*) refuse "is not a plain host:port" ;;
esac
case "$value" in
  *:*:*) refuse "has more than one port" ;;
  *:*) ;;
  *) refuse "has no port" ;;
esac

host="${value%%:*}"
port="${value#*:}"
[ -n "$host" ] || refuse "has an empty host"
case "$host" in
  .* | *. | *..* | -* | *-) refuse "has a malformed host" ;;
esac
case "$port" in
  '' | *[!0-9]* | 0*) refuse "has an invalid port" ;;
esac
if [ "${#port}" -gt 5 ] || [ "$port" -gt 65535 ]; then refuse "has an invalid port"; fi

host=$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')
allowlist="${KE_EGRESS_ALLOWLIST:-}"
set -f
old_ifs=$IFS
IFS=,
# shellcheck disable=SC2086  # splitting on commas is the point
set -- $allowlist
IFS=$old_ifs
set +f
for entry in "$@"; do
  entry=$(printf '%s' "$entry" | tr '[:upper:]' '[:lower:]' | tr -d ' \t')
  if [ -n "$entry" ] && [ "$entry" = "$host" ]; then
    exit 0
  fi
done
refuse "host is not on KE_EGRESS_ALLOWLIST"
