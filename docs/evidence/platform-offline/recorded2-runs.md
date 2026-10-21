# Recorded offline runs, round 2: after the D1/F6 fixes (2026-10-19)

Tester, plan item `platform-offline`. Tree: HEAD `1fe81dd` plus the uncommitted
working tree with the D1 fix in `bundle.sh` (jq) and the F6 fix in the installers
(`bundle.json` `"dirty": true`). This round used **no D1 filter and no docker
shim**: the real `bundle.sh`, with plain `docker` on aria-gb10. The steps follow
`docs/quickstart.md` § Offline bundle as it now reads (F1-F5).
Transcripts: `recorded2-amd64.txt` and `recorded2-arm64.txt` (home paths `<home>`).

## Verdict

- **arm64 (aria-gb10): PASS end to end with the real bundle.sh.** D1 is fixed on
  real Compose v5.2.0: each service maps to its own image. F6 holds: on a
  umask-0002 host, the installed tree is dirs and scripts 0755 and other files
  0644, with no violations.
- **amd64 (WSL): BLOCKED at step 3.** jq is not installed in the WSL build host
  (`dpkg -s jq`: not installed). Per the brief, nothing was installed. bundle.sh
  refused cleanly (rc=1, `bundle: jq is required on the build host …`) and wrote
  nothing (no `dist/`).
- **Arch refusal (amd64 bundle on aria-gb10): NOT RUN.** There is no amd64
  bundle. The round-1 refusal proof (recorded-arm64.txt R0-R7) still stands.
  Neither fix touches the arch check.

## Hosts

| | amd64 | arm64 |
|---|---|---|
| Host | dev host, WSL Ubuntu (bash 5.3.9, git 2.53, umask 0022) | aria-gb10, Ubuntu 24.04.5 aarch64 (bash 5.2.21, git 2.43, **umask 0002**) |
| jq | **absent** | jq-1.7 |
| Engine / Compose | not reached (no docker call before the jq check) | 29.6.2 overlay2 / v5.2.0 |
| Project, ports | n/a | `ke-proof2-arm64`, 127.0.0.1:47180/47181 (checked free) |
| Bundle | none written | 2.4 GiB (2,538,497,592 B), 19 files, manifest `5d543ef5…dce0e3` |

The arm64 image tar sizes are byte-identical to round 1: ke-app 325,377,536,
ke-gateway 55,294,976, neo4j 613,846,528, phoenix 1,028,783,616, postgres
472,081,408 and valkey 42,995,712 bytes. bundle.json lists the images in sorted
order (`api worker -> ke-app`, `gateway -> ke-gateway`, each vendor service to
its own pinned ref) with arch `arm64`, and all 6 images are linux/arm64.

## Steps (rc, wall time)

| Step | amd64 (WSL) | arm64 (aria-gb10) |
|---|---|---|
| 0 build-host prereqs (`jq --version`, docker, ports, clash) | **jq missing**, stop | PASS (jq-1.7; ports free; no clash) |
| 1 copy the tree (with .git; no .venv, dist) | PASS 4 s | PASS 6 s (tar over ssh) |
| 2 `bash scripts/build.sh` | skipped (cannot help the jq check) | PASS 2 s (cached) |
| 3 `bash scripts/bundle.sh --out dist/bundle-<arch>` (real, no filter) | **FAIL rc=1 0 s**: jq required; nothing written | **PASS 11 s** |
| 3e/3f bundle facts; build-host modes | n/a | arch arm64, 6/6 linux/arm64; modes 775 d, 664/644/755 f, tars 600 |
| 4 copy bundle + record into a private 0700 dir | n/a | PASS 1 s |
| 5a `sha256sum -c bundle-arm64.manifest.sha256` from the bundle's parent (F5) | n/a | PASS 0 s (`bundle-arm64/MANIFEST.sha256: OK`) |
| 5b `sha256sum MANIFEST.sha256` vs the record (by eye) | n/a | PASS (equal) |
| 5c `sha256sum -c --strict MANIFEST.sha256` | n/a | PASS 1 s (18 OK) |
| 6 `bash ./install.sh --expect-manifest <sha> <0700 parent>/ke`, PATH=/usr/local/bin:/usr/bin:/bin, umask 0002 | n/a | PASS 3 s |
| 6c installed modes (see below) | n/a | **PASS**, 0 violations |
| 7 `.env` from `.env.example`, both secrets `openssl rand -hex 24` (48 hex, never printed), ports 47180/47181 | n/a | PASS (`name: ke-proof2-arm64`, `pull_policy: never` x7) |
| 8 `bash scripts/launch.sh` (COMPOSE_PROJECT_NAME exported) | n/a | PASS 17 s, 7/7 healthy from bundle tags |
| 8b /healthz, /readyz, Phoenix | n/a | 200 / 200 ready (model_host not_configured) / 200 |
| 9 `bash scripts/smoke.sh` on the running stack | n/a | PASS 2 s (outage check skipped by design) |
| 10 `bash scripts/teardown.sh` | n/a | PASS 14 s |
| 11 `bash scripts/smoke.sh` on the stopped project | n/a | PASS 40 s (launch, readyz reports postgres down, ready again, teardown) |
| 12 `bash scripts/teardown.sh --volumes` | n/a | PASS 0 s (4 `ke-proof2-arm64_*` volumes removed) |
| 13 leftovers (project, and `knowledge-engine`) | n/a | none |
| Arch refusal | n/a | **NOT RUN** (no amd64 bundle) |
| Cleanup | PASS: proof dirs, tools, logs removed; dev daemon has no bundle/ke-vendor tag, no ke-proof volume/network | PASS (below) |

