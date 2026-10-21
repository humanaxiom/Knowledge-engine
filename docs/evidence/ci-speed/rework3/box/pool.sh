#!/usr/bin/env bash
# The real test.sh (pool) from the commit under test, unit stage + rest; wall of whole script.
s=$SECONDS
scripts/test.sh "${1:-fast}" 2>&1; rc=$?
echo "test.sh rc=$rc wall=$((SECONDS - s))s nproc=$(nproc)"
