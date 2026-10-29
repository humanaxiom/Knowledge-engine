#!/usr/bin/env bash
# platform-sbom U8b (PSC-15, PSC-23; design-notes "N4 amendment, U8" items 3
# and 6; ADR-KE-016 "Amended U8"): fetch the third-party source set into a
# directory, checking every file against docker/sources.lock.json.
#
#   scripts/bundle_fetch.sh --set sample|full --out DIR [--arch amd64|arm64]
#
# A host script (Linux and Git Bash), never bundled and never copied by
# bundle.sh. It is the only bundle step with a route out, and it has none of
# its own: the fetch runs in the `sources-fetch` service of
# docker-compose.sources.yml (read-only root, no capabilities, the project's
# default bridge), which reaches only the hosts in docker/source-policy.json.
# The operator order is scripts/build.sh, then this script, then
# scripts/bundle.sh. scripts/offline_check.sh runs it with --set sample.
#
# The arch is the Docker daemon's; --arch only asserts it (as bundle.sh).
# No retry (Q61): each failure is one `bundle_fetch: FAIL (stage <s>: <why>;
# no retry)` line and exit 1. A client failure passes the client's own FAIL
# line through, then one line naming the stage and the exit code (the client
# for any code but 125-127, which only docker compose returns), and exits
# with that code unchanged. In order:
#  1. arguments (exit 2 on anything else), `docker`, the arch;
#  2. --out (every trailing / stripped; a last component of . or .. is
#     refused): a symlink, a non-directory, an unlistable or a non-empty
#     directory is refused untouched; absent it is created 0700 (plain mkdir,
#     so one that appeared in between fails and is left alone); empty it is
#     used in place;
#  3. the ke-gates image is on the daemon, and the caller's uid:gid is numeric;
#  4. `== sources: pull ==`: the pinned SBOM generator, pulled through
#     docker-compose.sbom.yml (the one place it is pinned);
#  5. `== sources: fetch ==`: the one `sources-fetch` run, on its own
#     ke-fetch-<8 hex> project;
#  6. fetch.json (the completion record, written last by the client) is a
#     regular file; then `== sources: done (pull <a> s, fetch <b> s) ==`.
# The EXIT/INT/TERM/HUP trap brings the project down; on a failure it removes
# an --out it created and empties one it was given and saw at stage 2; it
# ignores further signals while it runs. It takes no caller key:
# -f, -p and --env-file name this script's own, and the repo-root .env is
# never read.
set -euo pipefail

fail() { echo "bundle_fetch: FAIL ($1; no retry)" >&2; exit 1; }
usage() { echo "usage: scripts/bundle_fetch.sh --set sample|full --out DIR [--arch amd64|arm64]" >&2; exit 2; }

set_name=""
out=""
asserted_arch=""
while [ $# -gt 0 ]; do
  case "$1" in
    --set) [ $# -ge 2 ] || usage; set_name="$2"; shift 2 ;;
    --out) [ $# -ge 2 ] || usage; out="$2"; shift 2 ;;
    --arch) [ $# -ge 2 ] || usage; asserted_arch="$2"; shift 2 ;;
    *) usage ;;
  esac
done
case "$set_name" in sample | full) ;; *) usage ;; esac
[ -n "$out" ] || usage
case "$asserted_arch" in "" | amd64 | arm64) ;; *) usage ;; esac

command -v docker > /dev/null 2>&1 || fail "tools: docker not on PATH"
case "$out" in /*) ;; *) out="$PWD/$out" ;; esac
while [ "${out%/}" != "$out" ]; do out="${out%/}"; done
case "${out##*/}" in . | ..) fail "stage out: $out ends in a . or .. component" ;; esac
CDPATH='' cd -- "$(dirname -- "$0")/.."

# Host paths for docker under Git Bash: cygpath where it exists.
hostpath() { if command -v cygpath > /dev/null 2>&1; then cygpath -m -- "$1"; else printf "%s" "$1"; fi; }
export MSYS_NO_PATHCONV=1
unset COMPOSE_PROFILES COMPOSE_PATH_SEPARATOR COMPOSE_FILE DOCKER_DEFAULT_PLATFORM COMPOSE_ENV_FILES

