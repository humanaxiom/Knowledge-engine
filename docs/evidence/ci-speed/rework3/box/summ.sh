#!/bin/bash
# summ.sh <samples.tsv>: averages over the run from first/last sample
awk 'NR==2{for(i=1;i<=NF;i++)a[i]=$i} NR>1{for(i=1;i<=NF;i++)b[i]=$i; if($2>mx)mx=$2; if($4>ma)ma=$4; if($3>ms)ms=$3; if($6>msh)msh=$6}
END{dt=b[1]-a[1]; printf "span=%ds cpu_avg=%.2f cpus cpu_some=%.1f%% mem_some=%.2f%% mem_full=%.2f%% io_some=%.2f%% io_full=%.2f%% majfault=%d read=%.0fMB write=%.0fMB peak_mem=%.2fGiB peak_anon=%.2fGiB peak_swap=%.0fMB peak_shmem=%.0fMB\n", dt,(b[8]-a[8])/1e6/dt,(b[9]-a[9])/1e4/dt,(b[10]-a[10])/1e4/dt,(b[11]-a[11])/1e4/dt,(b[12]-a[12])/1e4/dt,(b[13]-a[13])/1e4/dt,b[7]-a[7],(b[14]-a[14])/1e6,(b[15]-a[15])/1e6,mx/2^30,ma/2^30,ms/2^20,msh/2^20}' "$1"
