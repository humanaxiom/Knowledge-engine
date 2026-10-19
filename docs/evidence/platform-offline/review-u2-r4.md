# Review: platform-offline unit 2, re-review after rework round 4/5 (2026-10-19)

Reviewer. Base 1fe81dd; working tree on agent/platform-offline (uncommitted; install.sh staged == worktree).
Read: scripts/install.sh, scripts/install.ps1, tests/test_offline_bundle.py (round-4 tests), docs/quickstart.md,
architecture §2.5 (round-4 text) and requirements PS-3.1/PS-3.2 Docs (round 4), the handoff from "unit-2 rework
round 4/5" on, architect-u2r4.md, green-u2r4-verify-full.txt (555, 1 failure = the pre-re-seat L-11 test),
green-u2r4-windows.txt (11 OK), tester-r4b-verify-fast.txt (555 OK, skipped=6).
Raw probes, mutant diffs and results: `review-u2-r4-probes.txt`. Verify: `review-u2-r4-verify-fast.txt`.

Verdict: **CHANGES REQUESTED**. There are 2 blocking findings. Both are small, and both break a written round-4
acceptance criterion.

## Verify
- `COMPOSE_PROJECT_NAME=ke-review-r4 scripts/verify.sh fast`: `== verify fast: PASS ==`, Ran 555, OK (skipped=6).
- No `verify.sh full` after the tester's re-seat is in evidence yet; the orchestrator's pre-commit full run covers it.
- No probe debris in the repo. The root `.coverage.c3f6723effb0.pid109.*` (03:59, gitignored) predates this review.

## 1. Earlier findings
| Finding | Status | Evidence |
|---|---|---|
| RB6 `~/.ssh` emptied | fixed | Probe rb6_ssh_symlink on the working tree: victim `[id_ed25519, sub, sub/keep]` before and after, mode 0700, rc 1, no docker, refused at the `pwd -P` check (install.sh:325). The double mutant (pwd -P + emptiness dropped) reproduces the r3 wipe (`after=[]`), and `test_install_sh_never_empties_dir_swapped_in_for_staging` kills it |
| N6 `next:` line | fixed | install.sh:638 `bash scripts/launch.sh`; `test_install_sh_next_line_runs_launch_with_bash` |
| N7 ps1 staging-empty parity | fixed | install.ps1:266-268; mutant p_noempty killed by `test_install_ps1_refuses_non_empty_staging` |

