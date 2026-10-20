#!/usr/bin/env bash
# Installs an offline bundle (PS-3.1, architecture §2.5 Install):
#
#   bash install.sh [--expect-manifest <sha256>] <target>
#
# Runs from the bundle root, on its own directory. Everything in the bundle
# is untrusted until the manifest passes, and bundle.json stays untrusted
# after it: every value is matched against a fixed pattern, nothing is
# evaluated, and every expansion is quoted. Until the manifest check passes
# no `docker` command runs.
#
# Order: PATH check -> arguments -> claim the target (exclusive mkdir 0700 and a
# random marker file) -> private staging copy (0700, in the target's parent;
# the script moves into it and uses relative paths only) -> manifest (on
# staging) -> daemon -> bundle.json -> services -> per image (load, tag as
# `as`, inspect `as`) -> override -> publish into the claim, chmod 0755 last.
# Only the staged bytes are verified, loaded and published, so a change to
# the bundle directory after the copy (a hardlink partner, a swapped file), or
# a rename of the staging directory, cannot reach them. Staging is removed on
# every exit, and so is the claim unless it was published. Image ids are
# never compared (they differ by image store); nothing is removed or
# untagged; `:local` is never touched.
#
# The whole body is a function called on the last line and followed by `exit`,
# so bash has parsed all of it before it runs anything: a change made to this
# file while it runs is never read (security M-4).
#
# Integrity, not authenticity: this script ships inside the bundle it checks.
# Compare the manifest hash it prints with your release record (the
# `<out>.manifest.sha256` file bundle.sh wrote) or pass --expect-manifest.
set -euo pipefail
# A CDPATH from the caller would make every relative `cd` below print the
# directory it found (corrupting `$(cd ... && pwd -P)`) or pick another tree.
unset CDPATH
export LC_ALL=C

nl='
'

die() { echo "install: $*" >&2; exit 1; }

# Security L-9: a relative or empty PATH entry makes the shell search the
# current directory (the bundle root), so a tool shipped in the bundle would
# run before the manifest check. Builtins only, so nothing is searched here.
check_path() {
  local rest entry
  rest="${PATH-}:"
  while [ -n "$rest" ]; do
    entry="${rest%%:*}"
    rest="${rest#*:}"
    case "$entry" in
      /*) ;;
      *) die "PATH has a relative or empty entry ('$entry'); set PATH to absolute directories only" ;;
    esac
  done
}
check_path

# State the EXIT trap needs; set before anything can fail.
staging=""
target=""
claimed=0
claim_marker=""
restore_empty=0
published=0
pinned=0

# The one SHA-256 helper: `<hex>  <file>` from sha256sum, else shasum -a 256.
sha256_file() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum -- "$1"
  else
    shasum -a 256 -- "$1"
  fi
}

# in_list <needle> <newline-separated list>: exact, literal match.
in_list() {
  case "$nl$2$nl" in
    *"$nl$1$nl"*) return 0 ;;
  esac
  return 1
}

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
usage() { echo "usage: bash install.sh [--expect-manifest <sha256>] <target>" >&2; exit 2; }

# shellcheck disable=SC2317  # runs from the EXIT trap
cleanup() {
  # Security I-7: once pinned, the working directory is the staging directory
  # itself even if it was renamed away; empty it from inside before leaving.
  if [ "$pinned" -eq 1 ]; then
    rm -rf -- ./* ./.[!.]* ./..?* 2> /dev/null || true
  fi
  cd / || true
  # The claim is removed only while it is still ours: a real directory (not a
  # link) that still holds the marker. Whatever else sits there is not ours.
  if [ "$claimed" -eq 1 ] && [ "$published" -eq 0 ] && [ -n "$claim_marker" ] \
    && [ ! -L "$target" ] && [ -d "$target" ] && [ -f "$target/$claim_marker" ]; then
    rm -rf -- "$target" || true
    if [ "$restore_empty" -eq 1 ]; then mkdir -- "$target" || true; fi
  fi
  # Security M-7: the pinned staging was emptied from inside above; its name is
  # removed with rmdir only, so a directory swapped in under the name (and so
  # not empty) is left alone, never deleted recursively.
  if [ -n "$staging" ]; then
    case "$staging" in
      */.ke-install.*) rmdir -- "$staging" 2> /dev/null || true ;;
    esac
  fi
}

