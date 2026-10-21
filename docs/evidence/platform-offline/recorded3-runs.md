# Recorded offline run, round 3: amd64 with real jq, plus the arch refusal (2026-10-20)

Tester, plan item `platform-offline`. Tree: a clean clone of HEAD `e3d3fed`
(`git status --porcelain` empty, so `bundle.json` says `"dirty": false`). The
steps follow `docs/quickstart.md` § Offline bundle as it reads at `e3d3fed`. This
round used the real `bundle.sh` with real jq (1.8.1, apt) and no filter. The
harness is the same as in rounds 1 and 2: WSL Ubuntu, with docker calls going
through the recorded `docker.exe` shim, because WSL integration is still off.
Transcript: `recorded3-amd64.txt` (home paths shown as `<home>`).

## Verdict

- **amd64 (WSL build host, Docker Desktop daemon): PASS end to end.** Every
  step from clone to `teardown --volumes` returned rc 0 with the real bundle.sh
  (no D1 filter). This closes J1 from round 2.
- **Arch refusal (this amd64 bundle on aria-gb10, native): PASS.** The manifest
  matched, then install refused with `install: arch mismatch: this bundle is
  amd64 but the Docker daemon is arm64 (reported as aarch64); use the arm64
  bundle` (rc 1, 1 s). There were no image events in that window, the image
  list was unchanged, and no target was left behind.
- **Installed modes: PASS.** Dirs and `scripts/*` are 0755 and other files are
  0644, with 0 violations. After step 7, `.env` is 0600.

## Hosts

| | amd64 build + install | arch refusal |
|---|---|---|
| Host | dev host, WSL Ubuntu (bash 5.3.9, git 2.53, umask 0022), jq-1.8.1 | aria-gb10, aarch64 (bash 5.2.21, umask 0002), jq-1.7 |
| Engine / Compose | Docker Desktop 29.5.2, containerd store / v5.1.4 (docker.exe through the shim) | 29.6.2 overlay2 (native) |
| Project, ports | `ke-proof3-amd64`, 127.0.0.1:47180/47181 (checked free) | none (no launch) |
| Bundle | 941 MiB (986,150,539 B), 20 files, manifest `7a108691…0b20a2` | the same bundle, carried by tar over ssh |

Image tar sizes in bytes: ke-app 99,070,464; ke-gateway 23,074,304; neo4j
356,012,032; phoenix 326,907,904; postgres 163,448,832; valkey 17,510,912.
Only ke-app differs from round 1 (99,102,720). The extra file compared with
round 1 is `app/scripts/net_isolated.sh`. In `bundle.json`, `api worker` maps to
`ke-app:local`, `gateway` to `ke-gateway:local`, and each vendor service to its
own pinned digest ref, with arch `amd64`. All 6 images are linux/amd64.

## Steps (rc, wall time)

| Step | Result |
|---|---|
| 0 prereqs: jq, shim, docker 29.5.2 / Compose 5.1.4, clash check, ports | PASS (jq-1.8.1; no ke-proof3 resources; 47180/47181 free) |
| 1 clean clone of `/mnt/c/repos/Knowledge-engine`, detach at `e3d3fed` | PASS 0 s (porcelain 0) |
| 2 `bash scripts/build.sh` | PASS 13 s (mostly cached; pinned pulls ran) |
| 3 `bash scripts/bundle.sh --out dist/bundle-amd64` (real jq, no filter) | **PASS 16 s** |
| 3e/3f bundle facts; build-host modes | arch amd64, 6/6 linux/amd64; dirs 755, files 644, `install.sh` and `*.sh` 755, tars 644 |
| 4 copy the bundle and record into the private 0700 `<home>/ke-proof3` | PASS 1 s |
| 5a `sha256sum -c bundle-amd64.manifest.sha256` from the bundle's parent | PASS 0 s (`bundle-amd64/MANIFEST.sha256: OK`) |
| 5b `sha256sum MANIFEST.sha256` against the record | PASS (MATCH) |
| 5c `sha256sum -c --strict MANIFEST.sha256` inside the bundle | PASS 1 s (19 OK) |
| 6 `bash ./install.sh --expect-manifest <sha> <home>/ke-proof3/ke`, PATH=shim:/usr/local/bin:/usr/bin:/bin | PASS 69 s (docker.exe reads the tars over `\\wsl.localhost`) |
| 6c installed modes | **PASS**, 0 violations; parent stays 0700 |
| 7 `.env`: cp, `chmod 600`, both secrets `openssl rand -hex 24` (48 hex, never printed), ports 47180/47181, KE_ENV=dev, KE_AUTH__ENABLED=false, bind 127.0.0.1, `COMPOSE_PROJECT_NAME=ke-proof3-amd64` exported | PASS (`.env` 600; `name: ke-proof3-amd64`; `pull_policy: never` x7; 0 `changeme` values) |
| 8 `bash scripts/launch.sh` | PASS 17 s, 7/7 healthy from bundle tags |
| 8b /healthz, /readyz, Phoenix (curl.exe on the Windows host) | 200 / 200 ready (model_host not_configured) / 200 |
| 9 `bash scripts/smoke.sh` on the running stack | PASS 7 s (outage check skipped by design; stack still up, 9b) |
| 10 `bash scripts/teardown.sh` | PASS 3 s |
| 11 `bash scripts/smoke.sh` on the stopped project | PASS 37 s (launch, readyz reports postgres down, ready again, teardown) |
| 12 `bash scripts/teardown.sh --volumes` | PASS 1 s (4 `ke-proof3-amd64_*` volumes removed) |
| 13 leftovers (by project label, and `knowledge-engine`) | none |
| 14 installed modes after the run (`.env` expected 0600) | PASS, 0 violations |
| R0 carry the bundle and record to aria-gb10 `~/ke-proof3-refusal` (0700) | PASS 87 s |
| R1 `sha256sum -c` record from the parent; `-c --strict --quiet` inside; `.arch` | PASS (OK; all files OK; `amd64`) |
| R3 `env PATH=/usr/local/bin:/usr/bin:/bin bash ./install.sh --expect-manifest <sha> …/ke` | **refused as expected, rc 1, 1 s**: `arch mismatch` after the manifest match, before any load |
| R4/R5 image events in the R3 window; image list; target | none; unchanged (8 lines); no target |
| Cleanup (dev host, aria-gb10, WSL) | PASS (below) |

