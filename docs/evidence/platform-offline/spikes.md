# platform-offline spikes S1-S4 (2026-10-19, developer)

Scope: evidence only; no repo production file changed. Scratch: `<scratch>/spikes`.
All scratch containers, the `ke-spike-net` network, the `ke-spike-certs` and
`ke-spike-uvcache` volumes, the derived image and the pulled `docker:dind` image
were removed. Host: Docker Desktop 29.5.2, Windows 11, bind mounts are 9p.
`docker:dind` used: `docker@sha256:3e5756e2b6dad6a5f1f5deacf0a19f9eaa2581b76ae092b2d4a118162e1d4d4e`
(Engine 29.9.1, Compose v5.6.0).

## S1 image store and digests

- Host `docker info`: `Storage Driver: overlayfs`, `driver-type: io.containerd.snapshotter.v1`
  (containerd image store: yes).
- A fresh `docker:dind` (no flags) also uses it: `containerd-snapshotter=true storage-driver=overlayfs`.
  `--storage-driver=overlay2` gives the classic store.
- dind ran on an `--internal` network with an empty store (`Images: 0`); `docker pull alpine` failed (no DNS), as intended.

Valkey ref used: `valkey/valkey:8-alpine@sha256:081c2f5c...`.

| Variant | Result |
|---|---|
| `docker save --platform linux/amd64 <refs>`, load into containerd dind | NO. Vendor images load unnamed, and the ID is a NEW single-platform manifest digest (`ec9f656f...`, not the pinned one). `ref@digest` cannot resolve. First-party `ke-app:latest` / `ke-gateway:latest` keep their tag. |
| `docker save <ref@digest>` (no `--platform`), containerd dind | Digest preserved (`Loaded image ID: sha256:081c2f5c...` = the pinned digest) but UNNAMED: `docker image inspect <ref@digest>` -> `No such image`. |
| as above, then `docker tag sha256:081c2f5c... valkey/valkey:8-alpine` in dind | `ref@digest` resolves (`RepoDigests=[valkey/valkey@sha256:081c2f5c...]`). |
| tag on host, `docker save valkey/valkey:8-alpine`, load | `Loaded image: valkey/valkey:8-alpine`; `ref@digest` resolves directly. |
| classic store (`overlay2`) dind, either tar | NO. The ID becomes the config digest `09f1cebd...`; `RepoDigests` is empty; `ref@digest` never resolves, even with `valkey/valkey:8-alpine` tagged. |

- `docker compose up -d` (default pull policy), digest-pinned image, loaded and named, containerd dind: starts, **no pull**.
- Same compose, image absent: `Pulling` then `lookup registry-1.docker.io ... server misbehaving` (fails closed offline).
- Same compose, image loaded but unnamed: `up --pull never` -> `No such image: valkey/valkey:8-alpine@sha256:...`.
- Classic dind, digest-pinned compose: tries `https://registry-1.docker.io/v2/` and fails.
- **Fallback (store-independent) works on both stores:** `docker load` (per-image tar), read the `Loaded image ID: sha256:<id>` line, `docker tag <id> ke-spike/v:local`, compose `image: ke-spike/v:local`.
  Classic dind: `ke-spike/v:local Up`. Containerd dind: container Started, `valkey-cli ping` -> `PONG`; no pull in either.
