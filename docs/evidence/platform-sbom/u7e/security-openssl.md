# platform-sbom U7e: the OpenSSL advisory behind the failed verify-full scan

Date: 2026-10-28 (UTC). Auditor: security. Trigger:
`u7d/orchestrator-verify-full-after-claude-row.txt` l.2075-2372 (grype, fresh DB, `--only-fixed
--fail-on high`, ke-app only). Every lookup below was an https GET or HEAD from the dev box at
2026-10-28T00:22-00:25Z (no profile path recorded). Image reads used `docker run --rm --network
none` or `docker create` plus an export, with nothing executed from the images beyond
`dpkg-query`, `apk info` and `python3 -c "import ssl"`.

## Verdict: advisory confirmed
The scan failure is real and correct under the scan policy. The fixed packages are published,
and so is a newer base that already carries them.

## 1. The advisory
- **CVE-2026-84782** (OpenSSL Security Advisory, 29 September 2026; OpenSSL severity **High**).
  - DTLS retransmission reads from a stale buffer offset. A peer can be sent heap memory as
    handshake data, or the process can crash (CWE-125).
  - It affects **DTLS only**; OpenSSL 3.0, 3.4, 3.5, 3.6, 4.0, 1.1.1 and 1.0.2 are vulnerable.
- **The same update** also fixes:
  - CVE-2026-75806 (DTLS 1.2 AEAD DoS)
  - CVE-2026-75805 (CMP NULL dereference)
  - CVE-2026-35189 (CRLDP memory)
  - CVE-2026-54872 and CVE-2026-77696 (EC/SM2 timing)

  OpenSSL rates these Low; grype shows Medium or Low.
- **Debian security tracker:**
  - Release table for bookworm: `bookworm 3.0.20-1~deb12u2 vulnerable`, `bookworm (security)
    3.0.22-1~deb12u2 fixed`.
  - The bookworm fix comes from **DLA-4859-1** (Debian LTS, "openssl - security update", all six
    CVEs). For trixie the fix is `3.5.7-1~deb13u3` (DSA-6531-1); forky and sid have `3.6.5-1`.
  - The tracker gives no Debian urgency.
- **On deb.debian.org:** `debian-security/pool/updates/main/o/openssl/` serves (HEAD 200, no
  redirect) `openssl_3.0.22-1~deb12u2.dsc` and `libssl3_3.0.22-1~deb12u2_{amd64,arm64}.deb` and
  `openssl_3.0.22-1~deb12u2_amd64.deb`.
- **On snapshot.debian.org** (for the future lock key `deb:openssl@3.0.22-1~deb12u2`; mr
  `srcfiles?fileinfo=1`):

  | file | sha1 | size | archive | first_seen |
  |---|---|---|---|---|
  | `openssl_3.0.22-1~deb12u2.dsc` | `eb6d0239f546f68a2f309e70f791c93205412ef0` | 2742 | debian-security | 20261026T032458Z |
  | `openssl_3.0.22-1~deb12u2.debian.tar.xz` | `8c2ffdb13c2e8e9e1ac6f740d66def6cba2549e7` | 72104 | debian-security | 20261026T032458Z |
  | `openssl_3.0.22.orig.tar.gz` | `35825835dccec008fa886601c3b4d1e52a32544b` | 15330396 | debian-security | 20260925T023309Z |
  | `openssl_3.0.22.orig.tar.gz.asc` | `51e4e8ce6452a32a2a800cc933befafcec6e7199` | 931 | debian-security | 20260925T023309Z |

  - The `.dsc` from deb.debian.org has sha256 `7c45299a4363febec120676393d4314841c7c50da244a6e6a256f072d632d337`
    and sha1 `eb6d0239...`, the same sha1 as snapshot; it reads `Source: openssl`,
    `Version: 3.0.22-1~deb12u2`.
  - The `libssl3` binaries are on snapshot from 20261026T040329Z (amd64 and arm64 included).
