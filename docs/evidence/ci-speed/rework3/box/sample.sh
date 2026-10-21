#!/bin/bash
# sample.sh <out>: box cgroup (whole emulated runner) every 5 s
out="$1"; cg=/sys/fs/cgroup
echo "t mem_cur swap_cur anon file shmem pgmajfault usage_usec cpu_some_us mem_some_us mem_full_us io_some_us io_full_us rbytes wbytes" > "$out"
while :; do
  ms=$(cat $cg/memory.stat)
  g() { awk -v k="$1" '$1==k{print $2}' <<<"$ms"; }
  p() { awk -v k="$2" '$1==k{split($5,a,"="); print a[2]}' "$cg/$1.pressure"; }
  io=$(awk '{for(i=2;i<=NF;i++){split($i,a,"="); if(a[1]=="rbytes")r+=a[2]; if(a[1]=="wbytes")w+=a[2]}} END{print r+0, w+0}' $cg/io.stat)
  echo "$(date +%s) $(cat $cg/memory.current) $(cat $cg/memory.swap.current) $(g anon) $(g file) $(g shmem) $(g pgmajfault) $(awk '$1=="usage_usec"{print $2}' $cg/cpu.stat) $(p cpu some) $(p memory some) $(p memory full) $(p io some) $(p io full) $io" >> "$out"
  sleep 5
done
