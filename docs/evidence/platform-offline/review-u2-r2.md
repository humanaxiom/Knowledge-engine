# Review: platform-offline unit 2, re-review after rework round 2/5 (2026-10-19)

Reviewer. Base 1fe81dd; working tree on agent/platform-offline (uncommitted).
Read: `git diff 1fe81dd` for scripts/launch.sh, tests/fake_docker.py and docs/quickstart.md; the staged
scripts/bundle.sh and scripts/install.sh (index == working tree, mode 100755); the untracked
scripts/install.ps1 and tests/test_offline_bundle.py; architect-u2r2.md; green-u2r2-verify-full.txt
(`== verify full: PASS (299s) ==`); green-u2r2-windows-acl.txt (1 test OK).
Raw probes, mutant diffs and results: `review-u2-r2-probes.txt`. Verify: `review-u2-r2-verify-fast.txt`.

Verdict: **CHANGES REQUESTED** (3 blocking, all cheap).

## Verify
- `COMPOSE_PROJECT_NAME=ke-review-r2 scripts/verify.sh fast`: `== verify fast: PASS ==`, Ran 526, OK (skipped=1).
- `git ls-files -s scripts/`: bundle.sh, install.sh, launch.sh and teardown.sh are 100755. install.ps1 is untracked,
  so it still has to be added at commit time (a plain `git add` is right for it).

## 1. Earlier findings
| Finding | Status | Evidence |
|---|---|---|
| RB1 ps1 swallows SIGTERM/SIGHUP | fixed | mutants i1 (no `Install()`) and ani (`Assert-NotInterrupted` no-op) are both caught by `test_install_stops_on_signal_to_its_own_pid` (TERM+HUP). `test_install_ps1_session_recovers_after_signal` pins the reset and Dispose |
| RB2a Mac launch.sh needs bash 4 | fixed | no `mapfile`/`sort -V`; old vs new `at_least` and host_ip parse match on every realistic input (probes). See RB5b for the missing test |
| RB2b PS 5.1 | fixed | `#Requires -Version 7.3`; the quickstart uses `pwsh -File` |
| RB2c exec bit | fixed | 100755 in the index; `ExecBitTest`; the quickstart uses `bash ...` |
| RB2d /opt parent | fixed | operator-only parent text and `/opt/ke` recipe; quickstart tests |
| P1 HUP trap | fixed | INT/TERM/HUP/QUIT traps |
| P2 case rule | fixed | `refuse_case_clash` (awk tolower) runs before the copy, and the test names RULE_CASE |
| P3 separator | fixed | `Join-Path 'scripts' 'launch.ps1'` |
| P4 Ctrl+Break | fixed | SIGQUIT registered (.NET maps it to Ctrl+Break on Windows) |
| P5 forbid list | fixed | applies to all 3 operator scripts, with the extra forms |
| P6 quickstart notes | fixed | /tmp, .DS_Store/._*, OneDrive, shasum, Linux build host |
| P7 O(n^2) | fixed | one awk pass for unlisted files. `is_listed` still runs once per bundle.json entry, which is a handful |

New mutants (scratch, ke-gates, network none):
- Caught:
  - sync (`Sync-Pin` made a no-op): caught by the ps1 staging swap test.
  - chkp (`check_path` removed): caught by the sh PATH test.
  - unwrap2 (main wrapper removed, no trailing exit): caught by the append test.
  - clshab and clpsab (both claim checks removed, sh / ps1): caught by `replaced_during_load` (dir).
- Survive:
  - clsha, clshb, clpsa, clpsb (one claim check removed): each is masked by its sibling check (marker present
    and "holds exactly the marker"). This is defence in depth, so I accept it.
  - clshc (marker check removed from the sh `cleanup`): see N2.
  - unwrap (main wrapper removed, trailing `exit` kept): see RB3.
  - pspath (ps1 `Assert-SafePath` removed): see RB5a.
  - atl (`at_least` always true): see RB5b.

