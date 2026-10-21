# Security audit: PS-3.10 pinned Docker CLI and compose plugin (gates image)

- Date: 2026-10-19. Role: security (scoped review and security audit).
- Scope: `git diff HEAD -- docker/gates.Dockerfile tests/test_gates_docker_cli.py` on `agent/platform-offline` (HEAD 62fa043, uncommitted).
- Raw output: `docs/evidence/platform-offline/audit-cli-probes.txt`.

## Verdict: PASS / APPROVED

No critical, high or medium findings. Three low findings and four info notes, none merge-blocking.

## 1. Q48: an independent second fetch

- I downloaded both files again with `curl --proto =https --tlsv1.2 -fsSL` into a separate scratch dir (`cli-sec/`, not the developer's `cli-dl/`).
- **Docker CLI 29.9.1**: host `download.docker.com`, TLSv1.3, cert `CN=*.docker.com`, issuer Amazon RSA 2048 M04, verify ok. Served directly with HTTP 200 and no redirect.
  - x86_64 `c158ecc5…43ff57` matches the pin `DOCKER_SHA256_X64`.
  - aarch64 `3e93cc6d…1b2018` matches the pin `DOCKER_SHA256_ARM64`.
  - `docker-29.9.1.tgz.sha256` returns 404 on both arches, and the listing has no checksum file. This confirms that upstream publishes no checksum, so the pin is TOFU as Q48 allows.
  - 29.9.1 is the newest version in both stable listings.
- **compose v5.6.0**: `github.com`, which redirects over HTTPS to `release-assets.githubusercontent.com`. Both hosts use TLSv1.3 and verify ok.
  - x86_64 `40343e21…e76a` and aarch64 `733ec767…8ea2` match the pins.
  - Both also match the upstream `.sha256` assets and the GitHub API asset `digest` field, so three sources agree.
  - The release is not a prerelease and not a draft. It equals `releases/latest`, and its uploader is `github-actions[bot]`.
- The installed binaries in `ke-gates:latest` match too. The image's `/usr/local/bin/docker` has the same hash as `docker/docker` in my x86_64 tarball, and its compose plugin equals the pin.

## 2. Wrong-hash mutation (PS-3.10 *Mismatch fails the build*): 4 of 4 killed

I made scratch copies of the Dockerfile with the last hex digit of one pin incremented in each, and built them under the tag `ke-sec-mut:mN`.

| Mutant | Pin | Where built | Result |
|---|---|---|---|
| M1 | DOCKER_SHA256_X64 | desktop-linux amd64 | rc=1, `/tmp/docker.tgz: FAILED`, checksum did NOT match |
| M2 | COMPOSE_SHA256_X64 | desktop-linux amd64 | rc=1, `/tmp/docker-compose: FAILED` (the CLI step before it passed from cache) |
| M3 | DOCKER_SHA256_ARM64 | aria-gb10 native | rc=1, `/tmp/docker.tgz: FAILED` |
| M4 | COMPOSE_SHA256_ARM64 | aria-gb10 native | rc=1, `/tmp/docker-compose: FAILED` |

- No `ke-sec-mut` image exists on either host.
- `ke-gates:latest` (713633b5c7d7) is untouched.
- The aria-gb10 image list is identical before and after.
- Local arm64 emulation is not registered (`exec format error`), so I ran M3 and M4 on aria-gb10.

## 3. Install surface

- **Client only.** tar extracts exactly one member, `docker/docker`. The tarball also ships dockerd, containerd, containerd-shim-runc-v2, runc, ctr, docker-proxy and docker-init; none of them is on PATH or anywhere on `/` in the image.
- **Ownership and modes.** With `--no-same-owner`, the binary is root:root 0755; the tarball members are `runner/runner`. The plugin is installed with `install -m 0755` as root:root, and its directories are 0755. Nothing is writable by the gate user 10001.
- **Download leftovers.** The downloads go to `/tmp` and are removed in the same RUN, so neither file is in the image `/tmp`.
- **Secrets.** The build uses no token, no `--build-arg` override, no credentials in a URL and no `DOCKER_*` env. A secret-pattern scan of the diff, the new test and the new evidence found 0 hits.
- **Daemon access.** The gate services get no socket and no DOCKER_HOST (test green). Running the client gives "no daemon" (rc 1), as expected.

## 4. Tests: tests/test_gates_docker_cli.py

- **Control and empty file.** The current Dockerfile passes all 4 Dockerfile tests. An empty Dockerfile fails all 4.
- **Killed mutants.** These are all killed: unpack before the check, `|| true`, swapped arch branch, download straight into place, apt `docker-ce-cli`, compose 2.20.0, `set -u` without `-e`, `--ignore-missing`, `latest`, `get.docker.com | sh`, and an `http://` URL.
- **Surviving mutants.** None of these is a PS-3.10 acceptance criterion:
  - T10: extracting the whole tarball, including dockerd/containerd/runc/ctr (see L-CLIb).
  - T13: dropping `--no-same-owner`.
  - T14: not removing the download.
  - T16: plugin mode 4777.
- **Developer evidence.** `green-cli-verify-full.txt` shows the 5 new tests `ok` (594 tests) and both `sha256sum -c` `OK`. `red-cli-verify-fast.txt` shows the 4 expected failures.

## 5. Findings

### Low (non-blocking)

- **L-CLIa: curl does not restrict the protocol.** The new RUNs, and the existing pwsh RUN, use `curl -fsSL` without `--proto '=https' --tlsv1.2`. With `-L`, a redirect could therefore be followed to plain `http`. Integrity still holds, because the committed hash is checked before use; the exposure is a failed build or a fetch that can be observed. Fix (developer): use `curl --proto '=https' --tlsv1.2 -fsSL` on all three downloads.
- **L-CLIb: "client only" and `--no-same-owner` are not pinned by a test.** The Dockerfile comment and the handoff say there is no daemon, but mutant T10 (extract every member) and T13 survive. A static check would close this, for example: the tar step names only `docker/docker`, and it uses `--no-same-owner`. Owner: tester. A runtime check in `ci/deployable-offline` would also work.
- **L-CLIc: requirements text is stale.** In `docs/requirements.md`, PS-3.10 *Hash provenance* still says acceptance of a release with no upstream checksum "is open … not yet numbered". Q48 has ruled on it. Owner: analyst, to cite Q48.

### Info

- **I-CLI1: TOFU residual, accepted under Q48.** Two fetches at different times from the same CDN agree. A compromise of the download.docker.com origin before the first fetch would not be detected. On every bump, repeat an independent second fetch.
- **I-CLI2: the pins can be overridden at build time.** They are ARGs, so `--build-arg` can replace them. No script, CI file or compose file does so, and whoever controls the build controls the Dockerfile anyway.
- **I-CLI3: no CVE scan here.** The static Go binaries are not scanned in this item; that belongs to `platform-supply-chain` image-scan.
- **I-CLI4: no trace changes.** The change does not touch telemetry or spans.
