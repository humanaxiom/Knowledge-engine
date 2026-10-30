#!/usr/bin/env bash
# Writes the offline bundle (PS-3.1, architecture §2.5 Bundle):
#
#   scripts/bundle.sh --out <dir>-<arch> --sources <dir> [--sources-set full|sample] [--arch amd64|arm64]
#
# Run from a checkout on a linux build host (amd64 or arm64; the bundle is for the
# Docker daemon's own arch, and --arch only asserts it), after build.sh and
# scripts/bundle_fetch.sh. It never builds, pulls or pushes, and makes no
# network call: scripts/bundle_fetch.sh is the only bundle step with a route
# out (it pulls the SBOM generator this script needs, and fetches the source
# set). --sources is required: the directory scripts/bundle_fetch.sh wrote
# (--sources-set says which set it must hold, default full; sample is for
# verification only). Before anything is written, the sources-check stage
# re-hashes it against docker/sources.lock.json in the ke-app image (no
# network, read-only mounts); the bundle then ships each file as
# app/sources/files/<sha256>, app/sources/index.json (from the lock, the
# policy and the SBOMs; a package with no entry refuses the bundle) and a
# generated "Source code" section of THIRD_PARTY_NOTICES.md. The bundle holds the
# stack images only (one tar each, saved from a bundle tag with no
# --platform), the files `install` copies (app/, which also carries copies of
# NOTICE.md, THIRD_PARTY_NOTICES.md, LICENSE and licenses/), the two
# installers, the committed NOTICE.md and licenses/, a generated
# THIRD_PARTY_NOTICES.md (the ke-app image's package licences, read inside
# that image with no network, and the stack images' licences from NOTICE.md;
# any package or digest-pinned image without a licence refuses the bundle
# before anything is written), one SPDX 2.3 SBOM per image under app/sboms/
# (the pinned generator reads each saved tar with no network;
# scripts/sbom_check.py finishes and checks it), a bundle.json record and
# MANIFEST.sha256 over every other file. A failure after the first write
# removes what this run wrote (the --out directory it created, or the
# contents of the empty one it was given); no manifest and no record are left.
# Just before the first write --out is claimed with mkdir, or (when given) checked
# again to be a real directory and not a link (O-17 (1)); a record chmod that
# fails ends the run and leaves a record this run did not fully write (O-17 (2)).
# Paths (O-16): --out and --sources are made absolute, every trailing slash is
# stripped, and a path with an empty, . or .. segment is refused, never
# resolved. The parent of --out must exist: the run claims --out with a plain
# mkdir, and the release record is written under noclobber.
set -euo pipefail
export LC_ALL=C

usage() { echo "usage: scripts/bundle.sh --out <dir>-<arch> --sources <dir> [--sources-set full|sample] [--arch amd64|arm64]" >&2; exit 2; }
die() { echo "bundle: $*" >&2; exit 1; }
# A refusal at a named stage (O-15): one line.
stage_die() { echo "bundle: FAIL (stage $1: $2)" >&2; exit 1; }

out=""
asserted_arch=""
sources=""
sources_set=""
have_sources=0
have_sources_set=0
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
    --sources)
      [ "$#" -ge 2 ] || usage
      [ "$have_sources" -eq 0 ] || usage
      have_sources=1
      sources="$2"
      shift 2
      ;;
    --sources-set)
      [ "$#" -ge 2 ] || usage
      [ "$have_sources_set" -eq 0 ] || usage
      have_sources_set=1
      sources_set="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done
[ -n "$out" ] || usage
[ -n "$sources" ] || usage
if [ "$have_sources_set" -eq 0 ]; then sources_set=full; fi
case "$sources_set" in
  full | sample) ;;
  *) usage ;;
