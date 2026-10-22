# Security audit: platform-supply-chain unit 3 (2026-10-21)

Scope: `git diff 8b20fa5` (uncommitted unit 3): docker/app.Dockerfile (D10, no uv in the final stage),
uv.lock (certifi 2026.7.22 -> 2026.10.19), scripts/scan.sh (r1-a, r1-b, I-4, I-6), tests/fake_docker.py,
tests/test_image_scan.py, docs.

**Verdict: PASS.** 0 critical, 0 high, 1 low, 4 info.

Evidence: `security-u3-probes.txt` (image probes, base layers, builder/final tree compare, PyPI
metadata/provenance/wheel diff, SRANDOM probe, scan summary), `security-u3-real-scan.txt` (full real scan).
All work ran on a scratch copy of the tree. Containers had `--network none` and label
`ke.audit=security-u3`, except the scan, which runs in the own `ke-scan-<n>` project of scan.sh.

## 1. ke-app image (built from the scratch tree as ke-app:wt-5ec5ec5ec5ec)
- No uv/uvx. `command -v uv || command -v uvx` exits 127 and prints nothing. `find /` finds no file named
  uv/uvx/uv-*. The only uv* files are uvicorn, `uv_cache.json`/`uv_build.json` in the project dist-info
  (no secrets: timestamp, `{}`, `env:{}`) and `/app/uv.lock`.
- /app and /opt/venv are root:root 0755. No file under either is owned by a non-root user. uid 10001 cannot
  write /app, /app/engine, /opt/venv, bin or site-packages. The one file uid 10001 can write anywhere
  outside tmp/dev is `/opt/venv/.lock` (see I-1).
- No build secrets or caches in the final image. /root has no `.cache`. There is no /run/secrets and no
  .netrc/.pypirc/pip.conf/uv.toml/.env, no private key, no UV_* env var and no /usr/local/bin/uv. The builder
  has uv (58 MB) and /root/.cache/uv (55 MB); neither reaches the final image.
- Base: Dockerfile:7 and :23 use the same `python:3.12-slim-bookworm@sha256:34386ef0...7258`. The 4 base
  layers are the exact prefix of the RootFS of both the builder and the final image. The final image adds
  4 layers: venv, /app, WORKDIR, useradd.
- The image runs as `ke` (uid/gid 10001). Config User=ke, Entrypoint null, Cmd `python -m engine.api`.
- Builder leakage: the sha256, mode and owner of every file in /opt/venv and /app (5411 lines) are the
  same in builder and final. The history shows only `COPY /opt/venv` and `COPY /app` from the builder.
- `engine.notices` runs; `certifi.__version__` is 2026.10.19.

## 2. certifi 2026.10.19
- uv.lock matches PyPI (JSON API and simple API), and my own downloads hash to the same values:
  - sdist https://files.pythonhosted.org/packages/a6/bd/1436c50cc46699de0230fbaacc1d1de7bfec413176099949e9d5112e88f2/certifi-2026.10.19.tar.gz
    sha256 035c1e85572b141bf1c3a3eff0e33a8eb74917522f2559075ff8d2fea780a1ae, 137598 B, uploaded 2026-10-20T02:24:16Z
  - wheel https://files.pythonhosted.org/packages/c4/51/29046e48f693c54e5b7412216d447a1d8362c9653148d98c02cdf65fa733/certifi-2026.10.19-py3-none-any.whl
    sha256 42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b, 136464 B, uploaded 2026-10-20T02:24:15Z
- The installed certifi files in the image (`__init__`, core, cacert.pem, `__main__`) match the wheel by sha256.
- Legitimacy. Author, home page and licence are unchanged from 2026.7.22 (Kenneth Reitz,
  github.com/certifi/python-certifi, MPL-2.0). Not yanked. Both versions carry PyPI provenance from the same
  Trusted Publisher: GitHub `certifi/python-certifi`, `release.yml`, environment `release`. The attestation
  subjects equal the file hashes. The wheel diff against 2026.7.22 has no code change: only the version
  string, a Python 3.15 classifier, the setuptools generator 83.0.0 -> 84.2.0, and cacert.pem 121 -> 120
  roots with one removed (`emSign ECC Root CA - G3`) and none added. This is the usual Mozilla-bundle
  release shape. See I-3.

## 3. scan.sh
- Injection. On bash >= 5.1, `$project` is always `ke-scan-<digits>`. Probe: Git Bash 5.3 and Debian
  bash 5.2 ignore an environment `SRANDOM`. So the r1-a/r1-b strings (scan.sh:52, :55, :60) and the
  teardown hint (:65) carry no metacharacters beyond the intended literal `\$(docker ps ...)`. Container IDs
  reach `docker rm -f` as a quoted array (:58-59), never as text that gets re-parsed.
