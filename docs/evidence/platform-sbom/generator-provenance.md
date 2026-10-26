# syft provenance: platform-sbom unit U2 (PSC-20, PSC-1 form; design-notes N2; ADR-KE-013 amendment 1, D2)

- Author: security, 2026-10-23. Host: Windows 11 x86_64, Docker 29.5.2 (amd64, containerd store), buildx v0.34.0-desktop.1, gh 2.92.0, Git Bash.
- Raw output: `docs/evidence/platform-sbom/u2/security-*.txt` (registry digests, cosign image, cosign blob, binary match, release facts, cleanup).
- Downloads went to a new, empty scratch dir (`$TMP/syft-dl`, profile path redacted). Nothing from them was run.

## Pin line

```
anchore/syft:v1.54.1@sha256:3eb5379ba7b409c3f4069b686110527af0c47df993fa5c10d13e7cf34f49b1aa
```

Verification path: **N2 step 3 (fallback)**. Step 2 is not available: the index and both platform manifests carry
no cosign signature or attestation (section 3). Result: **PASS**. The signed `syft_1.54.1_checksums.txt` verifies against
anchore/syft's release workflow identity. Both linux archives match it, and the `/syft` binary copied out of each platform
image is byte-identical to the archive's binary (amd64 and arm64).

## 1. Release choice

- **v1.54.1**, published 2026-10-06T15:35:10Z (17 days old on 2026-10-23), not a prerelease or draft, `immutable: true`.
  v1.55.0 (2026-10-19, 4 days old) is too new. It is the syft that the pinned grype v0.120.1 embeds
  (grype `go.mod` at v0.120.1, line 81: `github.com/anchore/syft v1.54.1`).
- URL: https://github.com/anchore/syft/releases/tag/v1.54.1
- Tag object `749cd89ef26db65d5102d879f5dd63a174312b1e` -> commit `b254e6d92f28c3868a755f62fb3ca8f26e9fee76`. This equals the commit in the signing certificate (section 4a) and the image's `org.opencontainers.image.revision` label.
- Release workflow at the tag: `.github/workflows/release.yaml`, `on: workflow_dispatch`, `environment: release`, `id-token: write`.
  `.goreleaser.yaml` at the tag: `signs:` with `cosign sign-blob --bundle`, `artifacts: checksum` only; `dockers_v2` with
  `--provenance=false` and `sbom: false`; **no `docker_signs`**. That is why the image is unsigned.

## 2. Registry digests (independent check, no pull, no run)

`docker buildx imagetools inspect anchore/syft:v1.54.1` and `ghcr.io/anchore/syft:v1.54.1` give the same index and
the same platform digests. The local sha256 of the `--raw` index bytes is `3eb5379b...49b1aa` (`u2/security-registry-digests.txt`).

| Reference | Digest |
|---|---|
| multi-arch index (OCI image index, the pin) | `sha256:3eb5379ba7b409c3f4069b686110527af0c47df993fa5c10d13e7cf34f49b1aa` |
| linux/amd64 | `sha256:507b76f097cd0f4a0f998a346afe61f5776329913d6ab3c0bd678b6635356120` |
| linux/arm64 | `sha256:9c493ce4965bb26995e0f30b5a7799cb4628c83c1733cfca4dcd4ac2e92cb1a6` |

The index also lists ppc64le `a5daf02d...d58b`, riscv64 `3c45ad7a...2beb` and s390x `486cba6f...e86a`, and no attestation
manifests. The architect's three digests are confirmed.

## 3. N2 step 2: cosign verify of the image (FAILED: not signed)

