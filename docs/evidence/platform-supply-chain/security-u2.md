# Security audit: platform-supply-chain unit 2 (the scanner)

- Author: security, 2026-10-21. Branch `agent/platform-supply-chain` at 8900766 plus uncommitted U2.
- Scope: `docker-compose.scan.yml`, `scripts/scan.sh`, `docker/scan-ignore.yaml`,
  `tests/test_image_scan.py`, the `tests/test_stack_compose.py` carve-out, and the U2 evidence files.
  Read against ADR-KE-013 amendment 1, D1 to D5, and `scanner-provenance.md`.
- Host: Windows 11, Docker Desktop 29.5.2 (linux engine), Compose v5.1.4, Git Bash. Scratch copies
  only; scratch paths are written as `$SCRATCH`. Every container, volume and network was labelled
  `com.docker.compose.project=ke-secu2-*` and removed afterwards (0 left).

## Verdict: PASS

No critical or high finding. One medium (fails closed, not a false green) must be fixed before
PSC-6 wires the scan into `verify.sh full` on Linux CI. Three lows and three infos are non-blocking.

## Findings

| ID | Sev | Where | Finding | Recommendation |
|---|---|---|---|---|
| M-1 | medium | `scripts/scan.sh:66`; `docker-compose.scan.yml:14-15,49-52` | On a Linux engine (CI ubuntu-24.04, the ARM model hosts), `docker save -o` writes the tar **0600**, owned by the uid of the caller. docker/cli v29.5.2 `cli/command/image/save.go:77` calls `atomicwriter.New(opts.output, 0o600)`, which ignores umask. `scan` runs as root with `cap_drop: [ALL]`, so it has no CAP_DAC_OVERRIDE or CAP_DAC_READ_SEARCH and cannot read the file (probe P4). grype then fails, and scan.sh reports "a fixed High or Critical match, or a scanner error". The run **fails closed**, so this cannot produce a false green. But every Linux `full` run would be red, and the obvious workarounds weaken the gate. The GREEN real scan passed only because Docker Desktop bind mounts do not enforce the host uid and mode. The fake-docker tests cannot see this. | After the save, `chmod 0644 -- "$KE_SCAN_IN/ke-app.tar"`. The dir stays 0755 and owned by the caller; the content is the ke-app image, which ships in the bundle anyway. **Do not** use `cap_add` DAC_OVERRIDE or DAC_READ_SEARCH, `chmod 777`, `privileged`, or drop `read_only`. Confirm with one real run on a Linux engine before PSC-6. |
| L-1 | low | `scripts/scan.sh:46` | `cleanup` resets INT and TERM to the default (`trap - EXIT INT TERM`). A second TERM during teardown kills the script mid-`teardown.sh` (probe P6). That leaves the project containers, network and volume, and `dist/ke-scan-*/ke-app.tar`. D3 still holds, because the next run uses a new project and a new volume. The same pattern is in `scripts/offline_check.sh:154`. | In `cleanup`, reset EXIT and set INT and TERM to ignored (an empty-string trap action) instead of default, so teardown completes. Apply it to both scripts or to neither, for consistency. |
| L-2 | low | `scripts/scan.sh:58,66` | `mkdir -p` accepts a pre-existing `dist/<project>` (or a symlink to one). The tar sits in the checkout for the ~70 s scan-db stage before `scan` binds it. Anyone who can write to `dist/` can swap in a clean tar and get a false green. A symlink at the tar name itself is refused (`atomicwriter` Lstat: "cannot write to a symbolic link directly"). On Linux CI no other user can write there. On this host, `C:\repos` grants inherited Full Control to a second local account (`aria-alien1\thedo`) as well as to `adam`. That account could equally edit `scan.sh` or the ignore file, so the tar adds no new capability. | `mkdir -p dist && mkdir -m 0755 -- "$KE_SCAN_IN"`, so a pre-existing path fails the run. Human decision: whether a second account should have write access to the checkout. |
| L-3 | low | `scripts/scan.sh:29-34` | `DOCKER_DEFAULT_PLATFORM` from the caller is not cleared. If set to, for example, `linux/s390x`, compose pulls that manifest under the pinned index, and the qemu binfmt in Docker Desktop would run it. Only the amd64 and arm64 binaries were provenance-checked (D2). The index digest still fixes the content. | Add `DOCKER_DEFAULT_PLATFORM` to the `unset` on line 34. |
| I-1 | info | `docker-compose.scan.yml:20-29` | `scan-db` egress is unrestricted, like any default-bridge container. It can reach any host and the host gateway (host-published ports such as Phoenix). Bridges are isolated from the verify stack networks, and D4 puts the scan after `teardown_verify`. The provenance-verified binary is the only code in it. | None. SFU egress needs only `grype.anchore.io:443`, because `GRYPE_CHECK_FOR_APP_UPDATE=false` is set and confirmed in the container env. |
| I-2 | info | grype DB, D2/D3 | DB integrity rests on TLS only. grype v0.120.1 fetches `latest.json` over HTTPS (TLS 1.2 minimum, CA bundle fixed by the image digest). It joins the archive path onto the **same host** (`client.go` `ResolveArchiveURL`, `path.Clean`) and go-getter checks the SHA-256 of the archive against the checksum in the listing. Defaults that are in force: `ValidateAge` with a 5-day max built age, and `ValidateChecksum` (`installation/curator.go:56-58`). Neither the listing nor the DB is signed, so a compromise of grype.anchore.io or its CDN could serve a fresh but empty DB and yield a false green. Stale-DB replay is bounded by the 5-day age check. | Accept as residual, as the last paragraph of D2 does. No caller can set `ca-cert`, `update-url` or validate-age, because env is literal-only and the ignore schema allows only `ignore`. |
| I-3 | info | `docker-compose.scan.yml:9-17` | No memory or pids limit, and `/tmp` tmpfs is unbounded (the ke-app unpack is about 423 MB, held in RAM). | Availability only; optional. |

