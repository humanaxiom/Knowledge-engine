# grype provenance: platform-supply-chain unit 2 (PSC-1, ADR-KE-013 amendment 1, D2)

- Author: security, 2026-10-21. Host: Windows 11 x86_64, Docker 29.5.2 (amd64), buildx v0.34.0-desktop.1, Git Bash.
- Note: D2 and PSC-1 name this file `scanner-provenance.md`. It is written as
  `grype-provenance.md` per the orchestrator's instruction for this task. The docs or
  the file name need aligning (architect/orchestrator); this file was not renamed.
- Local download paths are redacted to `$TMP/grype-dl.XXXX` (the user profile temp dir).

## Pin line

```
anchore/grype:v0.120.1@sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe
```

Verification path used: **D2 step 3 (fallback)**. Step 2 is not available for this
release: the image index and both platform manifests carry no cosign signature
or attestation (section 3). Result: **PASS**. The signed `checksums.txt` verifies
against anchore/grype's release workflow identity. Both linux archives match it, and
the `/grype` binary copied out of each platform image is byte-identical to the
archive's binary (amd64 and arm64).

## 1. Release choice

Rule: the latest stable release that is at least ~2 weeks old on 2026-10-21.

```
$ gh api 'repos/anchore/grype/releases?per_page=15' --jq '.[] | [.tag_name, .published_at, .prerelease, .draft, .html_url] | @tsv'
v0.121.0	2026-10-19T20:32:56Z	false	false	https://github.com/anchore/grype/releases/tag/v0.121.0
v0.120.1	2026-10-06T20:46:45Z	false	false	https://github.com/anchore/grype/releases/tag/v0.120.1
v0.120.0	2026-10-02T14:23:18Z	false	false	https://github.com/anchore/grype/releases/tag/v0.120.0
v0.119.0	2026-09-17T16:45:23Z	false	false	https://github.com/anchore/grype/releases/tag/v0.119.0
...
```

- Chosen: **v0.120.1**, published **2026-10-06T20:46:45Z** (15 days old), not a prerelease or draft.
  v0.121.0 is 2 days old and was rejected.
- URL: https://github.com/anchore/grype/releases/tag/v0.120.1
- Tag object `0d30618ef52e666f1c626f4cc463eb940cb6e498` -> commit `6f8d854af29d3a3086b11a84afa51554a2a245fe`
  (`gh api repos/anchore/grype/commits/v0.120.1 --jq .sha`). This equals the commit in the signing certificate (section 4).
- Release workflow at the tag: `.github/workflows/release.yaml`, `on: workflow_dispatch`, `id-token: write`.
  `.goreleaser.yaml` at the tag has `signs:` with `cosign sign-blob --bundle`, `artifacts: checksum` only,
  and **no `docker_signs`** and no attestation. That is why the image is unsigned.

## 2. Registry digests (no pull, no run)

```
$ docker buildx imagetools inspect anchore/grype:v0.120.1
Name:      docker.io/anchore/grype:v0.120.1
MediaType: application/vnd.docker.distribution.manifest.list.v2+json
Digest:    sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe

Manifests:
  Name:      docker.io/anchore/grype:v0.120.1@sha256:7bb1480f73d9a23b8e6137669c9b780389492778dc2da5c818d0add7e828ed45
  MediaType: application/vnd.docker.distribution.manifest.v2+json
  Platform:  linux/amd64

  Name:      docker.io/anchore/grype:v0.120.1@sha256:906289103a4d477e0949e722213457733f3bfffb6f8c2dfb91760f1073acd429
  MediaType: application/vnd.docker.distribution.manifest.v2+json
  Platform:  linux/arm64

  Name:      docker.io/anchore/grype:v0.120.1@sha256:55e948e83e04b7bca5c261019d4c2c86f946bd4264f0f308e30dfa11345dfed3
  Platform:  linux/ppc64le
  Name:      docker.io/anchore/grype:v0.120.1@sha256:60acbbe556e904b75adfb1daa8d274e06c9d4a80d115c6b9b561f620808d5610
  Platform:  linux/s390x
```

