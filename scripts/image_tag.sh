#!/usr/bin/env bash
# Prints the per-worktree image tag, `wt-<12 hex>` (architecture §2.1): the
# first 12 hex digits of the SHA-256 of this checkout's physical path
# (`pwd -P`, no trailing newline). Called by scripts/verify.sh only, from the
# checkout root, so two worktrees never move each other's first-party image
# tags. It reads no environment variable and is not shipped in the bundle.
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."
real="$(pwd -P)"
if command -v sha256sum > /dev/null 2>&1; then
  digest="$(printf '%s' "$real" | sha256sum)"
else
  digest="$(printf '%s' "$real" | shasum -a 256)"
fi
printf 'wt-%s\n' "${digest:0:12}"
