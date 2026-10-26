#!/usr/bin/env bash
# `ci/deployable-offline` (PS-3.2, architecture §2.5): proves the offline
# bundle installs and runs on a clean Docker daemon with no route out. Called
# by scripts/verify.sh full, after the verify project is torn down. It is a
# CI and developer script: never shipped in the bundle, not an operator tool,
# and so not held to the bash 3.2 rule that install/launch/teardown follow.
#
# Two-sided, keyed on KE_OFFLINE_CLIENT=1:
#
# Host half (no KE_OFFLINE_CLIENT): runs its own project ke-offline-<random>
#   from the standalone docker-compose.offline.yml, and nothing else:
#   disk floor (7 GiB) -> pulls (SBOM generator, ke-app base, ke-neo4j base)
#   -> bundle.sh -> image-side drift check (the ke-app SBOM against an SBOM
#   of its base) -> ke-neo4j check (its config against the official image's,
#   its saved tar and SBOM without the fleet plugin) -> `dind` up ->
#   net_isolated.sh on the offline network -> `run offline-client`. The EXIT
#   trap always runs
#   `teardown.sh --volumes --profile offline` and removes the bundle. `df` is
#   logged around each stage.
#
# Client half (KE_OFFLINE_CLIENT=1, inside the offline-client container): the
#   inner daemon is clean and on the containerd store, then install -> launch
#   -> smoke (ci/offline included) -> teardown, then the daemon holds exactly
#   the bundle's image names, so nothing was pulled.
#   KE_OFFLINE_BUNDLE_DIR (default /bundle) and KE_OFFLINE_INSTALL_ROOT
#   (default /install) are TEST SEAMS ONLY: the container sets neither, and
#   the host half never reads them.
set -euo pipefail

