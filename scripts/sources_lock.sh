#!/usr/bin/env bash
# platform-sbom U7b (PSC-15, PSC-23; design-notes N5 and its U7 amendment,
# item 3): regenerate docker/sources.lock.json for one arch.
#
#   scripts/sources_lock.sh --arch amd64|arm64 --evidence-dir DIR [--refresh]
#
# DIR (an existing writable directory; relative to the repository root)
# receives each pgdg suite's InRelease the run was bound to, before the lock
# moves (U7d rework round 1, items 4 and 6).
#
# A maintainer tool with network, on a Linux or Git Bash host. Never run by
# scripts/verify.sh or CI, and not bundled. It:
#  1. refuses unless the six bundled images exist locally at the tags
#     scripts/build.sh gives them, and checks the 7 GiB floor (R6) on its
#     work dir (mktemp -d, removed on every exit path);
#  2. saves each image and runs the pinned `sbom` service (no network) for
#     its SPDX and syft-json documents;
#  3. runs `sbom_check.py lock-needs` in the gates image (no network,
#     read-only) for needs.json, with every saved tar (U7c A1);
#  4. runs the `sources-resolve` service (docker-compose.sources.yml), which
#     writes lock.new.json into the work dir only;
#  5. runs `sbom_check.py lock-check` on it and, on success, writes a temp
#     file in docker/, moves it over docker/sources.lock.json and prints
#     `git diff --stat`.
# Exit 0: written. 1: a failure, the lock unchanged. 2: a bad argument.
# 3: written, with manual neo4j entries pending (security's second fetch).
# The run's SBOMs are copied to <evidence-dir>/sboms/ on both the 0 and the 3
# path (U8-12); an existing sboms entry in the evidence dir is refused.
set -euo pipefail

fail() { echo "sources_lock: FAIL ($1; the lock is unchanged)" >&2; exit 1; }
# U7b rework round 1, item 4: the tools first.
for tool in jq git docker; do
  command -v "$tool" > /dev/null 2>&1 || fail "tools: $tool not on PATH"
done
cd -- "$(dirname -- "$0")/.."
usage() { echo "usage: scripts/sources_lock.sh --arch amd64|arm64 --evidence-dir DIR [--refresh]" >&2; exit 2; }

arch=""
evdir=""
refresh=()
while [ $# -gt 0 ]; do
  case "$1" in
    --arch) [ $# -ge 2 ] || usage; arch="$2"; shift 2 ;;
    --evidence-dir) [ $# -ge 2 ] || usage; evdir="$2"; shift 2 ;;
    --refresh) refresh=(--refresh); shift ;;
    *) usage ;;
  esac
done
case "$arch" in amd64|arm64) ;; *) usage ;; esac
[ -n "$evdir" ] || usage
if [ ! -d "$evdir" ] || [ ! -w "$evdir" ]; then fail "evidence: $evdir is not a writable directory"; fi
evdir="$(cd -- "$evdir" && pwd)"

hostpath() { if command -v cygpath > /dev/null 2>&1; then cygpath -m -- "$1"; else printf "%s" "$1"; fi; }
export MSYS_NO_PATHCONV=1
unset COMPOSE_PROFILES COMPOSE_FILE

# --- 1. the six images, at build.sh's tags ------------------------------------
compose=(docker compose -f docker-compose.yml --env-file .env.example)
services_out="$("${compose[@]}" config --services)" || fail "images: docker compose config --services failed"
model="$("${compose[@]}" config --format json)" || fail "images: docker compose config --format json failed"
ref_re='^[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?(@sha256:[0-9a-f]{64})?$'
refs=()
names=()
while IFS= read -r svc; do
  [ -n "$svc" ] || continue
  ref="$(printf '%s' "$model" | jq -er --arg s "$svc" '.services[$s].image')" \
    || fail "images: service $svc has no image"
  [[ "$ref" =~ $ref_re ]] || fail "images: service $svc: image reference fails its pattern"
  base="${ref%%@*}"
  repo="${base%:*}"
  if [[ "${base##*/}" != *:* ]]; then repo="$base"; fi
  name="${repo##*/}"
  case " ${names[*]-} " in *" $name "*) continue ;; esac
  refs+=("$ref")
  names+=("$name")
