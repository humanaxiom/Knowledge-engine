# Security re-audit: platform-offline unit 2, after rework round 4/5

Date 2026-10-19. Auditor: security. Scope: current `scripts/install.sh`
(staged) and `scripts/install.ps1` (untracked), against `security-u2-r3.md`
and the round-4 ruling (refuse a parent owned or writable by anyone but the
operator, root, SYSTEM or Administrators; fail closed). Probes ran with their
cwd in `<scratch>` only, a fake `docker` and `DOCKER_HOST=tcp://127.0.0.1:1`.
WSL fixtures lived on ext4 under `<wsltmp>` and were removed. No daemon,
image, HEAD, index or tracked file was touched. A PATH shim, a fake-docker
hook or a probe line in a scratch copy of install.ps1 stands in for a racer.
Raw output: `security-u2-r4-probes.txt` (A = WSL ext4, B = Git Bash/NTFS,
C/C2 = pwsh 7.6.7 on Windows 11).

**Verdict: PASS** (0 critical, 0 high, 1 medium, 4 low, 2 info). Nothing
merge-blocking. M-7 is cheap to fix and is recommended for this round.

## Prior findings, re-probed

| ID | Status | Evidence |
|---|---|---|
| H-2 (sh) | **Closed.** Staging name swapped for a symlink to a non-empty 0700 or 0755 operator dir, or to an EMPTY operator 0700 dir (which passes empty/-O/mode): all refused by the `pwd -P` check, exit 1, victim intact, 0 docker calls. | A2-700, A2-755, A2e |
| H-2 (ps1) | **Closed.** Junction swap before the kind check and after it (before Set-Location): refused, victim intact; the planted junction is removed as a link only. | W1A, W1B |
| M-5 | **Closed.** Target name swapped for a symlink at `chmod 0755 .`: the chmod hits the real claim, `-ef` fails, exit 1, victim stays 0700. | A6 |
| M-6 | **Closed.** Everyone AD, Everyone GW (stored FW), Everyone GA, Users Modify, AU DeleteChild: all refused, nothing created. | W2-W4b |
| L-15 | **Closed by reading the code** (no pwsh on Linux here): off Windows the parent owner (`ls -ldn`) and the owner of `.` are checked against `id -u`; read failures refuse. See L-18 for the sticky residue. | code 232-246, 269, 317-333 |

## The parent rule: does it remove the racer?

Yes, for the parent itself, on every platform tested:
- **Modes (A11):** 1777, 0777, 0775, 0770, 0757, 0730, 2775 refused, no
  target created; 0750, 0700, 1755 accepted. Foreign owner refused (A11o).
- **Fail closed:** `ls` failing, garbage, or no numeric owner; `id -u`
  failing, non-numeric or empty: all exit 1 before any target or docker call
  (A12, 6 cases). Windows ACL unreadable (owner denied READ_CONTROL through
  an OWNER RIGHTS ACE): refused (C2 W10).
- **Windows groups that include the operator and others** (Users, AU,
  Everyone) are refused (W4, W4b). A conditional (callback) ACE is returned
  by .NET and refused (W5); W5g proves such an ACE does grant write.
- **OWNER RIGHTS / CREATOR OWNER allowance is sound.** OW applies only to the
  owner, who must be the operator, SYSTEM or Administrators; Windows rewrites
  a non-inherit-only CO ACE to the owner SID (W6b), and an inherit-only one
  does not apply to the parent (skipped). Inherit-only Everyone FullControl is
  accepted and the target stays private, D:P(A;OICI;FA;;;me-sid) (W7).

Where it does not reach (judged below): ancestors (M-7), Git Bash on NTFS
(I-13), synced/network folders and macOS (I-14).

## Medium

### M-7 Cleanup removes staging recursively by name (sh and ps1)
- **Code.** install.sh:100-104 `rm -rf -- "$staging"`; install.ps1:841-847
  `Remove-Item -LiteralPath $script:Staging -Recurse` when the name is not a
  link. Both run on every exit, after the pinned emptying.
- **A2r / W1r (parent racer).** A non-empty operator-owned sibling renamed
  into the staging name: the empty/ACL check refuses correctly, then the
  cleanup deletes the sibling (`victim: GONE`). Precondition (rename rights in
  the parent) is now refused by the rule, so this alone would be Low.
- **A10 (ancestor racer, sh).** Grandparent `G` writable by others (0777, no
  sticky), parent `G/adam` operator-owned 0755: accepted (A10b). At any point
  during the install, the racer renames `adam`, symlinks `adam -> G`, and
  renames the real `adam` to `G/<staging name>`. The run dies at publish and
  `rm -rf "$staging"` deletes the whole operator folder `adam`
  (`notes/keep: GONE`). The window is the entire install (minutes for real
  images), not a race.
