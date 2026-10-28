# platform-sbom U7e: PSC-1 provenance of the new ke-app / ke-gates base (python 3.12.16-slim-bookworm)

Date: 2026-10-28 (UTC; human ruling 2026-10-27). Recorded by security under rule G5, before the
first build. Every network step was an https GET or HEAD from the dev box (Git Bash, curl); no
profile path is recorded. The images were read with `docker buildx imagetools inspect`,
`docker image inspect`, and `docker create` plus `docker cp` of single files: nothing ran for
this record.

Disclosure: for the advisory check of 2026-10-28T00:24Z (`u7e/security-openssl.md`) I ran the
index digest once with `docker run --rm --network none` (`dpkg-query`, `python3 -c "import
ssl"`), then removed it. That was before this record.

## 1. The image
- Reference to pin (multi-arch index, OCI image index):
  `python:3.12-slim-bookworm@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753`.
- Per-arch manifests in the index (PSC-21 needs both of ours):

  | platform | manifest digest | created (OCI annotation / config) | base debian:bookworm-slim digest |
  |---|---|---|---|
  | linux/amd64 | `sha256:72c1d56207fb14ca388f9b3855ac0e55ab557703928180ec40aa9d4c4f5d5f80` | 2026-10-26T22:46:30Z / 2026-10-26T22:55:16Z | `sha256:ec31d744f83f4a73447ba045aaab9409997efe5cc706eca4890c1be36cc1606a` |
  | linux/arm64/v8 | `sha256:04b6d37c0976bcb0757d6bf6819ee4b7a4094497717896bc002f845b9c06c752` | 2026-10-26T22:49:46Z / 2026-10-26T23:01:42Z | `sha256:991827bb788d78bbc130dcb851913beecff43296360f48838aca7cbdfae4375c` |

  The index also holds arm/v7, 386 and ppc64le images and one attestation manifest per arch
  (amd64 attestation `sha256:90d529ce...`, arm64 `sha256:c1415b70...`).
- **Source:** the annotations give `org.opencontainers.image.source =
  https://github.com/docker-library/python.git#3d7e95597e56a415d9e4abc0f15877e005d2cb2e:3.12/slim-bookworm`
  and `version 3.12.16-slim-bookworm`.
  - This is confirmed by `docker-library/official-images` `library/python` (fetched
    2026-10-28T01:00:42Z): `Tags: 3.12.16-slim-bookworm, 3.12-slim-bookworm`, `GitCommit:
    3d7e95597e56a415d9e4abc0f15877e005d2cb2e`, `Directory: 3.12/slim-bookworm`, Architectures
    amd64, arm32v7, arm64v8, i386, ppc64le.
  - The Dockerfile at that commit downloads the tarball, checks it with `sha256sum -c` against
    `PYTHON_SHA256`, and checks it with `gpg --batch --verify` against `GPG_KEY` (fetched from
    keys.openpgp.org).
- **Config (identical on amd64 and arm64):** `PYTHON_VERSION=3.12.16`,
  `PYTHON_SHA256=b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c`,
  `GPG_KEY=7169605F62C751356D054A26A821E680E5FA6305`.
- **dpkg status** (`/var/lib/dpkg/status` copied out; 105 packages on each arch; identical on
  amd64 and arm64):

  | package | version | source |
  |---|---|---|
  | libssl3 | 3.0.22-1~deb12u2 | openssl |
  | openssl | 3.0.22-1~deb12u2 | |
  | libc6 | 2.36-9+deb12u14 | glibc |
  | libgcc-s1, libstdc++6, gcc-12-base | 12.2.0-14+deb12u1 | gcc-12 |
  | libpq5 | not installed (the Dockerfile adds it) | |
  | ca-certificates | 20250419~deb12u2 | |
  | tzdata | 2026e-0+deb12u1 | |
  | base-files | 12.4+deb12u15 | |

- **Against the current ke-app (`ke-app:local`, built on the old base `sha256:34386ef0...`)**,
  only four base packages moved:
  - `libssl3` and `openssl` 3.0.22-1~deb12u1 -> **3.0.22-1~deb12u2** (DLA-4859-1; the advisory)
  - `ca-certificates` 20250419~deb12u1 -> 20250419~deb12u2
  - `tzdata` 2026c-0+deb12u1 -> 2026e-0+deb12u1

  No package was added or removed. ke-app adds the same four on top: libpq5, libldap-2.5-0,
  libsasl2-2, libsasl2-modules-db.
- **`/usr/local/lib/python3.12/LICENSE.txt`** is 13936 B, sha256
  `3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf`. That is the same in the
  new base, in the current ke-app, and in the tarball `LICENSE`.

## 2. Second fetch of the CPython source (2026-10-28T00:59:18Z)
`curl -q --proto '=https' --proto-redir '=https' --tlsv1.2 -sS` from
`https://www.python.org/ftp/python/3.12.16/` (one hop, no redirect, `www.python.org` served via
Fastly/varnish, Last-Modified Sun, 25 Oct 2026 19:24:29 GMT):

