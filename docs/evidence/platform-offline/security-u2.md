# Security audit: platform-offline unit 2 (PS-3.1 bundle + installers)

Date 2026-10-19. Auditor: security. Scope: `git diff 1fe81dd` plus untracked
`scripts/bundle.sh`, `scripts/install.sh`, `scripts/install.ps1` and
`tests/test_offline_bundle.py`. Threat model: the bundle is attacker-controlled
until the manifest passes, and `bundle.json` stays untrusted after that.
Probes ran only in `<scratch>`, with a fake `docker` (bash script / `docker.cmd`)
first on PATH and `DOCKER_HOST=tcp://127.0.0.1:1`, so the host daemon could not
be reached. pwsh 7 on Windows 11, Git Bash 5.

**Verdict: PASS** (0 critical, 0 high, 3 medium, 7 low, 2 info)

## Medium

### M-1 TOCTOU between the hash check and docker load / app copy (both installers)
- install.sh:78-86 hashes each file. It reads them again at :197 (`docker load -i`)
  and :217 (`cp -R`). install.ps1 does the same at :109-117, then :222 and :248-250.
  Nothing pins the bytes it verified. Loading 10 GB takes minutes, so the window is wide.
- Anyone who can write the bundle directory while the install runs (a network
  share, removable media, a shared host, or the hardlink in L-3) can swap a tar
  or app/scripts/launch.sh after it passes. The installer then loads the image
  and copies the script with no error. A swapped tar can also embed RepoTags that
  move arbitrary host tags (ke-*:local, postgres:...) during docker load,
  before any check runs.
- Repro (fake docker swaps images/web.tar and app/scripts/launch.sh when it gets `info`):

      SWAP_DIR=<scratch>/sh/B bash B/install.sh <scratch>/sh/tB   -> exit=0
      manifest web.tar: 602decf54da4a7a7...   loaded bytes: 0dc9ae2b681acce6... content=tar-EVIL
      target launch.sh: echo EVIL

- Fix options: (a) copy the bundle into a private staging dir (0700, on the
  target's disk), refuse links/hardlinks there, then verify and load and copy
  only from the staging dir; or (b) open each file once and hash the same
  stream you load or copy, comparing before tagging (and know that load has
  already happened by then). Add a test in which the fake docker mutates the
  bundle after `info`.

### M-2 install.ps1 accepts unhashed files that differ only by case (spec says ordinal)
- install.ps1:74 `$listed = @{}` and :99 `$present = @{}` are PowerShell
  hashtables, which compare keys case-insensitively. In a case-sensitive
  directory, ContainsKey('app/scripts/LAUNCH.ps1') is true when only
  app/scripts/launch.ps1 is listed. The extra file is never hashed (the loop at
  :109 walks only $listedOrder), and :248 copies it into the target.
  Architecture §2.5 requires paths "compared as ordinal strings". install.sh
  (bash associative arrays) refuses the same bundle.
- This is reachable on Windows. Directories created from WSL on /mnt/c are
  case-sensitive by default, and `fsutil file setCaseSensitiveInfo` sets the
  same flag. A genuine manifest still passes, so comparing its hash out of band
  does not catch the extra file.
- Repro (bundle root marked case-sensitive, extra app/scripts/LAUNCH.ps1):

      pwsh -File CS\install.ps1 -Target <scratch>\ps\tCS   -> exit=0, target gets scripts\LAUNCH.ps1
      bash CS/install.sh <scratch>/ps/tCSsh                 -> install: manifest: file is not listed: app/scripts/LAUNCH.ps1

  Variants launch.PS1, lAUNCH.ps1, launcH.ps1, app/Scripts/ and app/sCRIPTS/
  were all accepted. In every probe the genuine content won the overwrite in the
  case-insensitive target, because uppercase variants enumerate first. That
  ordering protects only names that are all lowercase today. It is not a control.
- Fix: build $listed, $present, $entryFile, $entryAs, $svcOwner and $isStack
  with `[hashtable]::new([StringComparer]::Ordinal)` (or a Dictionary with
  Ordinal). Also refuse two present paths that are equal under OrdinalIgnoreCase,
  because the target is case-insensitive. Add a pwsh test with a case variant
  (it runs on Linux in the gates image).

### M-3 Trust anchor: the installer verifies itself, and the out-of-band step is neither documented nor easy to do
- The installers ship inside the bundle they check. Their manifest check gives
  integrity only once the operator has (1) compared sha256(MANIFEST.sha256) with
  a value obtained out of band, and (2) checked that install.sh/install.ps1
  match their manifest lines before running either one. A tampered installer
  simply skips its own check.
- bundle.sh:181-183 prints the hash to the build host's terminal only. Nothing
  persists it next to the bundle for a release record. The installers never
  print the manifest hash they accepted. docs/quickstart.md says nothing about
  manifests yet (requirements.md:1335-1338 *Docs* is pending).
- Not blocking for this unit, because ADR-KE-012 accepts integrity-not-authenticity
  and the docs criterion is still open. MUST be closed before the item closes.
  The quickstart must give the two-step procedure above, including verifying
  the installer with the operator's own tool first (`sha256sum MANIFEST.sha256`
  → compare, then `sha256sum -c --strict MANIFEST.sha256` / `Get-FileHash`).
  Recommended: installers print the accepted manifest hash and optionally take
  `--expect-manifest <sha256>` / `-ExpectManifest`, refusing on a mismatch;
  bundle.sh writes the hash to a file outside the bundle dir.

