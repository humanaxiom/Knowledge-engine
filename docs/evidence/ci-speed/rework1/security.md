# ci-speed rework 1: security re-audit (2026-10-21)

**Verdict: PASS.** No critical, high or medium findings. Two lows and some info notes, none blocking.

- Scope: `git diff 0b874c2` working tree, plus untracked `docs/handoffs/ci-speed.md` and `docs/evidence/ci-speed/`. `docs/knowledge-engine-claude-code-prompt.md` is ignored.
- Focus: reworked `scripts/test.sh` (lines 53-185).
- Method:
  - Scratch copy of tracked files (no tests/ or docs/), with fake test modules and the scratch `fail_under` set to 0.
  - Run in `ke-gates:wt-33a132fbfdd7` with `--network none`, `--user 10001`, `--cap-drop ALL`, a read-only `/work` and a fresh tmpfs `/tmp`.
  - Containers named `ke-sec-r1-*` and labelled `ke.project=ke-sec-r1`.
  - Repo files, HEAD and index were not touched.
- Raw output and harness: `docs/evidence/ci-speed/rework1/security-scan/`.

## Checked and holding
- **Lookup output (test.sh:59-65) cannot inject into commands.**
  - `cov_data` and the derived `cov_dir`/`cov_name` are used only as quoted single words: `dirname --`/`basename --`, `--data-file=...`, the quoted glob prefix and `echo`. There is no eval and nothing is re-parsed.
  - Probe I1 used data_file `/tmp/x $(touch /tmp/PWNED1);`touch /tmp/PWNED2`;$IFS"q'r/.cov`. The run was green and created no PWNED file (`run-inj.txt`).
  - Empty or failed lookup exits 1 before any test runs. A whitespace value fails on EROFS (I3).
  - The value comes only from pyproject or `COVERAGE_*`. verify.sh passes only `KE_*` keys into the gates container, so the caller cannot steer it there.
- **Glob and word-splitting (test.sh:92, 106-110, 176-181).**
  - `collect_data` quotes the prefix `"$cov_dir/$cov_name.$label".*`, so only the trailing `.*` is a glob. Probe I2 used data_file `/tmp/d[1]/*.cov` with decoys in `/tmp/d1` and `/tmp/d[1]`. No decoy was collected or combined, and the run stayed green. This closes round-0 L4 (`compgen -G`).
  - The combine list is a quoted array.
  - `$(jobs -p)` is unquoted, but it holds only numeric PIDs.
- **Label- and module-derived paths.**
  - Labels come from `tests/test*.py` and `tests/*/`, with `/` mapped to `.`, so they contain no `/` and cannot traverse out of `$logs` or `$cov_dir`. They always start with `tests.`, so they cannot become an option.
  - A name with a space or newline breaks the `sort|cut` order list. The real name then has no rc file, and the run fails closed (test.sh:135-138).
- **mktemp -d log dir (test.sh:67-68).**
  - Created atomically with mode 0700 and owned by the runner. Seen in the control run: `LOGDIR /tmp/tmp.* 0o700 10001` (`run-ctrl.txt`).
  - Every file is written inside that private dir, so another uid cannot plant a symlink there. `rm -rf --` does not follow links.
  - The EXIT trap is not inherited by the `run_module` subshells, so a worker cannot delete it early. The dir was removed on green, INT and TERM runs (t1-t5).