| file | size | sha256 |
|---|---|---|
| `Python-3.12.16.tar.xz` | 20839652 B | **`b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c`** |
| `Python-3.12.16.tar.xz.asc` | 833 B | (signature) |
| `Python-3.12.16.tar.xz.sigstore` | 7436 B | (bundle) |

- **The tarball sha256 equals the base `PYTHON_SHA256`.**
- **OpenPGP:**
  - The key was fetched from `keys.openpgp.org` by fingerprint: rsa4096
    `7169 605F 62C7 5135 6D05 4A26 A821 E680 E5FA 6305`, Thomas Wouters <thomas@python.org>,
    2015-03-11, expiring 2030-08-04. That fingerprint equals the base `GPG_KEY`.
  - `gpg --verify Python-3.12.16.tar.xz.asc Python-3.12.16.tar.xz`: **Good signature** from
    "Thomas Wouters <thomas@python.org>", made Sun Oct 25 12:19:33 2026 PDT. The key is not
    certified in a local trust web, so gpg shows `[unknown]`; the fingerprint match is the
    check.
- **Sigstore (identity read only, the bundle is not verified; no sigstore client):** bundle
  v0.3, 1 tlog entry. Its certificate SAN is `email:thomas@python.org`, with OIDC issuer
  `https://accounts.google.com`, valid 2026-10-25 19:20:15 to 19:30:15 GMT. This is the
  identity python.org publishes for the 3.12 release manager.

## 3. Licence-file inputs (U1 pattern), read from the tarball in memory (nothing extracted)
| member | size | sha256 | equal to 3.12.15 |
|---|---|---|---|
| `Python-3.12.16/Doc/license.rst` | 54130 B | `341832873fd316a37927e79385093fbbfd40a467428480835fe435a80cadf4e5` | yes (U1 `Source sha256`) |
| `Python-3.12.16/Modules/_hacl/Hacl_Hash_SHA2.c` | 36131 B | `30638efb75c8b185bb09c3df6977e3f3c5d21a1e696218cf7ade6bc4d5201b31` | yes |
| `Python-3.12.16/Modules/_hacl/include/krml/internal/target.h` | 10653 B | `d16a59f37a1d4982626870e370889eb9d332a9ad035661b8062f549fc734d061` | yes |
| `Python-3.12.16/LICENSE` | 13936 B | `3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf` | equals the base `LICENSE.txt` |

The extracts use U1 ranges and are unchanged:
- **Incorporated software** (from the heading line to the end): sha256 `d4f3b214...698a`, 38036
  B, equal to the body of `licenses/CPython-3.12-incorporated.txt`.
- **HACL*** (`1,/^ \*\/$/`, 23 lines): sha256
  `998ce04fb8ad9dedb0bc1b44938f8c3dcf1089780fa105ce1c8c30fb5554d78c`.
- **KaRaMeL** (`1,/\*\//`, 2 lines): sha256
  `6b7cb4bd5441f287eeb8b745073c11bc5d2974252bec3b6d8c101ff67f918a26`.

So the three `licenses/CPython-3.12-*.txt` files need **only their headers** changed:
- `CPython 3.12.15` -> `3.12.16`
- the member and tarball paths -> `3.12.16`
- the tarball sha256 -> `b5796915...575c`
- for `-incorporated.txt`, the source URL `v3.12.15` -> `v3.12.16`, with the source sha256
  unchanged

The bodies stay byte-identical.

## 4. libpq5 and the lock
- **libpq5 (PSC-25 pin):**
  - `15.19-0+deb12u1` is still the newest `postgresql-15` on snapshot (then 15.18, 15.17).
  - It is served from `deb.debian.org/debian-security/pool/updates/main/p/postgresql-15/`:
    `libpq5` amd64 and arm64 and `libpq-dev` amd64, HEAD 200. It is not in the bookworm main
    pool (HEAD 404).
  - The new base apt sources include `bookworm-security`, so `LIBPQ_VERSION=15.19-0+deb12u1`
    (app and gates Dockerfiles) stays valid. No change.
- **libc6 and gcc-12 did not move** (2.36-9+deb12u14; 12.2.0-14+deb12u1). The lock keys
  `deb:glibc@...` and `deb:gcc-12@12.2.0-14+deb12u1` stay as they are.
- **Lock impact for ke-app:**
  - `deb:openssl@3.0.22-1~deb12u2` is new (snapshot `.dsc` sha1 `eb6d0239...`, see
    `u7e/security-openssl.md`), and postgres keeps `deb12u1`.
  - If its licence makes it needs-source, `deb:ca-certificates@20250419~deb12u2` (the
    `ca-certificates` source) replaces deb12u1 for ke-app.
  - `tzdata` follows the classifier.
  - The U3 ke-app fixture must move with the image (`u7e/security-openssl.md`, section 2).