esac
case "$sources" in
  /*) ;;
  *) sources="$PWD/$sources" ;;
esac
case "$out" in
  /*) ;;
  *) out="$PWD/$out" ;;
esac
# Every trailing slash goes, not one (O-16 (1)); a value empty after that is an
# argument-shape problem (exit 2).
while [ "${sources%/}" != "$sources" ]; do sources="${sources%/}"; done
[ -n "$sources" ] || usage
while [ "${out%/}" != "$out" ]; do out="${out%/}"; done
[ -n "$out" ] || usage
# A path with an empty, `.` or `..` segment is refused before any check runs
# (O-16 (1)); a `..` is refused, never resolved.
segment_bad() {  # $1: an absolute path with no trailing slash
  case "$1" in
    *//* | */./* | */. | */../* | */..) return 0 ;;
  esac
  return 1
}
if segment_bad "$out"; then stage_die out "--out has an empty, . or .. path segment: $out"; fi
if segment_bad "$sources"; then stage_die sources-check "--sources has an empty, . or .. path segment: $sources"; fi

case "$asserted_arch" in
  "" | amd64 | arm64) ;;
  *) echo "bundle: --arch must be amd64 or arm64" >&2; usage ;;
esac

CDPATH='' cd -- "$(dirname -- "$0")/.."
repo_root="$PWD"

# jq reads each service's image from the resolved compose model (defect D1); it
# is a build-host prerequisite; the path rule above runs first.
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
created=1
if [ -e "$out" ]; then
  created=0
  [ -d "$out" ] || die "--out exists and is not a directory: $out"
  # A listing that fails is a refusal, never an empty directory (reviewer N-9).
  out_entries="$(ls -A -- "$out")" || stage_die out "cannot list --out: $out"
  if [ -n "$out_entries" ]; then
    die "--out is not empty: $out"
  fi
fi
# The release record sits beside the bundle (security M-3); never overwrite one.
record="$out.manifest.sha256"
if [ -e "$record" ] || [ -L "$record" ]; then
  die "the manifest record already exists: $record"
fi

# --- the fetched source set: shell checks (U9-1, U9-2) ---------------------
# Nothing is written under --sources, ever; it is read through a :ro mount and
# `cp -P`. The rest of its check (fetch.json, the exact listing, every hash) is
# the sources-check stage below, in the ke-app image, before the first write.
if [ -L "$sources" ]; then stage_die sources-check "--sources is a symlink: $sources"; fi
[ -e "$sources" ] || stage_die sources-check "--sources does not exist: $sources"
[ -d "$sources" ] || stage_die sources-check "--sources is not a directory: $sources"
ls -A -- "$sources" > /dev/null 2>&1 || stage_die sources-check "cannot list --sources: $sources"
if [ -L "$sources/fetch.json" ] || [ ! -f "$sources/fetch.json" ]; then
  stage_die sources-check "--sources $sources has no fetch.json (or it is not a regular file); run scripts/bundle_fetch.sh --set $sources_set first"
fi
# Equal to, inside or containing --out, compared segment-wise after resolving
# links (--out at its nearest existing ancestor): no write may land under --sources.
real_dir() { ( CDPATH='' cd -P -- "$1" > /dev/null 2>&1 && pwd -P ); }
sources_real="$(real_dir "$sources")" || stage_die sources-check "cannot resolve --sources: $sources"
out_anc="$out"
out_rest=""
while [ ! -e "$out_anc" ]; do
  out_rest="/${out_anc##*/}$out_rest"
  out_anc="$(dirname -- "$out_anc")"
done
out_anc_real="$(real_dir "$out_anc")" || stage_die sources-check "cannot resolve --out: $out"
out_real="${out_anc_real%/}$out_rest"
case "$sources_real/" in
  "$out_real/"*) stage_die sources-check "--sources $sources is --out or inside it ($out); no write may land under --sources" ;;
esac
case "$out_real/" in
  "$sources_real/"*) stage_die sources-check "--out $out is inside --sources ($sources); no write may land under --sources" ;;
esac