done < <(printf '%s\n' "$services_out" | sort)
[ "${#refs[@]}" -gt 0 ] || fail "images: compose config lists no images"
# Round 1, item 6: exactly the six bundled images (the list bundle.sh saves).
six=(ke-app ke-gateway ke-neo4j phoenix postgres valkey)
for name in "${names[@]}"; do
  case " ${six[*]} " in *" $name "*) ;; *) fail "images: $name is not one of the six bundled images" ;; esac
done
for name in "${six[@]}"; do
  case " ${names[*]} " in *" $name "*) ;; *) fail "images: $name is missing from the stack" ;; esac
done
for ref in "${refs[@]}"; do
  docker image inspect --format '{{.Os}}/{{.Architecture}}' "$ref" > /dev/null 2>&1 \
    || fail "images: $ref not found: run scripts/build.sh first"
done

work="$(mktemp -d "${TMPDIR:-/tmp}/ke-sources.XXXXXXXX")" || fail "images: cannot create a work dir"
project="ke-sources-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
tmp=""
# shellcheck disable=SC2317  # runs from the EXIT trap
cleanup() {
  KE_SOURCES_IN=/nonexistent KE_SOURCES_OUT=/nonexistent KE_SOURCES_USER=0:0 \
    docker compose -p "$project" --env-file .env.example -f docker-compose.sources.yml down --volumes \
    > /dev/null 2>&1 || true
  rm -rf -- "$work"
  if [ -n "$tmp" ]; then rm -f -- "$tmp"; fi  # round 1, item 5
}
trap cleanup EXIT
avail="$(df -Pk -- "$work" | awk 'NR == 2 { print $4 }')"
[[ "$avail" =~ ^[0-9]+$ ]] || fail "images: cannot read the free space of $work"
[ "$avail" -ge 7340032 ] || fail "images: $work has ${avail} KiB free, below the 7 GiB floor (R6)"
mkdir -- "$work/tars" "$work/sboms" "$work/sboms/tmp" "$work/in" "$work/out"
chmod 0700 -- "$work/tars" "$work/sboms" "$work/sboms/tmp" "$work/in" "$work/out"
user="$(id -u):$(id -g)"

# --- 2. save, then the pinned SBOM generator (no network) ---------------------
for i in "${!refs[@]}"; do
  ref="${refs[$i]}"
  name="${names[$i]}"
  docker save -o "$(hostpath "$work/tars/$name.tar")" "$ref" || fail "sbom: $name: docker save failed"
  KE_SBOM_IN="$(hostpath "$work/tars")" KE_SBOM_OUT="$(hostpath "$work/sboms")" KE_SBOM_USER="$user" \
    docker compose -p "$project-sbom" --env-file .env.example -f docker-compose.sbom.yml \
    run --rm --pull never sbom "docker-archive:/in/$name.tar" --scope all-layers \
    -o "spdx-json=/out/$name.spdx.json" -o "syft-json=/out/$name.syft.json" \
    || fail "sbom: $name: the SBOM generator failed"
done

gates=(docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never
       --user "$user"
       -v "$(hostpath "$PWD")/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro"
       -v "$(hostpath "$PWD")/docker/source-policy.json:/opt/ke/source-policy.json:ro"
       -v "$(hostpath "$work/sboms"):/sboms:ro" -v "$(hostpath "$work/out"):/out:ro"
       --entrypoint python3 "ke-gates:${KE_IMAGE_TAG:-local}" -I /opt/ke/sbom_check.py)
sbom_args=()
tar_args=()
for name in "${names[@]}"; do
  sbom_args+=(--sbom "$name=/sboms/$name.spdx.json")
  tar_args+=(--tar "$name=/tars/$name.tar")  # U7c A1: every image (Temurin release, apk installed db)
done

