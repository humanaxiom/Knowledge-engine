# Security re-audit: platform-offline unit 2 (bundle + installers), final

Date 2026-10-19. Auditor: security. Scope: `git diff 1fe81dd` plus the untracked
`scripts/bundle.sh`, `scripts/install.sh`, `scripts/install.ps1`,
`tests/test_offline_bundle.py` and `docs/quickstart.md`. This covers the arch
checks, the bash 3.2/BSD rewrite of install.sh and the Add-Type interrupt handler.
Threat model as in `security-u2.md`: the bundle is attacker-controlled until the
manifest passes, and `bundle.json` stays untrusted after that.

Probes ran only in `<scratch>`, with a fake `docker` first on PATH and
`DOCKER_HOST=tcp://127.0.0.1:1`. No host daemon, image, HEAD or tracked file was
touched. Environments:
- Git Bash 5.3 on Windows/NTFS.
- WSL Ubuntu on ext4 with `awk` pointed at mawk, which gives real Linux symlink,
  cwd and rename semantics.
- pwsh 7.6.7 on Windows 11.

Raw output, redacted: `security-u2-final-probes.txt` (sections A to G).

**Verdict: FAIL** (0 critical, 1 high, 1 medium, 3 low, 4 info). H-1 blocks the merge.

## Prior findings: status (re-probed)

| ID | Status | Evidence |
|---|---|---|
| M-1 hash-then-load TOCTOU | Fixed for writers of the bundle dir. The fake docker swapped `images/web.tar` and a launch script after `info`; the installer still loaded `tar-genuine` and published the genuine script. A writer of the target's **parent** has a new route: see H-1. | A, B, D |
| M-2 ps1 case-insensitive keys | Fixed. In a case-sensitive dir, an unlisted `LAUNCH.ps1` beside the listed file is refused as "paths differ only by case" (E). sh on ext4 refuses it as "file is not listed" (B). | B, E |
| M-3 trust anchor | Code half fixed. A wrong expect value is refused with both values and no docker call. A malformed value is a usage error. Uppercase hex is accepted. The accepted hash is printed. bundle.sh writes `<out>.manifest.sha256` outside the bundle (by inspection plus the tests). Docs half: present, with gaps (Quickstart, below). | A, B, D |
| L-1 junction/symlink target | Fixed. A junction as the target, and a junction as the parent, are both refused and nothing is written. | D |
| L-2 target planted during load | Fixed. A symlink planted at the target during `load` gives "the target became a link"; nothing is written through it. Residual mv window: see L-8. | B |
| L-3 hardlinks | Fixed. Bytes are read once into staging, so the hardlink partner plus the swap had no effect. | A, B |
| L-4 manifest link/FIFO | Fixed. A junction named MANIFEST.sha256 is refused before any read. sh classifies entries with `find` before it opens anything. | D |
| L-5 loaded name vs `as` | Fixed in sh and ps1. | B, D |
| L-6 partial install / df | Fixed. A failed load leaves no target and no staging. df is parsed by shape. | B |
| L-7 untracked config | Fixed (`git ls-files -z -- config`). Nuance in I-4. | inspection |
| I-1 reserved names | Fixed in sh and ps1: `NUL.txt`, `lpt9`, `Com3.x`, trailing dot, `:`. | A, B, E |
| I-2 override mode | Fixed. sh uses `chmod 0644`; ps1 uses SetUnixFileMode. On Windows the override inherits the staging DACL, which grants the current user only. | inspection |

## High

### H-1 Staging can be swapped after verification; on Windows the documented target lets any local user do it
- Both installers verify staging and then reach it again by its **absolute
  path**, which is resolved by name each time:
  - sh: `docker load -i "$staging/$file"` (install.sh:411), `--project-directory "$staging/app"` (:383), `mv -- "$staging/app"` (:460);
  - ps1: `Join-Path $staging ...` (install.ps1:424-434, :453), `Directory.Move($appDir, ...)` (:512).
  Anyone who can rename entries in the target's parent can rename the verified
  staging dir away and put a lookalike under the same name. The installer then
  loads the attacker's tars, publishes the attacker's compose file, prints the
  accepted (genuine) manifest hash and exits 0.