| Reference | Digest |
|---|---|
| multi-arch index (the pin) | `sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe` |
| linux/amd64 | `sha256:7bb1480f73d9a23b8e6137669c9b780389492778dc2da5c818d0add7e828ed45` |
| linux/arm64 | `sha256:906289103a4d477e0949e722213457733f3bfffb6f8c2dfb91760f1073acd429` |

Cross-check: `docker buildx imagetools inspect ghcr.io/anchore/grype:v0.120.1` gives the same index
digest, `sha256:e4a44ef4...aebbbe`. The `--raw` index lists the same amd64/arm64 digests.

## 3. D2 step 2: cosign verify of the image (FAILED: not signed)

Cosign is not on the host. It was run from a pinned image, with every container labelled
`com.docker.compose.project=ke-security-psc` and run with `--rm`:

- cosign image: `ghcr.io/sigstore/cosign/cosign:v3.1.3@sha256:9e5c2f2edc34351160407ca3416c61855bdf9403c3c5936e0f0be7fc261611b8`
  (cosign v3.1.3, published 2026-08-06; v3.1.4 is 1 day old and was skipped. Index digest from
  `docker buildx imagetools inspect ghcr.io/sigstore/cosign/cosign:v3.1.3`; amd64
  `sha256:6ca1127dc1e9ff19f3f2bfa214936813a86fbbf52919652eda49d393c888ad3c`.)

```
$ COSIGN=ghcr.io/sigstore/cosign/cosign:v3.1.3@sha256:9e5c2f2edc34351160407ca3416c61855bdf9403c3c5936e0f0be7fc261611b8
$ docker run --rm --label com.docker.compose.project=ke-security-psc $COSIGN verify \
    --certificate-identity 'https://github.com/anchore/grype/.github/workflows/release.yaml@refs/heads/main' \
    --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
    docker.io/anchore/grype@sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe
Error: no signatures found
error during command execution: no signatures found
exit=10

$ ... verify --certificate-identity-regexp '^https://github.com/anchore/grype/' --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' <same digest>
Error: no signatures found
exit=10

$ ... tree docker.io/anchore/grype@sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe
No Supply Chain Security Related Artifacts found for image docker.io/anchore/grype@sha256:e4a44ef4...aebbbe
$ ... tree docker.io/anchore/grype@sha256:7bb1480f...ed45   -> No Supply Chain Security Related Artifacts found
$ ... tree docker.io/anchore/grype@sha256:90628910...d429   -> No Supply Chain Security Related Artifacts found
```

Neither the index nor the per-platform manifests carry a signature, attestation or SBOM.
D2 step 3 applies.

## 4. D2 step 3: signed checksums.txt, then the image binary

### 4a. Verify the checksums.txt signature

Release assets were downloaded into a new, empty directory (`$TMP/grype-dl.XXXX`):

```
$ gh release download v0.120.1 -R anchore/grype -p 'grype_0.120.1_checksums.txt' -p 'grype_0.120.1_checksums.txt.sigstore.json'
$ sha256sum grype_0.120.1_checksums.txt grype_0.120.1_checksums.txt.sigstore.json
c25b6095265b44fd9bbb9dbe76aca8daa394c5f0490793d2b52b16be4f5b71b1 *grype_0.120.1_checksums.txt
d6e9cd7e0e1c0384eb7f880640c61498388370d4bbf068ed3f84fc1941c511e8 *grype_0.120.1_checksums.txt.sigstore.json

$ docker run --rm --label com.docker.compose.project=ke-security-psc -v "<dl>:/work:ro" $COSIGN verify-blob \
    --bundle /work/grype_0.120.1_checksums.txt.sigstore.json \
    --certificate-identity 'https://github.com/anchore/grype/.github/workflows/release.yaml@refs/heads/main' \
    --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
    /work/grype_0.120.1_checksums.txt
Verified OK
exit=0
```

Signing certificate (from the bundle, `application/vnd.dev.sigstore.bundle.v0.3+json`, decoded with openssl):

