# Audit: smoke-gate loop 1 fix (D1 + F6), review and security, scoped

Date 2026-10-19. Auditor: security (covering review too, per the orchestrator's scope).
Scope: the delta from round 5 (baseline = scratch `base/`, whose install.sh/install.ps1
hashes equal those in `security-u2-r5.md`) to the current files: `scripts/bundle.sh`
(staged, sha256 `53c5e770...41be6`), `scripts/install.sh` (staged, `d14071df...cf74b`),
working-tree `scripts/install.ps1` (`056afccd...71938`). Index == worktree for the two
staged files. Raw output, delta, mutants, probes: `audit-d1-probes.txt`.

## Verdict

**PASS / APPROVED.** No critical, high or medium finding. Two low findings below; they do not block,
but L-D1a is docs-only and should go into this loop, because the recorded runs are
re-run anyway.

## D1, bundle.sh (jq over `config --format json`)

| Check | Result | How |
|---|---|---|
| No jq injection from service names | **OK.** `--arg s "$svc"` binds the name as a JSON string, and `.services[$s]` is a key lookup. The program text is constant. Also, the name must match `^[a-z0-9_-]+$` before jq runs. | 17 hostile names (`) \| env #`, `$ENV`, `\(env)`, quotes, `..`, newline, empty) were run against a crafted model. Every one is a literal key lookup: missing ones exit 1 with `null`, and the literal `) \| env #` key returns only its own value. |
| Exit statuses | **OK, fails closed.** null/missing → jq 1; a malformed model → 4; `.services` that is an array or not an object → 5; each one reaches `die`. An empty model makes jq exit **0** with no output. Two guards catch it: `[ -n "$model" ]` and then `[ -n "$ref" ]`. An object or array image gives multi-line output and dies on "more than one image". A compose failure is caught by `config --format json ... \|\| die`. | probes `[jq]`, `[jq-model]` |
| Deterministic order | **OK.** `sort` under `LC_ALL=C`. With two fake seeds, bundle.json `images` came out byte-identical. | probe `[order]` |
| jq check before any docker call | **OK.** It is the first command after `cd` (line 51), before `docker info`. With PATH holding no jq: rc 1, "jq is required…", 0 docker calls, empty docker log. | probe `[jq-missing]` |
| Real Compose | Compose v5.1.4 on the dev host (config only, no project touched): `config --images worker` printed valkey + ke-app (D1 reproduced). The jq lookup gave each sorted service exactly its own image. | end of probes file |
| Secrets | The model holds `.env.example` placeholders after interpolation, in memory only. It is never written, logged or traced. A secret-pattern grep of the delta found no matches. | probes file |

## F6, mode normalisation

- **install.sh.** cwd is the pinned, verified staging (`cd` at l.323, with `pwd -P`, owner and 0700 checks). Every path is relative (`app`, `app/scripts`), so no argument can start with `-`. `find` uses default `-P`: `-type d` and `-type f` never match a link, and a link given as a start point is not followed. `refuse_odd .` has already refused links, fifos, devices and sockets. The chmods run before publish and after the override is written. Every exit status ends in `die`. Only the operator can race the staging (it is 0700 in an operator-owned parent).
- **Hardlinks are neutralised by the copy.** `cp -R -P` (no `--preserve=links`) and the ps1 `File.Copy` give each name a fresh inode in staging. Probe: a bundle with hardlinks to an outside 0600 victim (one in `app/`, one in `app/scripts/`) installs rc 0; the victim stays 0600, the target files have different inodes with nlink 1 and get 0644 or 0755. Two hardlinked names inside the bundle become separate inodes, and the bundle source modes are not touched. If a copier did preserve links, both names would still be staging inodes.
- **install.ps1.** `$appDir='app'` resolves against `[Environment]::CurrentDirectory`, which l.263 pins to staging; it is changed again only after publish (l.804). Just before the chmods, `Get-BundleEntry` rescans and refuses non-file/dir entries (via `find`) and links/reparse points (via .NET). `SetUnixFileMode` runs only off Windows. The ps1 hardlink probe passes the same way.

## Tests vs mutants (scratch copies, gates image, no network)

| Mutant | Result |
|---|---|
| M1: restore round-5 `config --images "$svc"` | **killed**, 37 failures, all "more than one image", including all 6 seeds of `test_bundle_maps_each_service_to_own_image_despite_dependencies` |
| M2: all three install.sh find chmods → `:` | **killed**, 3 of 4 subtests of `InstallShTest.test_install_target_modes_ignore_build_host_umask`; the other 43 install tests stay green |
| M2d / M2f / M2s: drop one chmod line each | **killed**, 1 / 3 / 4 subtests |
| M3: install.ps1 mode loop iterates nothing | **killed**, 4 of 4 subtests (pwsh 7.4 off Windows) |
| Control (unmutated) | BundleScriptTest 24 OK; targeted D1 + F6 sh/ps1 OK |

## Findings

- **L-D1a (low, review/docs; route: documenter + architect).** jq is a new build-host
  prerequisite, but the only place it appears is bundle.sh's error message.
  `docs/quickstart.md` (Prerequisites / Offline bundle) never names it, and
  `docs/architecture.md` §2.5 Bundle step 1 (~l.1574) still says that the image list is
  `config --images`, which D1 shows is wrong on Compose 5.x. The developer's handoff line
  says jq is "now a documented build-host prerequisite"; that is not yet true. §2.5
  Install also does not record the F6 mode rule (dirs and `scripts/**` 0755, other
  files 0644).
- **L-D1b (low, tests; route: tester).** No committed test covers (a) refusal when jq is
  absent, before any docker call, or (b) `config --format json` failing, or a service
  with no `image` in the model. The probes show both behave correctly today, but nothing
  stops a regression.
- I-1 (info): the F6 subtest `umask0002 × install umask 022` does not discriminate,
  because `cp` applies the umask. The other subtests kill every mutant. No action.
- I-2 (info, nit): ps1 `Rel.StartsWith('scripts/')` is culture-sensitive. It has no
  effect, because manifest paths are limited to `[A-Za-z0-9._/-]`. `[StringComparison]::Ordinal`
  would be tidier.