## Checked and holding

- **Network isolation:** at runtime (`compose create --pull never` in project `ke-secu2-audit`,
  then `docker inspect`):
  - `scan`: `NetworkMode=none`.
  - `scan-db`: only `ke-secu2-audit_default` (bridge); the file declares no `networks`.
  - Neither service has a docker socket mount, a `DOCKER_*` env, ports, `privileged`, or
    host pid/ipc/uts/userns.
- **Hardening:** both services: `ReadonlyRootfs=true`, `CapDrop=[ALL]`, `CapAdd=[]`,
  `SecurityOpt=[no-new-privileges:true]`, tmpfs `/tmp`.
  - `scan` mounts: `/db` volume `rw=false`; `/in` and `/cfg/scan-ignore.yaml` binds `rw=false`.
  - `scan-db` mounts: `/db` volume only, rw.
  - User: image default (root), as D1 allows.
- **Env:**
  - Container env is exactly the literal D1 keys plus the PATH from the image.
  - Caller `SCAN_DB_URL` and `GRYPE_DB_UPDATE_URL` are ignored (line 18 is a constant; line 34
    unsets; `test_scan_updates_db_every_run` checks it with hostile values).
  - `COMPOSE_PROJECT_DIRECTORY`, `COMPOSE_ENV_FILES` and `COMPOSE_DISABLE_ENV_FILE` set by the
    caller do not move the bind sources (probe P1).
  - `--env-file .env.example` keeps the repo `.env` (the model keys) out, and `.env.example` sets
    no `COMPOSE_*`, `KE_SCAN_IN` or `GRYPE_*`.
- **KE_IMAGE_TAG injection:** checked against `^wt-[0-9a-f]{12}$` under `LC_ALL=C` before any
  docker call, always quoted, and the error escapes it with `printf %q`. 13 hostile cases are
  tested.
