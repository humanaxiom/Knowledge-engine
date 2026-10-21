# Review: platform-offline unit 2, final re-review after rework round 1 (+ arch, macOS portability), 2026-10-19

Reviewer. Base 1fe81dd; working tree on agent/platform-offline (uncommitted).
Read: `git diff 1fe81dd` (.gitignore, .dockerignore, tests/fake_docker.py, docs) and the untracked
scripts/bundle.sh, scripts/install.sh, scripts/install.ps1, tests/test_offline_bundle.py,
docs/quickstart.md. Checked against PS-3.1 (+ additions, arch, macOS), PS-3.2 *Docs*, §2.5, ADR-KE-012,
review-u2.md and security-u2.md. Raw probe output: `review-u2-final-probes.txt` (same dir).

Verdict: **CHANGES REQUESTED** (2 blocking, both cheap). The integrity core (staging, manifest
rules, arch, ordinal paths, trust anchor) is sound, and every earlier finding is fixed.

## Verify
- `COMPOSE_PROJECT_NAME=ke-review-u2f scripts/verify.sh fast`: `== verify fast: PASS ==`, Ran 501 tests OK (`review-u2-final-verify-fast.txt`).
- Developer full run (not re-run): `green-arch-verify-full.txt`, `== verify full: PASS (261s) ==`.
- Scratch baseline in ke-gates (network none): `tests.test_offline_bundle` Ran 66, OK.

## 1. Earlier findings: all fixed
| Finding | Status | How verified |
|---|---|---|
| B1 link/dot-dot unpinned | fixed | m3, m4, p3 now caught (dotdot/dot; symlink, unlisted dir/file symlink, fifo, manifest link/fifo) |
| B2 compose config in docs | fixed | requirements.md:1257, architecture.md:1779 (coverage only) |
| N1 ps1 fifo | fixed | find pre-pass on Linux; `unlisted_fifo` case |
| N2 link message path | fixed | bundle-relative path; cases assert it |
| N3 ps1 target link | fixed | `Get-EntryKind` refuses link targets |
| N4 dead `seen_as` | fixed | removed, comment explains |
| N5 ordinal tables | fixed | Dictionary/HashSet with `StringComparer.Ordinal` |
| N6 compose exit status | fixed | `$(...) or die` in bundle.sh:107 and install.sh:383 |
| N7 untested paths | fixed | unpinned third-party, unknown service, zero loads, sha12 vs git_sha |
| N8 GiB | fixed | "10 GiB", rounded down |
| M-1 TOCTOU | fixed | staging; st1/st2/st3 (load or copy from the bundle dir) caught |
| M-2 case | fixed | ordinal + listed-collision refusal in ps1 (and sh via awk) |
| M-3 trust anchor | fixed | prints hash, `--expect-manifest`/`-ExpectManifest`, `<out>.manifest.sha256`, quickstart steps |
| L-1..L-7, I-1, I-2 | fixed | per security-u2.md; tests listed in the handoff |

## 2. Mutants (scratch copies, ke-gates, network none)
Caught: m3, m4, p3; a1/a2 (installer arch check), a3 (bundle image arch), a4 (`--arch` assertion);
c1/c2 (1 MiB cap); st1/st2/st3 (staging bypass); i2 (`Environment.Exit(1)` on a stopped pipeline);
sh1 (shasum fallback).
Survive:
- mv1 (post-mv check removed), mv2/mv3/mv4 (pre-mv link checks removed too). Equivalent under
  the L-2 hook: a symlink planted at the target is refused by `rmdir` (ENOTDIR) anyway. The window
  between `rmdir` and `mv` cannot be reached by a docker hook. Accept; security owns the mv-window ruling.
- st4 (staging re-scan removed). Redundant with the root scan unless an entry is swapped between
  scan and copy. Accept.
- **i1 (`[KeInterrupt]::Install()` removed) survives the suite.** See RB1.

## 3. Blocking
- **RB1 install.ps1 swallows SIGTERM/SIGHUP sent to its own pid, then publishes and exits 1.**
  The handler sets `Fired` and cancels, but nothing reads `Fired` until the end. Probe: SIGTERM to
  the pwsh pid during `load` -> the install runs on, **publishes the target**, exits 1 with no message
  (8 s; SIGHUP the same). install.sh in the same case exits 143 after the current step and publishes
  nothing. The existing test signals the whole process group, which also kills the docker child, so
  it cannot tell; that is why i1 survives. Without the handler, SIGTERM to the pid and SIGHUP leave
  staging behind (probe), so the C# is needed but not pinned.
  Also: the registrations are never disposed and `Fired` is never reset. Run in-process
  (`.\install.ps1` in an open prompt, which the quickstart shows), the session afterwards ignores
  SIGTERM/SIGHUP, and a later clean run in that session publishes and exits 1 (probe).
  Fix (developer): check `[KeInterrupt]::Fired` after every docker call and before publish, and
  throw "install: interrupted". `Install()` resets `Fired`; dispose the registrations in `finally`.
  Test (tester): SIGTERM and SIGHUP to the installer pid only, during load. Expect non-zero, no
  target, no staging, for sh and ps1. This test also kills i1.
