#!/bin/sh
# Gateway entrypoint check (PS-2.14, ADR-KE-011 ports amendment, ruling R4).
#
# KE_BIND_ADDRESS is the host address compose publishes the gateway on. It is
# an IPv4 literal; IPv6 is not supported. Anything outside 127.0.0.0/8 exposes
# unauthenticated services to the LAN, so outside dev this exits non-zero and
# nginx never starts. A missing KE_ENV counts as not dev (fail closed). The
# message names the variable and never echoes its value.
set -eu
name=KE_BIND_ADDRESS
value="${KE_BIND_ADDRESS:-127.0.0.1}"

valid_octet() {
  case "$1" in '' | *[!0-9]*) return 1 ;; esac
  [ "${#1}" -le 3 ] || return 1
  case "$1" in 0?*) return 1 ;; esac
  [ "$1" -le 255 ]
}

case "$value" in
  .* | *. | *..*) bad=1 ;;
  *) bad=0 ;;
esac
if [ "$bad" = 0 ]; then
  set -f
  old_ifs=$IFS
  IFS=.
  # shellcheck disable=SC2086  # splitting on dots is the point
  set -- $value
  IFS=$old_ifs
  set +f
  [ "$#" -eq 4 ] || bad=1
fi
if [ "$bad" = 0 ]; then
  for octet in "$@"; do
    valid_octet "$octet" || bad=1
  done
fi
if [ "$bad" = 1 ]; then
  echo "error: $name is not an IPv4 address (IPv6 is not supported)" >&2
  exit 1
fi

if [ "$1" = 127 ]; then
  exit 0
fi
if [ "${KE_ENV:-}" = dev ]; then
  echo "warning: $name is not loopback; the stack is published beyond this host without authentication (dev only)"
  exit 0
fi
echo "error: $name is not loopback and KE_ENV is not dev; refusing to start (until auth-audit lands)" >&2
exit 1
