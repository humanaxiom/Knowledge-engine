#!/usr/bin/env bash
# run_exp.sh <name> <cpuset or "all"> <jobs> <unit>
S=<scratch>
name=$1; cpus=$2; jobs=$3; unit=$4
extra=()
[ "$cpus" != all ] && extra=(--cpuset-cpus "$cpus")
s=$(date +%s)
MSYS_NO_PATHCONV=1 docker run --rm --name "ke-arch-cs-$name" --user 10001:10001 --network none \
  --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:exec,mode=1777 \
  -e MYPY_CACHE_DIR=/tmp/mypy -e PYTHONDONTWRITEBYTECODE=1 -e GIT_OPTIONAL_LOCKS=0 \
  "${extra[@]}" -v "C:/repos/Knowledge-engine:/work:ro" -v "$(cygpath -w $S):/scratch:ro" -w /work \
  ke-gates:arch-cs bash /scratch/pool_experiment.sh "$jobs" > "$S/exp-$name.txt" 2>&1
echo "container total=$(( $(date +%s) - s ))s" >> "$S/exp-$name.txt"