die() { echo "offline_check: FAIL ($*)" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Client half
# ---------------------------------------------------------------------------
if [ "${KE_OFFLINE_CLIENT:-}" = 1 ]; then
  bundle="${KE_OFFLINE_BUNDLE_DIR:-/bundle}"
  root="${KE_OFFLINE_INSTALL_ROOT:-/install}"
  [ -w "${HOME:-/nonexistent}" ] || export HOME=/tmp
  say() { echo "offline-client: $*"; }

  # Fail closed (security L-OCb): the CA private key stays out of this
  # container only because Compose mounts the `client` subpath. If a `ca` or
  # `server` entry of any kind (directory, file, dangling link) is here, the
  # mount is wrong; refuse before any call to the inner daemon.
  certs_dir="${DOCKER_CERT_PATH:-/certs/client}"
  for name in ca server; do
    if [ -e "$certs_dir/$name" ] || [ -L "$certs_dir/$name" ]; then
      die "$certs_dir/$name exists: the client must hold only its own TLS files, never the CA or server material"
    fi
  done

  [ -f "$bundle/bundle.json" ] || die "no bundle.json in $bundle"

  # The store must be containerd (spike S1): the check says nothing about the
  # other store otherwise. Asserted rather than assumed.
  driver_status="$(docker info --format '{{.DriverStatus}}')" || die "cannot reach the inner daemon"
  case "$driver_status" in
    *io.containerd.snapshotter.v1*) say "inner daemon uses the containerd image store" ;;
    *) die "inconclusive: the inner daemon does not use the containerd image store (driver status: $driver_status)" ;;
  esac

  # Clean daemon: anything already in the store would hide a missing image.
  present="$(docker image ls -q)" || die "cannot list the inner daemon's images"
  if [ -n "$present" ]; then
    die "the inner daemon is not clean: it already holds images, so a missing image could hide"
  fi

  # No egress: a registry pull must fail. If it succeeds the daemon can reach
  # the internet and the run proves nothing, so the check is inconclusive.
  vendor_ref="$(sed -n 's/.*"ref": "\([^"]*@sha256:[0-9a-f]\{64\}\)".*/\1/p' "$bundle/bundle.json" | head -n 1)"
  [ -n "$vendor_ref" ] || die "bundle.json lists no digest-pinned vendor image"
  if timeout 60 docker pull "$vendor_ref" > /dev/null 2>&1; then
    die "inconclusive: the inner daemon pulled $vendor_ref, so it has a route out"
  fi
  say "a registry pull fails, as expected with no route out"

  # install.sh refuses a sticky world-writable parent, so make an operator-owned one.
  mkdir -m 0755 "$root/op"
  target="$root/op/ke"
  say "install"
  bash "$bundle/install.sh" "$target"
  CDPATH='' cd -- "$target"
  say "launch"
  bash scripts/launch.sh
  say "smoke (ci/offline included)"
  KE_SMOKE_OWNS_PROJECT=1 bash scripts/smoke.sh
  say "teardown"
  bash scripts/teardown.sh --volumes

  # No pull happened: the repository:tag names now in the store are exactly
  # the bundle's `as` names. Names, not IDs (IDs differ by store). Only a fully
  # dangling `<none>:<none>` row is ignored: any `repo:<none>` row is a name
  # the bundle did not give, and is how a digest-pinned pull is listed.
  want="$(sed -n 's/.*"as": "\([^"]*\)".*/\1/p' "$bundle/bundle.json" | LC_ALL=C sort -u)"
  have="$(docker image ls --format '{{.Repository}}:{{.Tag}}' | awk '$0 != "<none>:<none>"' | LC_ALL=C sort -u)"
  extra="$(LC_ALL=C comm -13 <(printf '%s\n' "$want") <(printf '%s\n' "$have"))"
  missing="$(LC_ALL=C comm -23 <(printf '%s\n' "$want") <(printf '%s\n' "$have"))"
  if [ -n "$extra$missing" ]; then
    {
      echo "offline_check: FAIL (the inner daemon's image names differ from the bundle's: an image was pulled or is missing)"
      while IFS= read -r name; do
        if [ -n "$name" ]; then echo "  not in the bundle: $name"; fi
      done <<< "$extra"
      while IFS= read -r name; do
        if [ -n "$name" ]; then echo "  missing: $name"; fi
      done <<< "$missing"
    } >&2
    exit 1
  fi
  say "image names equal the bundle's; nothing was pulled"
  exit 0
fi

# ---------------------------------------------------------------------------
# Host half
# ---------------------------------------------------------------------------
CDPATH='' cd -- "$(dirname -- "$0")/.."
started="$(date +%s)"
finished=0
# verify.sh sets MSYS_NO_PATHCONV for its container paths; bundle.sh hands an
# absolute host path to `docker save -o`, which Git Bash must convert.
unset MSYS_NO_PATHCONV

arch_raw="$(docker info --format '{{.Architecture}}')" || die "the Docker daemon does not answer (docker info failed)"
case "$arch_raw" in
  x86_64 | amd64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) die "the Docker daemon reports an unsupported architecture: $arch_raw" ;;
esac

# Its own project and file: never the caller's (verify's) project, and
# teardown.sh --volumes --profile offline inherits COMPOSE_FILE.
project="ke-offline-${RANDOM}${RANDOM}"
bundle_rel="dist/${project}-${arch}"
unset COMPOSE_PROFILES COMPOSE_PATH_SEPARATOR
export COMPOSE_PROJECT_NAME="$project"
export COMPOSE_FILE="docker-compose.offline.yml"
export KE_OFFLINE_BUNDLE="$bundle_rel"
export KE_ENV_FILE=".env.example"

compose() { docker compose --env-file .env.example --profile offline "$@"; }
# Host paths for docker under Git Bash (as bundle.sh): cygpath where it exists.
hostpath() { if command -v cygpath > /dev/null 2>&1; then cygpath -m -- "$1"; else printf "%s" "$1"; fi; }
drift_work=""

# Paths whose free space matters: the filesystem holding dist/, and the
# daemon's DockerRootDir when that path exists on this host (on Docker Desktop
# it is inside the VM and cannot be measured from here).
root_dir="$(docker info --format '{{.DockerRootDir}}' 2> /dev/null)" || root_dir=""
mkdir -p dist
df_paths=(dist)
if [ -n "$root_dir" ] && [ -d "$root_dir" ]; then df_paths+=("$root_dir"); fi

df_log() { # df_log STAGE
  echo "offline: df $1"
  df -Pk -- "${df_paths[@]}" || true
}

# shellcheck disable=SC2317  # runs from the EXIT trap
cleanup() {
  local rc=$?
  trap - EXIT INT TERM HUP
  df_log "before teardown"
  if ! bash scripts/teardown.sh --volumes --profile offline; then
    echo "offline_check: FAIL (teardown of project $project failed; remove it by hand: COMPOSE_FILE=docker-compose.offline.yml KE_OFFLINE_BUNDLE=$bundle_rel docker compose -p $project --profile offline down --volumes)" >&2
    if [ "$rc" -eq 0 ]; then rc=1; fi
  fi
  rm -rf -- "$bundle_rel" "$bundle_rel.manifest.sha256"
  if [ -n "$drift_work" ]; then rm -rf -- "$drift_work"; fi
  df_log "after teardown"
  if [ "$rc" -eq 0 ] && [ "$finished" -eq 1 ]; then echo "== offline_check: PASS ($(( $(date +%s) - started ))s) =="; fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

at_least() { # at_least MINIMUM VERSION: dotted numbers, field by field
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

df_log "start"

# Free disk (R6): at least 7 GiB on each measurable path, before anything is saved.
# Basis (ruling 1, docs/evidence/platform-offline/ci-39359710258.log): the
# measured need is the bundle (0.94 GiB) plus the dind image store (3.3 GiB),
# about 4.3 GiB; 7 GiB leaves about 60% headroom.
floor_kb=$((7 * 1024 * 1024))
avail_kb() { # avail_kb PATH: the Available column, the number before the capacity %
  df -Pk -- "$1" | awk '
    NR > 1 && v == "" {
      for (i = 4; i <= NF; i++) {
        if ($i ~ /^[0-9]+%$/ && $(i-1) ~ /^[0-9]+$/ && $(i-2) ~ /^[0-9]+$/ && $(i-3) ~ /^[0-9]+$/) { v = $(i-1); break }
      }
    }
    END { print v }'
}
for path in "${df_paths[@]}"; do
  free="$(avail_kb "$path")" || free=""
  case "$free" in
    '' | *[!0-9]*) die "cannot read the free space on $path" ;;
  esac
  if [ "$free" -lt "$floor_kb" ]; then
    die "need 7 GiB free on $path, found $((free / 1024 / 1024)) GiB"
  fi
done
if [ "${#df_paths[@]}" -eq 1 ]; then
  echo "offline: the daemon's DockerRootDir (${root_dir:-unknown}) is not on this host (Docker Desktop keeps it in a VM): not measurable, only dist/ is checked"
fi

# The inner volume.subpath mount needs a Compose that applies it.
compose_minimum=2.27
compose_version="$(docker compose version --short 2> /dev/null || true)"
compose_version="${compose_version#v}"
if [ -z "$compose_version" ] || ! at_least "$compose_minimum" "$compose_version"; then
  die "Docker Compose >= $compose_minimum is required for volume.subpath (found: ${compose_version:-none})"
fi

# platform-sbom U2 (PSC-20; design-notes "N1 amendment, U2" *Interim pull*):
# bundle.sh never pulls and refuses without the SBOM generator, so this check
# pulls it first, through its own compose file (the one place it is pinned).
# U8 replaces these lines with scripts/bundle_fetch.sh. The ${VAR:?} mounts get
# dummy values (pull reads no bind source); -f overrides COMPOSE_FILE.
echo "offline: pulling the SBOM generator (docker-compose.sbom.yml, service sbom)"
KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent KE_SBOM_USER="$(id -u):$(id -g)" \
  docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom \
  || die "pulling the SBOM generator failed (docker-compose.sbom.yml, service sbom); no retry"

# platform-sbom U4 (orchestrator ruling 6; design-notes "N1 amendment, U4"):
# the ke-app base, for the drift step below, pulled by its pinned digest (a
# no-op when the daemon holds it; BuildKit's cache is not the image store).
# Before bundle.sh, so a failed pull costs seconds; one call, no retry.
base_ref="$(sed -n 's/^FROM \([^ ]*\) AS runtime$/\1/p' docker/app.Dockerfile)"
[[ "$base_ref" =~ ^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$ ]] \
  || die "cannot read the ke-app base reference from docker/app.Dockerfile"
echo "offline: pulling the ke-app base ($base_ref)"
docker pull "$base_ref" > /dev/null || die "pulling the ke-app base failed ($base_ref); no retry"

# platform-sbom U4b (PSC-26, Q67; design-notes N16): the official neo4j image
# ke-neo4j is built from, by the pinned digest of docker/neo4j.Dockerfile's
# FROM, for the config check below. Before bundle.sh, one call, no retry.
neo4j_base="$(sed -n 's/^FROM \([^ ]*\) AS runtime$/\1/p' docker/neo4j.Dockerfile)"
[[ "$neo4j_base" =~ ^neo4j:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$ ]] \
  || die "cannot read the ke-neo4j base reference from docker/neo4j.Dockerfile"
echo "offline: pulling the ke-neo4j base ($neo4j_base)"
docker pull "$neo4j_base" > /dev/null || die "pulling the ke-neo4j base failed ($neo4j_base); no retry"

bash scripts/bundle.sh --out "$bundle_rel" || die "bundle.sh failed"
# CI run 39364201188: bundle.sh writes private (0600) files but the offline client runs as uid 10001; open only this throwaway dir, read-only.
chmod -R a+rX -- "$bundle_rel"
df_log "after bundle"

# platform-sbom U4 (PSC-14, PSC-22; design-notes N7, N10 B3): the image-side
# drift check. The base ($base_ref, pulled above before bundle.sh) gets its
# SBOM from the same generator, by a `docker save` outside the bundle (save
# names the ref if the image is missing), and the checker runs in the ke-app
# image being checked, with no network and read-only mounts.
libpq_pin="$(sed -n 's/^ARG LIBPQ_VERSION=//p' docker/app.Dockerfile)"
[ -n "$libpq_pin" ] || die "docker/app.Dockerfile has no ARG LIBPQ_VERSION="
app_ref="$(sed -n 's/.*"ref": "\(ke-app:[^"]*\)".*/\1/p' "$bundle_rel/bundle.json" | head -n 1)"
[ -n "$app_ref" ] || die "bundle.json names no ke-app image"
drift_work="$(mktemp -d "$PWD/dist/.ke-drift.XXXXXXXX")" || die "cannot create the drift work dir"
mkdir -- "$drift_work/in" "$drift_work/out" "$drift_work/out/tmp"
chmod 0700 -- "$drift_work/in" "$drift_work/out" "$drift_work/out/tmp"
docker save -o "$drift_work/in/base.tar" "$base_ref" || die "docker save of the ke-app base failed ($base_ref)"
MSYS_NO_PATHCONV=1 \
KE_SBOM_IN="$(hostpath "$drift_work/in")" KE_SBOM_OUT="$(hostpath "$drift_work/out")" KE_SBOM_USER="$(id -u):$(id -g)" \
  docker compose --env-file .env.example -f docker-compose.sbom.yml run --rm --pull never sbom \
  docker-archive:/in/base.tar --scope all-layers -o spdx-json=/out/raw.spdx.json >&2 \
  || die "SBOM generation failed for the ke-app base ($base_ref)"
repo_host="$(hostpath "$PWD")"
MSYS_NO_PATHCONV=1 \
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never \
  --user "$(id -u):$(id -g)" --label "com.docker.compose.project=${project}-sbomcheck" \
  -v "$repo_host/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro" \
  -v "$repo_host/tests/test_notice_ke_app.py:/opt/ke/added.py:ro" \
  -v "$repo_host/licenses:/opt/ke/licenses:ro" \
  -v "$(hostpath "$PWD/$bundle_rel/app/sboms"):/sboms:ro" \
  -v "$(hostpath "$drift_work/out"):/base:ro" \
  --entrypoint python "$app_ref" -I /opt/ke/sbom_check.py drift \
  --sbom /sboms/ke-app.spdx.json --base /base/raw.spdx.json --added-from /opt/ke/added.py \
  --libpq "$libpq_pin" --lock /app/uv.lock \
  --licence /opt/ke/licenses/CPython-3.12-incorporated.txt --licence /opt/ke/licenses/CPython-3.12-HACL.txt \
  --licence /opt/ke/licenses/CPython-3.12-KaRaMeL.txt \
  || die "the image-side drift check failed on the ke-app SBOM (see above)"
rm -rf -- "$drift_work"
drift_work=""
echo "offline: image-side drift check: the ke-app SBOM matches its base ($base_ref)"
df_log "after drift check"

# platform-sbom U4b (PSC-26; design-notes N16): ke-neo4j as bundled. Its
# `docker image inspect` config equals the official image's; no layer of
# images/ke-neo4j.tar holds /var/lib/neo4j/products, a whiteout of it or a
# fleet-management plugin file; app/sboms/ke-neo4j.spdx.json lists no such
# plugin but still lists Neo4j Community and the Temurin OpenJDK. The checker
# runs in the ke-app image, with no network and read-only mounts.
neo4j_ref="$(sed -n 's/.*"ref": "\(ke-neo4j:[^"]*\)".*/\1/p' "$bundle_rel/bundle.json" | head -n 1)"
[ -n "$neo4j_ref" ] || die "bundle.json names no ke-neo4j image"
neo4j_work="$(mktemp -d "$PWD/dist/.ke-neo4j.XXXXXXXX")" || die "cannot create the ke-neo4j work dir"
# drift_work is reused so the EXIT trap removes this work dir too (U4b review).
drift_work="$neo4j_work"
docker image inspect --format '{{json .Config}}' "$neo4j_base" > "$neo4j_work/official-config.json" \
  || die "docker image inspect of the ke-neo4j base failed ($neo4j_base)"
docker image inspect --format '{{json .Config}}' "$neo4j_ref" > "$neo4j_work/config.json" \
  || die "docker image inspect of $neo4j_ref failed"
chmod -R a+rX -- "$neo4j_work"
MSYS_NO_PATHCONV=1 \
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never \
  --user "$(id -u):$(id -g)" --label "com.docker.compose.project=${project}-sbomcheck" \
  -v "$repo_host/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro" \
  -v "$(hostpath "$PWD/$bundle_rel/app/sboms"):/sboms:ro" \
  -v "$(hostpath "$PWD/$bundle_rel/images"):/images:ro" \
  -v "$(hostpath "$neo4j_work"):/neo4j:ro" \
  --entrypoint python "$app_ref" -I /opt/ke/sbom_check.py neo4j \
  --official-config /neo4j/official-config.json --config /neo4j/config.json \
  --sbom /sboms/ke-neo4j.spdx.json --tar /images/ke-neo4j.tar \
  || die "the ke-neo4j check failed (see above): products/ or the fleet-management plugin, or a config change"
rm -rf -- "$neo4j_work"
drift_work=""
echo "offline: ke-neo4j check: config equals $neo4j_base; no products/ or fleet-management plugin in its tar or SBOM"
df_log "after ke-neo4j check"

echo "offline: starting dind (privileged) in project $project"
if ! compose up -d --wait dind; then
  die "dind did not come up. It runs privileged: a daemon that refuses privileged containers is a blocker for this check, and there is no way around it"
fi
df_log "after dind up"

bash scripts/net_isolated.sh "${project}_offline" || die "the offline network ${project}_offline is not internal and isolated"

echo "offline: running the offline client"
compose run --rm offline-client || die "the offline client failed (see its output above)"
df_log "after client run"
finished=1
exit 0
