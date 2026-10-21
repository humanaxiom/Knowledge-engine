#!/usr/bin/env bash
# Scans the ke-app image for known vulnerabilities (PS-3.6, ADR-KE-013
# amendment 1, D3/D4). Called by scripts/verify.sh full only, from the
# checkout root, with KE_IMAGE_TAG exported. Verify-only host script: Linux
# and dev (Git Bash), never in the bundle.
#
# It runs in its own ke-scan-<random> project and ignores the caller's
# COMPOSE_* and SCAN_DB_URL. In order: save the ke-app tar, pull the scanner
# and fetch a fresh vulnerability database (scan-db, the only step with a
# network), then scan the tar offline (scan). Each step runs once; a failure
# fails the script at once, naming the stage, and nothing later runs. On
# every exit it removes the project with its volumes and the saved tar.
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."

# The one database URL, never read from the environment (D3). It is the
# pinned grype's default db.update-url (grype config, recorded in the handoff).
SCAN_DB_URL="https://grype.anchore.io/databases"
scan_db_host="${SCAN_DB_URL#https://}"
scan_db_host="${scan_db_host%%/*}"

tag="${KE_IMAGE_TAG-}"
tag_re='^wt-[0-9a-f]{12}$'
if ! (export LC_ALL=C; [[ "$tag" =~ $tag_re ]]); then
  echo "scan: FAIL (KE_IMAGE_TAG is malformed, want wt-<12 hex>: $(printf '%q' "$tag"))" >&2
  exit 1
fi

export COMPOSE_FILE=docker-compose.scan.yml
export COMPOSE_PATH_SEPARATOR=":"
export COMPOSE_PROJECT_NAME="ke-scan-${RANDOM}${RANDOM}"
export KE_ENV_FILE=.env.example
export KE_SCAN_IN="./dist/${COMPOSE_PROJECT_NAME}"
unset COMPOSE_PROFILES COMPOSE_ENV_FILES GRYPE_DB_UPDATE_URL DOCKER_DEFAULT_PLATFORM

scanner="$(sed -n 's/^ *image: *//p' docker-compose.scan.yml | head -n 1)"
project="$COMPOSE_PROJECT_NAME"

fail() {
  echo "scan: FAIL ($1)" >&2
  exit 1
}

cleanup() {
  local status=$?
  trap - EXIT
  # A second signal must not cut teardown short.
  trap '' INT TERM
  # Force-remove this project's own containers (running or not) first, so a
  # signal mid-run leaves nothing for teardown.sh, which only reports, to miss.
  local ids=()
  if mapfile -t ids < <(docker ps -aq --filter "label=com.docker.compose.project=$project"); then
    if [ "${#ids[@]}" -gt 0 ] && ! docker rm -f "${ids[@]}" >/dev/null; then
      echo "scan: FAIL (could not remove the containers of project $project)" >&2
      status=1
    fi
  fi
  if ! scripts/teardown.sh --volumes; then
    echo "scan: FAIL (teardown of project $project failed; by hand: COMPOSE_FILE=docker-compose.scan.yml docker compose -p $project down --volumes)" >&2
    status=1
  fi
  rm -rf -- "$KE_SCAN_IN"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# An existing path fails the run: the directory is this scan's own.
mkdir -p dist
mkdir -m 0755 -- "$KE_SCAN_IN"

# The ignore entries in force, for the log (PSC-7).
echo "== scan: ignore entries (docker/scan-ignore.yaml) =="
cat docker/scan-ignore.yaml

echo "== scan: save =="
stage_start=$SECONDS
docker save -o "$KE_SCAN_IN/ke-app.tar" "ke-app:$tag" \
  || fail "stage save: could not save ke-app:$tag; no retry"
# docker save writes 0600 on a Linux engine; the cap-dropped scanner must read it.
chmod 0644 -- "$KE_SCAN_IN/ke-app.tar"
echo "scan: save took $((SECONDS - stage_start))s"

echo "== scan: scan-db =="
stage_start=$SECONDS
docker compose --env-file "$KE_ENV_FILE" pull scan-db \
  || fail "stage scan-db: pulling the scanner image $scanner failed; no retry"
docker compose --env-file "$KE_ENV_FILE" run --rm --pull never \
  -e "GRYPE_DB_UPDATE_URL=$SCAN_DB_URL" scan-db \
  || fail "stage scan-db: could not fetch the vulnerability database from $scan_db_host; no retry"
echo "scan: scan-db took $((SECONDS - stage_start))s"

echo "== scan: scan =="
stage_start=$SECONDS
rc=0
docker compose --env-file "$KE_ENV_FILE" run --rm --pull never scan || rc=$?
if [ "$rc" -ne 0 ]; then
  fail "stage scan: grype exited $rc: a fixed High or Critical match, or a scanner error; see the table above"
fi
echo "scan: scan took $((SECONDS - stage_start))s"

echo "== scan: done =="