## Low

- L-1 install.ps1 follows a junction/symlink target (install.ps1:126-133, :247-260).
  install.sh:92-95 refuses a symlinked target, but install.ps1 does not check
  ReparsePoint/LinkTarget on the target. Repro: `mklink /J tJ elsewhere`, then
  `install.ps1 -Target tJ` exits 0 and the files land in elsewhere\.
- L-2 Target check-then-use race (install.sh:92-99 vs :216-228; install.ps1:126 vs :247-260).
  The target is checked before the loads, which take minutes, and created only
  after them. mkdir -p, cp and the `>` override write (and CreateDirectory,
  Copy-Item and WriteAllText) all follow a symlink planted in the meantime,
  which matters in a shared parent dir. Fix: create the target exclusively at
  check time, or stage and rename.
- L-3 Hardlinks pass as regular files (install.sh:63,76; install.ps1:51).
  Repro: app/.env.example with link count 2 to a file outside the bundle →
  exit 0. This lets M-1 be carried out from outside the bundle dir. Fix: refuse
  link count > 1 (`find -links +1`; on Windows, nNumberOfLinks), or stage per M-1.
- L-4 install.ps1 reads MANIFEST.sha256 before the link check (:68 Test-Path
  follows links, and :77 ReadAllBytes runs before Get-BundleFile at :100). A
  symlinked manifest gets read (and a FIFO hangs, on Linux pwsh) before it is
  refused, and its first line is echoed through Format-Safe. install.sh:34 checks
  -L first. Fix: check LinkTarget/ReparsePoint on the manifest before reading it,
  and cap its size.
- L-5 Loaded name not compared with `as` (install.sh:207-210, install.ps1:236-239).
  A genuine tar is saved from `as` (bundle.sh:133), so a `Loaded image:` line
  must name `as` (otherwise accept only the ID form). Requiring that is cheap
  defense in depth against a tar that names another image (e.g. one swapped in via M-1).
- L-6 No protection against a partial install / weak disk floor. The installers
  have no free-space check and no staging. A failure after cp (for example a
  disk filled by the loads on the same volume) leaves a target without
  docker-compose.override.yml. Launching there would fall back to upstream refs
  without pull_policy: never, and a re-run is refused as "not empty". bundle.sh:52
  takes $4 of `df -P`, so a filesystem name containing spaces shifts the
  columns, and "Used" can be read as "Available" (the floor is bypassed, though
  a bundle without a manifest is still refused by install). Fix: stage plus
  atomic rename, and use `df -Pk --output=avail` or $(NF-2).
- L-7 bundle.sh copies config/ wholesale (bundle.sh:139). Untracked or ignored
  files under config/ would ship in the bundle, e.g. a local config/.env.local
  (ignored by `.env.*`, and invisible to `dirty` because `git status --porcelain`
  omits ignored files). Fix: copy `git ls-files -z config`, or refuse untracked
  or ignored files there.

## Info
- I-1 pathRe accepts Windows reserved names (CON, NUL, COM1...) and segments
  ending in `.`. These cannot be exploited while the manifest is genuine,
  because file-set equality catches them. Reject them anyway for parity, so a
  bundle that verifies on Linux cannot resolve differently on Windows. NTFS ADS
  are neither enumerated nor hashed, but `:` cannot appear in a listed path and
  nothing reads ADS.
- I-2 The override and the copied app inherit the operator's umask/ACL. That
  file decides which local image each service runs. Ties to carry N9 (quickstart umask).

## Checked and clean
- No docker call before the manifest passes. Hostile unlisted names
  `$(touch PWNED_C)` and `a]b` were refused, printed %q-escaped and never
  evaluated, and no docker call was made.
- bundle.json → docker args / YAML: every field is matched against a fixed
  anchored pattern ($ / \z, -cmatch, LC_ALL=C). CR, newline, `:`, `#`, quotes
  and spaces outside `services` are all impossible. Services are cross-checked
  against `compose config --services`. `as` cannot be :local, a digest or a
  registry host. Docker is called with quoted args / an arg array, and a loaded
  name starting with `-` is refused. No eval or Invoke-Expression. YAML
  injection is not possible.
- Secret patterns (keys, tokens, private keys, credentialed URLs) grepped over
  the diff and the new files: no hits (only the test literal /etc/passwd).
  .env is not bundled, and dist/ is in .gitignore and .dockerignore. The bundled
  .env.example carries the pre-existing placeholder
  KE_STORES__POSTGRES__PASSWORD=changeme-... (not new; the quickstart must say to change it).
- No tracing/span surface in this unit.

## Probe harness (scratch only)
- `<scratch>/mkbundle.sh` (one-image fixture bundle + manifest),
  `<scratch>/bin/docker` (bash fake; SWAP_DIR mutates the bundle on `info`),
  `<scratch>/winbin/docker.cmd` (Windows fake). Control runs A (sh and ps1)
  installed cleanly and wrote the expected override.
