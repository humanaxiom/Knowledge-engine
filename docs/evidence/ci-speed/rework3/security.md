# ci-speed rework 3: security audit

Date: 2026-10-21. Role: security. Branch agent/ci-speed, HEAD a375a4e and the
round-3 working tree. Scope: `git diff HEAD`, the untracked
`scripts/resource_probe.sh` and `tests/test_resource_probe.py`, then the whole
item (`git diff 0b874c2`). Rulings applied: the HUMAN RULINGS line in
docs/handoffs/ci-speed.md and architecture §2.2.1-r3.

## Verdict: PASS

There are no critical, high or medium findings, and four lows (non-blocking).
Rework-2 lows S1 and S3 (TERM/HUP and orphan handling) are moot because the
pool, its traps and `kill_jobs` are gone.

## Findings

| ID | Sev | Where | Finding | Suggested fix (follow-up) |
|---|---|---|---|---|
| S4 | low | tests/test_block_main_commit_hook.py:43, :46-57 | RUSAGE_CHILDREN counts only descendants that are waited for. A hook that does its work in a detached (setsid / double-forked) grandchild and reads the result through a pipe is not counted. The 60 s hang guard then lets it pass. Measured with a scratch mutant (12 s busy CPU in a detached grandchild, then the real hook): `test_long_command_finishes_quickly` and `test_one_megabyte_command_finishes_quickly` both **OK**, 4 calls of about 12 s in 48 s. Each such call is over Claude Code's 10 s hook timeout, which fails open for PreToolUse. This needs a deliberately obfuscated hook: the hook has no `&`, `<( )`, setsid or nohup today, and every hook diff is reviewed. It extends the blocking-hook gap the architecture already accepted (§2.2.1-r3, Consequences). | Add a wall bound equal to the 10 s hook timeout on the CPU-measured calls, or on one small-input call. It sits beside the CPU budget, not in place of it. |
| S5 | low | scripts/resource_probe.sh:28-36, 56-60, 69 | `read` on a FIFO or an endless source blocks forever: the probe hung until `timeout` killed it (rc 124). A 200 MB single-line file takes 7 s. test.sh calls the probe with no timeout. This is reachable only through the test-only `root` seam, or by someone who already controls the container's /proc or /sys mounts. It fails closed (the CI job times out red) and never fails open. | `read -t 5 -n 4096` (builtins), or `timeout 10 bash scripts/resource_probe.sh` in test.sh. |
| S6 | low | scripts/resource_probe.sh:73-74 | The `cpu_total_ticks` sum overflows: a crafted field of 9223372036854775807 prints `cpu_total_ticks=-9223372036854775808`, a minus sign outside `^([0-9]+|max|n/a)$`. A leading-zero field is summed as octal (`010` adds 8). Field `08` makes the arithmetic fail, and the probe recovers with n/a and rc 0. The only route is a crafted /proc/stat; kernel counters cannot get near 2^63. Nothing leaks and no code runs. | Use `$((10#$pr_v))`, cap fields at 18 digits, and print n/a on overflow. |
| S7 | low | scripts/resource_probe.sh:64 | GNU `nproc` honours `OMP_NUM_THREADS` and `OMP_THREAD_LIMIT`. With `OMP_NUM_THREADS=424242` the probe printed `nproc=424242`. This breaks the letter of "reads no environment variable": the value is digits only and not a secret, but it misreports the CPU count. | `OMP_NUM_THREADS= OMP_THREAD_LIMIT= nproc` (a prefix assignment, builtins only). |

Info (not findings):
- An exported bash function such as `BASH_FUNC_printf%%` overrides the probe's
  builtins and can print anything. This needs control of the CI or compose
  environment, which is trusted, and the gates service passes only listed keys.
- RUSAGE_CHILDREN also picks up stale `Popen` objects that `subprocess._cleanup`
  reaps during the measured call. That can only inflate the figure: a flaky
  red, never a false green.

## resource_probe.sh: what was checked (run-probe-adversarial.txt)

- **Arbitrary text.** Planted file text never reaches the output. This held
  for SECRET=, paths, control characters and CR, and for symlinks to
  /etc/hostname and /proc/self/environ. Unicode digits (Arabic-Indic,
  full-width, circled) are rejected under LC_ALL C and C.UTF-8. A hostile
  phase or root prints `phase=n/a` and n/a.
- **Command execution.** An arithmetic-injection field `a[$(touch …)]` is
  stopped by the `^[0-9]+$` guard before `$(( ))` runs, and nothing ran. The
  sources are read only with `read` and the output only with `printf '%s'`.
- **Leaks.** The real line holds no hostname, username, path or env value.
  The memory and PSI figures are hardware capacity (on CI, the hosted
  runner's published spec) and are acceptable in CI logs. The evidence holds
  host names, which the user ruling allows. The probe also writes nothing to
  stderr (`exec 2>/dev/null`).
- **Exit 0.** The probe exits 0 in every case except a hang (S5).

## test.sh after the revert (run-ts-*.txt, fixtures.txt; gates image, uid 10001, ro checkout, --network none)

| Fixture | Result |
|---|---|
| green fast and green full | rc 0, start and end lines |
| red top-level | rc 1, the end line printed, the sub-package run never starts |
| red sub-package | rc 1, the end line printed, the later package (`zsub`) never starts |
| `os._exit(0)` (no data) | `error: toplevel left no coverage data file`, rc 1 |
| probe mutant `exit 3` with green tests | rc 3 (red) |
| probe deleted | rc 127 (red) |
| integration red (full) | rc 1 |

- No swallowed failure. `unit_runs || unit_rc=$?` keeps the status, and the
  end probe runs at top level under `set -e`, so a failing probe can only turn
  green into red. Inside `unit_runs` (errexit off) every step has an
  explicit `|| return $?`.
- The probe output cannot match verify.sh's `^Ran N` or sentinel greps,
  because its values are digits, `max` or n/a.
- **Injection.** `cov_data`, `cov_dir`, `cov_name` and every label are
  double-quoted everywhere. The data-file glob quotes the literal part, and
  labels come only from `tests/*/` directory names (repo-controlled).
  `parallel = true` with a fresh /tmp tmpfs means no stale `.coverage.*` file
  can satisfy the per-label check. A dotted directory name (`tests/x.y`)
  could share a label prefix, but it is not an importable package, so its
  run fails closed.

## Evidence hygiene (secret-and-redaction-scan.txt)

- **Secret patterns.** 0 hits in rework3/, ci/, the probe and its test, and
  `git diff HEAD`. The whole item has 2 hits, both the literal scan-pattern
  text inside earlier scan files, not credentials.
- **Profile paths and SIDs.** None (no `C:\Users\<name>`, `/c/Users/`,
  AppData or `S-1-5-21`). `/home/runner` in the CI logs is the generic
  GitHub runner account, not a personal profile. The GITHUB_TOKEN and the
  checkout `AUTHORIZATION` header are masked as `***`. The only IPs are
  docker-internal (172.18.0.2, 192.168.144.2) and 127.0.0.1.
- The untracked `docs/knowledge-engine-claude-code-prompt.md` is out of scope
  and was excluded from commits before; keep it excluded.

## Evidence

The evidence files are in docs/evidence/ci-speed/rework3/security-scan/:
- harness scripts: `harness-*.sh.txt` and `mutant-hook-detached.sh.txt`;
- runs: `run-*.txt`;
- `fixtures.txt` and `secret-and-redaction-scan.txt`.

All runs used scratch copies only, in `--rm` containers labelled
`com.docker.compose.project=ke-security-cs3`. None remain, and no repo file
was modified apart from this evidence, the handoff line and the log line.