- **Signals and fail-closed behaviour (test.sh:71-84, 101-104, 111-154).**
  - Results:

    | Case | Exit code |
    |---|---|
    | TERM to test.sh while in the pool (k=1, inside the `wait -n` loop) | 143 |
    | INT, same point | 130 |
    | TERM during the `step` sub-package phase | 143 |
    | INT, same point | 130 |
    | TERM to test.sh's own process group | 143 |

  - In each case the pool children (uv and python) were gone and the dir was removed (`run-t1..t4*.txt`).
  - `wait -n || true` and the bare `wait` cannot hide a failure: a trap's `exit` leaves the shell, and status travels only through the `.rc` files.
  - A missing rc gives "no rc file" and fails. An empty or truncated rc gives `"" != 0` and fails. rc is written after `.sec`, as the last step.
  - Non-`step` foreground commands (erase, combine, report, mypy) defer the trap until they finish, then exit 143. A tty SIGINT kills the foreground group, and `set -e` exits non-zero.
  - No path was found where a signal or a failure ends in exit 0.
  - **Forging:** only the same uid can write `$logs` (0700), and that uid is the trusted test code. Not a finding.
- **Kill scope (test.sh:72-77).**
  - With `set -m`, every pool or step job leads its own process group, and `kill -TERM -- -<pgid>` reaches only those groups.
  - Two control processes survived every case: a `setsid sleep` and a `sleep` in the wrapper's own group (`OUT1`/`OUT2 alive` in t1-t5).
- **Combine (test.sh:176-183).**
  - combine gets the explicit list, and any file it leaves behind fails the run.
  - On a shared host, files that another user plants under `/tmp/.coverage.<label>.*` cannot be deleted by `erase`/`combine` because of the sticky `/tmp`. The run then fails, which is a DoS and not a fail-open. The gate uses a private tmpfs.
- **Hook:** `git diff -w 0b874c2 -- scripts/hooks/block-main-commit.sh` has 0 non-comment changed lines. Comment-only.
- **Secrets:** 0 hits in the diff's added lines and 0 in the untracked handoff and evidence. The only hits are the round-0 pattern line itself, and the CI log's `token: ***` and `AUTHORIZATION: basic ***` are masked by GitHub (`security-scan/secret-and-redaction-scan.txt`).
- **Redaction:** 0 profile paths and 0 SIDs in the diff, the handoff or the evidence. The one hit is the round-0 pattern line. `/home/runner/...` in `ci-39499437202.log` is the ephemeral GitHub runner workspace, not a profile, and is kept. This scan's own evidence holds no scratch or profile paths.
- **Out of scope for this change:** no new dependency, no network, no tracing or span change, and no prompt-injection surface.

## Findings
- **S1 (low): TERM only, with no wait and no KILL escalation.** test.sh:72-82.
  - A pool child that ignores or handles TERM outlives test.sh. Probe t5 (a test with `SIGTERM` set to `SIG_IGN`) exited 143, but its uv and python stayed alive (`run-t5-ign-term.txt`).
  - Such an orphan can write a late `/tmp/.coverage.<label>.*` after the run. On a host, the next run's `erase` removes it unless the orphan is still running.
  - The run still reads red, and in the gate the container teardown kills the orphan. Optional fix: after TERM, `wait` with a short deadline, then send `kill -KILL -- -<pgid>`.
- **S2 (low, test-only): the signal test's cleanup sends SIGKILL to PIDs that are already dead or reaped.** tests/test_harness_followups.py:813 and :817.
  - `os.kill(pid, SIGKILL)` targets the recorded grandchildren after the test has confirmed they are dead. `os.killpg(proc.pid, SIGKILL)` targets proc's group after `proc.wait()` has reaped it.
  - Under the pool, other modules run at the same time in the same PID namespace, so a reused PID could kill an unrelated test process. That gives a red flake, never a green.
  - Fix: skip the kill when `proc_alive(pid)` is false, and send `killpg` only while `proc.poll() is None`.

## Info (no action)
- The `python -c` lookup imports `coverage` with the checkout on `sys.path`. A `coverage.py` at the repo root would shadow it. It is the same trust domain as test.sh, and the gate checkout is read-only.
- `kill_jobs` falls back to `kill -TERM <pid>`, which can target a job that is done but not yet reported. This is theoretical PID reuse inside the container.
- `for d in tests/*/` has no `nullglob` and prints `find: 'tests/*'` when there are no sub-packages. This predates the change (base line 45) and is cosmetic.