## 2. Blocking
- **RB3 M-4 is not fixed: install.sh can still be rewritten while it runs.** The tail is two lines,
  `main "$@"` then `exit`. Before it runs an external command, bash moves its file offset back to the end of
  the command it is executing. So when `main` returns, bash reads the next line from the file again.
  - Probe 1: rewrite the bundle's install.sh in place at `docker info` (same inode, the fake's existing
    `write` hook), with `exit` replaced by `touch X; exit`. The injected command ran, and the run exited 0.
  - Probe 2: a synthetic script in gates bash 5.2 gives the same result, whether or not the tail sits on an
    8 KiB buffer boundary.
  - The one-line form `main "$@"; exit`, which the architect specified, is parsed whole before `main` runs.
    Mutant fix1 (that one-line form) passes the probe and the sh suite.
  - The tester's test only appends after `exit`, so it cannot see this. It also lets mutant unwrap survive.
  - Fix (developer): join the last two lines. Test (tester): add an in-place rewrite subtest (truncate and
    write, replacing the tail line) beside the append. That subtest kills unwrap too.
    Probe source: `review-u2-r2-probes.txt`, tests/scratch_m4.py section.
- **RB4 The quickstart's Windows code-first block is corrupted.** docs/quickstart.md:34 reads
  `scriptsaunch.ps1`; the `\l` of `scripts\launch.ps1` was eaten. This is a regression from 1fe81dd on the
  primary path, and bundle.sh ships this file inside every bundle. No test sees it.
  - Fix (documenter): restore the line.
  - Test (tester): every `scripts[/\]<name>` named in a quickstart code block must exist under scripts/.
- **RB5 Two changed behaviours have no test.**
  - (a) The ps1 PATH rule (L-9) is untested. Mutant pspath survives, and the architect flagged the gap.
    Mirror the sh test for pwsh: a relative entry, plus an empty entry on Linux, is refused with "PATH" named
    and no docker run.
  - (b) launch.sh `at_least` was rewritten, but no test drives a compose version other than the fake's fixed
    2.29.7. Mutant atl (always true) survives.
    - Make the fake's `compose version --short` configurable.
    - Expected results: 2.23.9 and 2 are refused; 2.24, 2.24.0-desktop.1 and 2.100.1 launch.
    - Run the cases under both bash and the BSD shims.

## 3. Warn-not-refuse ruling (sh vs ps1)
Both scripts apply it the same way:
- The warning is printed before the claim and staging, and the install continues (exit 0 under a shared
  parent; `InstallPs1WindowsAclTest` installs under Authenticated Users Modify).
- The text names the parent and says "writable by others".
- The POSIX rule is the same in both: group-writable, or other-writable without the sticky bit.

Gaps against architecture §2.5 are recorded as N1.

## 4. Nits
- N1 §2.5 conformance:
  - install.sh skips the bash-only rule "owned by neither the operator nor root".
  - install.ps1 does not count GenericWrite/GenericAll rights.
  - Implement both, or amend §2.5 (architect).
- N2 `cleanup`'s marker check is unpinned (clshc). In the `replaced_during_load` dir case, put a sentinel in
  the planted dir and assert that it survives.
- N3 quickstart:
  - Use `pwsh -NoProfile -File`, as the script header and the architect say.
  - "refuses an empty ... PATH entry" is not true on Windows, where ps1 drops empty entries.
  - Step 5 runs `scripts/launch.sh` directly although step 4 says `bash` is used so the file mode does not
    matter. Use `bash scripts/launch.sh` there and in install.sh's `next:` line, or explain.
- N4 Probe debris in the repo root must not be committed: fake.log, out.txt, dirlink_probe.py, and the empty
  directories elsewhere/, par/ and victimdir/. Remember to `git add` install.ps1 and
  tests/test_offline_bundle.py.
- N5 (info) launch.sh now refuses a non-numeric compose version such as `dev`, which `sort -V` accepted.
  This fails closed and is fine. A version like `2.024` now compares numerically.

## Conformance (no finding)
- launch.sh behaves as before:
  - The `=`-prefixed collect keeps empty host_ip values, and no match gives 0 elements (probe table).
  - The existing host_ip tests (N-3 cases, including empty host_ip) still pass.
- No eval or Invoke-Expression. Argv arrays only. No secrets in the diff.
- Observability: these are shell/pwsh operator scripts. There is no agent loop, model, retrieval or tool
  call, so no span is required.
