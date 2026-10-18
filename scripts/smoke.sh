#!/usr/bin/env bash
# Smoke test entrypoint: exports real OTLP traces to a stub collector and
# checks they arrive, proving the Phoenix export path works end-to-end.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run --locked python scripts/smoke_otlp.py
