#!/usr/bin/env bash
# Profiling experiment only (ci-speed architect). Runs INSIDE the gates image:
#   shard_experiment.sh <jobs> <unit: module|class>
# Splits the top-level unit modules into <jobs> shards (greedy, heaviest first
# by a weight proxy), runs each shard as its own `coverage run -p -m unittest`,
# waits, prints per-shard wall time, then combines coverage and reports.
set -uo pipefail
cd /work
jobs="${1:-2}"
unit="${2:-module}"
uv run --locked python -m coverage erase
mods=()
for f in tests/test*.py; do m="${f%.py}"; mods+=("${m//\//.}"); done
# Shard plan from a python helper (weights = recorded CI seconds where known,
# else 1 s); prints one line per shard with space-separated test names.
plan="$(uv run --locked python /scratch/shard_plan.py "$jobs" "$unit" "${mods[@]}")"
echo "$plan" | awk '{print "shard " NR-1 ": " NF " names"}'
s0=$(date +%s)
i=0
pids=()
while IFS= read -r line; do
  # shellcheck disable=SC2086
  ( t=$(date +%s); uv run --locked python -m coverage run -p -m unittest -v $line > "/tmp/shard$i.log" 2>&1; rc=$?
    echo "shard $i rc=$rc wall=$(( $(date +%s) - t ))s" >> /tmp/shard-times ) &
  pids+=($!)
  i=$((i+1))
done <<< "$plan"
for p in "${pids[@]}"; do wait "$p"; done
echo "all shards wall=$(( $(date +%s) - s0 ))s"
cat /tmp/shard-times
grep -h '^Ran ' /tmp/shard*.log
grep -h -E '^(OK|FAILED)' /tmp/shard*.log
grep -h -E '^(FAIL|ERROR):' /tmp/shard*.log | head -20
grep -c 'test_top_level_unit_suite_ran .* ok' /tmp/shard*.log | grep -v ':0'
uv run --locked python -m coverage combine >/dev/null
uv run --locked python -m coverage report | tail -1
