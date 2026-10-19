#!/usr/bin/env bash
# Test entrypoint, called only by scripts/verify.sh. Ends with the coverage and
# type-check gates.
#   fast: unit tests only.  full: unit tests, then the integration suite
#   (tests/integration) exactly once. Under `verify.sh full` that runs inside
#   the gates-it compose service, on the internal backend network against the
#   launched stack (PS-2.7, ADR-KE-009); nowhere else do those tests pass.
# Unit tests are discovered per directory so the integration package, which
# sits under tests/, is never picked up by the unit run.
# A package whose test*.py files define no tests fails closed (unittest exits
# 5 on an empty discovery), so a helper package must not be named test*.py.
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-full}"

# Stale data from an earlier run must not count towards this run.
uv run --locked python -m coverage erase

# Fail loudly before running anything: a test dir without __init__.py would
# otherwise be skipped silently. Applies at every depth.
while IFS= read -r d; do
  if [ ! -f "$d/__init__.py" ]; then
    echo "error: $d contains test*.py but has no __init__.py; its tests would be skipped" >&2
    exit 1
  fi
done < <(find tests -name __pycache__ -prune -o -name 'test*.py' -print | sed 's|/[^/]*$||' | sort -u)

# Top-level test modules (unittest's default pattern, test*.py).
shopt -s nullglob
mods=()
for f in tests/test*.py; do
  m="${f%.py}"
  mods+=("${m//\//.}")
done
shopt -u nullglob
if [ "${#mods[@]}" -eq 0 ]; then
  echo "error: no top-level unit tests in tests/" >&2
  exit 1
fi
uv run --locked python -m coverage run -p -m unittest -v "${mods[@]}"

# Other unit-test packages under tests/; integration excluded, and packages
# with no test*.py at any depth (helpers such as fixtures) are skipped.
for d in tests/*/; do
  d="${d%/}"
  case "$d" in tests/integration|tests/__pycache__) continue ;; esac
  [ -n "$(find "$d" -name __pycache__ -prune -o -name 'test*.py' -print -quit)" ] || continue
  uv run --locked python -m coverage run -p -m unittest discover -s "$d" -t . -v
done

if [ "$mode" = "full" ] && [ -d tests/integration ]; then
  uv run --locked python -m coverage run -p -m unittest discover -s tests/integration -t . -v
fi

# Quality gates (PS-1.6), configured in pyproject.toml: line + branch coverage
# of engine and harness_telemetry must reach the threshold on what this mode
# ran, and mypy --strict must be clean. Tests are in neither. These always run
# (no silent skip); test_engine_quality pins the configuration itself.
uv run --locked python -m coverage combine
uv run --locked python -m coverage report
uv run --locked python -m mypy
