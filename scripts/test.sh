#!/usr/bin/env bash
# Test entrypoint, called only by scripts/verify.sh.
#   fast: unit tests.  full: unit + integration (tests/integration, once it
#   exists; real stores via testcontainers arrive with platform-skeleton).
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-full}"
uv run --locked python -m unittest discover -s tests -t . -v
if [ "$mode" = "full" ] && [ -d tests/integration ]; then
  uv run --locked python -m unittest discover -s tests/integration -t . -v
fi