## 2. Mutants (full tests.test_offline_bundle in the gates image)
| Mutant | Result |
|---|---|
| sh: drop parent-policy refusal | killed (others_can_write x3, owned_by_another_user, cannot_check x2) |
| ps1: drop parent-policy refusal | killed (others_can_write x3) |
| ps1: ACL-read catch -> `return` | killed (`test_install_ps1_acl_read_failure_is_not_silent`, try_at_line=299) |
| ps1: mode-read catch -> `return` | killed (same test, try_at_line=318) |
| sh: drop owner/mode check after cd | killed by the re-seated `test_install_sh_refuses_staging_loosened_before_cd` (0755/0750/0701) |
| sh: drop `pwd -P` pin check | **survives** (emptiness check covers the test's non-empty victim). Probe: link to an EMPTY operator 0700 dir, rc 0, installs while working in that dir; nothing is lost. N12 |
| sh: drop emptiness check | **survives** (`pwd -P` covers the swap). A planted file is still refused, by the manifest rule. N12 |
| sh: drop both of the above | killed (H-2 test; victim wiped) |
| sh: drop both `-ef` checks at publish | **survives**. Probe: a real dir swapped in at `chmod 0755 .` gives rc 0 and a false "installed to". N11 |
| ps1: drop off-Windows staging owner check | **survives** (no test). N12 |

## 3. Blocking
- **RB7 (developer + tester): install.ps1 off Windows still exempts a sticky parent that others can write.**
  - install.ps1:328-330 refuses `OtherWrite` only `-and -not $sticky`.
  - That breaks PS-3.1 round 4 (requirements.md:1500-1501, "with or without the sticky bit (bash and pwsh
    off Windows)"), §2.5 (architecture.md:1836-1838, "sticky or not") and sh parity.
  - The tests miss it: 1777 is refused anyway via GroupWrite, and the test only uses 0777/0775/0770.
  - Probe: parents 0o1757 and 0o1703 give **rc 0, docker ran, installed**. install.sh refuses both.
  - Consequence: other accounts can create names in the parent. Off Windows the ps1 claim is a non-exclusive
    `CreateDirectory` followed by a mode-only check (no owner check, install.ps1:203-221). A 0700 directory an
    attacker creates in the window passes the claim:
    - as non-root, the marker write fails (DoS only);
    - as root, the app is published into an attacker-owned directory.
  - Fix (developer): remove `-and -not $sticky` (and `$sticky`).
  - Test (tester): add a sticky other-writable mode, e.g. 0o1757, to
    `test_install_flags_target_parent_others_can_write` (runs for sh and ps1). Correct its docstring, which says
    "world-writable without the sticky bit".
- **RB8 (documenter): the quickstart still says the installer warns.**
  - docs/quickstart.md:118-119 reads "The installer warns when the parent is writable by others."
  - PS-3.2 Docs round 4 (requirements.md:1694-1696) requires: the parent must be owned and writable only by
    you (or root/Administrators), and the installer **refuses** otherwise, including a sticky /tmp-style
    parent and `C:\`.
  - Ownership is not mentioned at all. The requirement lists this wording as "no test yet", so nothing caught it.
  - Lines 115-117 and the /opt/ke and $HOME recipes are correct under the new policy (probe: $HOME accepted,
    `C:\` refused on S-1-5-11).

## 4. Questions asked
- **ps1 chmod by name (install.ps1:800-807): acceptable, not blocking.**
  - Once RB7 lands, no other principal can create or rename entries in the parent. The guard-to-chmod window
    then needs the operator or root.
  - The architecture's alternative, `SetUnixFileMode('.')` (architecture.md:2111-2113), is not cwd-relative
    in .NET. Path.GetFullPath resolves '.' against the getcwd() string, so it is by name too. Only a native
    `chmod 0755 .` run from inside would act on the directory itself.
  - Architect: make §2.5 step 9 (pwsh off Windows) match the shipped code. It also promises an owner-of-'.'
    check that the code does not make (N14).
- **Write-SharedParentWarning: rename it (nit N13)**, e.g. Assert-OperatorOnlyParent. Only install.ps1:284
  and :436 use the name, and the test now finds the check by content.
- **OWNER RIGHTS / CREATOR OWNER on Windows: acceptable (nit N15).**
  - CREATOR OWNER (S-1-3-0) is never in a token. It is a placeholder substituted at inheritance, so an ACE on
    the parent itself grants nobody anything, and inherit-only ACEs are skipped anyway.
  - OWNER RIGHTS (S-1-3-4) applies to the object's owner. The owner check already limits that owner to the
    operator, SYSTEM or Administrators.
  - Windows probe: both accepted; CREATOR GROUP Modify and Everyone AppendData refused.
  - §2.5 says "a SID other than those three". Architect: record the two placeholders.
- **Docs vs the refuse policy:** architecture and requirements are consistent. The quickstart is not (RB8).
  The install.sh comment is stale (N10).

## 5. Nits
- N10 install.sh:161-162: the comment says "a sticky world-writable parent such as /tmp is allowed". The code
  (186-190) refuses it.
- N11 install.sh:230 and :232 both test `[ "$target" -ef . ]`. Keep one. Optionally pin it with a test: at
  `chmod 0755 .` a shim does `mv target target.away; mkdir target`, and the run must fail with no "installed to".
- N12 Single-layer mutants survive: sh `pwd -P`, sh emptiness, ps1 off-Windows staging owner. Today only the
  combination is pinned. Optional tests:
  - an sh swap to an EMPTY operator 0700 directory (must exit non-zero, no docker);
  - an sh twin of the ps1 N7 planted-file test (the refusal names staging).
- N13 Rename Write-SharedParentWarning (above).
- N14 Architecture drift (architect):
  - §2.5 step 2 says Assert-PrivateDirectory checks the owner off Windows (architecture.md:1937-1939). The
    code checks the owner only in Initialize-Staging, so the claimed target is not owner-checked. Moving the
    check into Assert-PrivateDirectory would cover the claim too (moot after RB7, defence in depth).
  - Step 9 pwsh text (above).
  - The pwsh owner read is `ls -ldn` (code) vs `stat -c %u` (doc). The code is fine; it matches sh.
- N15 Record OWNER RIGHTS / CREATOR OWNER in §2.5 (above).
- N16 ps1 off Windows has no `pwd -P` twin. Get-EntryKind '.' resolves through getcwd, so a symlink that
  Set-Location followed reads as 'dir'. The emptiness check is what protects a non-empty victim (the same
  position as the sh `pwd -P` mutant). This is a parity gap only.
- N8 (carried) Untracked docs/knowledge-engine-claude-code-prompt.md: keep it out of the commit.

## Conformance (no finding)
- There is no eval or Invoke-Expression; argv arrays are used throughout; there are no secrets.
- These are operator scripts with no agent loop, model call, retrieval or tool call, so no span is required.
