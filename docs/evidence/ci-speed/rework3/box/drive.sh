#!/usr/bin/env bash
# drive.sh <run-name> <stack|nostack> <pool|k1|onep>: verify-like env inside the 2-CPU/7 GiB box
set -uo pipefail
cd /repo
name=$1; stack=$2; shape=$3
export KE_IMAGE_TAG="$(bash scripts/image_tag.sh)" MSYS_NO_PATHCONV=1
export COMPOSE_PROJECT_NAME=ke-verify-r3 COMPOSE_FILE="docker-compose.yml:docker-compose.verify.yml" COMPOSE_PATH_SEPARATOR=":"
export KE_ENV_FILE=.env.example KE_SMOKE_OWNS_PROJECT=1 KE_MODEL_UPSTREAM="" KE_EGRESS_ALLOWLIST=""
out=/r3/out; mkdir -p $out
if [ "$stack" = stack ]; then
  docker compose --env-file .env.example ps --status running -q | grep -q . || { scripts/launch.sh > $out/launch-$name.txt 2>&1 || { echo launch failed; exit 1; }; }
  svc=gates-it; prof=gates-it; mode=full
else
  docker compose --env-file .env.example ps -q | grep -q . && scripts/teardown.sh --volumes > $out/teardown-$name.txt 2>&1
  svc=gates; prof=gates; mode=fast
fi
env=(); [ "$shape" = k1 ] && env=(-e OMP_NUM_THREADS=1)
cmd=(bash /r3/pool.sh $mode); [ "$shape" = onep ] && cmd=(bash /r3/onep.sh)
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' > $out/stats-before-$name.txt 2>&1
bash /r3/sample.sh $out/samples-$name.tsv & sp=$!
( while sleep 60; do docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}'; echo --; done ) > $out/stats-$name.txt 2>&1 & dp=$!
s=$(date +%s)
docker compose --env-file .env.example --profile $prof run --rm "${env[@]}" -v /r3:/r3:ro $svc "${cmd[@]}" > $out/run-$name.txt 2>&1
echo "drive: $name stack=$stack shape=$shape container wall=$(( $(date +%s) - s ))s start=$s" >> $out/run-$name.txt
kill $sp $dp 2>/dev/null