cosign image (the grype record's): `ghcr.io/sigstore/cosign/cosign:v3.1.3@sha256:9e5c2f2edc34351160407ca3416c61855bdf9403c3c5936e0f0be7fc261611b8`
(index digest re-checked with `imagetools inspect`). Every container ran with `--rm --label ke.scratch=sec-u2`.

```
$ docker run --rm --label ke.scratch=sec-u2 $COSIGN verify \
    --certificate-identity 'https://github.com/anchore/syft/.github/workflows/release.yaml@refs/heads/main' \
    --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
    docker.io/anchore/syft@sha256:3eb5379ba7b409c3f4069b686110527af0c47df993fa5c10d13e7cf34f49b1aa
Error: no signatures found
exit=10
$ ... verify --certificate-identity-regexp '^https://github.com/anchore/syft/' ... (docker.io and ghcr.io index)  -> no signatures found, exit=10
$ ... tree <index> / <amd64> / <arm64>  -> No Supply Chain Security Related Artifacts found (all three)
```

## 4. N2 step 3: signed checksums.txt, then the image binary

### 4a. The checksums.txt signature

```
$ gh release download v1.54.1 -R anchore/syft -p 'syft_1.54.1_checksums.txt' -p 'syft_1.54.1_checksums.txt.sigstore.json' \
    -p 'syft_1.54.1_linux_amd64.tar.gz' -p 'syft_1.54.1_linux_arm64.tar.gz'
7577f0d0b3fb16f65a2e56b413862f69aa5eaa2379d5760cb73d691ca7986059  syft_1.54.1_checksums.txt
0ceabca2ff98a0791cb09d70b175ab51f5d4798c2a4cb3b2d77be9e396e10b3e  syft_1.54.1_checksums.txt.sigstore.json
$ docker run --rm --label ke.scratch=sec-u2 -v "<dl>:/work:ro" $COSIGN verify-blob \
    --bundle /work/syft_1.54.1_checksums.txt.sigstore.json \
    --certificate-identity 'https://github.com/anchore/syft/.github/workflows/release.yaml@refs/heads/main' \
    --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' /work/syft_1.54.1_checksums.txt
Verified OK
exit=0
```

Both sha256 values equal the `digest` GitHub records for those release assets (`u2/security-release-facts.txt`).

Signing certificate (bundle `application/vnd.dev.sigstore.bundle.v0.3+json`, leaf decoded with openssl):

```
issuer=O=sigstore.dev, CN=sigstore-intermediate
notBefore=Oct  6 15:34:03 2026 GMT   notAfter=Oct  6 15:44:03 2026 GMT
SAN (critical)  URI:https://github.com/anchore/syft/.github/workflows/release.yaml@refs/heads/main
1.3.6.1.4.1.57264.1.1  (issuer)      https://token.actions.githubusercontent.com
1.3.6.1.4.1.57264.1.2  (trigger)     workflow_dispatch
1.3.6.1.4.1.57264.1.3  (commit)      b254e6d92f28c3868a755f62fb3ca8f26e9fee76   <- = v1.54.1 tag commit
1.3.6.1.4.1.57264.1.5  (repository)  anchore/syft
1.3.6.1.4.1.57264.1.6  (ref)         refs/heads/main
1.3.6.1.4.1.57264.1.11 (runner env)  self-hosted                                <- see G2
1.3.6.1.4.1.57264.1.21 (run)         https://github.com/anchore/syft/actions/runs/37480824322/attempts/2
rekor logIndex 3111715024, integratedTime 1791300844 (2026-10-06T15:34:04Z), hashedrekord 0.0.1
```

Run 37480824322: head_sha `b254e6d9...ee76`, main, workflow_dispatch, attempt 2, success.

Negative controls (same cosign image, `u2/security-cosign-blob.txt`):

```
NEG1 wrong identity (anchore/grype release.yaml): no matching CertificateIdentity ... got ".../anchore/syft/...release.yaml@refs/heads/main"  exit=1
NEG2 wrong issuer (https://accounts.google.com): expected issuer value "https://accounts.google.com", got "https://token.actions.githubusercontent.com"  exit=1
NEG3 tampered checksums.txt (amd64 line, first nibble c->d, separate copy): invalid signature when validating ASN.1 encoded signature  exit=1
```

### 4b. Archives match the signed checksums

```
c069905b391cc4c20a5ba65ad5c10be2a7ba074f8ea6ad203e24d14e303dad47  syft_1.54.1_linux_amd64.tar.gz
dfdf0537610113edbefe1f1fc6548bc957b2d77439636ec824fcf0e10d46d054  syft_1.54.1_linux_arm64.tar.gz
$ sha256sum -c --ignore-missing syft_1.54.1_checksums.txt
syft_1.54.1_linux_amd64.tar.gz: OK
syft_1.54.1_linux_arm64.tar.gz: OK
$ tar -tvzf syft_1.54.1_linux_<arch>.tar.gz   (both: CHANGELOG.md, LICENSE, README.md, syft; regular files, no ../ or links)
-rwxr-xr-x runner/runner 91779234 2026-10-06 07:36 syft   (amd64)
-rwxr-xr-x runner/runner 85196962 2026-10-06 07:36 syft   (arm64)
$ tar -xzf syft_1.54.1_linux_<arch>.tar.gz -C x-<arch> syft   (each into its own empty dir)
```

### 4c. /syft copied out of each platform image (docker create + docker cp; never run)

```
$ docker pull --platform linux/amd64 anchore/syft@sha256:507b76f097cd0f4a0f998a346afe61f5776329913d6ab3c0bd678b6635356120
$ docker pull --platform linux/arm64 anchore/syft@sha256:9c493ce4965bb26995e0f30b5a7799cb4628c83c1733cfca4dcd4ac2e92cb1a6
$ CA=`docker create --platform linux/amd64 --label ke.scratch=sec-u2 anchore/syft@sha256:507b76f0...6120`
$ CB=`docker create --platform linux/arm64 --label ke.scratch=sec-u2 anchore/syft@sha256:9c493ce4...b1a6`
$ docker container inspect -f '{{.State.Status}} started={{.State.StartedAt}}' $CA $CB
created started=0001-01-01T00:00:00Z   (both)
$ docker cp $CA:/syft img-amd64/ ; docker cp $CB:/syft img-arm64/
$ sha256sum x-amd64/syft img-amd64/syft x-arm64/syft img-arm64/syft ; cmp (both identical)
dbf75864e7a7ff9e1fbf00552c31483f693188632a9f68f343cd7653dac513d6 *x-amd64/syft
dbf75864e7a7ff9e1fbf00552c31483f693188632a9f68f343cd7653dac513d6 *img-amd64/syft
7d3cc523a2652d26568b9b2b94b5419dbf05f34ce896cf29904a0073d84eecf2 *x-arm64/syft
7d3cc523a2652d26568b9b2b94b5419dbf05f34ce896cf29904a0073d84eecf2 *img-arm64/syft
$ docker rm $CA $CB
```

| Platform | archive syft SHA-256 | image /syft SHA-256 | Match |
|---|---|---|---|
| linux/amd64 | `dbf75864e7a7ff9e1fbf00552c31483f693188632a9f68f343cd7653dac513d6` | same | yes |
| linux/arm64 | `7d3cc523a2652d26568b9b2b94b5419dbf05f34ce896cf29904a0073d84eecf2` | same | yes |

Chain: release-workflow OIDC identity (anchore/syft `release.yaml@refs/heads/main`, commit `b254e6d9`) -> signed
checksums.txt -> archive SHA-256 -> binary inside the archive == /syft in the platform manifest under the pinned index.

Q48: this is a signed upstream checksum, not trust-on-first-use.

Image config (both platforms): Entrypoint `["/syft"]`, User "" (root), 3 layers, created 2026-10-06T15:34:16Z
(13 s after the signing certificate was issued, 54 s before the release was published). Labels: `org.opencontainers.image.version=1.54.1`,
`org.opencontainers.image.revision=b254e6d92f28c3868a755f62fb3ca8f26e9fee76` (= the signed commit).
Contents (amd64; `docker export | tar -tv`, `docker image history`): a scratch image with
`COPY /etc/ssl/certs/ca-certificates.crt` (224449 bytes), `WORKDIR /tmp`, `COPY linux/amd64/syft /`. There are no other regular files
(the rest are entries Docker creates on create). This matches the Dockerfile at the tag (`FROM scratch`, certs from distroless static-debian13).

## 5. Gaps and residuals

| Id | Grade | Gap |
|---|---|---|
| G1 | info | The image is unsigned (no `docker_signs`, `--provenance=false`). Closed by the N2 step 3 chain above, which is the same as grype's. |
| G2 | low | Unlike grype v0.120.1 (`runs-on: ubuntu-24.04`), syft v1.54.1 was built on a self-hosted runner (a runs-on.com ephemeral instance; cert OID 1.3.6.1.4.1.57264.1.11 = `self-hosted`). The signature binds the workflow identity, repo, ref and commit. It does not attest a GitHub-hosted build machine, so the build host's integrity rests on Anchore's own infrastructure. Non-blocking: nothing to fix on our side. Re-check the runner environment at each syft bump. |
| G3 | info | `ca-certificates.crt` is not covered by the signature; the manifest digest fixes it. syft runs with `network_mode: none` (N1), so the file is not used. |
| G4 | info | ppc64le, riscv64 and s390x are not checked. They are not deployment arches (bundles are amd64/arm64). |
| G5 | info | The architect ran `syft config` from the pinned image (with `--network none --read-only`) before this record existed. The binary is now shown to be the signed release binary, so nothing is left over. For later pins: record provenance before the image is run. |

Every binary was tied to the release tarball; none was left unmatched.

## 6. Cleanup

- Removed: every container labelled `ke.scratch=sec-u2` (`docker ps -a --filter label=ke.scratch=sec-u2` is empty), the cosign image,
  the by-digest refs `anchore/syft@sha256:507b76f0...6120` and `@sha256:9c493ce4...b1a6`, the arm64 variant's content
  (`docker image rm --force --platform linux/arm64 anchore/syft:v1.54.1`), and every scratch download and extract dir.
- **Kept:** `anchore/syft:v1.54.1@sha256:3eb5379b...49b1aa` with its linux/amd64 content (the architect's pull; this host's platform),
  for the developer's U2 GREEN run and the interim pull path (`u2/security-cleanup.txt`).
