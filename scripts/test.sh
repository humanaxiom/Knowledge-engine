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
# Needs GNU `stat -c` and bash >= 4.4 (`wait -n`, `mapfile`, and empty-array
# expansion under `set -u`); it runs only in the gates image, not on macOS or a
# bare Windows shell.
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

# ci-speed (architecture 2.2.1): one coverage process per top-level module, at
# most k = min(nproc, 4) at once, largest file first (size, then name, so the
# order is deterministic). Each module logs to its own file; the logs are
# printed whole, in module order, once the pool is done, followed by one
# `unit: <s>s rc=<rc> <module>` line per module, so output never interleaves.
# A module fails the run if it exits non-zero, prints no `Ran N` line with
# N > 0, or leaves no coverage data file for `combine`.
# Every coverage run writes under its own --data-file name, beside the
# configured data_file (no COVERAGE_FILE env var, which would leak into nested
# runs): <dir>/<name>.<label>, the label being the dotted module or directory.
# `combine` gets exactly these files, and any it leaves behind fails the run.
k="$(nproc 2>/dev/null || echo 1)"
case "$k" in '' | *[!0-9]* | 0) k=1 ;; esac
[ "$k" -le 4 ] || k=4

# The data path comes from coverage's API, never from parsing its text output;
# an empty or failed lookup fails before any test runs (no .coverage fallback).
cov_data="$(uv run --locked python -c 'import coverage; print(coverage.Coverage().config.data_file)')" || cov_data=""
if [ -z "$cov_data" ]; then
  echo "error: could not read coverage's data_file; refusing to run tests" >&2
  exit 1
fi
cov_dir="$(dirname -- "$cov_data")"
cov_name="$(basename -- "$cov_data")"

logs="$(mktemp -d)"
trap 'rm -rf -- "$logs"' EXIT
# Job control gives each background job its own process group, so a signal can
# take down the uv/python children of a job along with it.
set -m
# TERM first; a group that is still alive after about 2 s gets KILL, so a
# module that ignores TERM cannot outlive the script.
kill_jobs() {
  local p i alive
  local pids=()
  for p in $(jobs -p); do
    pids+=("$p")
    kill -TERM -- "-$p" 2>/dev/null || kill -TERM "$p" 2>/dev/null || true
  done
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    alive=0
    for p in "${pids[@]}"; do
      if kill -0 -- "-$p" 2>/dev/null || kill -0 "$p" 2>/dev/null; then alive=1; fi
    done
    [ "$alive" -eq 1 ] || return 0
    sleep 0.1
  done
  for p in "${pids[@]}"; do
    kill -KILL -- "-$p" 2>/dev/null || kill -KILL "$p" 2>/dev/null || true
  done
}
on_signal() {
  trap '' INT TERM
  kill_jobs
  exit "$1"
}
trap 'on_signal 130' INT
trap 'on_signal 143' TERM

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
  [ "$found" -eq 1 ]
}
# A foreground step that stays interruptible: the trap fires while we wait.
step() {
  "$@" &
  wait "$!"
}

mapfile -t order < <(
  for m in "${mods[@]}"; do
    printf '%s %s\n' "$(stat -c %s -- "${m//.//}.py")" "$m"
  done | sort -k1,1nr -k2,2 | cut -d' ' -f2
)
run_module() {
  local m="$1"
  local rc=0
  local start="$SECONDS"
  uv run --locked python -m coverage run -p --data-file="$cov_dir/$cov_name.$m" -m unittest -v --durations 10 "$m" >"$logs/$m.log" 2>&1 || rc=$?
  echo "$((SECONDS - start))" >"$logs/$m.sec"
  echo "$rc" >"$logs/$m.rc"
}
for m in "${order[@]}"; do
  while [ "$(jobs -rp | wc -l)" -ge "$k" ]; do wait -n || true; done
  run_module "$m" &
done
wait

failed=0
for m in "${mods[@]}"; do
  if [ -f "$logs/$m.log" ]; then
    cat -- "$logs/$m.log"
  else
    echo "error: $m has no log file; its output is lost" >&2
    failed=1
  fi
done
for m in "${mods[@]}"; do
  if [ ! -f "$logs/$m.rc" ]; then
    echo "error: $m has no rc file; it did not finish" >&2
    failed=1
    continue
  fi
  rc="$(cat -- "$logs/$m.rc")"
  echo "unit: $(cat -- "$logs/$m.sec" 2>/dev/null || echo 0)s rc=$rc $m"
  if [ "$rc" != 0 ]; then
    echo "error: $m exited with status $rc" >&2
    failed=1
  elif [ -f "$logs/$m.log" ] && ! grep -Eq '^Ran [1-9][0-9]* tests? in ' "$logs/$m.log"; then
    echo "error: $m printed no 'Ran N tests' line with N > 0" >&2
    failed=1
  fi
  if ! collect_data "$m"; then
    echo "error: $m left no coverage data file ($cov_dir/$cov_name.$m.*)" >&2
    failed=1
  fi
done
[ "$failed" -eq 0 ] || exit 1

# Other unit-test packages under tests/; integration excluded, and packages
# with no test*.py at any depth (helpers such as fixtures) are skipped.
for d in tests/*/; do
  d="${d%/}"
  case "$d" in tests/integration|tests/__pycache__) continue ;; esac
  [ -n "$(find "$d" -name __pycache__ -prune -o -name 'test*.py' -print -quit)" ] || continue
  label="${d//\//.}"
  step uv run --locked python -m coverage run -p --data-file="$cov_dir/$cov_name.$label" -m unittest discover -s "$d" -t . -v
  collect_data "$label" || { echo "error: $label left no coverage data file" >&2; exit 1; }
done

if [ "$mode" = "full" ] && [ -d tests/integration ]; then
  step uv run --locked python -m coverage run -p --data-file="$cov_dir/$cov_name.tests.integration" -m unittest discover -s tests/integration -t . -v
  collect_data tests.integration || { echo "error: tests.integration left no coverage data file" >&2; exit 1; }
fi

# Quality gates (PS-1.6), configured in pyproject.toml: line + branch coverage
# of engine and harness_telemetry must reach the threshold on what this mode
# ran, and mypy --strict must be clean. Tests are in neither. These always run
# (no silent skip); test_engine_quality pins the configuration itself.
uv run --locked python -m coverage combine "${data_files[@]}"
for i in "${!data_files[@]}"; do
  if [ -e "${data_files[$i]}" ]; then
    echo "error: ${data_labels[$i]}: combine left ${data_files[$i]} unconsumed" >&2
    failed=1
  fi
done
[ "$failed" -eq 0 ] || exit 1
uv run --locked python -m coverage report
uv run --locked python -m mypy