- r1-a: a failed `docker ps` is caught by `if ! listing="$(...)"`, and `local` is declared separately so its
  status is not masked (:53-56). This fails closed with status 1.
- I-4: `trap "" INT TERM` (:48) now comes before `trap - EXIT` (:49).
- See L-1 for older bash.

## 4. Real scan (re-run myself, scratch tree, KE_IMAGE_TAG=wt-5ec5ec5ec5ec)
- Exit 0. Afterwards no ke-scan container, volume or network was left, and dist/ was empty.
  `docker/scan-ignore.yaml` is `ignore: []`, so every suppression below comes from the grype --only-fixed
  handling (no fix, or wont-fix). None is an ignore entry.
- 289 rows. High/Critical: 82, all `deb`, all suppressed, none with a fix: 52 have no fix and 30 are
  wont-fix.
  - Critical (3, wont-fix): libsqlite3-0 CVE-2025-7458; libc6 and libc-bin CVE-2026-5450.
  - Top packages: the util-linux family (bsdutils, libblkid1, libmount1, libsmartcols1, libuuid1, mount,
    util-linux, util-linux-extra), 6 each, 48 in total; libc6/libc-bin 4 each; libsqlite3-0 3.
  - Highest EPSS: libtasn1-6 CVE-2025-13151, 1.2%.
- Not suppressed (13, all below High): python 3.12.15 binary (6 Medium, 1 Negligible) and pip 25.0.1
  (5 Medium, 1 Low, all fixed upstream; see I-2).
- No python- or rust-type High/Critical remain: certifi, quinn-proto and rustls are gone. The numbers
  match the developer evidence u3-real-scan.txt (82 High/Critical).
- Worth noting: glibc CVE-2026-5450 is Critical and wont-fix in bookworm. Watch for a Debian DSA or base
  refresh, and consider a trixie base in a later item.

## 5. Evidence sweep (u3-*.txt)
No profile paths, no SIDs, no secrets. Grep for keys, tokens, PEM private keys, credential URLs and
password assignments found only compose warnings that KE_STORES__NEO4J__PASSWORD is not set, and
placeholder-secret notices. The IPs are docker-internal (127.0.0.1, 172.19/192.168 bridges). The diff
itself matched no secret pattern.

## Findings
- **L-1 (low, non-blocking) scripts/scan.sh:31.** `${SRANDOM}` exists only in bash >= 5.1. On older bash
  (macOS /bin/bash 3.2, the future MLX Mac host) there are two failure modes:
  - Unset: `set -u` aborts with a bare "SRANDOM: unbound variable", exit 127, before the trap. This fails
    closed but names no stage.
  - Set in the caller environment: the value is used verbatim in COMPOSE_PROJECT_NAME, KE_SCAN_IN
    (mkdir :77, `rm -rf` :68) and the printed hand commands (:52, :65). Probe: bash 5.0 with
    `SRANDOM=evil/../..` gives `ke-scan-evil/../..`.

  The old `${RANDOM}${RANDOM}` was always digits. Exploiting this needs control of the caller
  environment, and the supported hosts (Git Bash 5.3, Ubuntu 24.04 bash 5.2) are unaffected.
  Suggested fix: after :37, check that the project matches ^ke-scan-[0-9]+$ (or that BASH_VERSINFO is
  at least 5.1), and otherwise print `scan: FAIL (bash >= 5.1 needed ...)` and exit 1.
- **I-1 (info, pre-existing)** `/opt/venv/.lock` is the empty uv lock file, root-owned, mode 0666, carried
  over by Dockerfile:26. It is the only path uid 10001 can write outside tmp. Nothing reads it at runtime,
  and uid 10001 cannot replace it. It could be dropped in the builder.
- **I-2 (info, pre-existing)** The system pip 25.0.1 from the base image stays in the final stage with 6
  fixed Medium/Low GHSAs. It is not on the runtime path. Removing pip/setuptools from the final stage
  follows the same reasoning as D10.
- **I-3 (info)** certifi was taken 2 days after release, inside the settle period, for a Critical fix
  (orchestrator ruling). I read the provenance publisher from the PyPI integrity API over TLS but did not
  verify the Sigstore bundles cryptographically. 2026.10.18 came out a day earlier; 2026.10.19 is the
  latest release and is not yanked.
- **I-4 (info)** tests/test_image_scan.py r1-b runs the hand command parsed from the scan.sh output with
  `bash -c`, under the fake-docker PATH, in the network-none gates container. This is acceptable for a
  harness that tests the script of the repository itself.
