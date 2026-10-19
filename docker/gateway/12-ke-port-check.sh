#!/bin/sh
# Gateway entrypoint check (security L-3, ADR-KE-009 F-A).
#
# Every operator-set variable the nginx templates substitute (other than
# KE_MODEL_UPSTREAM, which 11-ke-upstream-check.sh validates, and
# NGINX_LOCAL_RESOLVERS, which the image computes) is a port. Each must be a
# decimal integer 1-65535: no sign, no leading zero, no whitespace. Otherwise
# a value could add nginx locations or listeners. The message names the
# variable and never echoes its value. Runs before 20-envsubst.
set -eu

refuse() {
  echo "error: $1 is not a port number (1-65535); refusing to start" >&2
  exit 1
}

check_port() {
  name=$1
  value=
  eval "value=\${$name-}"
  case "$value" in '' | *[!0-9]* | 0*) refuse "$name" ;; esac
  [ "${#value}" -le 5 ] || refuse "$name"
  [ "$value" -le 65535 ] || refuse "$name"
}

for var in KE_GATEWAY_API_LISTEN KE_GATEWAY_PHOENIX_LISTEN KE_GATEWAY_MODEL_LISTEN \
  KE_API__LISTEN_PORT PHOENIX_PORT; do
  check_port "$var"
done