- **Exact pinned image:**
  - The created containers report image ID `sha256:e4a44ef4...aebbbe`, the pinned index.
  - A decoy local tag with the right name but a different digest is refused with
    "No such image" (probe P2). There is no tag fallback.
  - The pull is by digest; both runs use `--pull never`.
- **Fail closed:**
  - `set -euo pipefail`; every docker stage has `|| fail`; the scan exit code is captured and any
    non-zero fails the run; a failed teardown sets status 1.
  - The pinned grype, in labelled network-less containers (probe P3):
    - `db update` with no network: exit 1, naming the host.
    - Scan with an empty DB and auto-update off: exit 1, "database does not exist".
    - Missing tar: exit 1.
  - The real scan exits 2 on the certifi and quinn-proto findings (developer evidence).
- **Teardown:** the EXIT trap runs on normal exit, `fail`, INT (130), TERM (143) and HUP (129)
  (probe P5). See L-1 for a second signal.
- **Ignore file:** `ignore: []`. `check_scan_ignores` limits the file to a single `ignore` list of
  `{vulnerability, package.name, reason, until}`, so it cannot set `fix-state`, `exclude`, `db.*`
  or `match` options. A case-variant key such as `Ignore:`, which viper would accept, fails the
  exact-key check. PyYAML runs with `safe_load`.
- **Test file:** no `shell=True`, `eval`, `pickle` or unsafe YAML loader. Subprocesses use argv
  lists with a scrubbed env.
- **Stack carve-out** (`tests/test_stack_compose.py:243-249`): limited to exactly
  `docker-compose.scan.yml` and the services `scan-db` and `scan`.
- **Evidence files** (`u2-*.txt`, `scanner-provenance.md`) and all 25 changed or untracked files:
  - The secret-pattern sweep found no hits. Patterns: AWS, GitHub, Slack, OpenAI and Anthropic
    keys, Google API keys, JWTs, PEM private keys, credentials in URLs, password/token/api-key
    assignments, `S-1-5-21-` SIDs, `C:\Users`, `/c/Users`, AppData.
  - URLs and IPs in the evidence are public hosts, 127.0.0.1, and Docker-internal 172.18/192.168.144
    addresses. No model-host value appears.

## Probe transcript (abridged; scratch paths redacted)

```
P1 compose config, caller COMPOSE_PROJECT_DIRECTORY=$SCRATCH/evil (its ignore file sets fix-state: fixed):
   bind sources stay $SCRATCH/repo/dist/ke-scan-123 and $SCRATCH/repo/docker/scan-ignore.yaml
   (also for COMPOSE_ENV_FILES, COMPOSE_DISABLE_ENV_FILE)
P2 docker tag ke-app:local ke-secu2-probe:v0.120.1; image ke-secu2-probe:v0.120.1@sha256:e4a44ef4...:
   Error response from daemon: No such image: ke-secu2-probe:v0.120.1@sha256:e4a44ef4...aebbbe   rc=1
P3 anchore/grype@sha256:7bb1480f...ed45, --read-only --cap-drop ALL no-new-privileges, tmpfs /tmp and /db:
   A  --network none db update -> ERROR unable to update vulnerability database: ... unable to download
      listing: Get "https://grype.anchore.io/databases/v6/latest.json": ... network is unreachable   rc=1
   B  scan, empty DB, GRYPE_DB_AUTO_UPDATE=false -> ERROR failed to load vulnerability db: database does not exist   rc=1
   C  scan, no tar -> failed to catalog: no source providers were able to resolve the input "/in/ke-app.tar"   rc=1
P4 named volume, file uid 1000 mode 0600 in a 0755 dir:
   root, --cap-drop ALL, no-new-privileges -> cat: /x/d/ke-app.tar: Permission denied   rc=1
   root, default caps (control)           -> data   rc=0
P5 replica of scan.sh:44-56 (set -m for INT): INT rc=130, TERM rc=143, HUP rc=129; teardown start and end logged each time
P6 TERM, then a second TERM 1 s into a 3 s teardown -> rc=143, "teardown start" logged, no "teardown end"
```
