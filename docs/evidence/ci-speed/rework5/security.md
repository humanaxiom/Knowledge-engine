# ci-speed rework 5: security re-audit (final round)

Date: 2026-10-21. Role: security. Branch agent/ci-speed, HEAD a375a4e plus the
working tree. Scope: the round-5 delta (tests and docs only):
`tests/test_block_main_commit_hook.py` (S9 fix and widened nested-shell rule),
`tests/test_resource_probe.py` (R6/R7/R9/R18 tests, inotify skip), and the S8 /
S10 wording in `docs/architecture.md` §2.2.1-r3 decisions 4 and 6 and
`docs/requirements.md` CS-11, CS-12 and "Follow-ups (not in ci-speed)". The hook
and `scripts/resource_probe.sh` are unchanged in round 5 (hook sha256
9bbcfc6e…, no diff against HEAD).

## Verdict: PASS

No critical, high or medium findings. S9 is closed. S8 is documented
accurately. S10 is partly closed and the rest is accepted residual risk with the
allow-list follow-up recorded. One new low (S11) and two info items (I1, I2)
are follow-ups only; none of them blocks the merge.

## 1. S9 and S10 against the round-5 test (security-scan/run-s9-r5.txt)

The rework-4 harness (`rework4/security-scan/harness-s4-bypass.py.txt`, run
unchanged) against the round-5 test file (sha256 2abf94b1…):

| Group | Rework 4 | Rework 5 |
|---|---|---|
| S9: FF, VT, FS, NEL, U+2028, CR before `#`; `\x1f#` function; `#`-line in a multi-line string; `#`-line in a heredoc | 9 bypasses | **9/9 caught** |
| Control rows (`&`, `$( &)`, `exec … &`, `{ } &`, function, `\&`, `${v:+&}`) | caught | caught; today's hook passes |
| S10 nested shell / stdin: `source /dev/stdin`, `. /dev/stdin`, `bash -s`, `bash --norc -c`, `bash -o posix -c`, `$BASH -c`, `dash -c` | bypass | **7/7 caught** |
| S10 rest: `se''tsid`, `${c}sid`, `ev''al`, `trap` string at EXIT, `mapfile -C`, `${x@P}`, `python3 … Popen(start_new_session=True)` | bypass | **7 bypasses remain** |

