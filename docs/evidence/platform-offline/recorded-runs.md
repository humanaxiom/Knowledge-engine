# Recorded offline runs: bundle, install, launch, smoke, teardown (2026-10-19)

Tester, plan item `platform-offline`, unit 2. Tree: HEAD `1fe81dd` plus the
uncommitted unit-2 working tree (`bundle.json` says `"dirty": true`).
Full transcripts, with every command and its output: `recorded-amd64.txt` and
`recorded-arm64.txt` in this directory (home paths shown as `<home>`).

## Verdict

**The recorded proof is not complete. `scripts/bundle.sh` fails on real
Compose on both hosts (defect D1).** Every step after the bundle passed on both
architectures, but only because a recorded filter stood in for the failing
`docker compose config --images <svc>` call. Once D1 is fixed, step 3 (bundle)
and the steps after it have to be re-run before the offline path counts as
proven. The arch refusal is proven end to end: it is not affected by D1.

## Hosts

| | Run 1 (amd64) | Run 2 (arm64) |
|---|---|---|
| Host | dev host, WSL Ubuntu (bash 5.3, git 2.53) against Docker Desktop 4.75 | aria-gb10, Ubuntu 24.04 aarch64 (bash 5.2, git 2.43) |
| Engine / Compose | 29.5.2, containerd image store / v5.1.4 | 29.6.2, overlay2 (classic store) / v5.2.0 |
| Project, ports | `ke-proof-amd64`, 127.0.0.1:47180/47181 | `ke-proof-arm64`, 127.0.0.1:47180/47181 |
| Bundle | 941 MiB (986,170,543 B), 19 files | 2.4 GiB (2,538,493,615 B), 19 files |
| Manifest sha256 | `fdcf80b6…0436c` | `cab1be80…655c4` |

Image tar sizes in bytes, amd64 / arm64: ke-app 99,102,720 / 325,377,536;
ke-gateway 23,074,304 / 55,294,976; neo4j 356,012,032 / 613,846,528;
phoenix 326,907,904 / 1,028,783,616; postgres 163,448,832 / 472,081,408;
valkey 17,510,912 / 42,995,712. The amd64 tars are smaller because the
containerd store saves compressed layers and the classic store saves them
uncompressed.

## Steps (rc, wall time)

| Step | amd64 | arm64 |
|---|---|---|
| 0 `docker version` on the build host | **FAIL**: WSL has Docker Desktop's stub (integration off); deviation shim, see below | PASS |
| 1 copy the tree (with .git; no .venv, dist) | PASS 3 s | PASS 9 s (tar over ssh) |
| 2 `bash scripts/build.sh` | PASS 5 s (cached) | PASS 31 s |
| 3 `bash scripts/bundle.sh --out dist/bundle-<arch>` | **FAIL** 1 s (D1) | **FAIL** 1 s (D1) |
| 3d the same with the D1 filter (recorded deviation) | PASS 20 s | PASS 12 s |
| 3e bundle.json `arch`; image platforms | amd64; 6/6 linux/amd64 | **arm64; 6/6 linux/arm64** |
| 4 copy bundle + record into a private 0700 dir | PASS 1 s | PASS 0 s |
| 5a `sha256sum MANIFEST.sha256` = the out-of-band record | PASS (MATCH) | PASS (MATCH) |
| 5b `sha256sum -c --strict MANIFEST.sha256` | PASS 1 s | PASS 1 s |
| 6 `bash ./install.sh --expect-manifest <sha> <parent 0700>/ke`, clean absolute PATH | PASS 69 s (docker.exe reads over `\\wsl.localhost`) | PASS 4 s |
| 7 `.env` from `.env.example`, ports 47180/47181 | PASS | PASS |
| 8 `bash scripts/launch.sh` | PASS 17 s (2nd attempt: tester-harness bug on the 1st, see below) | PASS 17 s |
| 8b host: /healthz, /readyz, Phoenix | 200 / 200 ready / 200 | 200 / 200 ready / 200 |
| 9 `bash scripts/smoke.sh` on the running stack (postgres stop skipped by design) | PASS 6 s | PASS 2 s |
| 10 `bash scripts/teardown.sh` | PASS 4 s | PASS 11 s |
| 11 `bash scripts/smoke.sh` on the stopped project (launches, postgres outage, tears down) | PASS 35 s | PASS 40 s |
| 12 `bash scripts/teardown.sh --volumes` | PASS 1 s | PASS 1 s |
| 13 project leftovers (containers, networks, volumes) | none | none |
| Cleanup: untag the 6 `ke-*:bundle-*` / `ke-vendor/*` tags, check that the pinned refs still resolve, remove the proof dirs | PASS | PASS (`*:probe-arm64` untouched) |

`docker compose ps` showed every service running from its bundle tag
(`ke-app:bundle-1fe81ddbfb60`, `ke-vendor/postgres:0ea6700a3b4f`, …), and the
override carries `pull_policy: never` for all 7 services.

## Arch refusal, end to end (on aria-gb10): PASS

The amd64 bundle was carried to aria-gb10 (86 s, 941 MiB) into a 0700 dir. It
was verified (MATCH, all files OK, `"arch": "amd64"`), then
`install.sh --expect-manifest fdcf80b6…` printed the manifest match and then
`install: arch mismatch: this bundle is amd64 but the Docker daemon is arm64
(reported as aarch64); use the arm64 bundle`, rc=1, in 1 s. No `docker` image
event occurred in that window (R4), and a live tag/untag positive control with
the same query shape is listed (R7). The image list is unchanged and no target
was left behind (R5). R6, a control over an older window, came back empty
because the daemon's event buffer had rolled over; it is void and was replaced
by R7.