- **Windows.** The same ancestor rename is refused while the run holds its
  cwd and marker handle (W11: `mv ... Permission denied`); only the finally
  block, after the cwd is released, is open. Narrow.
- **ADR-KE-012 is wrong on this point.** Its reason for not checking
  ancestors ("the staging pin ... and the claim marker still hold against
  that") does not hold for the cleanup, as A10 shows.
- **Why Medium, not High.** It needs an install under a non-sticky ancestor
  that others can write, outside every documented path (home, `/opt/ke` as
  root, the Windows profile). And such an ancestor writer can already swap the
  installed tree for their own and get code execution at the next `launch`
  by the operator, so no new capability class is gained.
- **Fix (two lines).** sh: `rmdir -- "$staging" 2> /dev/null || true` (a
  pinned staging is already emptied from inside, and an unpinned one was never
  filled). ps1: `[System.IO.Directory]::Delete($script:Staging, $false)` in a
  try. Correct the ADR sentence; optionally add "and every directory above it"
  to the quickstart parent rule. Test: the A2r shim (sibling renamed in) leaves
  the sibling intact.

## Low
- **L-16 Claim removal by name** (install.sh:95-98, ps1 Close-Claim 395-400).
  `rm -rf "$target"` after a marker check by name, and the ps1 marker handle is
  closed just before. This is a check-then-act gap of one statement and needs a
  parent or ancestor racer. Optional fix: cd in, check the marker and `-O .`,
  empty from inside, `cd /`, then `rmdir` by name.
- **L-17 Publish `mv` by name** (install.sh:213-216). With a parent or
  ancestor racer, the verified app files move into a victim dir and overwrite
  same-named files (A6b overwrote `docker-compose.yml` in the victim). The run
  exits 1. On Windows the open marker handle blocks the swap. The rule removes
  the precondition, so accept.
- **L-18 ps1 off Windows still exempts a sticky world-writable parent**
  (install.ps1:328-330), contrary to the ruling, §2.5 and install.sh (A11:
  1777 refused). It is not exploitable as such, because sticky stops others
  renaming entries the operator owns, and install.ps1 is Windows-only. Drop the
  `-not $sticky` clause and add a 1777 case. The chmod of the target by name
  (ps1 off Windows only, re-checked by Get-EntryKind) is **acceptable** under
  the rule: the window is in-process, and the only principals who can swap
  the name are the operator and root.
- **L-19 Stale text.** quickstart.md:119 still says "The installer warns when
  the parent is writable by others" (it refuses). install.sh:160-162 still
  says "a sticky world-writable parent such as /tmp is allowed".

## Info
- **I-13 Git Bash on NTFS (noacl mount).** `ls -ldn` shows `drwxr-xr-x`,
  owned by you, for an Everyone-Modify parent, so the rule is blind there. But
  `mkdir -m 0700` always fails on that mount, so install.sh never gets past
  the claim (G1/G2: exit 1, 0 docker calls). Keep install.ps1 as the Windows
  path. If Git Bash support is added, the rule must read the NTFS ACL.
- **I-14 Out of sight of the check.**
  - **Synced folders (OneDrive, Dropbox).** They carry the profile ACL, but
    collaborators can rename items through the cloud.
  - **NFS.** It trusts uids by number, and NFSv4 ACLs show only as mode bits.
  - **macOS.** The `ls -lde` allow-entry branch is unverified (no Mac). A
    failing `uname -s` skips it, which is not fail-closed, but this is the
    I-11 PATH-trust class.
  - **Recommendation.** Extend the "not shared or synced media" sentence in
    the quickstart (lines 82-85) to the target. I-11 (PATH) stays accepted.

## Checked and clean
- **Secret grep.** `git diff 1fe81dd` (working tree, excluding evidence),
  the staged scripts and install.ps1 were searched for AWS, GitHub, Slack and
  OpenAI keys, private keys, JWTs, credentialed URLs and
  password/secret/token assignments. There were no hits.
- **Tracing.** No tracing or span surface changed.
- **New deletion and chmod paths.** The pinned emptying (sh and ps1) runs
  only after the empty, real-path, owner and 0700/ACL checks, and is turned
  off before publish leaves staging. `chmod 0755 .` acts on the cwd after the
  marker and `-O .` checks. `chmod 0644` acts on a relative path inside the
  pinned staging. A failure after `cd "$target"` cannot delete the target,
  because the marker is gone or the check refuses.
- **Repo root.** After the audit, `git status --short` shows only this file
  and `security-u2-r4-probes.txt` as new entries.
