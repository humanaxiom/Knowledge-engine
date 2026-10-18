#!/usr/bin/env bash
# Test entrypoint for CI and the tester agent.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run --locked python -m unittest discover -s tests -t . -v