```
issuer=O=sigstore.dev, CN=sigstore-intermediate
notBefore=Oct  6 20:43:04 2026 GMT   notAfter=Oct  6 20:53:04 2026 GMT
X509v3 Subject Alternative Name: critical
    URI:https://github.com/anchore/grype/.github/workflows/release.yaml@refs/heads/main
1.3.6.1.4.1.57264.1.1  (issuer)        https://token.actions.githubusercontent.com
1.3.6.1.4.1.57264.1.2  (trigger)       workflow_dispatch
1.3.6.1.4.1.57264.1.3  (commit)        6f8d854af29d3a3086b11a84afa51554a2a245fe   <- = v0.120.1 tag commit
1.3.6.1.4.1.57264.1.5  (repository)    anchore/grype
1.3.6.1.4.1.57264.1.6  (ref)           refs/heads/main
1.3.6.1.4.1.57264.1.21 (run)           https://github.com/anchore/grype/actions/runs/37522364926/attempts/1
rekor logIndex: 3116274917  integratedTime: 1791319384 (2026-10-06T20:43:04Z)
```

Negative controls (the same cosign image):

```
NEG1 wrong identity (anchore/syft release.yaml):
Error: failed to verify certificate identity: no matching CertificateIdentity found, last error:
expected SAN value "https://github.com/anchore/syft/.github/workflows/release.yaml@refs/heads/main",
got "https://github.com/anchore/grype/.github/workflows/release.yaml@refs/heads/main"
exit=1
NEG2 tampered checksums.txt (first hex nibble of the amd64 line changed):
Error: failed to verify signature: could not verify message: invalid signature when validating ASN.1 encoded signature
exit=1
```

### 4b. Archives match the signed checksums

```
$ grep -E 'linux_(amd64|arm64)\.tar\.gz' grype_0.120.1_checksums.txt
0a9ee97ef5ae2ee953b0a80098105052e846cdbe319a57d808b519c33cd1343d  grype_0.120.1_linux_amd64.tar.gz
29f47391dc283aa79fcc38e65224cd61f64dec0ecfd0db7074128ebf8ff23514  grype_0.120.1_linux_arm64.tar.gz
$ gh release download v0.120.1 -R anchore/grype -p 'grype_0.120.1_linux_amd64.tar.gz' -p 'grype_0.120.1_linux_arm64.tar.gz'
$ sha256sum -c --ignore-missing grype_0.120.1_checksums.txt
grype_0.120.1_linux_amd64.tar.gz: OK
grype_0.120.1_linux_arm64.tar.gz: OK
$ tar -tvzf grype_0.120.1_linux_<arch>.tar.gz     (both: CHANGELOG.md, LICENSE, README.md, grype; regular files, no ../ or links)
-rwxr-xr-x runner/runner 95244450 2026-10-06 09:42 grype   (amd64)
-rwxr-xr-x runner/runner 88211618 2026-10-06 09:42 grype   (arm64)
$ tar -xzf grype_0.120.1_linux_<arch>.tar.gz -C x-<arch> grype     (each into its own empty dir)
```

### 4c. /grype copied out of each platform image (docker create + docker cp; never run)

```
$ docker pull --platform linux/amd64 anchore/grype@sha256:7bb1480f73d9a23b8e6137669c9b780389492778dc2da5c818d0add7e828ed45
$ docker pull --platform linux/arm64 anchore/grype@sha256:906289103a4d477e0949e722213457733f3bfffb6f8c2dfb91760f1073acd429
$ CA=$(docker create --platform linux/amd64 --label com.docker.compose.project=ke-security-psc anchore/grype@sha256:7bb1480f...ed45)
$ CB=$(docker create --platform linux/arm64 --label com.docker.compose.project=ke-security-psc anchore/grype@sha256:90628910...d429)
$ docker container inspect -f '{{.State.Status}} started={{.State.StartedAt}}' $CA $CB
created started=0001-01-01T00:00:00Z
created started=0001-01-01T00:00:00Z
$ docker cp $CA:/grype img-amd64/ ; docker cp $CB:/grype img-arm64/
$ sha256sum x-amd64/grype img-amd64/grype x-arm64/grype img-arm64/grype
d6e3248b0e788b4da7450a9e03d1e72811771cf97de3640a18e6517bf6507eb7 *x-amd64/grype
d6e3248b0e788b4da7450a9e03d1e72811771cf97de3640a18e6517bf6507eb7 *img-amd64/grype
94afbea0a9b65a3a83b820e622e8ac337e26608c860315208d58dad9a80b25db *x-arm64/grype
94afbea0a9b65a3a83b820e622e8ac337e26608c860315208d58dad9a80b25db *img-arm64/grype
$ docker rm $CA $CB
```

