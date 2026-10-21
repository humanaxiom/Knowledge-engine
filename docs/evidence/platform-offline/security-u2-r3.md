# Security re-audit: platform-offline unit 2, after rework round 3/5 (incl. 3b)

Date 2026-10-19. Auditor: security. Scope: current `scripts/install.sh`
(staged) and `scripts/install.ps1` (untracked), against `security-u2-r2.md`.
Probes ran with their cwd in `<scratch>` only, with a fake `docker` and
`DOCKER_HOST=tcp://127.0.0.1:1`. WSL fixtures lived on ext4 under `<wsltmp>`
and were removed afterwards. No daemon, image, HEAD, index or tracked file was
touched. Where a racer is needed, a PATH shim (sh) or one probe line in a
scratch copy of install.ps1 (`install-hooked.ps1`) stands in for it.
Raw output: `security-u2-r3-probes.txt` (A = WSL ext4, B = Git Bash/NTFS,
C = pwsh 7.6.7 on Windows 11).

**Verdict: FAIL** (0 critical, 1 high, 2 medium, 2 low, 2 info).
H-2 is new and a regression from the I-7 change: the new "empty the pinned
directory" cleanup deletes the contents of a directory outside staging.

## Prior findings, re-probed

| ID | Status | Evidence |
|---|---|---|
| M-4b | **Closed.** Tail is `main "$@"; exit` on one line; an in-place rewrite from the `exit` offset at `docker info` ran nothing (no INJ marker, rc 0). | A1, B G3 |
| L-11 | **Fixed for an attacker-owned or loosened lookalike** (A4: refused, victim untouched). **Not fixed for a symlink to an operator-owned directory**, which now leads to H-2. | A2-A4 |
| L-12 (sh) | Marker-exists check and real-dir re-check are in. The window between the re-check and `chmod 0755` remains (M-5). | A6 |
| L-12 (ps1) | Marker check, re-check and non-Windows refusal are in. Residual: owner not checked (L-15). | code |
| L-13 | **Closed.** Git Bash/NTFS: exit 1, no target left, a pre-existing empty target is put back, no docker call. Nit: the message "something appeared there" is misleading in this case. | B G1, G2 |
| I-7 | **Works** on a renamed real staging: the `.moved` dir is left empty after both a failed and a successful run. | A7, A7b |

## High

### H-2 The I-7 cleanup empties a directory outside staging (sh and ps1)
- **install.sh.** `staging` is chmod'ed and entered **by name** (lines 279-284).
  1. A racer who can rename entries in the parent swaps the fresh name for a
     symlink to any operator-owned directory.
  2. `chmod 0700` follows the link, so even a 0755 victim then passes the mode
     check. `cd` follows it, `[ -O . ]` and `drwx------` pass, and
     `pinned=1` is set.
  3. The bundle is copied into the victim. The manifest check dies on the
     victim's own files ("file is not listed").
  4. `cleanup` runs `rm -rf ./* ./.[!.]* ./..?*` inside the victim.

  Results:
  - A2 (swap before chmod, victim 0755): the victim ends up **mode 700 and
    empty**; exit 1.
  - A3 (swap after chmod, before cd, victim 0700): the victim ends up
    **empty**; exit 1.

  The victim can be the operator's home or `~/.ssh`. When run as root (the
  `/opt/ke` recipe), it can be any root-owned directory, `/` included. In
  round 2 the same race only removed the link, so this is new with I-7.
- **install.ps1 on Windows.** Between `FileSystemAclExtensions.Create` and
  `Set-Location` (lines 236-238), a racer with delete-child on the parent
  renames staging and plants a **junction** (no privilege needed) to a victim.
  - `Set-Location` and `CurrentDirectory` take the junction path.
  - `Assert-PrivateDirectory '.'` correctly refuses it ('link').
  - The `finally` block then sees a pin whose *name* starts with
    `.ke-install.` and runs `Get-ChildItem $pin | Remove-Item -Recurse`
    **through the junction**.

  C W1: victim `[sub keep1]` became `[]`; exit 1. ps1 on Linux is not
  affected, because getcwd returns the real path and the name test fails.
- **Precondition.** A parent that another account can rename entries in. For
  sh it is only warned about; on Windows it is warned about, but see M-6. In
  sh the window is the fork+exec of `chmod`, and inotify or
  ReadDirectoryChangesW signals the moment to strike.
- **Why high.** It is arbitrary recursive deletion of the operator's data, a
  capability the parent's writer did not have before. It goes well beyond
  replacing the target.
- **Fix, sh.** Drop the chmod by name: `mktemp -d` already creates 0700. After
  `cd`, require all of the following before setting `pinned=1`:
  - `pwd -P` equals `$staging`;
  - the directory is **empty** (`ls -A .` prints nothing; a fresh mktemp dir
    always is);
  - `[ -O . ]`;
  - mode `drwx------`.

  If a chmod is wanted, use `chmod 0700 .` after these checks.
- **Fix, ps1.**
  - Set `$script:Pinned` only after `Assert-PrivateDirectory '.'` passes.
  - Before emptying, require `(Get-EntryKind $pin) -eq 'dir'` (not 'link').
  - On Windows, also require the private ACL on the pin.
  - Never enumerate a reparse point.
- **Tests.**
  - sh: a symlink-swap shim with a non-empty operator-owned victim; assert the
    victim is intact.
  - Windows: a junction case, through a seam or a racer as in W1.