# --- free disk (R6): 7 GiB, before any save --------------------------------
# Basis (ruling 1, docs/evidence/platform-offline/ci-39359710258.log): the
# measured need is this bundle (0.94 GiB) plus the dind image store (3.3 GiB),
# about 4.3 GiB; 7 GiB leaves about 60% headroom.
# The Available column is the number before the "NN%" capacity field, so a
# filesystem or mount name with spaces cannot shift it (security L-6).
# Measured on --out and on dirname(--out), where the SBOM work dir unpacks
# (review N5; design-notes "N1 amendment, U4 rework"), each at its nearest
# existing ancestor; the second is skipped when both probe the same path.
floor_kb=$((7 * 1024 * 1024))
floor_probe() { local p="$1"; while [ ! -e "$p" ]; do p="$(dirname "$p")"; done; printf '%s' "$p"; }
check_floor() {  # $1: the path named in the message, $2: its probe
  local df_text avail_kb
  df_text="$(df -Pk -- "$2")" || die "cannot read the free space on $2"
  avail_kb="$(printf '%s\n' "$df_text" | awk '
    NR > 1 && v == "" {
      for (i = 4; i <= NF; i++) {
        if ($i ~ /^[0-9]+%$/ && $(i-1) ~ /^[0-9]+$/ && $(i-2) ~ /^[0-9]+$/ && $(i-3) ~ /^[0-9]+$/) { v = $(i-1); break }
      }
    }
    END { print v }')"
  case "$avail_kb" in
    '' | *[!0-9]*) die "cannot read the free space on $2" ;;
  esac
  if [ "$avail_kb" -lt "$floor_kb" ]; then
    die "need 7 GiB free on $1, found $((avail_kb / 1024 / 1024)) GiB"
  fi
}
out_probe="$(floor_probe "$out")"
check_floor "$out" "$out_probe"
out_parent="$(dirname -- "$out")"
parent_probe="$(floor_probe "$out_parent")"
if [ "$parent_probe" != "$out_probe" ]; then
  check_floor "$out_parent" "$parent_probe"
fi

# --- the stack's images ----------------------------------------------------
# No profile: the stack services only (verification images are not bundled).
unset COMPOSE_PROFILES COMPOSE_FILE
compose=(docker compose -f docker-compose.yml --env-file .env.example)

# The first character is never `-`, so no reference reads as an option (security I-1).
ref_re='^[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?(@sha256:[0-9a-f]{64})?$'
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

# --- the SBOM generator (PSC-20, ADR-KE-016 point 1, design-notes N1) ------
# Its reference is read from its own compose file (the one place it is
# pinned) and the image must be on this daemon, or the bundle is refused here,
# before anything is written. This script never pulls it. Compose refuses to
# load the file while its ${VAR:?} mounts are unset, even for `config`, so
# they get dummy values here (N1 amendment, U2); the run that uses them is
# below. --env-file .env.example keeps the repo-root .env out of this file.
# The generator runs as the caller's uid:gid (security L-2; `user:` in the file).
sbom_user="$(id -u):$(id -g)"
[[ "$sbom_user" =~ ^[0-9]+:[0-9]+$ ]] || die "id -u / id -g gave no numeric uid:gid"
sbom_ref="$(KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent KE_SBOM_USER="$sbom_user" \
  docker compose --env-file .env.example -f docker-compose.sbom.yml config --images sbom)" \
  || die "docker compose config --images sbom failed for docker-compose.sbom.yml"
[ -n "$sbom_ref" ] || die "docker-compose.sbom.yml names no image for the sbom service"
[[ "$sbom_ref" != *$'\n'* ]] || die "docker-compose.sbom.yml names more than one image for the sbom service"
[[ "$sbom_ref" =~ $ref_re && "$sbom_ref" == *"@sha256:"* ]] \
  || die "the SBOM generator reference has no digest pin or fails its pattern: $(printf '%q' "$sbom_ref")"
sbom_platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$sbom_ref" 2> /dev/null)" \
  || die "the SBOM generator image is not present ($sbom_ref); run scripts/bundle_fetch.sh first; this script never pulls"
# Each bundle's SBOMs come from its own daemon's arch, never emulated (PSC-21).
[ "$sbom_platform" = "linux/$arch" ] \
  || die "the SBOM generator image $sbom_ref is $(printf '%q' "$sbom_platform"), not linux/$arch (no emulation)"