Summary: 7 bypasses of 32 cases (rework 4: 23 of 32 counting S9 and S10). The
7 remaining are the accepted residual risk of §2.2.1-r3 decision 6. The
allow-list follow-up is recorded in architecture decision 6 ("Follow-up
(DEFERRED …)") and in requirements "Follow-ups (not in ci-speed)" ("Hook command
allow-list (security S10)"). The arithmetic-subscript row still launches
nothing. No sleep was left after the run.

## 2. S8 wording (architecture decision 4 "Limits of these bounds", CS-11)

Accurate. Both texts say that a NUL-filled or sparse file and the `[ -f ]`→open
FIFO race are bounded only by the CI job timeout, that they need the test-only
`root` argument or control of `/proc` and `/sys` (in production the root is `/`
and those trees are kernel-owned), and that they fail red, never green, with
nothing leaked. The `timeout 10` wrapper is DEFERRED with its trade-off
(architecture "Alternatives considered"; requirements "Follow-ups"). The
"Consequences" bullet matches. Re-checked in bash 5.2.15
(security-scan/run-s8-r5.txt): an open of a FIFO with no writer blocked until it
was killed (rc 124 at 8 s); `read -t` on a regular sparse NUL file ignored `-t`.

Info I1 (no action needed; it is wording only and does not hide any risk):
- "`-t` applies to pipes and terminals only" is narrower than real. `-t` also
  fires on a character device: `/dev/zero` timed out at 1.0 s (rc 142). So a
  race that swaps in `/dev/zero` is bounded (64 × 1 s), and the two documented
  cases stay the complete set.
- "1 GB costs about 11 s" is the round-4 full-probe figure. A bare read took
  2.5 s today, so the text overstates the cost, which is the safe direction.
- Outside CI (a local `scripts/verify.sh`), nothing bounds the hang until the
  operator stops it. It is still never green.

## 3. Round-5 test changes: no new risk (security-scan/run-tests-leftovers-r5.txt)

- Hook test: the three new or changed tests (`test_detector_splits_on_newline_only`,
  `test_full_check_rejects_hidden_separator_and_hash_line_mutants`, and the
  widened `test_detector_flags_each_construct_and_allows_plain_redirection`)
  are static. They build mutant text in memory and pass it to the detector;
  no payload (`sleep 30NN …`, here-documents, `bash -c`) is written to disk or
  run.
- Probe tests: `test_each_reader_caps_bytes_and_lines` writes three fixture
  trees (≤ 270 KB) under the test's `mkdtemp` and removes them at cleanup. It
  runs the probe through `probe_bounded`, which uses its own session and a
  `killpg` SIGKILL at 10 s. `test_no_root_path_reads_no_env` runs the real
  probe from the repo root. The two new runs point script names at planted
  directories that hold numbers only. `ENV`, `BASH_ENV`, `SHELLOPTS`, `PS4`,
  `IFS`, `PATH` and `BASH*` are excluded, so no planted path is executed. The
  inotify fd is closed at cleanup, and a missing inotify is now a named skip.
  The canary secrets are generated per run (uuid) and are never real values.
- Run: all 13 tests in ResourceProbeTest and HookLaunchesNoBackgroundWorkTest
  passed in 0.94 s as uid 10001. Afterwards the container had no process other
  than the shell, and `/tmp` was empty.

## 4. Evidence hygiene (security-scan/secret-and-redaction-scan.txt)

`rework5/mutants.txt` and `rework5/verify-fast.txt` hold 0 secret-pattern hits
and 0 profile paths or SIDs. They also hold no `KE_MODEL_UPSTREAM` or
`KE_EGRESS_ALLOWLIST` values, no IPs and no e-mail addresses. Scanning the
lines added by `git diff HEAD`, plus the untracked probe and its test, also
gives 0 hits. The files in this directory were written from container output
only.

## Follow-ups (non-blocking)

| ID | Sev | Where | Finding | Suggested follow-up |
|---|---|---|---|---|
| S10 | low (accepted) | tests/test_block_main_commit_hook.py:806-822 | 7 off-list mutants still launch un-waited work (table in §1). | The allow-list follow-up as recorded. |
| S11 | low | tests/test_block_main_commit_hook.py:814-815; docs/requirements.md CS-12; architecture decision 6 | The widened rule catches `-c`/`-s` and a pipe into a shell, but not a shell that reads its script from stdin through a redirect. 6 mutants pass the full static check, pass `bash -n`, return in 0.03 s and leave an un-waited `sleep`: `bash` and `sh` fed by a here-string, `bash` fed by a here-document, `bash /dev/stdin`, `bash -i` and `bash -` fed by a here-string (security-scan/run-r5-shell-stdin.txt). These are siblings of the listed `bash -s` and "piping into a shell". So "a nested shell … `bash -s`; piping into a shell" slightly overstates what is covered. A quote-split shell word (`ba` + empty quotes + `sh -c`) and `$(echo bash) -c` also pass, but they belong to the S10 quote-split and built-word class. The impact is the same as S10: a deliberately hostile hook edit, and at worst one hook call that fails open past 10 s. | Fold into the S10 allow-list follow-up. If the deny-list stays, flag any shell word that has no script-file operand or whose operand is `/dev/stdin`, `-` or `-i`. |
| I2 | info | tests/test_block_main_commit_hook.py:937, 958, 967 | The test source has literal U+2028/U+2029 characters inside string literals. They are intentional test data and harmless to Python, but invisible in a diff, which is the S9 concern. | Write them as `" "` / `" "` escapes. |

Carried over: S8 `timeout 10` wrapper (DEFERRED, recorded).

## How it was run

- All runs used scratch copies only, in `ke-gates:wt-33a132fbfdd7` (bash
  5.2.15, Python 3.12.15). Each container was `--rm`, `--network none`, uid
  10001, with a tmpfs `/tmp` and read-only mounts. Each was labelled
  `com.docker.compose.project=ke-security-cs5` and named
  `ke-security-cs5-s9`, `-extra`, `-s8` or `-t3`. No container remains.
- No repo file was modified apart from this file, `rework5/security-scan/`,
  one handoff line and one log line.

The files are in `docs/evidence/ci-speed/rework5/security-scan/`:
- `run-s9-r5.txt`;
- `harness-r5-shell-stdin.py.txt` and `run-r5-shell-stdin.txt`;
- `run-s8-r5.txt`;
- `run-tests-leftovers-r5.txt`;
- `secret-and-redaction-scan.txt`.