## Medium

### M-5 install.sh: window between the real-directory re-check and `chmod 0755` (Q1)
- **A6.** A chmod shim swaps `t` for a symlink to a 0700 victim at the
  `chmod 0755` call. Result: **exit 0** and "installed to t", the victim is
  now **0755**, and the app files sit in `t.moved`.
- **Cross-user.** The racer polls `stat t`, which needs only search permission
  on the parent; the marker `rm` changes the mtime. The window is the
  fork+exec of `chmod`.
- **Impact.**
  - An operator-owned (or, as root, root-owned) directory of the attacker's
    choosing becomes 0755, which exposes 0644 files that relied on a private
    directory.
  - The operator sees a false success.
- **Not acceptable as is: close it** with the cd-and-chmod-`.` variant:
  1. After the moves, set `pinned=0`, so cleanup cannot empty the target.
  2. `cd -- "$target"`.
  3. Require `[ -f "./$claim_marker" ] && [ -O . ]`. The random marker in a
     0700 dir cannot be present in a swapped directory.
  4. `rm -- "./$claim_marker"`.
  5. `chmod 0755 .`.
  6. `cd /`.
- **ps1 on Linux.** It has the same shape: `SetUnixFileMode` follows a link
  after the re-check. The gap is in-process only, so it is Low there, given
  L-15 and the Windows-only use.

### M-6 install.ps1: the Windows shared-parent warning never fires (regression from the GenericWrite/GenericAll mask) (Q3)
- **Cause.** `[System.Security.AccessControl.FileSystemRights]0x40000000` and
  `0x10000000` **throw** in PowerShell, because they are not defined enum
  values (verified directly). The throw happens inside the `try`, and
  `catch { return }` hides it, so `Write-SharedParentWarning` silently
  returns for every parent.
- **Evidence.** C W2 (Everyone CreateDirectories) and W3 (Everyone `GW`) both
  installed with no warning. Round 2 showed this warning firing.
- **Why the test missed it.** The tester's test is static (it greps for the
  constants), so it stays green.
- **Note.** NTFS maps GW to FW when it stores the ACE (W3 shows
  `(A;;FW;;;WD)`), so the generic bits only add value for unmapped ACEs. The
  mask itself is fine once it can be computed.
- **Fix.**
  - Compute the mask as an integer: the named rights cast to `[long]`, then
    `-bor 0x40000000L -bor 0x10000000L`. Test it against
    `[long]$rule.FileSystemRights`.
  - Make the `catch` print "could not check the parent" instead of returning
    silently.
  - Add a behavioural Windows test: an Everyone CreateDirectories ACE on the
    parent produces the warning.

## Low
- **L-15 install.ps1 off Windows checks mode bits only** (Q3).
  - Group or other write without sticky is refused correctly, and a POSIX ACL
    shows up through the group mask bits.
  - A parent **owned by another user**, mode 0755, is accepted. Its owner can
    still rename staging or the target.
  - `Assert-PrivateDirectory` on Linux checks the mode, not the owner, so a
    symlinked attacker-owned 0700 staging passes.
  - Fix: refuse a parent owned by neither the operator nor root, and check the
    owner of `.` (the UnixStat UserId in PS 7.4+, or `stat`).
  - Low because the quickstart restricts install.ps1 to Windows.
- **L-14 (carried).** The Windows target ACL is owner-only; confirm it in the
  live Windows smoke.

## Info
- **I-11 PATH and the `id -u` / `ls -ldn` owner check** (Q4).
  - Both are resolved through PATH. An absolute, attacker-writable entry can
    make `id -u` lie: in A8 a shim made a false warning fire, and answering
    with the parent's uid suppresses a true one.
  - This is not a new exposure. The same entry already controls `docker`,
    `sha256sum`, `cp`, `chmod` and `rm`, so the manifest check itself falls
    to it. The owner check is advisory, and `[ -O . ]` is a builtin.
  - The trust anchor stays the quickstart's clean, absolute, root-owned PATH.
    Optional hardening: pin `PATH=/usr/bin:/bin:/usr/sbin:/sbin` plus the
    docker directory at the top of install.sh.
- **I-12 Cleanup, other paths** (Q2).
  - A failed `cd` exits under `set -e` with `pinned=0`. A5: exit 1, and the
    caller's cwd bait is intact.
  - Inherited EXIT traps do not fire in command-substitution, pipeline or
    paren subshells (A9). The `cd "$root"` inside `refuse_case_clash`
    therefore cannot empty the bundle.
  - `pinned` is set only after the checks, and the main shell never runs `cd`
    after that. Leftover literal globs are harmless under `rm -f`, and
    `rm -rf` does not follow inner links.
  - ps1 on Linux tests the real getcwd name. The remaining ps1 edge: a
    throwing `Set-Location` leaves the pin as the caller's cwd, which is
    emptied only if its name starts with `.ke-install.`. The H-2 Pinned flag
    closes it.

## Checked and clean
- **Secret grep.** I grepped `git diff 1fe81dd` (working tree and index) and
  install.ps1 for AWS, GitHub, Slack and OpenAI keys, private keys, JWTs,
  credentialed URLs and password/secret/token assignments. There are no hits
  beyond the known dummy fixture.
- No tracing or span surface changed.
- **Repo root.** After the audit, `git status --short` shows only this file
  and `security-u2-r3-probes.txt` as new untracked entries.