# --- licence notices (PS-3.8): everything that can refuse the bundle runs here,
# before any tag or save, so a refusal leaves nothing in --out and no record.
#
# Vendor images: every digest-pinned stack image needs a row with a licence in
# the committed NOTICE.md (Image | Reference | Licence | Source | Note), keyed by
# its full pinned reference, so a digest bump has to be reviewed again.
notice_src="$(cat -- NOTICE.md)" || die "NOTICE.md is missing or unreadable; it carries the vendor image licences"
[ -s LICENSE ] || die "LICENSE is missing or empty (the project MIT licence is committed and ships at the bundle root)"
for lic in GPL-3.0.txt LGPL-3.0.txt; do
  [ -s "licenses/$lic" ] || die "licenses/$lic is missing or empty (the full licence texts are committed and ship with the bundle)"
done
# One record per row, fields (reference, image, licence, source, note) joined by
# the ASCII unit separator: not whitespace, so an empty cell stays empty.
sep=$'\037'
declare -A vendor_row=()
while IFS="$sep" read -r nref nrest; do
  [ -n "$nref" ] || continue
  if [ "$nref" = ERR ]; then
    IFS="$sep" read -r why bad_ref <<< "$nrest"
    die "NOTICE.md vendor row for the image $bad_ref is malformed: $why"
  fi
  [ -z "${vendor_row[$nref]+x}" ] || die "NOTICE.md lists $nref twice"
  vendor_row[$nref]="${nref}${sep}${nrest}"
