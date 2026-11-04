# platform-sbom U7e: security review of the GREEN diff (2026-10-28, UTC)

Scope: `git diff 45411ae -- docker/ licenses/ NOTICE.md tests/fixtures/` (tests/*.py excluded this round, per brief).
Method: read-only. Downloads went into new empty scratch dirs (never the repo), scripts lived in a separate dir and ran with `python -I`.
Images were read with `docker create` plus `docker cp` and never started; the scans ran with `--network none`. Profile paths are redacted as <scratch>.

## Verdict: PASS (0 critical, 0 high, 1 medium, 2 low; none blocking)

## 1. FROM lines and NOTICE: PASS
- app.Dockerfile l.13 (builder) and l.45 (runtime), and gates.Dockerfile l.9, are each byte-equal to
  `python:3.12-slim-bookworm@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753`. NOTICE.md l.74 is the same.
- No `34386ef0` or `3.12.15` is left in docker/, licenses/ or NOTICE.md. The Dockerfile diff is only those 3 lines.
- No libssl pin was added. gates.Dockerfile l.16's unpinned `libssl3` is older than this change and unchanged; the image resolves it to deb12u2.

## 2. Licence files: PASS. The M-2 NOTICE sentences still hold.
- I re-fetched `raw.githubusercontent.com/python/cpython/v3.12.16/Doc/license.rst` (200, 54130 B, no redirect). Its sha256 is `341832873f...f4e5`, equal to the file header and to the tarball's own `Doc/license.rst`.
- My own second-fetch tarball (2026-10-28, kept in <scratch>) re-hashed to `b5796915...575c` before it was read. I read the members in memory and extracted nothing.
- The incorporated, HACL (23 lines) and KaRaMeL (2 lines) bodies equal the source extracts and the 45411ae (3.12.15) bodies byte for byte. Only header lines changed: 1-2 in incorporated, 1-4 in HACL and KaRaMeL. Line counts are unchanged.
- `Modules/_hacl/` headers: 13 MIT and 5 Apache-2.0, plus README, refresh.sh, types.h and namespaces.h with no licence header. There is no new third-party header.
- The new ke-app's `/usr/local/lib/python3.12/LICENSE.txt` is 13936 B, sha256 `3b2f81fe...a3bf`, unchanged, with 0 expat/mpdecimal/HACL hits. So NOTICE's "licence stack only" sentence and its incorporated/HACL/KaRaMeL sentences stay true.

## 3. Lock entries: PASS
- I re-fetched each .dsc from its locked URL (200, no redirect):
  - `snapshot.debian.org/file/eb6d0239...2ef0`: sha1 `eb6d0239...`, sha256 `7c45299a...d337`, 2742 B. All equal to the lock.
  - `.../file/197e29fa...f66a`: sha1 `197e29fa...`, sha256 `a041820e...c0b7`, 1924 B. All equal to the lock.
- Both .dsc files are clearsigned. Source and Version equal the key. Every other file's sha256 and size equals the .dsc's Checksums-Sha256, and its `/file/<sha1>` URL equals the .dsc's Checksums-Sha1.
- The file sets match exactly: openssl has orig, orig.asc and debian.tar.xz; ca-certificates has its tar.xz.
- `mr/file/<sha1>/info`: openssl is in debian-security, first_seen 20261026T032458Z; ca-certificates is in debian-security, first_seen 20261020T211310Z.
- `lock_problems(lock text, policy, 6 U3 fixtures, amd64) == []`. `lock_text(lock) == file` (canonical, no CR, 183 components). `lock_needs` problems: [].
- `deb:openssl@3.0.22-1~deb12u1` is still needed, by postgres (libssl3 and openssl rows). `~deb12u2` is needed by ke-app only.
- `ca-certificates~deb12u1`: no fixture carries it now. ke-neo4j and phoenix use `@20250419`, a separate key that is kept. Removing it is correct.
- tzdata has no key: it is `LicenseRef-public-domain`, so needs is False (no `always` entry). It is consistent with U7d, where 2026c had no key either.
- The lock is tool-generated. `lock-run-1.txt` ends with the tool's `git diff --stat` line (+65/-12), which `sources_lock.sh` prints only after lock-check passes and the move. Shared orig tarballs reuse the deb12u1 sha1 URLs, as expected. No hand edit is visible.

## 4. Fixture: PASS
- `tests/fixtures/sbom-u3/ke-app.pkgs.tsv` is cmp-equal to `u7e/sboms/ke-app.pkgs.tsv`. It has 154 rows.
- The changed rows are 10, 93, 114, 131, 147 and 154: ca-certificates, libssl3, openssl, python 3.12.16, tzdata and the oci root digest. Each is explained by base-dpkg-diff.txt or by the CPython and image change.
- The new ke-app and ke-gates images both hold base-files 12.4+deb12u15. Their `/usr/share/common-licenses/Apache-2.0` is sha256 `cfc7749b...3d30`, equal to `APACHE_2_SHA256` and `licenses/Apache-2.0.txt`, so the pin holds.

## 5. OWASP and general: PASS
- No secrets, tokens, keys, connection strings, signed query strings, profile paths or SIDs were found. The grep covered the diff and every u7e evidence file, including the sboms/ file.
- No new network path: the Dockerfiles change only the digest, and the new URLs are notice text and https snapshot/python.org lock URLs on allowed hosts.
- No product code, agent tool use or tracing changed.

## 6. Scan: PASS for ke-app
- The developer's direct `scripts/scan.sh` showed exit 0. My own run used the pinned grype v0.120.1 with a fresh DB v6.1.10 (built 2026-10-27T06:30Z), `--network none`, `--only-fixed --fail-on high`, on `ke-app:wt-33a132fbfdd7`. It exited 0 (`security-scan-ke-app.txt`).
- CVE-2026-84782 is resolved: there are 0 hits, and libssl3/openssl deb12u2 show only the suppressed Negligible CVE-2025-27587.
- The unsuppressed rows are only CPython 3.12.16 Medium/Negligible, whose fixes exist only on other release lines. Nothing fixed-and-High remains in ke-app.
- ke-gates is not in the gate's scope (scan.sh scans ke-app only, Q68/A68). My supplementary run exited 2 (`security-scan-ke-gates.txt`). See M-1.

## Findings
- **M-1 (medium, non-blocking; older than this change and not caused by it).** ke-gates carries fixed Critical/High findings outside the Debian base:
  - `/usr/local/lib/docker/cli-plugins/docker-compose` (COMPOSE_VERSION 5.6.0): Go stdlib go1.26.8 has GO-2026-6612 and -6604 (Critical) plus 8 High; golang.org/x/net v0.58.0 has -6612 (Critical) plus 3 High.
  - `/usr/local/bin/uv` (0.11.21): quinn-proto 0.11.14 has GHSA-4w2j-m93h-cj5j (High).
  - U7e does not touch either pin. ke-gates is not bundled and runs with no network (fast) or on the internal backend network (full), so exposure is low.
  - Follow-up for the human: bump the compose and uv pins, and add ke-gates to the "Scan every bundled image" follow-up.
- **L-1 (low).** `fixture-diff.txt`, `developer-green.md` and the developer's handoff line say "7 rows differ", but the diff has 6. Each of the 6 is explained, so only the count is wrong.
- **L-2 (low, tester's file).** The comment above `APACHE_2_SHA256` (tests/test_notice_ke_app.py l.238-239) names only the old base `34386ef0...7258`. The hash still holds on `6dd8b6da...9753`, so add the new digest to the comment.
- Info: postgres still carries openssl deb12u1 and is not scanned (Q70, known). `lock-run-1.txt` does not print the exit code (see section 3).