# --- 1. the arch: the daemon's ------------------------------------------------
arch_raw="$(docker info --format '{{.Architecture}}')" || fail "stage arch: the Docker daemon does not answer (docker info failed)"
case "$arch_raw" in
  x86_64 | amd64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) fail "stage arch: the Docker daemon reports an unsupported architecture: $(printf '%q' "$arch_raw")" ;;
esac
if [ -n "$asserted_arch" ] && [ "$asserted_arch" != "$arch" ]; then
  fail "stage arch: --arch $asserted_arch does not match the Docker daemon ($arch, reported as $arch_raw)"
fi

# --- 2. --out ------------------------------------------------------------------
given=0
if [ -L "$out" ]; then fail "stage out: $out is a symlink"; fi
if [ -e "$out" ]; then
  [ -d "$out" ] || fail "stage out: $out exists and is not a directory"
  entries="$(ls -A -- "$out")" || fail "stage out: cannot list $out"
  [ -z "$entries" ] || fail "stage out: $out is not empty"
  given=1
fi

# --- 3. the gates image, the caller's uid:gid ----------------------------------
gates_ref="ke-gates:${KE_IMAGE_TAG:-local}"
docker image inspect --format '{{.Os}}/{{.Architecture}}' "$gates_ref" > /dev/null 2>&1 \
  || fail "stage images: $gates_ref not found: run scripts/build.sh first"
user="$(id -u):$(id -g)"
[[ "$user" =~ ^[0-9]+:[0-9]+$ ]] || fail "stage images: id -u / id -g gave no numeric uid:gid"

project="ke-fetch-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
created=0
# shellcheck disable=SC2317  # runs from the EXIT trap
cleanup() {
  local rc=$?
  trap '' INT TERM HUP
  trap - EXIT
  KE_SOURCES_IN=/nonexistent KE_SOURCES_OUT=/nonexistent KE_SOURCES_USER="$user" \
    docker compose -p "$project" --env-file .env.example -f docker-compose.sources.yml down --volumes \
    > /dev/null 2>&1 || true
  if [ "$rc" -ne 0 ]; then
    if [ "$created" -eq 1 ]; then
      rm -rf -- "$out"
    elif [ "$given" -eq 1 ] && [ -d "$out" ] && [ ! -L "$out" ]; then
      find "$out" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + || true
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [ "$given" -eq 0 ]; then
  mkdir -- "$out" || fail "stage out: cannot create $out (it appeared after the check, or the parent is not writable)"
  created=1
  chmod 0700 -- "$out" || fail "stage out: cannot chmod $out"
fi

# --- 4. pull the SBOM generator (docker-compose.sbom.yml pins it) ---------------
echo "== sources: pull =="
pull_start=$SECONDS
sbom_ref="$(KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent KE_SBOM_USER="$user" \
  docker compose --env-file .env.example -f docker-compose.sbom.yml config --images sbom)" \
  || fail "stage pull: docker compose config --images sbom failed for docker-compose.sbom.yml"
[[ "$sbom_ref" =~ ^[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$ ]] \
  || fail "stage pull: the SBOM generator reference has no digest pin or fails its pattern: $(printf '%q' "$sbom_ref")"
KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent KE_SBOM_USER="$user" \
  docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom \
  || fail "stage pull: pulling the SBOM generator $sbom_ref failed"
pull_secs=$((SECONDS - pull_start))

# --- 5. fetch (the one network step) ---------------------------------------------
echo "== sources: fetch =="
fetch_start=$SECONDS
rc=0
KE_SOURCES_IN=/nonexistent KE_SOURCES_OUT="$(hostpath "$out")" KE_SOURCES_USER="$user" \
  docker compose -p "$project" --env-file .env.example -f docker-compose.sources.yml \
  run --rm --pull never sources-fetch --arch "$arch" --set "$set_name" || rc=$?
if [ "$rc" -ne 0 ]; then
  case "$rc" in
    125 | 126 | 127) who="docker compose run exited $rc" ;;
    *) who="sources_fetch.py exited $rc" ;;
  esac
  echo "bundle_fetch: FAIL (stage fetch: $who; no retry)" >&2
  exit "$rc"
fi
fetch_secs=$((SECONDS - fetch_start))

# --- 6. the completion record ------------------------------------------------------
if [ -L "$out/fetch.json" ] || [ ! -f "$out/fetch.json" ]; then
  fail "stage fetch: $out/fetch.json is not a regular file"
fi
echo "== sources: done (pull $pull_secs s, fetch $fetch_secs s) =="
