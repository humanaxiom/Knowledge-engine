#!/usr/bin/env bash
# One-process unit stage, as test.sh did at 0b874c2 (plus --durations 30 for per-test data).
set -euo pipefail
cd /work
uv run --locked python -m coverage erase
shopt -s nullglob; mods=(); for f in tests/test*.py; do m="${f%.py}"; mods+=("${m//\//.}"); done
s=$SECONDS
uv run --locked python -m coverage run -p -m unittest -v --durations 30 "${mods[@]}" 2>&1 || echo "onep rc=$?"
echo "onep unit wall=$((SECONDS - s))s"