## Defects and quickstart findings

- **D1 (blocker, `scripts/bundle.sh`)**: `docker compose config --images <svc>`
  also prints the images of `<svc>`'s `depends_on` services, in varying order
  (worker gives ke-app + valkey; api gives ke-app + postgres + neo4j + valkey),
  so bundle.sh dies with `service worker resolves to more than one image`
  before it writes anything. This happens on Compose 5.1.4 and 5.2.0. The unit
  tests missed it because `tests/fake_docker.py` (`FAKE_COMPOSE_IMAGES`) prints
  only the named service's own image. A RED test needs a fake that emulates
  the dependency images. The per-service image could instead be read from
  `docker compose config --format json` (`.services.<svc>.image`).
- **F1 (quickstart, medium)**: offline step 5 says only "launch". It never says
  to create and edit `.env` first. launch.sh silently creates `.env` with
  `KE_ENV=dev` and placeholder secrets, and nothing tells the operator how to
  change ports or secrets before first start.
- **F2 (quickstart, medium)**: the project name is never mentioned. The
  compose file pins `name: knowledge-engine`, so every install on a host shares
  one project and its volumes unless `COMPOSE_PROJECT_NAME` is set. The tester
  incident below shows the risk: a second install, or a failed override,
  silently lands on `knowledge-engine`, and `teardown.sh --volumes` there
  deletes that project's data.
- **F3 (quickstart, low)**: the offline section never names the smoke test.
  The bundle ships `scripts/smoke.sh`, and the Mac note says only that it "is
  not run on the Mac". Missing: `bash scripts/smoke.sh`, and that it only does
  the store-outage check when the project is stopped (it then launches and tears
  down itself).
- **F4 (quickstart, low)**: on a Windows dev host the "Linux build host" can be
  WSL only with Docker Desktop's WSL integration enabled for that distro.
  Without it, `docker` in WSL is a stub that refuses. Not stated.
- **F5 (quickstart, low)**: the out-of-band record is in `sha256sum` format
  (`<hash>  bundle-<arch>/MANIFEST.sha256`). `sha256sum -c
  bundle-<arch>.manifest.sha256`, run from the bundle's parent directory, is
  simpler than comparing by eye but is not mentioned.
- **F6 (code, low; for security to judge)**: modes come from the build host.
  On a umask-0002 build host, bundle files are 0664, directories 0775 and image
  tars 0600. After install on aria-gb10, `config/`, `docs/` and `scripts/` are
  0775 (group-writable; here it is the user's private group). The top level is
  0755. On run 1 the tree came from NTFS, so `docker-compose.yml` and
  `.env.example` were installed 0755.
- **F7 (cosmetic)**: build.sh (no `.env` yet) and smoke.sh's no-.env resolve
  print a dozen Compose warnings of the form "KE_ENV variable is not set". The
  image order in bundle.json follows `config --services`, which is not stable
  between runs.

## Deviations and limits (read before relying on this)

- **D1 filter**: `KE_PROOF_D1=1`, set for step 3d only. It answered only
  `compose … config --images <svc>`, with `.services.<svc>.image` from
  `compose … config --format json`. bundle.sh itself was not changed. Source:
  step 3c (amd64) and 0d (arm64).
- **amd64 docker CLI**: WSL integration is off on this host, and turning it on
  would change Docker Desktop settings while other projects are running. A
  recorded shim forwarded `docker` to the Windows `docker.exe` (same daemon,
  context desktop-linux). It translated absolute Linux path arguments with
  `wslpath -w` and forwarded `COMPOSE_PROJECT_NAME` via WSLENV. Bash, GNU tools
  and git were Linux.
- **Tester-harness incident (amd64, step 8, first attempt)**: the shim used the
  WSLENV `/u` flag, which forwards in the wrong direction, so the stack came up
  as project `knowledge-engine` (the compose default) instead of
  `ke-proof-amd64`. The tester stopped the run and checked that every
  container's working_dir was the proof install and that all 4 volumes and 2
  networks had been created by that launch at 18:52:39Z. Then the tester tore it
  down with `--volumes`, fixed the flag (`/w`) and re-ran steps 8 to 13. Nothing
  that existed before was touched.
- **Not a cold daemon**: each install loaded into the build daemon, where
  bundle.sh had already created the `as` tags and the layers existed. The load
  path ran, but a load into a daemon without the images, with no network, is
  not shown here. That is PS-3.2's DinD offline check.
- **Side effect on the dev host**: build.sh rebuilt `ke-app:latest`,
  `ke-gateway:latest` and `ke-gates:latest` from the copied tree. The new IDs are
  fd67bae609aa, f36ca68d0cd6 and f7f8b66cdc8a. The previous IDs (a282edb109ed,
  aff3f01d36bf, 2dabbb2b63a4) no longer resolve, because the containerd store
  drops an image record when its only tag moves. Building from the same tree
  restores them functionally. On aria-gb10, build.sh created `ke-app:latest`,
  `ke-gateway:latest` and `ke-gates:latest` and pulled the 4 pinned vendor
  images. Those were left in place, because pinned images must not be removed
  and the tag-removal list named only the `bundle-`/`ke-vendor` tags.