# --- 3. what the images need ---------------------------------------------------
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never \
  --user "$user" \
  -v "$(hostpath "$PWD")/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro" \
  -v "$(hostpath "$PWD")/docker/source-policy.json:/opt/ke/source-policy.json:ro" \
  -v "$(hostpath "$work/sboms"):/sboms:ro" -v "$(hostpath "$work/tars"):/tars:ro" \
  --entrypoint python3 "ke-gates:${KE_IMAGE_TAG:-local}" -I /opt/ke/sbom_check.py lock-needs \
  --policy /opt/ke/source-policy.json "${sbom_args[@]}" "${tar_args[@]}" \
  > "$work/in/needs.json" || fail "needs: sbom_check.py lock-needs failed"
if [ -f docker/sources.lock.json ]; then
  cp -- docker/sources.lock.json "$work/in/sources.lock.json"
else
  printf '{\n "components": {},\n "format": 1\n}\n' > "$work/in/sources.lock.json"
fi

# --- 4. resolve (the network step) --------------------------------------------
rc=0
KE_SOURCES_IN="$(hostpath "$work/in")" KE_SOURCES_OUT="$(hostpath "$work/out")" KE_SOURCES_USER="$user" \
  docker compose -p "$project" --env-file .env.example -f docker-compose.sources.yml \
  run --rm --pull never sources-resolve --arch "$arch" "${refresh[@]}" || rc=$?
case "$rc" in
  0|3) ;;
  *) fail "resolve: scripts/sources_resolve.py exited $rc" ;;
esac
[ -f "$work/out/lock.new.json" ] || fail "resolve: no lock.new.json was written"

# --- 5. check, then write --------------------------------------------------------
check_rc=0
"${gates[@]}" lock-check --lock /out/lock.new.json --policy /opt/ke/source-policy.json --arch "$arch" \
  "${sbom_args[@]}" --pending-neo4j > "$work/check.out" 2> "$work/check.err" || check_rc=$?
# Round 1, item 2: the decision is lock-check's exit code alone (3: only
# neo4j keys missing, security's second fetch pending).
pending=0
case "$check_rc" in
  0) ;;
  3) pending=1 ;;
  *) cat -- "$work/check.err" >&2; fail "check: sbom_check.py lock-check found problems" ;;
esac
# U8-12 (design-notes N4 amendment U8 item 9): the run's SPDX documents (the files
# lock-needs and lock-check read) are kept in <evidence-dir>/sboms/, before the
# InRelease copies and the lock move. An existing sboms entry, a link or anything
# but a regular file, or a failed copy fails, with the lock unchanged.
# mkdir without -p fails on any existing entry, a link included.
mkdir -- "$evdir/sboms" 2> /dev/null || fail "evidence: $evdir/sboms exists"
for name in "${names[@]}"; do
  f="$work/sboms/$name.spdx.json"
  if [ -L "$f" ]; then fail "evidence: $f is a link"; fi
  if [ ! -f "$f" ]; then fail "evidence: $f is not a regular file"; fi
  cp -P -- "$f" "$evdir/sboms/" || fail "evidence: copy of $f failed"
done
# U7d rework round 1, items 4 and 6 (security R-1, L-1): each pgdg suite's InRelease the
# run was bound to goes to --evidence-dir before the lock moves; a link or anything but a
# regular file fails, and a failed copy fails, with the lock unchanged.
shopt -s nullglob
inreleases=("$work/out"/pgdg-*.InRelease)
shopt -u nullglob
for f in "${inreleases[@]}"; do
  if [ -L "$f" ]; then fail "evidence: $f is a link"; fi
  if [ ! -f "$f" ]; then fail "evidence: $f is not a regular file"; fi
  cp -P -- "$f" "$evdir/" || fail "evidence: copy of $f failed"
done
tmp="$(mktemp docker/.sources.lock.json.XXXXXXXX)" || fail "check: cannot create a temp file in docker/"
cp -- "$work/out/lock.new.json" "$tmp" || fail "check: cannot write $tmp"
chmod 0644 -- "$tmp" || fail "check: cannot chmod $tmp"  # round 1, item 9
# A failed move exits 1 (set -e); the EXIT trap removes the temp file.
mv -f -- "$tmp" docker/sources.lock.json
tmp=""
git diff --stat -- docker/sources.lock.json
if [ "$pending" -eq 1 ] || [ "$rc" -eq 3 ]; then
  echo "sources_lock: written; neo4j entries pending: security's second fetch, then the entry by hand" >&2
  exit 3
fi
exit 0
