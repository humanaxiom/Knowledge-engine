# ci-speed rework 4: security re-audit

Date: 2026-10-21. Role: security. Branch agent/ci-speed, HEAD a375a4e, plus the
working tree (round 3 after the revert, and round 4). Scope: the round-4 delta,
which is the hardened untracked `scripts/resource_probe.sh` (with
`tests/test_resource_probe.py`), the static S4 test in
`tests/test_block_main_commit_hook.py:798-856`, and the docs. Rulings applied:
architecture §2.2.1-r3 decision 4 (Hardening) and decision 6 (S4: no wall
bound, static test, accepted residual risk).

## Verdict: PASS

There are no critical, high or medium findings. S6 and S7 are closed. S5 is
closed for the cases it was raised for. S4 is mitigated as ruled. Three new
lows are recorded below (S8–S10); none of them blocks the merge.

## Round-3 findings: status

| ID | Status | Evidence (run-probe-r4.txt) |
|---|---|---|
| S5 | **Closed for the cases raised.** A FIFO at one source or at every source, a /dev/zero or /dev/urandom symlink, or a directory gives n/a in 0.02–0.03 s. A 200 MB single line now takes 0.04 s (round 3: 7 s). The printable worst case, with all 9 files at 64+ lines of 4095 chars, takes 0.08 s for the whole probe. Through the real root (`/`), a run takes 0.02 s. Two root-seam residuals remain (S8). | rows "FIFO …", "/dev/zero …", "200 MB …", "worst case …" |
| S6 | **Closed.** 2^63−1 (19 digits) gives n/a and n/a. `010` gives 10, and `08`/`09` sum in base 10 (total 44). 8 × 18-digit maxima give 7999999999999999992 with no overflow. 18 leading zeros work. Signed, short, 23-digit and `a[$(…)]` fields give n/a, and the injection did not run. `num` prints 2^64−1 (20 digits) and rejects 21 digits. 0 shape violations on any row. | S6 rows |
| S7 | **Closed.** `OMP_NUM_THREADS=424242`, `OMP_THREAD_LIMIT=3`, and both set together all give the real `nproc=24`. With `ROOT` or `pr_root` in the env and no root argument, the probe reads the real `/`. | S7 rows |
| S4 | **Mitigated as ruled.** The static test catches every listed construct written plainly: `&`, `&` inside `$( )`, `exec … &`, `{ …` then `} &` on the next line, a function that backgrounds, and `\&` or `${v:+&}` (these two launch nothing, so flagging them is strict but harmless). The hook as it is today passes, and it is pure printable ASCII. The bypasses are S9 (the test's line reading) and S10 (outside the list, already accepted). | run-s4-bypass.txt |

## New findings (all non-blocking)

| ID | Sev | Where | Finding | Suggested fix (follow-up) |
|---|---|---|---|---|
| S8 | low | scripts/resource_probe.sh:30-31, 43-44, 62-63, 74-75; scripts/test.sh:93, 111; docs/architecture.md:903-908 | Two residuals, both reachable only through the test-only `root` seam (in production the root is `/`, and /proc and /sys/fs/cgroup are kernel-owned). **(a) NUL bytes.** Bash `read` drops NUL bytes without counting them toward `-n`, and bash ignores `-t` on a regular file. A sparse NUL file therefore defeats both caps. 100 MB takes 1.2 s, 1 GB takes 10.9 s, and 1 TB ran until it was killed at 60 s (rc 124). With every source symlinked to one 1 TB file, it was killed at 30 s. A bare `read -t 1 -n 4096` on a 1 GB NUL file took 4 s, so the timeout had no effect. **(b) TOCTOU.** A rename race that swaps cpu.max between a regular file and a FIFO, after `[ -f ]` and before the open, hung 474 of 3000 runs. An open of a FIFO blocks in open(2), and `-t` cannot interrupt it. test.sh calls the probe with no timeout, so either case hangs the job until the CI job timeout. That fails closed (red, never green), and nothing leaks. The architecture text "Reading stops at the first timeout … an oversized or endless regular file is cut off" is not true for these cases. | Use `timeout 10 bash scripts/resource_probe.sh …` in test.sh (coreutils is already required by `nproc`), and correct the wording at architecture:903-908 (`-t` applies to pipes and terminals only). |
| S9 | low | tests/test_block_main_commit_hook.py:815-816 | The static S4 test reads lines differently from bash, which misses 9 constructs that are on the list. In each case below, the mutated hook passed `test_hook_launches_no_background_work`, passed `bash -n`, returned in 0.03 s, and left an un-waited `sleep` running. **(a)** `str.splitlines()` also splits on FF, VT, FS, CR, U+0085 and U+2028, which bash treats as word characters. So `_x=<FF>#; sleep 9 &` is one bash line that runs `sleep` in the background, but Python sees `#; sleep 9 &` as a comment line. These characters are invisible or near-invisible in a diff, a "Trojan Source"-style trick. **(b)** `str.lstrip()` strips `\x1f`, so the line `<US>#() { sleep 9 & }` (a function named `<US>#`) and the call `<US>#` are both skipped. **(c)** A line that starts with `#` but is not a comment is skipped: `#$(sleep 9 &)` inside a multi-line double-quoted string, or inside an unquoted here-document. This needs a deliberately hostile hook edit. The worst outcome is a hook call over 10 s, which fails open for that call. That is the same impact the residual risk already accepts. | One deterministic assertion closes (a) and (b): the hook contains only `\t`, `\n` and printable ASCII (it does today). Split with `text.split("\n")`. Also scan comment lines, which closes (c); no comment in the hook trips the scan today. |
| S10 | low (accepted) | tests/test_block_main_commit_hook.py:802-803 | These are outside the list, the residual risk accepted in §2.2.1-r3 decision 6. Recorded so the size of that risk is on file: 13 more mutants pass the test and launch un-waited work. They are: `se''tsid -f`, `${c}sid -f`, `ev''al`, `source /dev/stdin` and `. /dev/stdin` fed by a here-string, `bash -s` fed by a here-string, `bash --norc -c`, `bash -o posix -c`, `$BASH -c`, `dash -c`, a `trap` string run at EXIT, `mapfile -C`, `${x@P}`, and `python3 … Popen(start_new_session=True)`. In each, `&` comes from `a=$'\x26'`, so no literal `&` is on the line. `bash --norc -c` and `bash -o x -c` are near misses of the listed "nested shell" pattern, because the regex allows short flags only. A deny-list cannot be complete for bash. | If the risk is ever revisited, use an allow-list of the commands and builtins the hook may call, not a longer deny-list. Otherwise, no action; keep the human review of every hook diff. |

Info: the arithmetic-subscript route (`(( _q ))` with
`_q='_r[$(… &)]'`) launched nothing in bash 5.2.15. The hook failed
first under `set -e`.

## Evidence hygiene (security-scan/secret-and-redaction-scan.txt)

- Secret patterns: 0 hits in rework4/ (green-verify-fast/full, red-verify-fast,
  s4-mutants, nit5-p7-mutant), in the probe and its test, in the hook test and
  in the lines `git diff HEAD` adds. The only hits are the pattern text in the
  scan file itself.
- Profile paths and SIDs: none. There is no Windows user-profile path,
  `/c/Users/`, AppData or `S-1-5-21`.
- Auth headers and `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST` values: none. The
  model tests skip with the key name only.
- IPs: only 127.0.0.1 and the docker-internal 172.18.0.2 and 192.168.160.2.

## How it was run

- Everything ran on scratch copies of the probe, the hook and the hook test,
  in the gates image `ke-gates:wt-33a132fbfdd7` (bash 5.2.15).
- Each container was `--rm`, `--network none`, labelled
  `com.docker.compose.project=ke-security-cs4` and named
  `ke-security-cs4-probe`, `-race` or `-s4`, with the scratch directory
  bind-mounted read-only at `/w`.
- The probe harness ran as uid 0, so the /proc/kmsg check was possible: it
  gave n/a, because docker drops CAP_SYSLOG. The race and S4 harnesses ran as
  uid 10001.
- No containers remain, and no repo file was modified apart from this
  evidence, the handoff line and the log line.

The files are in docs/evidence/ci-speed/rework4/security-scan/:
- harnesses: `harness-probe-r4.sh.txt`, `harness-race-r4.sh.txt` and
  `harness-s4-bypass.py.txt`;
- runs: `run-probe-r4.txt`, `run-race-r4.txt` and `run-s4-bypass.txt`. The
  last is passed through `cat -v`, because the mutant names contain raw
  control characters.
- `secret-and-redaction-scan.txt`.