## Installed modes on aria-gb10 (umask 0002 for both the build and the install)

The bundle on the build host, before install, still carried umask-0002 modes:
6 directories 0775, `bundle.json` and `MANIFEST.sha256` 0664, image tars 0600,
`install.sh` 0755, other files 0644. bundle.sh does not normalise modes; the
installers do.

The installed target, `find . -printf "%m %y %p"`:
`.`, `config/`, `docs/`, `scripts/` are 0755 (4 dirs). The 5 files under
`scripts/` (launch/teardown .sh/.ps1, smoke.sh) are 0755. `config/defaults.yaml`,
`docker-compose.yml`, `docker-compose.override.yml`, `docs/quickstart.md` and
`.env.example` are 0644. The rule check (dirs 0755, `scripts/*` 0755, other files
0644, no non-file/dir entries) found 0 violations. The private parent stayed
0700.

## Cleanup (human-approved)

- aria-gb10: untagged the 6 `ke-*:bundle-1fe81ddbfb60` / `ke-vendor/*` tags.
  `docker ps -a --filter ancestor=…` (by id and by ref) showed no container on
  `ke-app|ke-gateway|ke-gates:latest`, the 4 pinned vendor images, or the 2
  dangling build outputs. All of them were removed. The dangling pair
  `64676a69…` (ke-app) and `d2b5d004…` (ke-gates) was Created 18:50:50Z, inside
  round 1's build step, and before round 1 only `*:probe-arm64` ke images
  existed (recorded-arm64.txt 0c). Kept: `ke-{app,gateway,gates}:probe-arm64`
  and every other image. Proof, tools and log dirs were removed. The image list
  diff from before the run shows only those removals.
- Dev host: no docker command ran in WSL. The proof, tools and log dirs were
  removed (`~/ke-sec-probe*` is not ours and was left alone).

## New findings

- **J1 (environment, blocks the amd64 proof)**: jq is absent from the WSL build
  host, so the amd64 bundle and the arch refusal cannot be repeated until jq is
  installed there (a human decision; the brief forbids installing it). The
  alternative is another amd64 Linux build host that has jq.
- **F8 (quickstart, medium)**: jq is not named anywhere in `docs/quickstart.md`.
  The prerequisites list Git and Docker, and the offline section says only "bash
  script, Linux build host". The developer handoff calls jq "a documented
  build-host prerequisite", but only bundle.sh's error message names it. An
  operator who follows the quickstart on a stock host hits this exactly as WSL
  did.
- **F9 (install.sh message, low)**: the installer ends with
  `next: cd <target> && bash scripts/launch.sh`. That skips the `.env` step the
  quickstart now requires (F1), so an operator who follows the installer output
  gets placeholder secrets and `KE_ENV=dev`. install.ps1 was not run this round.
- **F10 (quickstart, low)**: step 5 says to set real secrets but never says what
  to do with `KE_ENV`. `.env.example` has `KE_ENV=dev`, so following the text
  leaves the stack in dev, the mode the same paragraph calls "fine only for local
  development".
- **F12 (quickstart, low/medium; for security to judge; related to carried L-3)**:
  `cp .env.example .env` makes the file that now holds the real secrets mode
  0644, readable by every local user (step 7: `644 .env`). The quickstart could
  say `chmod 600 .env`.
- **F11 (build.sh, low, observation)**: ke-app (api, worker) and ke-gates are each
  built twice, once per service, and `:latest` lands on either result. Round 1
  bundled ke-app `64676a69…`; this round, after a cached rebuild of the same
  tree, it bundled `5b5c95a1…`. Every build leaves a dangling duplicate behind.
- **F7 persists (cosmetic)**: build.sh and smoke.sh print Compose "variable is
  not set" warnings (56 lines in the arm64 transcript).

## Deviations and limits

- Tester harness: steps 7-13 were fed to `ssh … bash -s` on stdin, and smoke.sh
  (through docker compose) consumed the rest of the script after step 9. The
  stack was left up, as step 9 leaves it. Steps 10-13 were resumed from a script
  file with stdin `</dev/null`, under the same exported project name. The product
  was not involved. The NOTE is in the transcript.
- `grep -c changeme .env` printed 1. That match is the comment on line 35, not a
  value (step 7c).
- Not a cold daemon: install loaded into the build daemon, where the images
  already existed. A cold-daemon load is PS-3.2's DinD offline check.
- amd64: build.sh was not run, so `ke-*:latest` on the dev host is unchanged.
