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
# Needs bash >= 4.4 (empty-array expansion under `set -u`) and nproc (for
# scripts/resource_probe.sh); it runs only in the gates image, not on macOS or
# a bare Windows shell.
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."

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

# ci-speed (architecture 2.2.1-r3): the top-level modules run in ONE coverage
# process; sub-package runs and the integration run follow in sequence, and the
# first failing run stops the script (the resource probe's end line still
# prints). Every coverage run writes under its own --data-file name, beside the
# configured data_file (no COVERAGE_FILE env var, which would leak into nested
# runs): <dir>/<name>.<label>, the label being `toplevel`, `tests.<pkg>` or
# `tests.integration` (none is a dot-prefix of another, so the glob for one
# never matches another's files). `combine` gets exactly the files collected
# from these labels, and any it leaves behind fails the run.

# The data path comes from coverage's API, never from parsing its text output;
# an empty or failed lookup fails before any test runs (no .coverage fallback).
cov_data="$(uv run --locked python -c 'import coverage; print(coverage.Coverage().config.data_file)')" || cov_data=""
if [ -z "$cov_data" ]; then
  echo "error: could not read coverage's data_file; refusing to run tests" >&2
  exit 1
fi
cov_dir="$(dirname -- "$cov_data")"
cov_name="$(basename -- "$cov_data")"

# Data files of this run, with the label of the run that wrote each one.
data_files=()
data_labels=()
collect_data() {
  local label="$1" f found=0
  shopt -s nullglob
  for f in "$cov_dir/$cov_name.$label".*; do
    data_files+=("$f")
    data_labels+=("$label")
    found=1
  done
  shopt -u nullglob
  if [ "$found" -eq 0 ]; then
    echo "error: $label left no coverage data file ($cov_dir/$cov_name.$label.*)" >&2
    return 1
  fi
}

# One coverage run per label: run, then require its data. Explicit returns,
# because errexit is off inside a function called from `||`.
cov_run() {
  local label="$1"
  shift
  uv run --locked python -m coverage run -p --data-file="$cov_dir/$cov_name.$label" -m unittest "$@" || return $?
  collect_data "$label" || return 1
}

unit_runs() {
  bash scripts/resource_probe.sh start
  cov_run toplevel -v --durations 10 "${mods[@]}" || return $?

  # Other unit-test packages under tests/; integration excluded, and packages
  # with no test*.py at any depth (helpers such as fixtures) are skipped.
  local d label
  for d in tests/*/; do
    d="${d%/}"
    case "$d" in tests/integration | tests/__pycache__) continue ;; esac
    [ -n "$(find "$d" -name __pycache__ -prune -o -name 'test*.py' -print -quit)" ] || continue
    label="${d//\//.}"
    cov_run "$label" discover -s "$d" -t . -v || return $?
  done
}
# The probe's end line prints even when a unit run failed; the failure still
# fails the run and no later run starts.
unit_rc=0
unit_runs || unit_rc=$?
bash scripts/resource_probe.sh end
[ "$unit_rc" -eq 0 ] || exit "$unit_rc"

if [ "$mode" = "full" ] && [ -d tests/integration ]; then
  cov_run tests.integration discover -s tests/integration -t . -v
fi

# Quality gates (PS-1.6), configured in pyproject.toml: line + branch coverage
# of engine and harness_telemetry must reach the threshold on what this mode
# ran, and mypy --strict must be clean. Tests are in neither. These always run
# (no silent skip); test_engine_quality pins the configuration itself.
uv run --locked python -m coverage combine "${data_files[@]}"
failed=0
for i in "${!data_files[@]}"; do
  if [ -e "${data_files[$i]}" ]; then
    echo "error: ${data_labels[$i]}: combine left ${data_files[$i]} unconsumed" >&2
    failed=1
  fi
done
[ "$failed" -eq 0 ] || exit 1
uv run --locked python -m coverage report
uv run --locked python -m mypy