- Side effect on the host store: a `docker rmi valkey/valkey:8-alpine` of a tag I had added also removed the host's pinned valkey entry. I restored it by loading the saved tar and tagging `valkey/valkey:8-alpine`; `ref@digest` resolves again on the host (`sha256:081c2f5c...`). One extra local tag remains on the host.
- Not tested: a classic-store BUILD host (the CI runner's store type is unknown; measured on the first CI run).

## S2 gates as uid 10001, repo `:ro`

Final command (repo bind-mounted `:ro`, plus a one-line-edited pyproject bound over `/work/pyproject.toml`, see item 4):
`docker run --rm --user 10001 --network none -v <repo>:/work:ro --tmpfs /tmp:exec,mode=1777 -e UV_CACHE_DIR=/tmp/uv -e UV_NO_SYNC=1 -e MYPY_CACHE_DIR=/tmp/mypy -e PYTHONDONTWRITEBYTECODE=1 -e GIT_OPTIONAL_LOCKS=0 -w /work ke-gates:latest bash scripts/test.sh fast`
Result: 419 tests OK, coverage 89%, `Success: no issues found in 17 source files`, exit 0
(tail: `docs/evidence/platform-offline/spike-s2-run7-tail.txt`).
That run used `UV_NO_SYNC=1`, which is NOT acceptable (item 5); the accepted uv setup was verified separately.

Failures found, in order (path -> error):

1. `/.cache/uv` -> `failed to create directory ... Permission denied (os error 13)` (HOME is `/` for an unknown uid).
   With `UV_CACHE_DIR` on tmpfs it fails differently: `Because hatchling was not found in the cache ... network was disabled`
   (the build-time cache is `/root/.cache/uv`, root 0700, unreadable). `uv run` also reinstalls the editable project on every run and
   rewrites `/opt/venv/.../_editable_impl_knowledge_engine.pth` -> `Permission denied`.
2. `/work/.coverage` -> `OSError: [Errno 30] Read-only file system` (`coverage erase`; a stale file exists in the checkout). Parallel `.coverage.*` and `.mypy_cache` fail the same way (mypy crashes without a cache dir).
3. `--tmpfs /tmp` is **noexec** by default: tests that run copied `scripts/*.sh` fail with `scripts/lint.sh: Permission denied` (197 failures, 1 error). It needs `exec`.
4. `COVERAGE_FILE=/tmp/.coverage` as an env var is wrong: nested coverage runs started by tests inherit it and write statement-only data into the same files, so the end step fails with `Can't combine statement coverage data with branch data`. Putting `data_file = "/tmp/.coverage"` under `[tool.coverage.run]` in pyproject avoids it (nested runs use their own pyproject); verified with the bind-mounted edit: combine, report and mypy pass.
5. `UV_NO_SYNC=1` hides a gate: with a drifted `pyproject.toml` (extra dependency, `uv.lock` unchanged) `uv run --locked` still printed `ran`. Root without it fails ("unsatisfiable"). Verified alternative: a derived image with `UV_CACHE_DIR=/opt/uv-cache` (a copy of `/root/.cache/uv`), `chown -R 10001:0 /opt/venv /opt/uv-cache`, `USER 10001`. There `uv run --locked` passes (`Uninstalled 1 package ... Installed 1 package ... ran`) and the drifted pyproject still fails.
6. git as uid 10001 on the 9p mount worked (`git status` fine). A Linux CI bind mount owned by another uid may need `safe.directory`; unmeasured.

Minimal writable set (proposal for L-5):
- Image: build-time `UV_CACHE_DIR=/opt/uv-cache` and `/opt/venv` owned by 10001 (group 0); compose `user: "10001"`.
- tmpfs `/tmp` with `exec,mode=1777`.
- Env: `MYPY_CACHE_DIR=/tmp/mypy`, `PYTHONDONTWRITEBYTECODE=1`, `GIT_OPTIONAL_LOCKS=0`.
- pyproject (needs its own test): `[tool.coverage.run] data_file = "/tmp/.coverage"`; not the env var `COVERAGE_FILE`.
- Checkout `:ro`; nothing else writable. No `UV_NO_SYNC`.
- The architect's L-5 text lists `COVERAGE_FILE` and a `/tmp` tmpfs: both need these corrections (data_file, `exec`) plus the image ownership change.

## S3 dind client key and network

- dind with `DOCKER_TLS_CERTDIR=/certs` on a volume: `/certs/client` is `drwxrwxrwt`, `key.pem` is `-rw-r--r--` (0644). `/certs/ca/key.pem` is `-rw-------` root: never mount `ca/`.
- `docker run --user 10001 -v ke-spike-certs:/certs:ro` read `/certs/client/key.pem` (`-----BEGIN PRIVATE KEY-----`). Mounting only the client dir works: `--mount type=volume,src=...,dst=/certs/client,volume-subpath=client,readonly`.
- uid 10001 with `DOCKER_HOST=tcp://docker:2376 DOCKER_TLS_VERIFY=1 DOCKER_CERT_PATH=/certs/client` -> `29.9.1 client-as-uid10001 ok`.
- Server cert SANs are the container id, `docker` and `localhost` only. `tcp://dind:2376` fails (`certificate is valid for ..., docker, localhost, not dind`): give dind the network alias `docker`, or set `DOCKER_TLS_SAN`.
- Without the TLS env: `Client sent an HTTP request to an HTTPS server`.
- `ke-gates` has no docker CLI (the plan already adds it).
- Inner network: `network create -o com.docker.network.bridge.gateway_mode_ipv4=isolated` WITHOUT `--internal` is rejected: `gateway mode 'isolated' can only be used for an internal network`. With `--internal` it is created (`internal=true`, option kept, inspect gateway `invalid IP`). Two containers on it: peer ping OK (`1 packets received`), `ip route` shows only the subnet route (no default), `1.1.1.1` -> `Network unreachable`, the `.1` address answers (a container takes it, as the architecture notes). The option is honoured inside dind.

## S4 disk and timing

- Host free disk now: `C: 3.7T size, 573G used, 3.2T avail (16%)`; box: 24 CPUs, 31 GiB. CI runner figures unknown; measured on the first CI run.
- `docker save` (containerd store, no `--platform`), per image: ke-app 1.3 s / 99 MB; ke-gateway 0.5 s / 23 MB; postgres 2.0 s / 163 MB; neo4j 4.3 s / 356 MB; valkey 0.4 s / 17.5 MB; phoenix 3.6 s / 327 MB.
- All six in one tar: **10.8 s, 957,783,040 bytes (about 0.96 GB)**; with `--platform linux/amd64`: 10.8 s, 957,755,904 bytes.
- `docker load` of that tar into an empty dind: 15.3 s; dind `/var/lib/docker` 60 MB -> 3,312 MB after load.
- Footprint estimate: tar 1.0 GB + inner store 3.3 GB + gates image 1.35 GB + host copies of the stack images (about 3.3 GB) = about 9 GB all resident, plus build cache.

## Recommendations

**R2: store-independent install; no containerd prerequisite for operators.** Viable and tested on both stores (S1 fallback).
- Bundle: one tar per image (`docker save <name:tag>`, no `--platform`: that flag changes the manifest digest, so the pinned reference can no longer be checked). `bundle.json` records `file`, source `ref`, `as` (e.g. `ke-vendor/valkey:<digest12>`; first-party `ke-app:bundle-<sha12>`).
- Install: verify `MANIFEST.sha256` first, `docker load -i <file>`, parse the single `Loaded image ID` / `Loaded image` line, `docker tag <id> <as>`. Never rely on `ref@digest` resolving on the target: the classic store never resolves it, and containerd only does if the image is named.
- Launch: install writes a compose override mapping each service to its `as` tag. No digest reference remains, so nothing is pulled; a missing image fails closed (verified).
- Cost: the digest pin is checked on the build host (it resolves `ref@digest` before saving) and by the tar hashes after, not by the target daemon. The target-side ID differs per store, so do not compare IDs.
- Keep a containerd-store requirement only for the `dind` daemon that `ci/deployable-offline` chooses; it is not an operator prerequisite. The CI build host's store is unmeasured, so `bundle.sh` should use only `docker tag` + `docker save <tag>`, which work on both.

**R6 (disk).** Measured: 0.96 GB bundle tar, 3.3 GB inner store, about 9 GB all resident. Require 10 GB free at the start of `bundle.sh` and `offline_check.sh` (fail with a clear message, not a mid-run ENOSPC), and remove the verify stack and the dind volume before the next stage. A standard GitHub runner has roughly 14 GB free after the OS (unmeasured here), so this is tight: the first CI run should print `df` before and after each offline stage, and the 10 GB figure is a default until then, not a CI measurement.
