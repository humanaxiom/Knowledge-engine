#!/usr/bin/env bash
# Writes the offline bundle (PS-3.1, architecture §2.5 Bundle):
#
#   scripts/bundle.sh --out <dir>-<arch> [--arch amd64|arm64]
#
# Run from a checkout on a linux build host (amd64 or arm64; the bundle is for the
# Docker daemon's own arch, and --arch only asserts it), after build.sh. It never
# builds, pulls or pushes, and makes no network call. The bundle holds the
# stack images only (one tar each, saved from a bundle tag with no
# --platform), the files `install` copies (app/), the two installers, a
# bundle.json record and MANIFEST.sha256 over every other file.
set -euo pipefail
export LC_ALL=C

usage() { echo "usage: scripts/bundle.sh --out <dir>-<arch> [--arch amd64|arm64]" >&2; exit 2; }
die() { echo "bundle: $*" >&2; exit 1; }

out=""
asserted_arch=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --out)
      [ "$#" -ge 2 ] || usage
      out="$2"
      shift 2
      ;;
    --arch)
      [ "$#" -ge 2 ] || usage
      asserted_arch="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done
[ -n "$out" ] || usage
case "$out" in
  /*) ;;
  *) out="$PWD/$out" ;;
esac
out="${out%/}"

case "$asserted_arch" in
  "" | amd64 | arm64) ;;
  *) echo "bundle: --arch must be amd64 or arm64" >&2; usage ;;
esac

cd "$(dirname "$0")/.."

# jq reads each service's image from the resolved compose model (defect D1); it
# is a build-host prerequisite, checked before anything else runs.
command -v jq > /dev/null 2>&1 \
  || die "jq is required on the build host (it reads the resolved compose model); install it first (for example apt-get install jq, brew install jq)"

# --- arch: the target daemon's, normalised (PS-3.1 Arch) -------------------
daemon_arch_raw="$(docker info --format '{{.Architecture}}')" || die "the Docker daemon does not answer (docker info failed)"
case "$daemon_arch_raw" in
  x86_64 | amd64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) die "the Docker daemon reports an unsupported architecture: $(printf '%q' "$daemon_arch_raw") (supported: amd64, arm64)" ;;
esac
if [ -n "$asserted_arch" ] && [ "$asserted_arch" != "$arch" ]; then
  die "--arch $asserted_arch does not match the Docker daemon ($arch, reported as $daemon_arch_raw); this script builds for the daemon's arch"
fi
case "${out##*/}" in
  *-"$arch") ;;
  *) echo "bundle: the --out name must end in -$arch (got ${out##*/})" >&2; usage ;;
esac

# --- output directory ------------------------------------------------------
if [ -L "$out" ]; then
  die "--out is a symlink: $out"
fi
if [ -e "$out" ]; then
  [ -d "$out" ] || die "--out exists and is not a directory: $out"
  if [ -n "$(ls -A -- "$out")" ]; then
    die "--out is not empty: $out"
  fi
fi
# The release record sits beside the bundle (security M-3); never overwrite one.
record="$out.manifest.sha256"
if [ -e "$record" ] || [ -L "$record" ]; then
  die "the manifest record already exists: $record"
fi

# --- free disk (R6): 10 GiB, before any save -------------------------------
# The Available column is the number before the "NN%" capacity field, so a
# filesystem or mount name with spaces cannot shift it (security L-6).
floor_kb=$((10 * 1024 * 1024))
probe="$out"
while [ ! -e "$probe" ]; do probe="$(dirname "$probe")"; done
df_text="$(df -Pk -- "$probe")" || die "cannot read the free space on $probe"
avail_kb="$(printf '%s\n' "$df_text" | awk '
  NR > 1 && v == "" {
    for (i = 4; i <= NF; i++) {
      if ($i ~ /^[0-9]+%$/ && $(i-1) ~ /^[0-9]+$/ && $(i-2) ~ /^[0-9]+$/ && $(i-3) ~ /^[0-9]+$/) { v = $(i-1); break }
    }
  }
  END { print v }')"
