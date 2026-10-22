# security-u5: unit 5 re-check of L-3 and L-4 (2026-10-22)

**Verdict: PASS.** 0 critical, 0 high, 0 medium. L-3 closed, L-4 closed. 2 new lows (non-blocking, test/pre-existing), 2 info.
Scope: `git diff e6e1d28 -- scripts tests` (verify.sh, offline_check.sh, 3 test modules) plus the u5-* evidence.
Probe output, drivers and stubs: `security-u5-probes.txt` (this directory). Scratch copies only, in labelled
`ke.audit=security-u5` containers with `--network none`; 0 containers left; no repo file modified
(verify.sh sha256 50fe24b8..., offline_check.sh 2abbcc16..., the same at the start and end).

## L-3: closed
- Only emitter of `verify full: PASS` is the host half, `scripts/verify.sh:100-101`, gated on `rc -eq 0 && finished -eq 1`
  (`finished=0` :88, `finished=1` :132 after offline_check :131). Traps INT/TERM/HUP :115-117.
- Inner half prints `== gates-it: PASS ==` in full (`verify.sh:158-159`); fast keeps `== verify fast: PASS ==` (:161).
  Grep of scripts/, CI and *.py/*.ps1 outside tests: no consumer parses either line (CI uses the exit code).
- Probe Q1 (security-u4-r1 matrix, extended): the fake docker runs the **real** inner half of the copied verify.sh.
  Phases gates-it, smoke, scan, offline_check x INT/TERM/HUP/QUIT/USR1/KILL x group/verify/stage, plus swallow-and-exit-0
  stages: 97 cases each on bash 5.2.15 (gates image) and 5.0.17 (ubuntu 20.04), columns identical; 34 cases on Git Bash 5.3.9.
  **0 invariant violations.** In every case the count of lines with `verify full: PASS` is 0 or 1; when 1, rc is 0,
  it is the outer `== verify full: PASS (Ns) ==`, it is the last line, and gates-it rc 0 and offline_check both ran.
  The 24 PASS rows per bash are the control, QUIT not delivered, or a stage that finished or swallowed and exited 0
  (the truthful rows accepted in security-u4-r1).
- **SIGKILL to verify.sh after gates-it** (smoke, scan, offline_check) and to the group: rc 137, no `verify full: PASS`;
  the last line is an orphaned stage's own output (`stub smoke: done`, `stub scan: done`) or `== gates-it: PASS ==`.
  SIGKILL to verify during gates-it: last line `== gates-it: PASS ==` (the orphaned inner half), never `verify full: PASS`.
  USR1 to verify alone: same shape (rc 138; Git Bash 158).
- u5-green-verify-full.txt:1517 `== gates-it: PASS ==`, :2148 `== verify full: PASS (632s) ==` (only such line, last).

## L-4: closed
- `scripts/offline_check.sh`: `finished=0` :115, `trap 'exit 129' HUP` :169, HUP added to the reset in cleanup :155,
  PASS gated on `rc -eq 0 && finished -eq 1` :163, `finished=1` :241 after the client run.
- Probe Q2, the real offline_check.sh copy (host half; docker/df faked, bundle/net_isolated/teardown stubbed),
  bash 5.2 and 5.0 identical: HUP, INT, TERM to the group or the script, during the client run and during bundle.sh:
  exit **129 / 130 / 143**, **no `offline_check: PASS`**, teardown exactly once, bundle dir and manifest removed.
- **USR1** (pin is a recorded follow-up): to group or script, client or bundle phase: exit 138, no PASS (the finished
  flag holds), teardown once, bundle removed. USR1 to the stage only: the stage dies, `die` gives rc 1, no PASS.
- QUIT and signals to the stage alone: PASS only where the stage really finished (or swallowed and exited 0); truthful.

## Fake gates-it (tests/test_stack_scripts.py:933-958)
- Normal operation stays in its sandbox. Probe Q3a: all 29 tests of VerifyHostHalfTest + VerifyCallsLintTest run as
  **root** (a write anywhere would succeed), `--network none`, no docker socket, repo read-only: all pass, and
  `find / -xdev -newer marker` shows no write outside /tmp; /tmp holds nothing new afterwards.
- No network or docker reach: the inner half (KE_IN_GATES=1) calls only the lint/test/smoke stand-ins it wrote; the
  stub docker is first on PATH; `"${@: -1}"` is `full` from verify.sh:121 and the inner re-validates it (verify.sh:21-24).
- What it runs: `bash $inner/scripts/verify.sh` plus mktemp/mkdir/cp/printf/chmod/rm and the inner half's git/grep/tee.

## New findings
- **L-5 (low, test-only).** tests/test_stack_scripts.py:943 `inner="$(mktemp -d)"` is unguarded (the stub has no
  `set -e`). If mktemp fails, `$inner` is empty: the stub writes `/scripts/{verify,lint,test,smoke}.sh` at the
  filesystem root, runs `/scripts/verify.sh` from `/`, and leaves them (`rm -rf ""` is a no-op). Probe Q3c (root,
  /tmp read-only) reproduced it; it failed closed (rc 1) only because the inner half's own mktemp also failed. Not
  reachable in the gates container (uid 10001, read-only /work, tmpfs /tmp); on Git Bash `/` is the Git install dir.
  Fix: `inner="$(mktemp -d)" || exit 97` and `: "${inner:?}"` before use.
- **L-6 (low, pre-existing, not introduced by U5).** A signal to the group *during* offline_check's own teardown
  (cleanup resets its traps at :155) kills teardown.sh mid-way: rc 130/143/129, no PASS, but the bundle dir and
  manifest stay in dist/ and the project (privileged dind) may be left up, with no "remove it by hand" hint.
  Before U5 INT/TERM behaved the same and HUP was already default inside cleanup. Recommend a follow-up: ignore
  INT/TERM/HUP while tearing down, or print the hand-removal command on a second signal.
- I-1 (info). The fake's mktemp dir is under the system TMPDIR, not the test's own temp dir (`_clean_env` passes only
  PATH/HOME); removed by its EXIT trap, leaked only on SIGKILL. The inner half runs `git rev-parse`/`git diff --quiet`
  with cwd there, so git searches parent dirs (read-only queries). Optional: set TMPDIR to self.tmp in `_env`.
- I-2 (info). offline_check: INT to the script alone while cleanup's teardown runs, after a finished run, still prints
  PASS rc 0 (bash absorbs SIGINT on a foreground child that exits normally). The run had finished and teardown
  completed, so the PASS is truthful; Q2 flags this row only because its rule was stricter than the requirement.

## Evidence sweep
u5-green-verify-fast/full, u5-red-mutants(.py), u5-red-verify-fast (5168 lines) and the added diff lines: no profile
paths, no SIDs, no keys/tokens/private keys/JWTs, no credentialed URLs, no e-mail addresses. Addresses only loopback and
docker bridge. Model keys unset (u5-green-verify-full.txt:1). security-u5-probes.txt has only container paths.
