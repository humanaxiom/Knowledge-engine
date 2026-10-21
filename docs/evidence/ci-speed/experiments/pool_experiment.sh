#!/usr/bin/env bash
# Profiling experiment only (ci-speed architect), INSIDE the gates image:
#   pool_experiment.sh <cap>
# One process per top-level unit module, heaviest file first, at most
# k = min(nproc, cap) at once; logs printed in module order afterwards.
set -uo pipefail
cd /work
cap="${1:-4}"
k="$(nproc)"; [ "$k" -gt "$cap" ] && k="$cap"
uv run --locked python -m coverage erase
mapfile -t ordered < <(for f in tests/test*.py; do printf '%s %s\n' "$(wc -c < "$f")" "$f"; done | sort -k1,1nr -k2,2 | awk '{print $2}')
dir=/tmp/ke-unit; mkdir -p "$dir"
echo "nproc=$(nproc) k=$k modules=${#ordered[@]}"
s0=$(date +%s); running=0
for f in "${ordered[@]}"; do
  m="${f%.py}"; m="${m//\//.}"
  if [ "$running" -ge "$k" ]; then wait -n; running=$((running-1)); fi
  ( t=$(date +%s.%N)
    uv run --locked python -m coverage run -p -m unittest -v --durations 5 "$m" >"$dir/$m.log" 2>&1
    echo $? >"$dir/$m.rc"
    python3 -c "import sys; print(f'{float(sys.argv[2])-float(sys.argv[1]):.1f}')" "$t" "$(date +%s.%N)" >"$dir/$m.sec" ) &
  running=$((running+1))
done
wait
echo "pool wall=$(( $(date +%s) - s0 ))s"
fail=0; ranlines=0
for f in tests/test*.py; do
  m="${f%.py}"; m="${m//\//.}"
  rc="$(cat "$dir/$m.rc")"; [ "$rc" = 0 ] || fail=1
  grep -Eq '^Ran [1-9][0-9]* tests?' "$dir/$m.log" && ranlines=$((ranlines+1))
  printf '%6ss rc=%s %s\n' "$(cat "$dir/$m.sec")" "$rc" "$m"
done | sort -rn
for f in tests/test*.py; do m="${f%.py}"; m="${m//\//.}"; grep -E '^(FAIL|ERROR):' "$dir/$m.log"; done | head
echo "Ran-lines: $(cat "$dir"/*.log | grep -cE '^Ran [1-9]') of ${#ordered[@]} modules"
echo "tests: $(cat "$dir"/*.log | grep -E '^Ran ' | awk '{s+=$2} END {print s}')"
grep -h 'test_top_level_unit_suite_ran .* ok' "$dir"/*.log
uv run --locked python -m coverage combine >/dev/null
uv run --locked python -m coverage report | tail -1