- **The CPython Mediums** (CVE-2025-12781, -15366, -15367, CVE-2026-12345, -3446, -6019, and
  the Negligible CVE-2026-3479):
  - grype lists fixes only for 3.13, 3.14 and 3.15, not for 3.12.
  - CPython 3.12.16 now exists on python.org (`/ftp/python/3.12.16/`). Whether it fixes these
    is not in the grype data and was not checked further.
  - **Scan policy:** `--only-fixed --fail-on high` (`docker-compose.scan.yml`). Mediums never
    fail, and a High with no fix never fails. Only a fixed High or Critical fails. So the
    OpenSSL High alone is the blocker.
- **Exposure, for context only:** ke-app uses OpenSSL through Python `ssl` and libpq, both TLS
  over TCP. Nothing in the engine uses DTLS. The practical risk is low, but the policy fails on a
  fixed High regardless, which is right: we do not argue with the gate.

## 2. Fix form (recommendation; the orchestrator decides)
- **A newer base already exists.** `python:3.12-slim-bookworm` now resolves to
  `sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753` (Hub `last_updated`
  2026-10-27T05:08Z; image created 2026-10-26T22:55Z). Read offline, it holds
  `libssl3=3.0.22-1~deb12u2` and `openssl=3.0.22-1~deb12u2`, `PYTHON_VERSION=3.12.16` and
  `OpenSSL 3.0.22`. (I pulled it once to read it, then removed it locally.)
- **Preferred for the U7d commit: the pinned apt install in the runtime stage of
  `docker/app.Dockerfile`**, as libpq5 is pinned today: `libssl3=3.0.22-1~deb12u2
  openssl=3.0.22-1~deb12u2` (an `ARG` beside `LIBPQ_VERSION`, `--no-install-recommends`).
  - It is the smallest reviewed change.
  - It fails the build by name when the version leaves the mirror, which is fail closed.
  - It leaves the CPython version, and so the CPython licence files that U1 verified (the drift
    check pins `CPython X.Y.Z` to the SBOM), untouched.
- **Then, as its own plan item: the base bump to `6dd8b6da...`** (CPython 3.12.16). It also
  needs:
  - the CPython licence-file refresh, with a second fetch of the 3.12.16 tarball against the
    base `PYTHON_SHA256`
  - the gates image pin
  - a fresh SBOM and lock
  - the libssl3 pin dropped again once the base carries it

  Done now, it widens U7d well beyond the advisory.
- **Either way, the lock moves:**
  - ke-app SBOM will list `openssl 3.0.22-1~deb12u2`, so the lock needs
    `deb:openssl@3.0.22-1~deb12u2` (the snapshot row above).
  - postgres keeps `3.0.22-1~deb12u1`, so both keys stay.
  - The committed-lock test reads the U3 fixtures, where ke-app has deb12u1, so the new key
    would count as stale against them. The fixture (or the test input) must move with the
    image. This is for the architect, not a security finding.

## 3. The other bundled images (read from the local images)
| image | package | version | state |
|---|---|---|---|
| ke-app (`ke-app:local`, bookworm) | libssl3, openssl | 3.0.22-1~deb12u1 | **vulnerable** (the scan finding) |
| postgres (`postgres:16-bookworm@sha256:0ea6700a...`) | libssl3, openssl | 3.0.22-1~deb12u1 | **vulnerable**; not scanned (Q70); PostgreSQL uses TLS, not DTLS. A newer upstream digest is the fix; the lock and NOTICE then move with it |
| phoenix (`arizephoenix/phoenix:version-20.22.0@...`, trixie, distroless) | libssl3t64 | 3.5.7-1~deb13u3 | fixed (DSA-6531-1) |
| ke-neo4j (`ke-neo4j:local`, trixie) | libssl3t64, openssl | 3.5.7-1~deb13u3 | fixed |
| *outside the question:* ke-gateway (Alpine 3.23.3) | libssl3, libcrypto3 | 3.5.5-r0 | below upstream 3.5.9; whether Alpine backported is not checked |
| *outside the question:* valkey (Alpine 3.24.2) | libssl3, libcrypto3, openssl | 3.5.8-r0 | below upstream 3.5.9; same caveat |

The two Alpine rows are information for the orchestrator. ke-gateway is first-party and not
scanned under Q70; neither image uses DTLS.