done < <(printf '%s\n' "$notice_src" | LC_ALL=C awk -F'|' '
  function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
  # A licence is an SPDX id, or ids joined by AND, OR or WITH, single-spaced.
  function spdx_like(s,    n, parts, i) {
    n = split(s, parts, " ")
    if (n < 1 || n % 2 == 0 || s !~ /^[A-Za-z0-9]/) return 0
    for (i = 1; i <= n; i++) {
      if (i % 2 == 0) { if (parts[i] != "AND" && parts[i] != "OR" && parts[i] != "WITH") return 0 }
      else if (parts[i] !~ /^[A-Za-z0-9][A-Za-z0-9.+-]*$/ || parts[i] ~ /^(AND|OR|WITH)$/) return 0
    }
    return 1
  }
  # A refusal record: ERR, the reason and the pinned reference (read back below).
  function bad(why,    ref) {
    ref = "(unreadable)"
    if (match($0, /[A-Za-z0-9._\/:-]+@sha256:[0-9a-f]+/)) ref = substr($0, RSTART, RLENGTH)
    printf "ERR\037%s\037%s\n", why, ref
  }
  { sub(/\r$/, "") }
  /^\|/ && index($0, "@sha256:") > 0 {
    if ($0 ~ /[\001-\037\177]/) { bad("the row holds a control byte"); next }
    if (NF != 7) { bad("the row has " (NF - 2) " cells, not 5 (a pipe inside a cell?)"); next }
    if (!spdx_like(trim($4))) { bad("its Licence cell is not an SPDX id or expression"); next }
    ref = trim($3); gsub(/`/, "", ref)
    printf "%s\037%s\037%s\037%s\037%s\n", ref, trim($2), trim($4), trim($5), trim($6)
  }')
vendor_refs=()
missing_licence=()
for ref in "${refs[@]}"; do
  [[ "$ref" == *"@sha256:"* ]] || continue
  vendor_refs+=("$ref")
  row="${vendor_row[$ref]:-}"
  licence=""
  if [ -n "$row" ]; then IFS="$sep" read -r _ _ licence _ <<< "$row"; fi
  if [ -z "$licence" ] || [[ "${licence,,}" =~ ^(unknown|n/?a|none|tbd|todo|-+|\?+)$ ]]; then
    missing_licence+=("$ref")
  fi
done
if [ "${#missing_licence[@]}" -gt 0 ]; then
  die "no licence entry in NOTICE.md for the stack image(s): ${missing_licence[*]}"
fi

# Python packages: run the generator inside the ke-app image being bundled, with
# no network and no pull. The compose label overrides the one the image carries
# (the same hazard as smoke.sh's control run), so this container never looks
# like part of the project that built it.
app_ref=""
for ref in "${refs[@]}"; do
  if [ "${ref_name[$ref]}" = ke-app ]; then
    [ -z "$app_ref" ] || die "more than one ke-app image in the stack: $app_ref and $ref"
    app_ref="$ref"
  fi
done
[ -n "$app_ref" ] || die "the stack has no ke-app image to read the package licences from"
project="$(printf '%s' "$model" | jq -er '.name')" || die "the resolved compose model has no project name"
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "the compose project name fails its pattern"
package_table="$(docker run --rm --network none --pull never --label "com.docker.compose.project=${project}-notices" --entrypoint python "$app_ref" -m engine.notices)" \
  || die "the licence notices generator failed in $app_ref (a package has no licence file in the image); no bundle written"
case "$package_table" in
  "| Package | Version | Licence | Licence files |"*) ;;
  *) die "the licence notices generator printed no package table" ;;
esac

# --- sources-check (U9-2, U9-3): before the first write -----------------------
# The same hardened ke-app run as `finish` below (no network, read-only root, no
# capabilities, the caller's uid:gid, every mount :ro). It prints the distinct
# sha256 of the planned files, sorted; --out does not exist yet.
# Git Bash rewrites container paths in arguments; MSYS_NO_PATHCONV stops that, so host
# paths for mounts and KE_SBOM_* are handed over in Windows form (cygpath -m) where it exists.
hostpath() { if command -v cygpath > /dev/null 2>&1; then cygpath -m -- "$1"; else printf "%s" "$1"; fi; }
check_run() {  # $1...: the subcommand and its arguments; check_mounts holds the extra -v mounts
  MSYS_NO_PATHCONV=1 \
  docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never \
    --user "$sbom_user" --label "com.docker.compose.project=${project}-sbomcheck" \
    -v "$(hostpath "$repo_root")/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro" \
    -v "$(hostpath "$repo_root")/docker/sources.lock.json:/opt/ke/sources.lock.json:ro" \
    -v "$(hostpath "$repo_root")/docker/source-policy.json:/opt/ke/source-policy.json:ro" \
    "${check_mounts[@]}" \
    --entrypoint python "$app_ref" -I /opt/ke/sbom_check.py "$@"
}
t_mark=$SECONDS
check_mounts=(-v "$(hostpath "$sources"):/sources:ro")
check_text="$(check_run sources-check --lock /opt/ke/sources.lock.json --policy /opt/ke/source-policy.json \
  --dir /sources --arch "$arch" --set "$sources_set")" \
  || stage_die sources-check "the source set in --sources failed its check (see above); no bundle written"
[ -n "$check_text" ] || stage_die sources-check "the check listed no source file"
mapfile -t source_shas <<< "$check_text"
for sha in "${source_shas[@]}"; do
  [[ "$sha" =~ ^[0-9a-f]{64}$ ]] || stage_die sources-check "the check printed a line that is not a sha256"
done
t_check=$((SECONDS - t_mark))

dirty=false
if [ -n "$(git status --porcelain)" ]; then dirty=true; fi

# --- write the bundle ------------------------------------------------------
# The first write. From here a non-zero exit removes what this run wrote (O-10):
# --out itself when this run created it, else its contents (it was given empty);
# the record only if this run wrote it. INT, TERM and HUP become a non-zero exit.
sbom_project="${project}-sbom"
sbom_work=""
wrote=0
record_made=0
bundle_cleanup() {
  local rc=$?
  trap '' INT TERM HUP
  trap - EXIT
  CDPATH='' cd -- "$repo_root" > /dev/null 2>&1 || true
  if [ "$rc" -ne 0 ] && [ "$wrote" -eq 1 ]; then
    if [ "$created" -eq 1 ]; then
      rm -rf -- "$out" || echo "bundle: warning: could not remove $out" >&2
    else
      find -- "$out" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + > /dev/null 2>&1 \
        || echo "bundle: warning: could not remove all of the contents of $out" >&2
    fi
    if [ "$record_made" -eq 1 ]; then rm -f -- "$record" || echo "bundle: warning: could not remove $record" >&2; fi
  fi
  if [ -n "$sbom_work" ]; then
    # `down` binds nothing, so the raw (non-hostpath) KE_SBOM_* values below are harmless here.
    ( KE_SBOM_IN="$out/images" KE_SBOM_OUT="$sbom_work" KE_SBOM_USER="$sbom_user" \
        docker compose -p "$sbom_project" --env-file .env.example -f docker-compose.sbom.yml down ) \
      > /dev/null 2>&1 || echo "bundle: warning: docker compose -p $sbom_project down failed" >&2
    rm -rf -- "$sbom_work" || echo "bundle: warning: could not remove $sbom_work" >&2
  fi
  exit "$rc"
}
trap bundle_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
# --out is claimed with a plain mkdir (no -p): it fails if --out appeared since
# the check above (a directory or a link) or its parent is missing, and then
# nothing has been written (O-16 (2), O-17 (1)); `created` was decided once, at
# the early check, and the cleanup removes only a directory this run made. A
# given (empty) --out is re-checked to be still a real directory, not a link.
if [ "$created" -eq 1 ]; then
  mkdir -- "$out" || stage_die out "--out appeared after its check (or cannot be created; its parent must exist, and --out must not): $out; no bundle written"
else
  { [ ! -L "$out" ] && [ -d "$out" ]; } || stage_die out "--out was replaced after its check (it is no longer a real directory): $out; no bundle written"
fi
wrote=1
mkdir -p -- "$out/images"
for ref in "${refs[@]}"; do
  as="${ref_as[$ref]}"
  docker tag "$ref" "$as" || die "tagging image ${ref_name[$ref]} ($ref) failed; no bundle written"
  docker save -o "$out/images/${ref_name[$ref]}.tar" "$as" || die "saving image ${ref_name[$ref]} failed; no bundle written"
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
cp -- scripts/net_isolated.sh "$app/scripts/net_isolated.sh"
cp -- docs/quickstart.md "$app/docs/quickstart.md"

cp -- scripts/install.sh scripts/install.ps1 "$out/"
# NOTICE.md and licenses/ ship as committed (the checks above already refused a
# tree without them), and THIRD_PARTY_NOTICES.md is generated from this build.
tick='`'
cp -- NOTICE.md "$out/"
cp -- LICENSE "$out/LICENSE"
# Only tracked licence texts ship, as with config/ (security L-7).
licenses_found=0
while IFS= read -r -d '' f; do
  licenses_found=1
  mkdir -p -- "$out/$(dirname -- "$f")"
  cp -P -- "$f" "$out/$f"
done < <(git ls-files -z -- licenses)
[ "$licenses_found" -eq 1 ] || die "git ls-files lists no tracked file under licenses/"
{
  printf '# Third-party notices\n\n'
  printf 'Generated by scripts/bundle.sh from build %s. NOTICE.md holds the statements that cannot be generated, and licenses/ the full licence texts.\n\n' "$git_sha"
  printf '## Python packages in the ke-app image\n\n'
  printf 'Read from the image being bundled; the licence files are paths inside its site-packages directory.\n\n'
  printf '%s\n\n' "$package_table"
  printf '## Stack images\n\n'
  printf 'The third-party images in this bundle, by pinned reference. The licence of each is the reviewed entry in NOTICE.md.\n\n'
  printf '| Image | Reference | Licence | Source | Note |\n|---|---|---|---|---|\n'
  for ref in "${vendor_refs[@]}"; do
    IFS="$sep" read -r _ nimage nlicence nsource nnote <<< "${vendor_row[$ref]}"
    printf '| %s | %s%s%s | %s | %s | %s |\n' "$nimage" "$tick" "$ref" "$tick" "$nlicence" "$nsource" "$nnote"
  done
} > "$out/THIRD_PARTY_NOTICES.md"

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

# --- SBOMs (PSC-13; ADR-KE-016 points 1, 2 and 6; design-notes N1, N3, N6) --
# One SPDX 2.3 document per saved tar, at app/sboms/<name>.spdx.json. syft
# reads the tar with no network in its own project (<project>-sbom), as the
# caller's uid:gid, into a fresh per-image work dir outside --out (it also
# takes the unpack, TMPDIR=/out/tmp). scripts/sbom_check.py then runs in the
# ke-app image (no network, read-only mounts, its own label) and prints the
# final document: the image named by its ref and its tar's config digest, a
# fresh urn:uuid namespace, and for ke-app the runtime packages checked
# against uv.lock. Any failure stops here, before the manifest and the record.
# Beside --out, so the 7 GiB floor measured above covers the unpack (review N6).
sbom_work="$(mktemp -d "$(dirname -- "$out")/.ke-sbom.XXXXXXXX")" || die "cannot create the SBOM work dir"
mkdir -p -- "$app/sboms"
for ref in "${refs[@]}"; do
  name="${ref_name[$ref]}"
  work="$sbom_work/$name"
  # mkdir -m fails under Git Bash on NTFS (cannot change permissions); create, then chmod.
  mkdir -- "$work" "$work/tmp" || die "cannot create the SBOM work dir for image $name"
  chmod 0700 -- "$work" "$work/tmp" || die "cannot restrict the SBOM work dir for image $name"
  MSYS_NO_PATHCONV=1 \
  KE_SBOM_IN="$(hostpath "$out/images")" KE_SBOM_OUT="$(hostpath "$work")" KE_SBOM_USER="$sbom_user" \
    docker compose -p "$sbom_project" --env-file .env.example -f docker-compose.sbom.yml \
    run --rm --pull never sbom "docker-archive:/in/$name.tar" --scope all-layers -o spdx-json=/out/raw.spdx.json \
    >&2 || die "SBOM generation failed for image $name ($ref); no bundle written"
  site_args=()
  if [ "$ref" = "$app_ref" ]; then
    site_args=(--site /opt/venv/lib/python3.12/site-packages --lock /app/uv.lock)
  fi
  MSYS_NO_PATHCONV=1 \
  docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never \
    --user "$sbom_user" --label "com.docker.compose.project=${project}-sbomcheck" \
    -v "$(hostpath "$repo_root")/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro" -v "$(hostpath "$work"):/work:ro" -v "$(hostpath "$out/images"):/images:ro" \
    --entrypoint python "$app_ref" -I /opt/ke/sbom_check.py finish \
    --name "$name" --ref "$ref" --arch "$arch" --git-sha "$git_sha" \
    --raw /work/raw.spdx.json --tar "/images/$name.tar" "${site_args[@]}" \
    > "$app/sboms/$name.spdx.json" || die "the SBOM check failed for image $name ($ref); no bundle written"
done

# --- the source set (PSC-15, PSC-24; design-notes "N9 amendment, U9") ---------
# The copy: each distinct sha256 sources-check listed, as a regular file named by
# its sha256. `cp -P`, no -p, no link, no reflink: a link that replaced a checked
# file is copied as a link and the manifest step refuses it, and a later write
# to --sources cannot change shipped bytes. The shipped bytes are hashed again
# against their names below.
t_mark=$SECONDS
mkdir -- "$app/sources" "$app/sources/files" || stage_die copy "cannot create app/sources/; no bundle written"
for sha in "${source_shas[@]}"; do
  cp -P -- "$sources/$sha" "$app/sources/files/$sha" \
    || stage_die copy "copying source file $sha failed; no bundle written"
done
t_copy=$((SECONDS - t_mark))

# index.json: from the lock, the policy, this bundle's SBOMs and the copied files
# (validate first; a package with no lock entry, or a file not shipped, refuses).
# Its stderr (the exempt components' lines) is passed through.
t_mark=$SECONDS
index_sboms=()
for ref in "${refs[@]}"; do
  index_sboms+=(--sbom "${ref_name[$ref]}=/sboms/${ref_name[$ref]}.spdx.json")
done
check_mounts=(-v "$(hostpath "$app/sboms"):/sboms:ro" -v "$(hostpath "$app/sources/files"):/files:ro")
check_run index --lock /opt/ke/sources.lock.json --policy /opt/ke/source-policy.json \
  --arch "$arch" --set "$sources_set" --git-sha "$git_sha" --files /files "${index_sboms[@]}" \
  > "$app/sources/index.json" \
  || stage_die index "the source index failed (see above); no bundle written"
t_index=$((SECONDS - t_mark))

# The "Source code" section of THIRD_PARTY_NOTICES.md, from the shipped index.
t_mark=$SECONDS
check_mounts=(-v "$(hostpath "$app/sources"):/idx:ro")
check_run notices --index /idx/index.json > "$sbom_work/source-code.md" \
  || stage_die notices "the Source code section failed (see above); no bundle written"
{ printf '\n'; cat -- "$sbom_work/source-code.md"; } >> "$out/THIRD_PARTY_NOTICES.md" \
  || stage_die notices "cannot append the Source code section; no bundle written"
t_notices=$((SECONDS - t_mark))
echo "bundle: sources: check $t_check s, copy $t_copy s, index $t_index s, notices $t_notices s"

# app/ carries the notices too (U9-8), so the section's paths resolve from the
# installed copy: byte-identical to the bundle-root copies, which stay.
# Taken from the bundle-root copies under --out, not the tree, so they match
# those copies by construction (O-16 (7), reviewer N-2).
cp -- "$out/NOTICE.md" "$app/NOTICE.md" || stage_die copy "app/NOTICE.md could not be copied; no bundle written"
cp -- "$out/THIRD_PARTY_NOTICES.md" "$app/THIRD_PARTY_NOTICES.md" \
  || stage_die copy "app/THIRD_PARTY_NOTICES.md could not be copied; no bundle written"
cp -- "$out/LICENSE" "$app/LICENSE" || stage_die copy "app/LICENSE could not be copied; no bundle written"
while IFS= read -r -d '' f; do
  mkdir -p -- "$app/$(dirname -- "$f")" || stage_die copy "app/$(dirname -- "$f")/ could not be created; no bundle written"
  cp -P -- "$out/$f" "$app/$f" || stage_die copy "app/$f could not be copied; no bundle written"
done < <(git ls-files -z -- licenses)

# --- manifest: every regular file except itself, LC_ALL=C order ------------
CDPATH='' cd -- "$out"
if [ -n "$(find . -mindepth 1 ! -type f ! -type d -print -quit)" ]; then
  stage_die manifest "the bundle holds an entry that is neither a file nor a directory (symlink?); no bundle written"
fi
mapfile -d '' -t files < <(find . -type f -print0 | sort -z)
: > MANIFEST.sha256.tmp
source_lines=0
for f in "${files[@]}"; do
  rel="${f#./}"
  [[ "$rel" =~ ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ ]] \
    || stage_die manifest "a bundle path fails the manifest pattern: $(printf '%q' "$rel"); no bundle written"
  sum="$(sha256sum -- "$rel")"
  if [[ "$rel" == app/sources/files/* ]]; then
    # ADR point 3, on the bytes that ship: the name is the sha256 (security I-4).
    [[ "$rel" =~ ^app/sources/files/[0-9a-f]{64}$ && "${rel##*/}" == "${sum:0:64}" ]] \
      || stage_die manifest "$rel: the bytes do not match the name; no bundle written"
    source_lines=$((source_lines + 1))
  fi
  printf '%s  %s\n' "${sum:0:64}" "$rel" >> MANIFEST.sha256.tmp
done
[ "$source_lines" -eq "${#source_shas[@]}" ] \
  || stage_die manifest "app/sources/files/ holds $source_lines files, the check listed ${#source_shas[@]}; no bundle written"
# install refuses a manifest over 1 MiB; the cap is never raised.
manifest_bytes="$(wc -c < MANIFEST.sha256.tmp)"
manifest_bytes="${manifest_bytes//[[:space:]]/}"
if [ "$manifest_bytes" -gt 1048576 ]; then
  stage_die manifest "MANIFEST.sha256 would be $manifest_bytes bytes, over install's 1 MiB cap; no bundle written"
fi
mv -- MANIFEST.sha256.tmp MANIFEST.sha256

sum="$(sha256sum -- MANIFEST.sha256)"
manifest_sha="${sum:0:64}"
# The release record: one sha256sum-format line, outside the bundle and
# outside its manifest, to be handed to the operator through another channel.
# Written under noclobber: a record that appeared since the check is never
# overwritten, and then the run ends non-zero with the O-10 cleanup (O-16 (3)).
( set -C; printf '%s  %s/MANIFEST.sha256\n' "$manifest_sha" "$(basename -- "$out")" > "$record" ) \
  || die "cannot write the release record $record (it exists, or is not writable); no bundle written"
chmod 0644 -- "$record" || die "cannot set the mode of the release record $record; no bundle written"
record_made=1
echo "bundle written: $out"
echo "manifest sha256: $manifest_sha"
echo "release record: $record"