| Platform | archive grype SHA-256 | image /grype SHA-256 | Match |
|---|---|---|---|
| linux/amd64 | `d6e3248b0e788b4da7450a9e03d1e72811771cf97de3640a18e6517bf6507eb7` | same | yes |
| linux/arm64 | `94afbea0a9b65a3a83b820e622e8ac337e26608c860315208d58dad9a80b25db` | same | yes |

Chain: release-workflow OIDC identity -> signed checksums.txt -> archive SHA-256 -> binary inside
the archive == /grype in the platform manifest under the pinned index.

Q48: this is a signed upstream checksum, not trust-on-first-use. The release
archives' published SHA-256 matches, and the image binary matches the archive binary.

Image config (both platforms): Entrypoint ["/grype"], User "" (root, as D1 records), 3 layers,
created 2026-10-06T20:43Z (minutes before the release was published).

Image contents (amd64; `docker create` + `docker export | tar -t`, never run; `docker image history`):
a scratch image with 3 layers: `COPY grype /`, `WORKDIR /tmp`, and
`COPY /etc/ssl/certs/ca-certificates.crt` (224449 bytes). There are no other regular files
(the rest are entries Docker creates on create: .dockerenv, etc/hosts, etc/hostname, etc/resolv.conf, dev/console). Labels: `org.opencontainers.image.version=0.120.1`,
`org.opencontainers.image.revision=6f8d854af29d3a3086b11a84afa51554a2a245fe` (= the signed commit).

Residual (info): the signature chain covers /grype, the only executable. `ca-certificates.crt`
is not covered by a signature, but the manifest digests above fix it. It is the trust root for
grype's HTTPS DB fetch, so the pin is what keeps it from changing.

## 5. Vulnerability-DB host (egress)

Read from source at tag v0.120.1; the binary is never run:

- `grype/db/v6/distribution/client.go:56`: `DefaultConfig()` sets `LatestURL: "https://grype.anchore.io/databases"`.
  `latestURL()` appends `/v6/latest.json`. `ResolveArchiveURL()` joins the listing path
  onto the **same host** and adds the listing checksum (go-getter checks it after download).
- `cmd/grype/cli/options/database.go:38`: `update-url` defaults to that `LatestURL`.
- Live check (https-only, TLS1.2+): `https://grype.anchore.io/databases/v6/latest.json` returned 200 with no
  redirect (Cloudflare edge). The listing names `vulnerability-db_v6.1.10_...tar.zst` and
  `checksum: sha256:fe51ed05...`. A HEAD of the archive on the same host returned 200 with no redirect.

**DB host for SFU egress: `grype.anchore.io` (HTTPS 443).**
`SCAN_DB_URL` (D3) = `https://grype.anchore.io/databases`. The developer still confirms it
with the pinned image `grype config` output, as D3 requires.

Second host, not needed if D1 holds: the app-update check (`check-for-app-update`, default `true`,
`cmd/grype/cli/options/grype.go:72`) contacts `https://toolbox-data.anchore.io`
(`cmd/grype/cli/commands/update.go:18`). D1 sets `GRYPE_CHECK_FOR_APP_UPDATE=false` on
both `scan-db` and `scan`, so `toolbox-data.anchore.io` must **not** need an egress allowance. If a
scan-db run is seen contacting it, that is a D1 defect.

## 6. Cleanup

- Removed: all containers labelled `ke-security-psc` (`docker rm`), the cosign image
  (`ghcr.io/sigstore/cosign/cosign@sha256:9e5c2f2e...11b8`), the arm64 grype image
  (`anchore/grype@sha256:90628910...d429`), and the download directory `$TMP/grype-dl.XXXX`.
- **Kept:** the amd64 grype image `anchore/grype@sha256:7bb1480f73d9a23b8e6137669c9b780389492778dc2da5c818d0add7e828ed45`
  (this host's native platform), for the developer's `grype config` read (D3) and the GREEN runs.
