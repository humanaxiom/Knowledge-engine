#!/usr/bin/env bash
# Resource probe: prints one `resources:` line of fixed keys (ci-speed,
# architecture 2.2.1-r3 decision 4), called by scripts/test.sh at the start and
# end of the unit stage.
#   usage: resource_probe.sh <start|end> [root]
# Every value is digits, `max` (cpu_max_quota and cg_mem_max only) or `n/a`
# (source missing, unreadable, or not a number). No file text and no
# environment variable is ever printed. Always exits 0 and writes nothing to
# stderr. `root` (default /) is a test seam; test.sh never passes it.
# Needs bash builtins and nproc only.
exec 2>/dev/null
set -u

pr_phase="${1:-}"
case "$pr_phase" in start | end) ;; *) pr_phase="n/a" ;; esac
pr_root="${2:-/}"
pr_root="${pr_root%/}"

# num <text>: the text if it is all digits, else n/a.
num() {
  if [[ "${1:-}" =~ ^[0-9]{1,20}$ ]]; then printf '%s' "$1"; else printf 'n/a'; fi
}
# nummax <text>: as num, but `max` is allowed.
nummax() {
  if [ "${1:-}" = max ]; then printf 'max'; else num "${1:-}"; fi
}
# field <file> <key>: second word of the first line whose first word is <key>.
field() {
  local fl_k="" fl_v="" fl_n=0
  [ -f "$1" ] || return 0
  while [ "$fl_n" -lt 64 ] && read -r -t 1 -n 4096 fl_k fl_v _; do
    fl_n=$((fl_n + 1))
    if [ "$fl_k" = "$2" ]; then
      printf '%s' "$fl_v"
      return 0
    fi
  done <"$1"
  return 0
}
# psi <file> <some|full>: the total= value on that line.
psi() {
  local ps_f=() ps_w="" ps_n=0
  [ -f "$1" ] || return 0
  while [ "$ps_n" -lt 64 ] && read -r -t 1 -n 4096 -a ps_f; do
    ps_n=$((ps_n + 1))
    if [ "${ps_f[0]:-}" = "$2" ]; then
      for ps_w in "${ps_f[@]}"; do
        case "$ps_w" in total=*)
          printf '%s' "${ps_w#total=}"
          return 0
          ;;
        esac
      done
      return 0
    fi
  done <"$1"
  return 0
}
# one <file>: the first line of the file.
one() {
  local on_l=""
  [ -f "$1" ] || return 0
  read -r -t 1 -n 4096 on_l <"$1"
  printf '%s' "$on_l"
}

cg="$pr_root/sys/fs/cgroup"
pr_quota="" pr_period="" pr_cpu="" pr_u="" pr_n="" pr_s="" pr_i="" pr_w="" pr_irq="" pr_sirq="" pr_st=""
pr_nproc="$(OMP_NUM_THREADS='' OMP_THREAD_LIMIT='' nproc)"
pr_cpu_max="$(one "$cg/cpu.max")"
read -r pr_quota pr_period _ <<<"$pr_cpu_max"
pr_steal="n/a"
pr_total="n/a"
if [ -f "$pr_root/proc/stat" ]; then
  read -r -t 1 -n 4096 pr_cpu pr_u pr_n pr_s pr_i pr_w pr_irq pr_sirq pr_st _ <"$pr_root/proc/stat"
fi
if [ "${pr_cpu:-}" = cpu ]; then
  pr_ok=1
  pr_sum=0
  for pr_v in "${pr_u:-}" "${pr_n:-}" "${pr_s:-}" "${pr_i:-}" "${pr_w:-}" "${pr_irq:-}" "${pr_sirq:-}" "${pr_st:-}"; do
    if [[ "$pr_v" =~ ^[0-9]{1,18}$ ]]; then pr_sum=$((pr_sum + 10#$pr_v)); else pr_ok=0; fi
  done
  if [ "$pr_ok" -eq 1 ]; then
    pr_steal="$((10#$pr_st))"
    pr_total="$pr_sum"
  fi
fi

printf 'resources: phase=%s' "$pr_phase"
printf ' nproc=%s' "$(num "$pr_nproc")"
printf ' cpu_max_quota=%s' "$(nummax "${pr_quota:-}")"
printf ' cpu_max_period=%s' "$(num "${pr_period:-}")"
printf ' cg_cpu_usage_us=%s' "$(num "$(field "$cg/cpu.stat" usage_usec)")"
printf ' cg_cpu_throttled_us=%s' "$(num "$(field "$cg/cpu.stat" throttled_usec)")"
printf ' mem_total_kib=%s' "$(num "$(field "$pr_root/proc/meminfo" MemTotal:)")"
printf ' mem_available_kib=%s' "$(num "$(field "$pr_root/proc/meminfo" MemAvailable:)")"
printf ' swap_total_kib=%s' "$(num "$(field "$pr_root/proc/meminfo" SwapTotal:)")"
printf ' swap_free_kib=%s' "$(num "$(field "$pr_root/proc/meminfo" SwapFree:)")"
printf ' cg_mem_max=%s' "$(nummax "$(one "$cg/memory.max")")"
printf ' cg_mem_peak=%s' "$(num "$(one "$cg/memory.peak")")"
printf ' psi_cpu_some_us=%s' "$(num "$(psi "$pr_root/proc/pressure/cpu" some)")"
printf ' psi_memory_some_us=%s' "$(num "$(psi "$pr_root/proc/pressure/memory" some)")"
printf ' psi_memory_full_us=%s' "$(num "$(psi "$pr_root/proc/pressure/memory" full)")"
printf ' psi_io_some_us=%s' "$(num "$(psi "$pr_root/proc/pressure/io" some)")"
printf ' psi_io_full_us=%s' "$(num "$(psi "$pr_root/proc/pressure/io" full)")"
printf ' cpu_steal_ticks=%s' "$(num "$pr_steal")"
printf ' cpu_total_ticks=%s\n' "$(num "$pr_total")"
exit 0