case "$avail_kb" in
  '' | *[!0-9]*) die "cannot read the free space on $probe" ;;
esac
if [ "$avail_kb" -lt "$floor_kb" ]; then
  die "need 10 GiB free on $out, found $((avail_kb / 1024 / 1024)) GiB"
fi

# --- the stack's images ----------------------------------------------------
# No profile: the stack services only (verification images are not bundled).
unset COMPOSE_PROFILES COMPOSE_FILE
compose=(docker compose -f docker-compose.yml --env-file .env.example)

ref_re='^[a-z0-9._/-]+(:[A-Za-z0-9._-]+)?(@sha256:[0-9a-f]{64})?$'
services_out="$("${compose[@]}" config --services)" || die "docker compose config --services failed"
[ -n "$services_out" ] || die "compose config lists no services"
# Sorted, so the bundle does not depend on Compose's service order (it is not
# stable between runs).
services_out="$(printf '%s\n' "$services_out" | sort)" || die "cannot sort the service list"
mapfile -t services <<< "$services_out"

# Each service's own image comes from the resolved model, `.services.<svc>.image`.
# `config --images <svc>` is not used: Compose 5.x also prints the images of the
# service's depends_on services, in a varying order (defect D1).
model="$("${compose[@]}" config --format json)" || die "docker compose config --format json failed"
[ -n "$model" ] || die "docker compose config --format json printed nothing"

refs=()                       # distinct references, in sorted service order
declare -A ref_services=()    # ref -> space-separated service names
for svc in "${services[@]}"; do
  [[ "$svc" =~ ^[a-z0-9_-]+$ ]] || die "service name fails its pattern: $svc"
  ref="$(printf '%s' "$model" | jq -er --arg s "$svc" '.services[$s].image')" \
    || die "service $svc has no image in the resolved compose model"
  [ -n "$ref" ] || die "service $svc has no image"
  [[ "$ref" != *$'\n'* ]] || die "service $svc resolves to more than one image"
  [[ "$ref" =~ $ref_re ]] || die "image reference fails its pattern (service $svc)"
  if [ -z "${ref_services[$ref]+x}" ]; then
    refs+=("$ref")
    ref_services[$ref]="$svc"
  else
    ref_services[$ref]+=" $svc"
  fi
done

git_sha="$(git rev-parse HEAD)"
[[ "$git_sha" =~ ^[0-9a-f]{40}$ ]] || die "git rev-parse HEAD gave no commit"

declare -A ref_as=() ref_name=()
declare -A seen_name=()
for ref in "${refs[@]}"; do
  base="${ref%%@*}"
  repo="${base%:*}"
  # A colon in the last path segment is a tag; otherwise it is a port-less repo.
  if [[ "${base##*/}" != *:* ]]; then repo="$base"; fi
  name="${repo##*/}"
  [[ "$name" =~ ^[a-z0-9._-]+$ ]] || die "image name fails its pattern: $ref"
  if [[ "$ref" == *"@sha256:"* ]]; then
    digest="${ref##*@sha256:}"
    as="ke-vendor/${name}:${digest:0:12}"
  else
    [[ "$repo" =~ ^ke-[a-z0-9._-]+$ ]] \
      || die "image $ref has no digest pin and is not a first-party ke-* image"
    as="${repo}:bundle-${git_sha:0:12}"
  fi
  if [ -n "${seen_name[$name]+x}" ]; then
    die "two images would both be saved as $name.tar: ${seen_name[$name]} and $ref"
  fi
  # Under this scheme two images with one `as` also share a name, so the
  # name check above is the collision check.
  seen_name[$name]="$ref"
  ref_as[$ref]="$as"
  ref_name[$ref]="$name"
done