- **RB2 The quickstart's commands fail as written** (PS-3.2 *Docs*; documenter, with one
  developer action):
  (a) macOS: "follow steps 3 to 5". Step 5 `scripts/launch.sh` uses `mapfile` (bash 4) at
  launch.sh:61,63 and `sort -V` at :27, so it fails under stock /bin/bash 3.2. Q53 is open, and an
  air-gapped Mac cannot install a newer bash. State the limitation, or resolve Q53 first.
  (b) Windows: `.\install.ps1` in Windows PowerShell 5.1 (the default `powershell.exe`) dies with a
  C# compile error at Add-Type (probe). It needs pwsh 7. Document `pwsh -File .\install.ps1 ...`,
  the interface the tests and the script header use. That also keeps the RB1 handlers out of the
  user's session. Add a `#Requires -Version` line for the lowest pwsh the script really needs:
  `CreateDirectory(path, UnixFileMode)` is .NET 7, so pwsh 7.3+ on Linux.
  (c) `scripts/bundle.sh ...` and `./install.sh ...` need the exec bit. Both files are untracked,
  and `core.filemode=false` here, so a plain `git add` commits them 100644. A Linux checkout then
  gets "Permission denied", and FAT/zip carriage strips the bit anyway. Use `bash scripts/bundle.sh`
  and `bash install.sh` (the scripts' own usage lines). Also commit with `git add --chmod=+x`,
  pinned by a test on `git ls-files -s`.
  (d) `/opt/knowledge-engine`: staging is created in the target's parent, so a non-root operator
  gets "cannot create a staging directory in /opt". Say the parent must be writable and must have
  free space for the whole bundle.

## 4. sh / ps1 parity
Same order, rules, messages and refusals for the manifest, arch, bundle.json, services, load,
override and publish. Differences:
- Interrupt: RB1. sh has no HUP trap. It still cleans up through EXIT in the probe but dies by the
  signal (nit P1).
- Case collision on case-insensitive staging (NTFS bind mount, standing in for APFS): both fail
  closed and clean up. ps1 says "paths differ only by case"; sh prints a raw `cp: ... File exists`
  (GNU cp 9.1). §2.5 wants the rule named. BSD `cp -n` may skip silently, which is still safe,
  because the staged file set is then checked (nit P2).
- Publish: ps1 `Directory.Move` refuses an existing destination. sh `mv` may move into a planted
  dir and is post-checked (accepted design; security to judge).
- ps1 prints `scripts\launch.ps1` as the next step even on Linux pwsh (nit P3).

## 5. Add-Type KeInterrupt (question 3)
- Justified: yes. Without it, SIGTERM to the pid and SIGHUP leave `.ke-install.*` behind (probe).
- Minimal: yes (3 registrations and a flag; a single-quoted here-string, so nothing is interpolated).
  The comment's "Ctrl+Break" claim is wrong: SIGQUIT is not registered (nit P4). Not minimal in
  lifetime: RB1.
- Fail-safe: yes. In Windows PowerShell 5.1 the compile error, and in ConstrainedLanguage "Cannot add
  type", both stop the script before the `try`. No staging, no docker, rc 1. The messages are
  cryptic, though; RB2(b)'s `#Requires` gives a clear one. Under WDAC a trusted (signed) script runs
  in FullLanguage and compiles. Not proven here: the Windows Ctrl+C path (no console in CI).

## 6. Portability tests vs a real Mac (question 4)
The forbid list is self-checked and install.sh is clean. It still misses bash 4+ forms such as
`[[ -v`, `${x@Q}`, negative subscripts `${a[-1]}`, `$EPOCHSECONDS`, `printf '%(...)T'` and `local -`
(nit P5). The shim run is bash 5 `--posix` plus GNU tools that refuse GNU options. It does not
model the following:
- BSD semantics: `cp -n` exit status, `cp -R src/.`, BWK awk, `wc` padding (handled), and `"${a[@]}"`
  on an empty array under `set -u` in bash < 4.4 (install.sh guards the only array that can be empty).
- macOS facts that would break a real install:
  - `/tmp` is a symlink, so `install.sh ... /tmp/x` is refused ("the target's parent is a link").
  - Finder `.DS_Store` and AppleDouble `._*` files (browsing, exFAT/FAT USB carriage) are refused as
    "file is not listed".
  - On Windows, OneDrive placeholder files are reparse points and are refused.
  - The quickstart should warn about all three (nit P6).
- Launch on the Mac fails (RB2a).
The manual Mac proof must stay on the item's close list.

## 7. Nits
- P1 install.sh: add `trap 'exit 129' HUP` for parity.
- P2 install.sh: map a failed staging copy to "paths differ only by case", or pre-check source names
  with an awk `tolower` pass.
- P3 ps1 next-step line: use the platform separator.
- P4 KeInterrupt comment: drop "Ctrl+Break", or register SIGQUIT.
- P5 forbid list: add the forms listed in section 6.
- P6 quickstart: macOS `/tmp`, `.DS_Store`/`._*`, OneDrive. Also give `shasum -a 256 -c MANIFEST.sha256`
  for step 2 on a Mac, and say that bundle.sh needs a bash 4/GNU (Linux) build host.
- P7 install.sh:193-196: the comment says linear, but `is_listed` runs awk once per present file over
  the whole manifest, which is O(files x manifest), up to ~15k awk runs at the cap and only on a
  hostile bundle. One awk pass over the find list would be linear.

## Conformance (no finding)
- No docker before the manifest passes (both installers). Arch is refused before `compose config`
  and before any load.
- No eval or Invoke-Expression; argv arrays; bundle.json fixed patterns. No secrets in the diff.
- Observability: shell/pwsh scripts only; no agent loop, model, retrieval or tool call, so no span is
  needed.
