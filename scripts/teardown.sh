#!/usr/bin/env bash
# Stops and removes the project's containers and networks (PS-2.9). Named
# volumes are kept unless --volumes is given. Honors KE_ENV_FILE and
# COMPOSE_PROJECT_NAME.
#
# Afterwards it lists what is still labelled with the project (containers and
# networks, plus volumes when --volumes was asked) and exits non-zero if
# anything is left, naming it. It only reports: it never removes a leftover
# itself, so it cannot touch another project or a profile's containers (F3,
# security L-9).
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."

args=()
[ -n "${KE_ENV_FILE:-}" ] && args+=(--env-file "$KE_ENV_FILE")
down=()
volumes=0
profile=()
# The one profile this script accepts is `offline`, for scripts/offline_check.sh
# (architecture §2.5): it names the compose file through COMPOSE_FILE, which
# this script inherits. Any other profile, a repeat or an empty value is refused.
while [ "$#" -gt 0 ]; do
  if [ "$#" -ge 2 ] && [ "${#profile[@]}" -eq 0 ] && [ "$1 $2" = "--profile offline" ]; then
    profile=(--profile offline)
    shift 2
    continue
  fi
  case "$1" in
    --volumes) down+=(--volumes); volumes=1 ;;
    *) echo "usage: scripts/teardown.sh [--volumes] [--profile offline]" >&2; exit 2 ;;
  esac
  shift
done

# The project name is the one compose resolves, not a guess; without it the
# leftover check could not be scoped, so nothing is taken down.
project="$(docker compose ${args[@]+"${args[@]}"} config | sed -n 's/^name: *//p' | head -n 1)"
if [ -z "$project" ]; then
  echo "teardown: FAIL (cannot read the compose project name)" >&2
  exit 1
fi

docker compose ${args[@]+"${args[@]}"} ${profile[@]+"${profile[@]}"} down ${down[@]+"${down[@]}"}

filter="label=com.docker.compose.project=${project}"
left_containers="$(docker ps -a --filter "$filter" --format '{{.Names}}')"
left_networks="$(docker network ls --filter "$filter" --format '{{.Name}}')"
left_volumes=""
[ "$volumes" -eq 1 ] && left_volumes="$(docker volume ls --filter "$filter" --format '{{.Name}}')"
if [ -n "$left_containers$left_networks$left_volumes" ]; then
  {
    echo "teardown: FAIL (project $project still has resources after down; remove them by hand):"
    for name in $left_containers; do echo "  container $name"; done
    for name in $left_networks; do echo "  network $name"; done
    for name in $left_volumes; do echo "  volume $name"; done
  } >&2
  exit 1
fi