## Installed tree (step 6c, umask 0022)

`.`, `config/`, `docs/`, `scripts/` are 0755. The 6 files under `scripts/`
(launch/teardown .sh/.ps1, smoke.sh, net_isolated.sh) are 0755.
`.env.example`, `config/defaults.yaml`, `docker-compose.yml`,
`docker-compose.override.yml` and `docs/quickstart.md` are 0644. There are no
non-file or non-directory entries. Step 14 adds `.env` at 0600 and nothing else.

## Cleanup

- Dev host: untagged `ke-app:bundle-e3d3fed80932` and
  `ke-gateway:bundle-e3d3fed80932`. Both were this run's tags (their IDs match
  3e), and no container used them. The pre-existing `ke-*:bundle-f7e9074f7462`
  and the 4 `ke-vendor/*` tags were left as they were, with the same IDs as
  before. Compared with the image list before the run, the only differences
  are build.sh's own outputs from step 2: `ke-app:local` and `ke-gateway:local`
  were added, and `ke-gates:local` moved from `73095ae8ed5e` to `1caa2dec6f3b`.
  They are left in place. No ke-proof3 or knowledge-engine container, volume or
  network is left. `~/ke-proof3`, `~/ke-proof3-src`, `~/ke-proof3-tools` and
  `~/ke-proof3-logs` were removed.
- aria-gb10: removed `~/ke-proof3-refusal` and `~/ke-proof3-refusal-logs`. No
  bundle or vendor tag was created there, and the image list stayed at 8 lines.

## Quickstart and earlier findings, re-checked

- Fixed since round 2: **F8** (jq is a named build-host prerequisite, with
  install commands), **F9** (install.sh ends with `next: cd … && cp .env.example
  .env && chmod 600 .env (set real secrets in it), then bash
  scripts/launch.sh`), **F10** (step 5 says to keep `KE_ENV=dev` and explains
  prod), **F12** (step 5 has `chmod 600 .env` before the secrets go in, and
  `.env` stayed 0600 through launch and smoke).
- **F7 persists (cosmetic)**: there are 56 Compose "variable is not set"
  warnings (build 28, each smoke 14).
- **F11 persists (observation)**: build.sh still prints `ke-app:local Built` and
  `ke-gates:local Built` twice.

## New findings (quickstart, followed as an operator would)

- **Q1 (quickstart, low)**: in step 5 the code block ends with `bash
  scripts/launch.sh`, but the `COMPOSE_PROJECT_NAME` advice only comes after
  four more paragraphs. An operator who copies the block launches under the shared
  default project `knowledge-engine` before reading it. That was the round-1
  harness incident, and with it the `teardown --volumes` risk the same section
  warns about. The `export COMPOSE_PROJECT_NAME=…` line (or a pointer to it)
  could sit in or before the block. This run exported it before step 7, as the
  text says.
- **Q2 (smoke output, cosmetic)**: on an operator install, smoke prints
  `smoke: ci/offline api has no route to 192.168.112.2:8100` (and the same for
  worker). The `ci/offline` label means nothing to an operator, and neither the
  quickstart nor the smoke paragraph mentions the check. It passes, so it is not
  a defect.
- Not a finding: `docker compose config` lists `image: ke-app:local` and
  `image: ke-gates:local` at indent 2. These are the `x-app`/`x-gates`
  extension fields, and every service uses its bundle tag.

## Deviations and limits

- **docker CLI (amd64)**: as in rounds 1 and 2, WSL integration is off. The
  recorded shim (step 0b) forwards to `docker.exe` on the same daemon. It
  translates absolute paths with `wslpath -w` and forwards
  `COMPOSE_PROJECT_NAME` with WSLENV `/w`. It has no D1 filter. Bash, jq, GNU
  tools, sha256sum and git were the Linux ones. The quickstart's own route (WSL
  integration on) was not exercised.
- **Harness slip**: step 2b inspected `ke-*:latest` (stale images) instead of
  build.sh's `:local` outputs. 3e and C0 record the real IDs. This had no
  effect on the proof.
- **Not a cold daemon**: install loaded into the build daemon, and the
  `ke-vendor/*` tags already existed there. A cold-daemon load is PS-3.2's DinD
  offline check.
- The arch refusal ran from the bundle as carried. aria-gb10's umask is 0002,
  but the carried modes came from the WSL build (tar preserves them).