- **Windows makes this reachable by a local user who has no other access.**
  install.ps1:142-150 creates staging with `CreateDirectory`, which inherits the
  parent's ACL, and only afterwards protects it with Get-Acl/Set-Acl. The
  quickstart's own example, `-Target C:\knowledge-engine`, puts staging directly
  under `C:\`. On this host `C:\` grants `Authenticated Users:(OI)(CI)(IO)(M)` and
  `(AD)` (G).
  - Captured on a scratch parent with those ACEs: the staging dir was first seen
    as `D:AI(A;OICIID;0x1301bf;;;AU)...` (E, acl-window), i.e. Authenticated Users
    have Modify, including DELETE, until Set-Acl runs. A crude PowerShell poller
    caught the window.
  - A handle opened in that window keeps DELETE after the DACL changes, because
    Windows checks access when a handle is opened.
  - `C:\` lets any user create folders. The attacker can therefore rename staging
    later and create the lookalike, which then belongs to them.
  - The published target is that attacker-owned directory, so they keep control
    after the install.
- Repro (same user; the fake docker renames staging at `info` and plants a lookalike):
  - sh, Linux semantics (B): `exit=0`, `loaded-bytes content=tar-EVIL`, published `launch.sh` is `echo EVIL`, and the compose file has `privileged: true`.
  - ps1, Windows (E): `exit=0`, `loaded content: tar-EVIL`, published `launch.ps1` is `Write-Host EVIL`, and the compose file has `privileged: true`.
- Impact: the integrity guarantee of M-1/M-3 is bypassed in the documented
  Windows setup, while the installer reports success. A privileged compose file
  run through Docker Desktop executes code as the operator, which amounts to a
  local privilege escalation. On POSIX the same attacker can already replace the
  target after the install, so there the extra exposure is small. It still
  matters in sticky dirs and for the misleading "matches" message.
- Introduced by the M-1 rework: staging is new.
- Fix:
  1. ps1: create staging with its protected DACL in one call, for example
     `[System.IO.FileSystemAclExtensions]::Create([IO.DirectoryInfo]$path, $sec)`.
     That call is a no-op when the directory already exists, so afterwards check
     that the owner is the current user and that the DACL is exactly the
     intended one.
  2. Pin staging for the rest of the run:
     - Windows: make staging the process's current directory
       (`[Environment]::CurrentDirectory` and `Set-Location`). The OS then
       refuses to rename it (no FILE_SHARE_DELETE).
     - bash: after `cd "$staging"`, use relative paths only (`./$file`,
       `./app`). The cwd follows the inode on Linux and macOS.
  3. Quickstart: the Windows example should use a parent only the operator can
     write (for example `$env:USERPROFILE\knowledge-engine`). The installers
     should refuse, or at least warn about, a parent that others can write
     (POSIX: `-perm -0002` without the sticky bit, or group-writable; Windows:
     write or AD rights for principals other than the user, Administrators and
     SYSTEM).
  4. Tests:
     - The fake docker renames staging at `info` and plants a lookalike (sh and
       ps1). Install must refuse, or load only the verified bytes.
     - A ps1 test (it can run on Windows hosts only) asserts that staging never
       carries an inherited ACE.

## Medium

### M-4 install.sh is read lazily from the bundle dir, so a bundle-dir writer can change it after the operator checked it
- The quickstart has the operator hash install.sh (step 3.2) and then run
  `./install.sh` from the bundle dir. bash reads a script as it executes it, so
  changes made to the file while it runs are picked up.
- Repro (C): the fake docker appends `touch <scratch>/INJECTED` to the bundle
  copy of install.sh at `info`. The install finished and `INJECTED` exists. The
  injected code ran after verification, from a file the operator had already
  checked.
- The precondition is the M-1 attacker (a share, removable media or a shared host).
- ps1 parses the whole file before it runs, so only the gap between the
  operator's check and the run applies there.
- Fix:
  - Wrap the body of install.sh as `main() { ... }; main "$@"; exit`, so bash
    parses all of it before running anything.
  - Quickstart: if the bundle is on media or a share that others can write,
    first copy it to a directory only you can write, then verify, then run.

## Low

- **L-8 Post-checked mv publish (no mv -T).** Racer in the window (B):
  - Planted directory: the app lands at `target/app` inside it. Planted symlink:
    the app lands in the symlink's target (`victimdir/app`).
  - Either way the installer refuses afterwards with exit 1. It leaves the
    misplaced copy behind.
  - What leaks: only verified, secret-free app files, under the fixed name
    `app`, written as the installing user to a place the racer chose.

  "Detected after, not prevented" is acceptable here. The racer needs write
  access to the parent, and that same attacker class (H-1) can do more once H-1
  is fixed. Portable alternative that is atomic:
  - Claim the target at step 1 with `mkdir -m 0700 -- "$target"`. That call is
    exclusive, does not follow a final symlink, and works on POSIX and BSD; an
    existing empty target is removed with rmdir first.
  - Stage inside the claimed directory, rename entries within a 0700 directory
    only the operator can write, and `chmod 0755` last as the publish step.

  This also closes the step-1 to step-9 check-then-use gap. Other options:
  - A perl one-line rename(). rename(2) never moves into a directory and
    replaces only an empty one. perl ships on macOS and most Linux hosts.
  - `mv -T` when `mv --version` reports GNU.

  An `ln -s` publish does not help, because the target must not be a link.
- **L-9 Relative PATH entries run bundle code before verification.** With
  `PATH=":$PATH"`, an executable `mktemp` in the bundle root ran (`PWNED_PATH`
  exists) before the manifest check refused the file (C). install.sh resolves
  tools from the operator's cwd, which is the bundle root, and later from
  staging. Fix: at the top of install.sh, refuse or strip empty, `.` and
  relative PATH entries. ps1 never searches the cwd for native commands.
- **L-10 install.ps1 interrupts.** By code reading; I did not probe it, because
  there is no Linux pwsh outside the gates image.
  - `KeInterrupt.Handle` sets `Cancel=true` for SIGTERM and SIGHUP, and nothing
    else stops the script. If one arrives between docker calls (for example
    while it hashes), the install runs on, publishes, and exits 1.
  - SIGINT works only because pwsh's own handler stops the pipeline.
  - Ctrl+Break (SIGQUIT) is not registered, so it kills the process without
    cleanup and leaves staging behind (private, no secrets).
  - Fix: throw when `[KeInterrupt]::Fired` is set, at every step boundary and
    on each loop iteration, and register SIGQUIT.
  - Test: send SIGTERM to pwsh alone during hashing (a large staged file);
    expect no target and exit 1.

## Info

- **I-3 `cp -R -P -n` differs from section 2.5.** The architecture says copies
  use `set -C` plus `cat`, which refuses case-only collisions. Behaviour of `-n`:
  - BSD/macOS `cp -n` skips silently.
  - GNU coreutils 9.x warns "behavior of -n is non-portable" on every run (B),
    and 9.2-9.4 exit 1 on a skip.

  Safety holds anyway. On a case-insensitive staging volume the first entry
  written decides both the name and the content, so a variant written first is
  refused as unlisted, and one written second is dropped. Neither reopens M-1
  or L-3, because each byte is still read once, into staging. BSD `cp -R`
  re-creates FIFOs and devices and does not follow links, and `refuse_odd`
  catches those on staging. `find` is used only with `-type`/`-print0`.
  Align the doc or the code. Plain `cp -R -P` into a fresh, empty staging is
  also safe, because the later hash check catches an overwrite.
- **I-4 bundle.sh**
  - Line 54 prints the raw daemon Architecture on refusal; use `%q`. A remote
    context daemon is the source.
  - Line 185 copies with `cp --`, which follows a tracked symlink under
    `config/` and would bundle its target's content. Use `cp -P`, so the
    existing "neither a file nor a directory" refusal fires.
- **I-5** The unlisted-file check (install.sh lines 257-265) depends on
  errexit + pipefail to propagate `die` out of the piped subshell. Add an
  explicit `|| exit 1` for robustness on bash 3.2.
- **I-6 Arch values from docker info.** They are handled correctly, as
  untrusted input:
  - Exact match against 4 literals.
  - Rejected values are printed with `%q` (sh) or Format-Safe (ps1). A newline,
    an escape sequence or a trailing space is refused with no load (B, D).
  - The arch-mismatch message prints the raw value only after it has matched a
    literal.

## New surface: judgements

- **awk manifest checks.** No injection. The program text is constant, and the
  only data enters through `ENVIRON["KE_PATH"]`, never `-v`, so there is no
  escape processing. Hostile unlisted names (a `$(touch PWNED)` name, a literal
  backslash-n, a double quote, a `]`) were refused, printed with `%q`, and
  nothing ran (B, under mawk).
- **Locale.** `LC_ALL=C` is exported, so `tolower`, ranges and `sort` are
  byte-wise. Listed paths are ASCII after the bash regex, so they match the ps1
  `ToLowerInvariant`.
- **NUL.** bash `read` drops a NUL that awk keeps. That only matters for a
  tampered manifest, which the expect value already rejects; even then it fails
  closed (C).
- **CRLF** is refused by the character rule.
- **Add-Type.** It compiles a constant, single-quoted here-string with no
  interpolation, so no untrusted input reaches the compiler. Under
  ConstrainedLanguage (and therefore WDAC/AppLocker script enforcement) Add-Type
  is refused at line 167, before staging exists. Nothing is created and pwsh
  exits non-zero (F). That is fail-safe, but install.ps1 is unusable under CLM;
  most of its .NET calls would be blocked there too. Document it.
- **Quickstart trust anchor.** The order is correct: compare the manifest hash
  out of band, check the installer, then run with the expect value. It is not
  sufficient yet:
  - (a) The Windows example target is the H-1 vector.
  - (b) It does not say to copy the bundle off shared or writable media before
    verifying (M-4).
  - (c) On a Mac, step 2 needs `shasum -a 256 -c MANIFEST.sha256`, because
    `sha256sum` may be absent. Note that Get-FileHash prints uppercase.
  - (d) It should say to run `bash ./install.sh` with a PATH that has no
    relative entries (L-9).
  - (e) It should state that the target's parent must be writable only by the
    operator.

## Checked and clean
- **Secret patterns.** I grepped the diff and the new files (5,299 lines) for
  AWS, GitHub, Slack and OpenAI keys, private keys, JWTs, credentialed URLs and
  password/secret/token assignments. The only hit is the test fixture
  `KE_SECRET=local-only` used by the L-7 test.
- `dist/` was added to `.gitignore` and `.dockerignore`.
- The edits to existing tests weaken no security assertion.
- There is no tracing or span surface in this unit.