# Refuses the first entry under $1 that is neither a regular file nor a
# directory; names the rule and the bundle-relative path.
refuse_odd() {
  local all entry rel
  all="$(find "$1" ! -type f ! -type d -print)" || die "cannot scan $1"
  if [ -z "$all" ]; then return 0; fi
  entry="${all%%"$nl"*}"
  rel="${entry#"$1"/}"
  if [ -L "$entry" ]; then
    die "refused (rule: a symlink or link is not allowed): $(printf '%q' "$rel")"
  elif [ -p "$entry" ]; then
    die "refused (rule: a fifo / named pipe is not allowed): $(printf '%q' "$rel")"
  fi
  die "refused (rule: only regular files and directories are allowed; this is a device or socket): $(printf '%q' "$rel")"
}

# Refuses two entries under $1 whose names are equal ignoring case (a
# case-insensitive volume such as macOS APFS would merge them; review P2).
refuse_case_clash() {
  local clash first second
  clash="$(cd -- "$1" && find . -mindepth 1 -print | awk '
    { l = tolower($0) }
    l in seen { if (a == "") { a = seen[l]; b = $0 } next }
    { seen[l] = $0 }
    END { if (a != "") { print a; print b } }')" || die "cannot scan $1"
  if [ -z "$clash" ]; then return 0; fi
  first="${clash%%"$nl"*}"
  second="${clash#*"$nl"}"
  die "refused (rule: paths differ only by case): $(printf '%q' "${first#./}") and $(printf '%q' "${second#./}")"
}

# Free KiB on the filesystem of $1, read from `df -Pk` by shape: the
# Available column is the number before the "NN%" capacity field, so a
# filesystem or mount name with spaces cannot shift it.
free_kb() {
  local text
  text="$(df -Pk -- "$1")" || return 1
  printf '%s\n' "$text" | awk '
    NR > 1 && v == "" {
      for (i = 4; i <= NF; i++) {
        if ($i ~ /^[0-9]+%$/ && $(i-1) ~ /^[0-9]+$/ && $(i-2) ~ /^[0-9]+$/ && $(i-3) ~ /^[0-9]+$/) { v = $(i-1); break }
      }
    }
    END { print v }'
}

# is_listed <path>: whether MANIFEST.sha256 lists exactly this path.
is_listed() {
  KE_PATH="$1" awk 'substr($0, 67) == ENVIRON["KE_PATH"] { f = 1 } END { exit !f }' MANIFEST.sha256
}

# refuse_unsafe_parent <dir>: security H-1 fix 3, hardened by the round-4
# ruling. Whoever can write the parent can replace the target (or race the
# staging name) during and after the install, so the parent must be writable
# by nobody but its owner (a sticky world-writable parent such as /tmp is
# refused too: the sticky bit is no exemption) and owned by the operator or root. Any failure reading the owner,
# the mode or the operator's uid refuses (fail closed).
refuse_unsafe_parent() {
  local listing modes group other owner me acl
  listing="$(ls -ldn -- "$1")" || die "cannot check the target's parent $1 (reading its owner and mode failed); use a directory only you can write"
  modes="${listing%% *}"
  owner="$(printf '%s
' "$listing" | awk '{ print $3 }')"
  case "$owner" in
    '' | *[!0-9]*) die "cannot check the target's parent $1 (its owner could not be read); use a directory only you can write" ;;
  esac
  case "$modes" in
    d?????????*) ;;
    *) die "cannot check the target's parent $1 (its mode could not be read); use a directory only you can write" ;;
  esac
  me="$(id -u)" || me=""
  case "$me" in
    '' | *[!0-9]*) die "cannot check the target's parent $1 (the operator's uid could not be read with id -u)" ;;
  esac
  if [ "$owner" != "$me" ] && [ "$owner" != 0 ]; then
    die "refused (rule: the target's parent must be owned by you or root): $1 is owned by another user (uid ${owner}); its owner can replace the installed target; use a directory you own"
  fi
  group="${modes:5:1}"
  other="${modes:8:1}"
  # Architecture section 2.5: the sticky bit is no exemption (a 1777 parent lets
  # anyone create entries in it), so only the operator may hold w.
  if [ "$group" = w ] || [ "$other" = w ]; then
    die "refused (rule: the target's parent must be writable only by you or root): $1 is writable by others (group or world, mode ${modes}); anyone who can write it can replace the installed target; use a directory only you can write"
  fi
  # macOS: an extended ACL is invisible in the mode; any `allow` entry refuses.
  if [ "$(uname -s)" = Darwin ]; then
    acl="$(ls -lde -- "$1")" || die "cannot check the target's parent $1 (reading its ACL failed); use a directory only you can write"
    case "$acl" in
      *"$nl"*" allow "*) die "refused (rule: the target's parent must not be writable by others): $1 has an access-control entry that allows another principal; use a directory only you can write" ;;
    esac
  fi
}

