# Security re-audit: platform-offline unit 2, after rework round 2/5

Date 2026-10-19. Auditor: security. Scope: the current `scripts/install.sh`,
`scripts/install.ps1` (still untracked), the `scripts/bundle.sh` and
`scripts/launch.sh` changes, and the offline section of `docs/quickstart.md`.
Checked against `security-u2-final.md` and `architect-u2r2.md`.

Probes ran only in `<scratch>`, with a fake `docker` and
`DOCKER_HOST=tcp://127.0.0.1:1`. No daemon, image, HEAD, index or tracked file
was touched. Environments:
- WSL Ubuntu on ext4, with mawk. This is the authoritative POSIX run.
- Git Bash 5.3 on NTFS.
- pwsh 7.6.7 on Windows 11.

There is no pwsh on Linux outside the gates image, so install.ps1 on POSIX was
judged by reading the code. Raw output: `security-u2-r2-probes.txt`, sections A
to D.

**Verdict: PASS** (0 critical, 0 high, 1 medium, 4 low, 4 info). H-1 is closed.
Nothing open blocks the merge. M-4b is a one-line fix and should go in with this
unit.

## Prior findings, re-probed

| ID | Status | Evidence |
|---|---|---|
| H-1 Windows | **Closed.** Staging and the claimed target were first seen as `O:<me>D:P(A;OICI;FA;;;<me>)`: a protected DACL, one ACE and nothing inherited, under a parent carrying the Authenticated Users `(OI)(CI)(IO)(M)` and `(AD)` ACEs of `C:\`. Both the staging rename and the target rename were refused at info, load, tag and inspect, even for the same user. The genuine tar was loaded and the genuine launch.ps1 published, exit 0. docker ran with its cwd set to the real staging. | D |
| H-1 POSIX (install.sh) | **Closed** for a swap at each docker step: info, compose, load, tag, inspect. In every case the genuine tar was loaded, the genuine files were published and the compose file had no `privileged`. Residual: L-11. | A |
| M-4 | **Partly fixed (M-4b).** An append is ignored. An in-place rewrite still runs. | A |
| L-8 | **Acceptable.** The claim was replaced between the publish check and the first `mv`, by a planted dir or a symlink. Both runs exited 1 ("the claim marker is gone"). The verified app files land in the planted place, and the mode of the symlink target stays untouched (0700). This is detected after the fact, as ruled. | A |
| L-9 | **Fixed.** install.sh refuses `:x`, `x:`, `.`, `bin` and `a::b`, and the planted `mktemp` never ran. install.ps1 refuses `.`, `winbin` and `C:winbin`. On Windows it drops empty entries (by design) and accepts quoted absolute entries. | A, C, D |
| L-10 | **Fixed** for sh: a signal to its own pid gives INT 130, QUIT 131, TERM 143 and HUP 129, with no target and no staging left. The first INT/QUIT pass exited 0, but that was the background-job SIG_IGN artifact: SigIgn was 0 on the re-run. ps1 was judged by reading the code. `Assert-NotInterrupted` follows every docker call, runs on each loop iteration and before publish, and SIGQUIT is registered. | B |

## Answers to the five questions

1. **H-1 on Windows.** Staging and the target are created with their protected
   DACL in one call, so there is no window with an inherited ACE.
   `Assert-PrivateDirectory` then checks the owner and the DACL, on `.` for
   staging (the pinned directory itself) and by name for the target.
   - The claimed target is the same directory that is published: the open
     marker handle and the pinned cwd block renames, and the probe confirmed it.
   - A pre-created target owned by someone else is refused by the owner check
     and is not removed.
   - **WARN rather than refuse is acceptable on Windows.** Integrity no longer
     depends on the parent. The warning is even over-cautious for `C:\`: there
     AU has `AD` but not delete-child, so others cannot rename the protected
     target afterwards.
2. **install.ps1 on Linux/macOS.** The residual is **acceptable as Low (L-12)**,
   because:
   - the quickstart sends Linux and macOS operators to install.sh;
   - the only precondition is a parent that another account can write without
     sticky, and that account can already replace the target after any install;
   - the warning fires.

   It is wider than the spawn-by-name window, though (see L-12). Recommended
   closure, which does not need "refuse non-Windows" (that would remove the
   gates' ps1 coverage): on non-Windows only, install.ps1 should **refuse**,
   rather than warn about, a parent that is group- or other-writable without
   sticky, or that is owned by neither the operator nor root. That removes the
   precondition for every POSIX ps1 race, and the existing test already accepts
   a refusal. Also add one quickstart line: "install.ps1 is for Windows; use
   install.sh on Linux and macOS".
3. **Claim-marker publish.**
   - On Windows, no race is left: the marker is held open, the cwd is pinned,
     and the ACL admits only the operator.
   - On POSIX sh, the remaining windows (claim to marker, and check to `mv`) all
     end in exit 1. Either the marker is missing or `chmod 0755` is refused on a
     directory the attacker owns. A planted symlink is refused by `-L`.
   - A **stray renamed staging** (`.ke-install.*.moved` in my probes,
     `*.swapped` in the tests) is not a security problem. It is owned by the
     operator, mode 0700 and secret-free, and the cleanup `rm -rf` of the
     lookalike under the old name does not follow links. It does keep the image
     tars, which can be gigabytes, and it is evidence of an attack (I-7).
4. **New code.**
   - launch.sh `at_least`: only leading-digit strings, defaulting to 0, reach
     `$((10#...))`, so there is no arithmetic injection. Malformed versions fail
     closed.
   - The `=` prefix in `collect` keeps empty values, so the bind-address refusal
     stays fail-closed. There is no regression from the `mapfile` version.
   - bundle.sh: `%q` is used at line 54. Line 56 prints the raw value only after
     it has matched a literal.
   - bundle.sh `cp -P` on tracked `config/`: a tracked symlink is now copied as
     a link and refused by the existing scan (line 211). `cp -R` on `licenses`
     does not dereference either. The other `cp --` calls copy fixed tracked
     names (I-8).
   - The `[Environment]::Exit(1)` runs only when `$finished` is false, which is
     the stopped-pipeline case. It runs inside `finally` after staging, the
     claim, PATH and the signal registrations are cleaned up, so it fails
     closed. It would close an interactive host session if the script were run
     in-process. The documented `pwsh -File` call is a child process.
5. **Quickstart trust anchor: sufficient.**
   - (a) The Windows example now uses `$HOME\knowledge-engine`, and there is a
     "not directly under C:\ or /opt" rule.
   - (b) Copy off shared media first.
   - (c) `shasum -a 256` (and `-c`) on a Mac.
   - (d) A clean absolute PATH and `bash ./install.sh`.
   - (e) An operator-only parent, with the `/opt/ke` chown recipe.

   Nits:
   - Use `pwsh -NoProfile -File`, as in the script header.
   - Note that Get-FileHash prints uppercase hex.
   - Add the Windows-only line for install.ps1 from item 2.

## Medium

### M-4b The trailing `exit` is still read lazily, so a bundle-dir writer runs code after a successful install
- install.sh ends with `main "$@"` (line 569) and `exit` (line 570) on
  **separate lines**. bash parses and runs line 569, and only then reads line 570
  from the file, at the byte offset where 569 ended.
- Repro (A, `M4-inplace-rewrite-of-trailing-exit`): at `docker info`, the fake
  truncates the bundle's install.sh at the offset of `exit` and writes
  `touch <scratch>/.../INJECTED-rewrite` there. The install ran, `exit=0`, and
  the marker file exists.
- The tester's append-only case passes, because the original `exit` still comes
  before the appended text.
- Precondition: write access to the bundle dir during the run, the M-1 attacker.
  The quickstart's private-copy step now removes this for an operator who
  follows it.
- Fix: put both on one line, `main "$@"; exit`, as ruled in ADR-KE-012 and
  `architect-u2r2.md`. Add a test case that overwrites the bytes after
  `main "$@"` in place, not only one that appends.

## Low

- **L-11 install.sh: gap between `chmod 0700` and `cd`.**
  - Lines 257-262: `mktemp -d`, then an external `chmod 0700 -- "$staging"`,
    then `cd -- "$staging"` **by name**.
  - Repro (A, `H1-chmod-cd-gap`): a `chmod` shim stands in for a racer who
    renames staging and plants a lookalike in that ~1 ms window. The installer
    then works inside the lookalike, and the attacker's post-verification write
    was loaded (`loaded-bytes content=tar-EVIL`, exit 0).
  - Cross-user, the lookalike is owned by the attacker and writable by the
    operator, which inotify on the parent makes practical. The precondition is
    a shared POSIX parent (warned), and that parent's other writers can replace
    the target afterwards anyway.
  - Fix: right after `cd`, check the directory you are in. Use `[ -O . ]`, and
    `ls -ld .` must show `drwx------`. Alternatively run `chmod 0700 .` after
    the `cd`, which fails on a directory someone else owns. Then drop the chmod
    by name.
- **L-12 install.ps1 on POSIX (judged by reading the code).**
  - PowerShell starts native commands in its location by name. `Sync-Pin`
    re-reads `getcwd()` before each docker call, which leaves a sub-millisecond
    window.
  - The publish step has a further gap:
    - it checks the target by name, then moves each entry to `$targetPath/<name>`;
    - `[IO.File]::Delete($markerPath)` **does not throw when the file is missing**;
    - `SetUnixFileMode($targetPath)` **follows a symlink**.

    So a racer who swaps `t` for a symlink after the check gets **exit 0**:
    "installed to t", the verified files moved into a directory of the
    attacker's choosing that the operator owns, and that directory set to 0755.
    The sh twin fails here, because `rm` of the missing marker dies.
  - Fix:
    - Refuse a shared parent on non-Windows (item 2).
    - Assert `File.Exists($markerPath)` before deleting it.
    - Re-check `Get-EntryKind $targetPath -eq 'dir'` immediately before
      `SetUnixFileMode`.
- **L-13 install.sh under Git Bash/NTFS** (C):
  - `mkdir -m 0700` fails with "cannot change permissions", the install exits 1
    and an empty target dir is left behind (`claimed` is set only after mkdir
    succeeds).
  - It fails closed, and Windows operators are directed to install.ps1. Either
    remove the dir when the claim step fails, or state that install.sh on
    Windows is unsupported.
- **L-14 The Windows target ends up owner-only** (D: the target ACL after
  install is `D:P(A;OICI;FA;;;<me>)`, so SYSTEM and Administrators have no ACE).
  This is good for confidentiality, but backup or AV agents and Docker Desktop
  bind mounts that run as SYSTEM may lose access. Confirm it in the live
  end-to-end smoke on Windows before shipping.

## Info

- **I-7** The renamed staging is left behind after an attack on POSIX (Q3).
  Optionally empty `.` while still pinned in the EXIT trap (for example
  `find . -mindepth 1 -delete`) before `cd /`, and print a line naming the
  attack.
- **I-8** Other bundle.sh `cp --` sources are fixed tracked names; a tracked
  symlink there would be dereferenced. Repo review covers it.
- **I-9** `scripts/install.ps1` is **untracked**, while install.sh and bundle.sh
  are staged. It must be added in the commit, because bundle.sh copies it and
  the tests use it.
- **I-10** Over-reporting: the Windows warning fires for parents like `C:\`
  (AU `AD`), and the POSIX warning fires for `1777` parents because the group
  `w` bit is set. Both are acceptable over-reporting.

## Checked and clean
- **Secret grep.** I grepped `git diff 1fe81dd`, install.ps1 and the evidence
  `.txt` files for AWS, GitHub, Slack and OpenAI keys, private keys, JWTs,
  credentialed URLs and password/secret/token assignments. The only hit is
  `KE_STORES__POSTGRES__PASSWORD=REALSECRET` in the committed unit-1 evidence
  `security-l5-probes.txt`, which is a dummy probe fixture.
- No tracing or span surface changed in this unit.
