#!/usr/bin/env bash
# Exits 0 only for a Docker network that is internal and whose bridge has
# gateway_mode_ipv4=isolated, read from ONE `docker network inspect`
# (architecture §2.5). Called by smoke.sh (the stack's backend network) and by
# offline_check.sh (the offline network).
#
#   scripts/net_isolated.sh <network>
set -euo pipefail

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "usage: scripts/net_isolated.sh <network>" >&2
  exit 2
fi
network="$1"

if ! inspected="$(docker network inspect --format '{{json .}}' "$network")"; then
  echo "net_isolated: FAIL (cannot inspect network $network)" >&2
  exit 1
fi
if ! printf '%s\n' "$inspected" | grep -Eq '"Internal": *true'; then
  echo "net_isolated: FAIL (network $network is not internal)" >&2
  exit 1
fi
if ! printf '%s\n' "$inspected" | grep -Eq '"com\.docker\.network\.bridge\.gateway_mode_ipv4": *"isolated"'; then
  echo "net_isolated: FAIL (network $network is not isolated: gateway_mode_ipv4 is not 'isolated')" >&2
  exit 1
fi
echo "net_isolated: $network is internal with gateway_mode_ipv4=isolated"