# publish_into_claim: the target must still be the directory this run claimed
# (a real directory holding exactly the marker). Each top-level entry of the
# staged app/ is renamed into it, the marker is removed and 0755 is set last.
publish_into_claim() {
  local held entry expected
  expected="$(cd -- "$(dirname -- "$target")" && pwd -P)/${target##*/}" || die "cannot resolve the target: $target"
  if [ -L "$target" ] || [ ! -d "$target" ] || [ ! -f "$target/$claim_marker" ]; then
    die "the target is no longer the directory this install claimed (something replaced it during install): $target"
  fi
  held="$(ls -A -- "$target")" || die "cannot read the target: $target"
  if [ "$held" != "$claim_marker" ]; then
    die "the claimed target holds something besides the install's marker: $target"
  fi
  for entry in app/* app/.[!.]* app/..?*; do
    if [ ! -e "$entry" ] && [ ! -L "$entry" ]; then continue; fi
    mv -- "$entry" "$target/" || die "cannot publish to the target: $target"
  done
  # Security I-7: staging may have been renamed away; the working directory is
  # still it, so empty it from inside (verified at the pin) before leaving.
  rm -rf -- ./* ./.[!.]* ./..?* 2> /dev/null || true
  # Security M-5: work on the directory itself, not on its name. Leave the
  # staging pin (cleanup must not empty the target), step into the target,
  # and require this run's marker and ownership before touching its mode.
  pinned=0
  cd -- "$target" || die "cannot enter the target (something replaced it during install): $target"
  { [ -f "./$claim_marker" ] && [ ! -L "./$claim_marker" ] && [ -O . ]; } \
    || die "the target is no longer the directory this install claimed (something replaced it during install): $target"
  rm -- "./$claim_marker" || die "the claim marker is gone (something replaced the target during install): $target"
  chmod 0755 . || die "cannot open up the published target: $target"
  # The name must still lead to the directory just published.
  { [ "$(cd -- "$target" 2> /dev/null && pwd -P)" = "$expected" ] && [ "$target" -ef . ]; } \
    || die "the target's name no longer leads to the directory this install published (something replaced it during install): $target"
  cd / || die "cannot leave the target"
  published=1
}

main() {
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  trap 'exit 131' QUIT

  # --- 1. arguments --------------------------------------------------------
  local expect="" have_expect=0 have_target=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --expect-manifest)
        [ "$#" -ge 2 ] || usage
        expect="$2"
        have_expect=1
        shift 2
        ;;
      -*) usage ;;
      *)
        [ "$have_target" -eq 0 ] || usage
        target="$1"
        have_target=1
        shift
        ;;
    esac
  done
  [ "$have_target" -eq 1 ] || usage
  if [ "$have_expect" -eq 1 ]; then
    [[ "$expect" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "install: --expect-manifest must be 64 hex characters" >&2; exit 2; }
    expect="$(lower "$expect")"
  fi
  [ -n "$target" ] || die "the target is empty"
  case "$target" in
    /*) ;;
    *) target="$(pwd -P)/$target" ;;
  esac
  while [ "${#target}" -gt 1 ] && [ "${target%/}" != "$target" ]; do target="${target%/}"; done
  [ "$target" != "/" ] || die "the target is the filesystem root"

  local root parent_raw parent
  root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

  parent_raw="$(dirname -- "$target")"
  if [ -L "$parent_raw" ]; then die "the target's parent is a link: $parent_raw"; fi
  [ -d "$parent_raw" ] || die "the target's parent is not a directory: $parent_raw"
  parent="$(cd -- "$parent_raw" && pwd -P)"
  case "$parent/" in
    "$root"/*) die "the target must be outside the bundle directory: $target" ;;
  esac
  refuse_unsafe_parent "$parent"

  if [ -L "$target" ]; then die "the target is a link: $target"; fi
  if [ -e "$target" ]; then
    [ -d "$target" ] || die "the target exists and is not a directory: $target"
    if [ -n "$(ls -A -- "$target")" ]; then
      die "the target is not empty: $target (install into a new directory)"
    fi
    rmdir -- "$target" || die "cannot replace the empty target: $target"
    restore_empty=1
  fi
  # Claim the target: mkdir is exclusive and does not follow a final symlink.
  # A random marker file inside it tells this run's claim from anything planted.
  if ! mkdir -m 0700 -- "$target"; then
    # Security L-13: Git Bash on NTFS creates the directory, then fails to set
    # its mode; leave no empty target behind (put back an empty one we removed).
    rmdir -- "$target" 2> /dev/null || true
    if [ "$restore_empty" -eq 1 ]; then mkdir -- "$target" 2> /dev/null || true; fi
    die "cannot claim the target (mkdir failed; the directory may have appeared during install, or its parent is not writable): $target"
  fi
  claimed=1
  local claim_file
  claim_file="$(mktemp "$target/.ke-claim.XXXXXXXX")" || { rmdir -- "$target" || true; die "cannot create the claim marker in $target"; }
  claim_marker="${claim_file##*/}"

  # --- 2. staging ----------------------------------------------------------
  staging="$(mktemp -d "$parent/.ke-install.XXXXXXXX")" || die "cannot create a staging directory in $parent"
  # Pin staging: the working directory follows the directory itself, not its
  # name, so renaming staging away and planting a lookalike under its name
  # (security H-1) changes nothing below, where only relative paths are used.
  # Security H-2: no chmod by name (mktemp -d creates 0700, and a chmod
  # through a swapped-in link would change someone else's directory). Pin only
  # after the directory we are in is the one created: its real path is the
  # staging path, it is empty, ours, and drwx------. Until then cleanup
  # empties nothing.
  cd -- "$staging" || die "cannot enter the staging directory: $staging"
  local stmode
  stmode="$(ls -ld -- .)" || die "cannot inspect the staging directory"
  stmode="${stmode%% *}"
  if [ "$(pwd -P)" != "$staging" ]; then
    die "the staging directory is not the one this install created (its name leads elsewhere): $staging"
  fi
  if [ -n "$(ls -A)" ]; then
    die "the staging directory is not empty (something replaced it after creation): $staging"
  fi
  if [ ! -O . ] || [ "${stmode:0:10}" != "drwx------" ]; then
    die "the staging directory is not private (owner or mode is wrong): $staging"
  fi
  pinned=1

  refuse_odd "$root"
  refuse_case_clash "$root"

  local need_bytes need_kb need_gib avail_kb
  need_bytes="$(find "$root" -type f -exec wc -c {} \; | awk '{ s += $1 } END { printf "%.0f", s }')"
  need_kb=$(((need_bytes + 1023) / 1024))
  need_gib=$(((need_kb + 1048575) / 1048576))
  avail_kb="$(free_kb "$parent")" || avail_kb=""
  case "$avail_kb" in
    '' | *[!0-9]*) die "cannot read the free space on $parent" ;;
  esac
  if [ "$avail_kb" -lt "$need_kb" ]; then
    die "need $need_gib GiB free on $parent, found $((avail_kb / 1048576)) GiB"
  fi

  # One read of every byte, into the empty staging. Links are copied as links
  # (never followed) and refused by the scan that follows. No `cp -n` (GNU 9
  # warns, 9.2-9.4 exit 1 on a skip): a name collision was refused above, and
  # an overwrite on a case-insensitive volume fails the hash check below.
  cp -R -P -- "$root/." .
  refuse_odd .

  # --- 3. manifest (staged) ------------------------------------------------
  if [ ! -f MANIFEST.sha256 ] || [ -L MANIFEST.sha256 ]; then
    die "manifest: MANIFEST.sha256 is missing or not a regular file"
  fi
  local manifest_size sum manifest_sha
  manifest_size="$(wc -c < MANIFEST.sha256)"
  manifest_size="${manifest_size//[[:space:]]/}"
  if [ "$manifest_size" -gt 1048576 ]; then
    die "manifest: MANIFEST.sha256 is too large ($manifest_size bytes; the size cap is 1 MiB)"
  fi

  sum="$(sha256_file MANIFEST.sha256)"
  manifest_sha="${sum:0:64}"
  if [ -n "$expect" ] && [ "$expect" != "$manifest_sha" ]; then
    die "manifest: the manifest sha256 is $manifest_sha, not the value given to --expect-manifest ($expect)"
  fi

  local manifest_re='^([0-9a-f]{64})  (.+)$'
  # Parallel lists (bash 3.2 has no associative arrays): the manifest's paths in
  # file order and their hashes. Duplicate and case-collision detection, and
  # the unlisted-file check, run in one awk pass each over MANIFEST.sha256 (a
  # path starts at column 67), so a manifest at the size cap stays linear.
  local listed_order=() listed_hash=() n=0 line hash path segment stem
  local segments=()
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    [[ "$line" =~ $manifest_re ]] \
      || die "manifest: line $n is malformed, not '<64 hex>  <path>': $(printf '%q' "$line")"
    hash="${BASH_REMATCH[1]}"
    path="${BASH_REMATCH[2]}"
    if [[ "$path" == /* ]]; then
      die "manifest: line $n: path is absolute (leading '/'): $(printf '%q' "$path")"
    fi
    if [[ "$path" == *\\* ]]; then
      die "manifest: line $n: path has a backslash: $(printf '%q' "$path")"
    fi
    if [[ "$path" =~ [^A-Za-z0-9._/-] ]]; then
      die "manifest: line $n: path has a character outside [A-Za-z0-9._/-]: $(printf '%q' "$path")"
    fi
    if [[ "$path" == */ || "$path" == *//* ]]; then
      die "manifest: line $n: path has an empty segment: $(printf '%q' "$path")"
    fi
    IFS=/ read -r -a segments <<< "$path"
    for segment in "${segments[@]}"; do
      if [ "$segment" = "." ] || [ "$segment" = ".." ]; then
        die "manifest: line $n: path has a '.' or '..' segment: $(printf '%q' "$path")"
      fi
      if [[ "$segment" == *. ]]; then
        die "manifest: line $n: path has a segment with a trailing dot: $(printf '%q' "$path")"
      fi
      stem="${segment%%.*}"
      case "$stem" in
        [Cc][Oo][Nn] | [Pp][Rr][Nn] | [Aa][Uu][Xx] | [Nn][Uu][Ll] | [Cc][Oo][Mm][1-9] | [Ll][Pp][Tt][1-9])
          die "manifest: line $n: path has a Windows reserved name: $(printf '%q' "$path")"
          ;;
      esac
    done
    listed_order+=("$path")
    listed_hash+=("$hash")
  done < MANIFEST.sha256

  # Every path is now of the safe set, so a space separates a collision's pair.
  local clash pair
  clash="$(awk '
    { p = substr($0, 67); l = tolower(p) }
    p in seen { print "dup " p; exit }
    l in low { print "case " low[l] " " p; exit }
    { seen[p] = 1; low[l] = p }' MANIFEST.sha256)" || die "manifest: cannot scan MANIFEST.sha256"
  case "$clash" in
    "dup "*) die "manifest: duplicate path: ${clash#dup }" ;;
    "case "*)
      pair="${clash#case }"
      die "manifest: paths differ only by case: ${pair%% *} and ${pair#* }"
      ;;
  esac

  # Every file present must be listed (nothing but MANIFEST.sha256 may be
  # extra). A file name with a newline is never listed; it is found NUL-safely
  # first so the line-based pass below cannot be fooled by its fragments.
  find . -type f -print0 | {
    while IFS= read -r -d '' f; do
      case "$f" in
        *"$nl"*) die "manifest: file is not listed: $(printf '%q' "${f#./}")" ;;
      esac
    done
  } || exit 1
  local unlisted
  unlisted="$(find . -type f -print | awk '
    FILENAME == ARGV[1] { listed[substr($0, 67)] = 1; next }
    { p = substr($0, 3) }
    p == "MANIFEST.sha256" || p in listed { next }
    first == "" { first = p }
    END { print first }' MANIFEST.sha256 -)" || die "manifest: cannot scan the staged files"
  if [ -n "$unlisted" ]; then
    die "manifest: file is not listed: $(printf '%q' "$unlisted")"
  fi

  local count idx
  count=${#listed_order[@]}
  idx=0
  while [ "$idx" -lt "$count" ]; do
    path="${listed_order[$idx]}"
    if [ ! -f "$path" ] || [ -L "$path" ]; then
      die "manifest: listed file is missing: $path"
    fi
    sum="$(sha256_file "$path")"
    if [ "${sum:0:64}" != "${listed_hash[$idx]}" ]; then
      die "manifest: hash mismatch: $path"
    fi
    idx=$((idx + 1))
  done

  if [ -n "$expect" ]; then
    echo "manifest sha256: $manifest_sha (matches --expect-manifest)"
  else
    echo "manifest sha256: $manifest_sha (not checked: compare it with the value from your release record)"
  fi

  # --- 4. daemon -----------------------------------------------------------
  local daemon_arch_raw daemon_arch
  daemon_arch_raw="$(docker info --format '{{.Architecture}}')" || die "the Docker daemon does not answer (docker info failed)"
  case "$daemon_arch_raw" in
    x86_64 | amd64) daemon_arch=amd64 ;;
    aarch64 | arm64) daemon_arch=arm64 ;;
    *) die "the Docker daemon reports an unsupported architecture: $(printf '%q' "$daemon_arch_raw") (supported: amd64, arm64)" ;;
  esac

  # --- 5. bundle.json (staged) ---------------------------------------------
  local ref_re as_re header_re entry_re
  ref_re='[a-z0-9._/-]+(:[A-Za-z0-9._-]+)?(@sha256:[0-9a-f]{64})?'
  as_re='(ke-[a-z0-9._-]+:bundle-[0-9a-f]{12}|ke-vendor/[a-z0-9._-]+:[0-9a-f]{12})'
  header_re='^\{"format": 1, "git_sha": "([0-9a-f]{40})", "dirty": (true|false), "created": "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", "arch": "(amd64|arm64)", "images": \[$'
  entry_re='^\{"file": "(images/[A-Za-z0-9._-]+\.tar)", "ref": "('"$ref_re"')", "as": "('"$as_re"')", "services": "([a-z0-9_-]+( [a-z0-9_-]+)*)"\}(,?)$'
  # BASH_REMATCH groups: 1 file, 2 ref (3-4 inner), 5 as (6 inner), 7 services (8 inner), 9 comma.
  local files=() refs=() ases=() svcs=() commas=() git_sha="" state bundle_arch
  [ -f bundle.json ] || die "bundle.json is missing"
  n=0
  state=header
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    case "$state" in
      header)
        [[ "$line" =~ $header_re ]] || die "bundle.json: line $n does not match the header pattern"
        git_sha="${BASH_REMATCH[1]}"
        bundle_arch="${BASH_REMATCH[3]}"
        if [ "$bundle_arch" != "$daemon_arch" ]; then
          die "arch mismatch: this bundle is $bundle_arch but the Docker daemon is $daemon_arch (reported as $daemon_arch_raw); use the $daemon_arch bundle"
        fi
        state=images
        ;;
      images)
        if [ "$line" = "]}" ]; then
          state=closed
          continue
        fi
        [[ "$line" =~ $entry_re ]] \
          || die "bundle.json: line $n does not match the image entry pattern (file, ref, as, services)"
        files+=("${BASH_REMATCH[1]}")
        refs+=("${BASH_REMATCH[2]}")
        ases+=("${BASH_REMATCH[5]}")
        svcs+=("${BASH_REMATCH[7]}")
        commas+=("${BASH_REMATCH[9]}")
        ;;
      *) die "bundle.json: line $n follows the closing line" ;;
    esac
  done < bundle.json
  [ "$state" = closed ] || die "bundle.json: the closing line ]} is missing"
  [ "${#files[@]}" -gt 0 ] || die "bundle.json: no images"

  local first_party_re='^ke-[a-z0-9._-]+:bundle-([0-9a-f]{12})$'
  local entry_file_nl="" entry_as_nl="" svc_nl="" svc_list=() i last s names=()
  for i in "${!files[@]}"; do
    last=$((${#files[@]} - 1))
    if [ "$i" -lt "$last" ] && [ -z "${commas[$i]}" ]; then
      die "bundle.json: image entry $((i + 1)) lacks its trailing comma"
    fi
    if [ "$i" -eq "$last" ] && [ -n "${commas[$i]}" ]; then
      die "bundle.json: the last image entry has a trailing comma"
    fi
    if in_list "${files[$i]}" "$entry_file_nl"; then die "bundle.json: duplicate file ${files[$i]}"; fi
    if in_list "${ases[$i]}" "$entry_as_nl"; then die "bundle.json: duplicate as ${ases[$i]}"; fi
    entry_file_nl="$entry_file_nl$nl${files[$i]}"
    entry_as_nl="$entry_as_nl$nl${ases[$i]}"
    if [[ "${ases[$i]}" =~ $first_party_re ]] && [ "${BASH_REMATCH[1]}" != "${git_sha:0:12}" ]; then
      die "bundle.json: first-party as ${ases[$i]} does not carry the header git_sha (${git_sha:0:12})"
    fi
    is_listed "${files[$i]}" || die "bundle.json: ${files[$i]##*/} is not in the bundle"
    read -r -a names <<< "${svcs[$i]}"
    for s in "${names[@]}"; do
      if in_list "$s" "$svc_nl"; then die "bundle.json: service $s is in more than one entry"; fi
      svc_nl="$svc_nl$nl$s"
      svc_list+=("$s")
    done
  done
  for path in ${listed_order[@]+"${listed_order[@]}"}; do
    case "$path" in
      images/*)
        if ! in_list "$path" "$entry_file_nl"; then
          die "bundle.json does not list ${path##*/} (every image tar must be listed)"
        fi
        ;;
    esac
  done

  # --- 6. services: every stack service has exactly one entry --------------
  [ -f app/docker-compose.yml ] || die "app/docker-compose.yml is missing"
  [ -f app/.env.example ] || die "app/.env.example is missing"
  unset COMPOSE_PROFILES COMPOSE_FILE
  local config_out stack_services=() stack_nl=""
  config_out="$(docker compose --project-directory app -f app/docker-compose.yml \
    --env-file app/.env.example config --services)" \
    || die "docker compose config --services failed"
  [ -n "$config_out" ] || die "docker compose config lists no services"
  while IFS= read -r s; do
    [[ "$s" =~ ^[a-z0-9_-]+$ ]] || die "docker compose config printed a service name that fails its pattern"
    stack_services+=("$s")
  done <<< "$config_out"
  for s in "${stack_services[@]}"; do
    if ! in_list "$s" "$svc_nl"; then
      die "stack service $s has no bundle.json entry"
    fi
    stack_nl="$stack_nl$nl$s"
  done
  for s in "${svc_list[@]}"; do
    if ! in_list "$s" "$stack_nl"; then
      die "bundle.json names service $s, which the stack does not have"
    fi
  done

  # --- 7. load (from staging), tag as `as`, inspect `as` -------------------
  local loaded_name_re='^Loaded image: (.+)$'
  local loaded_id_re='^Loaded image ID: (sha256:[0-9a-f]{64})$'
  local file as output found=() named l
  for i in "${!files[@]}"; do
    file="${files[$i]}"
    as="${ases[$i]}"
    output="$(docker load -i "$file")" || die "docker load failed for ${file##*/}"
    found=()
    named=0
    while IFS= read -r l; do
      if [[ "$l" =~ $loaded_name_re ]]; then
        found+=("${BASH_REMATCH[1]}")
        named=1
      elif [[ "$l" =~ $loaded_id_re ]]; then
        found+=("${BASH_REMATCH[1]}")
        named=0
      fi
    done <<< "$output"
    if [ "${#found[@]}" -ne 1 ]; then
      die "docker load of ${file##*/} printed ${#found[@]} 'Loaded image' lines; exactly one is required"
    fi
    case "${found[0]}" in
      -*) die "docker load of ${file##*/} named an image starting with '-'" ;;
    esac
    if [ "$named" -eq 1 ] && [ "${found[0]}" != "$as" ]; then
      die "docker load of ${file##*/} named an image other than its as ($as)"
    fi
    docker tag "${found[0]}" "$as" || die "docker tag failed for ${file##*/}"
    docker image inspect "$as" > /dev/null || die "image $as is not present after loading ${file##*/}"
    echo "loaded ${file##*/} as $as"
  done

  # --- 8. compose override (staged app/) -----------------------------------
  local override=app/docker-compose.override.yml
  {
    printf 'services:\n'
    for i in "${!files[@]}"; do
      read -r -a names <<< "${svcs[$i]}"
      for s in "${names[@]}"; do
        printf '  %s:\n    image: "%s"\n    pull_policy: never\n' "$s" "${ases[$i]}"
      done
    done
  } > "$override" || die "cannot write the compose override"
  chmod 0644 -- "$override"

  # F6: the published modes come from this installer, not from the build host
  # or the umask. Relative paths inside the pinned staging only; -type f and
  # -type d never match a link, so nothing is followed. Directories and
  # everything under scripts/ are 0755, every other file 0644.
  find app -type d -exec chmod 0755 {} + || die "cannot set the staged directory modes"
  find app -type f -exec chmod 0644 {} + || die "cannot set the staged file modes"
  if [ -d app/scripts ]; then
    find app/scripts -type f -exec chmod 0755 {} + || die "cannot set the staged script modes"
  fi

  # --- 9. publish into the claim -------------------------------------------
  publish_into_claim

  echo "manifest sha256: $manifest_sha"
  echo "installed to $target"
  printf 'next: cd %q && cp .env.example .env && chmod 600 .env (set real secrets in it), then bash scripts/launch.sh\n' "$target"
}

main "$@"; exit