# The digest pin is enforced here, on the build host: the image must be
# present under exactly this reference, and be linux/$arch.
for ref in "${refs[@]}"; do
  platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$ref")" \
    || die "image not present locally (build it or pull it first; this script never pulls): $ref"
  [ "$platform" = "linux/$arch" ] || die "image $ref is $platform, not linux/$arch"
done

dirty=false
if [ -n "$(git status --porcelain)" ]; then dirty=true; fi

# --- write the bundle ------------------------------------------------------
mkdir -p -- "$out/images"
for ref in "${refs[@]}"; do
  as="${ref_as[$ref]}"
  docker tag "$ref" "$as"
  docker save -o "$out/images/${ref_name[$ref]}.tar" "$as"
done

app="$out/app"
mkdir -p -- "$app/scripts" "$app/docs"
cp -- docker-compose.yml .env.example "$app/"
# Only tracked config ships: an ignored local file (.env.local, a key) stays
# behind (security L-7).
config_found=0
while IFS= read -r -d '' f; do
  config_found=1
  mkdir -p -- "$app/$(dirname -- "$f")"
  cp -P -- "$f" "$app/$f"
done < <(git ls-files -z -- config)
[ "$config_found" -eq 1 ] || die "git ls-files lists no tracked file under config/"
for f in launch.sh teardown.sh smoke.sh launch.ps1 teardown.ps1; do
  cp -- "scripts/$f" "$app/scripts/$f"
done
if [ -f scripts/net_isolated.sh ]; then cp -- scripts/net_isolated.sh "$app/scripts/"; fi
cp -- docs/quickstart.md "$app/docs/quickstart.md"

cp -- scripts/install.sh scripts/install.ps1 "$out/"
if [ -f NOTICE.md ]; then cp -- NOTICE.md "$out/"; fi
if [ -d licenses ]; then cp -R -- licenses "$out/licenses"; fi

{
  printf '{"format": 1, "git_sha": "%s", "dirty": %s, "created": "%s", "arch": "%s", "images": [\n' \
    "$git_sha" "$dirty" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$arch"
  last=$((${#refs[@]} - 1))
  i=0
  for ref in "${refs[@]}"; do
    comma=","
    if [ "$i" -eq "$last" ]; then comma=""; fi
    printf '{"file": "images/%s.tar", "ref": "%s", "as": "%s", "services": "%s"}%s\n' \
      "${ref_name[$ref]}" "$ref" "${ref_as[$ref]}" "${ref_services[$ref]}" "$comma"
    i=$((i + 1))
  done
  printf ']}\n'
} > "$out/bundle.json"

# --- manifest: every regular file except itself, LC_ALL=C order ------------
cd "$out"
if [ -n "$(find . -mindepth 1 ! -type f ! -type d -print -quit)" ]; then
  die "the bundle holds an entry that is neither a file nor a directory (symlink?)"
fi
mapfile -d '' -t files < <(find . -type f -print0 | sort -z)
: > MANIFEST.sha256.tmp
for f in "${files[@]}"; do
  rel="${f#./}"
  [[ "$rel" =~ ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ ]] \
    || die "a bundle path fails the manifest pattern: $(printf '%q' "$rel")"
  sum="$(sha256sum -- "$rel")"
  printf '%s  %s\n' "${sum:0:64}" "$rel" >> MANIFEST.sha256.tmp
done
mv -- MANIFEST.sha256.tmp MANIFEST.sha256

sum="$(sha256sum -- MANIFEST.sha256)"
manifest_sha="${sum:0:64}"
# The release record: one sha256sum-format line, outside the bundle and
# outside its manifest, to be handed to the operator through another channel.
printf '%s  %s/MANIFEST.sha256\n' "$manifest_sha" "$(basename -- "$out")" > "$record"
chmod 0644 -- "$record"
echo "bundle written: $out"
echo "manifest sha256: $manifest_sha"
echo "release record: $record"
