# Security review: Q83 (a) re-lock diff (2026-11-02)

Scope: `git diff docker/sources.lock.json` (working tree vs HEAD bc5e65e), plus
`sources_lock-run.txt`, `dpkg-before.txt`, `dpkg-after.txt`, `build-no-cache.txt`,
`sboms.md` in this directory, and the six SBOMs at <scratch>/relock-20261102-sboms/
(read with `python -I` scripts kept in a separate dir, never run inside it).
Network: available; snapshot.debian.org and security-tracker.debian.org were
queried over HTTPS (curl `--proto =https`). Downloads went to an empty dir of their own.

**Verdict: PASS.** No critical/high/medium findings. Two low, one informational.

## 1. Diff adds exactly one entry, changes nothing else: CONFIRMED
- `git diff --numstat`: `42 0 docker/sources.lock.json`.
- Structural JSON compare of HEAD vs working copy: top-level keys `components`, `format`
  in both; `format` unchanged; components 183 -> 184; added
  `deb:cyrus-sasl2@2.1.28+dfsg-10+deb12u1`; removed none; changed none (no host,
  URL, hash, size, upstream or arch change in any other key).
- `deb:cyrus-sasl2@2.1.28+dfsg-10` is unchanged and keeps `arches: [amd64]`.
- Both files are canonical (`json.dumps(indent=1, sort_keys=True)` + LF, no CRLF); the new
  key sits in sort order between `deb:cyrus-sasl2@2.1.28+dfsg-10` and `deb:dash@0.5.12-12`.
- No secret-like content in the diff (grep for AKIA/ghp_/PRIVATE KEY/token/secret/password/
  `://user@`): none.

## 2. Hosts, URL shape, .dsc checksums: CONFIRMED
- All three URLs are `https://snapshot.debian.org/file/<sha1>`; `snapshot.debian.org` is
  in `docker/source-policy.json` `hosts`.
- Shape matches `scripts/sources_resolve.py` `resolve_deb` / `dsc_files` (l.717-744): the .dsc
  entry has `upstream.alg sha1`, `from "snapshot.debian.org mr/package fileinfo"`; the
  others have `alg sha256`, `from "<dsc> Checksums-Sha256"`, value == sha256; kind deb,
  origin generated. Same shape as the existing -10 entry.
- Fetched `https://snapshot.debian.org/file/4602f48152c33d44ae1c10e21dddc9779fa4a56d`: HTTP
  200, 3670 bytes, sha1 4602f481...a56d, sha256 088990ef...2ff0 (== lock). Source
  cyrus-sasl2, Version 2.1.28+dfsg-10+deb12u1, PGP-signed (issuer fpr 6201FBFF...7B5847,
  debian@alteholz.de; signature not verified locally, no Debian keyring; the lock's trust
  model is snapshot's sha1 over TLS).
- .dsc Checksums-Sha256 / Checksums-Sha1 vs lock:
  - orig.tar.xz: a15886d7...b3d9, 797472; sha1 8b00d7de...b244 (== lock URL). Same file
    and URL as the -10 entry's orig (same upstream tarball).
  - debian.tar.xz: 390fa943...f8b4, 99600; sha1 a8d9eb37...1952 (== lock URL).
- Beyond the resolver: fetched snapshot's `srcfiles?fileinfo=1` (all three names map to
  the lock's sha1s; new files first seen in archive `debian-security` 20261030T155321Z)
  and both tarballs: sha256 and sizes equal the lock.

## 3. SBOM hashes and the shipped versions: CONFIRMED
- sha256, size and `.packages | length` of all six SBOMs equal `sboms.md`
  (ke-app 154, ke-gateway 72, ke-neo4j 340, phoenix 278, postgres 150, valkey 25; all SPDX-2.3).
- ke-app.spdx.json: libsasl2-2 and libsasl2-modules-db 2.1.28+dfsg-10+deb12u1 (upstream
  cyrus-sasl2); libldap-2.5-0 2.5.13+dfsg-5; libpq5 15.19-0+deb12u1.
- postgres.spdx.json: libsasl2-2 and libsasl2-modules-db 2.1.28+dfsg-10, so keeping the
  -10 key for amd64 is right.

## 4. No other ke-app package changed: CONFIRMED
- dpkg-before/after differ only in libsasl2-2 and libsasl2-modules-db (-10 -> +deb12u1);
  libldap-2.5-0 and libpq5 the same. These files list only the four runtime-stage apt packages.
- build-no-cache.txt runtime stage: apt fetched exactly those four (sasl from
  bookworm-security, libldap from bookworm, libpq5 from bookworm-security); base images
  digest-pinned.
- ke-app SBOM vs committed fixture `HEAD:tests/fixtures/sbom-u3/ke-app.pkgs.tsv`
  (purl, version, declared|concluded licence), 154 vs 154 rows. The only differences:
  - libsasl2-2: fixture `...@2.1.28%2Bdfsg-10?...` -> SBOM `...@2.1.28%2Bdfsg-10%2Bdeb12u1?...`
  - libsasl2-modules-db: same change.
  - image root `pkg:oci/%2Fin%2Fke-app.tar@sha256%3A...`: digest 1c7c08b2...3f7d ->
    d3b2c840...981e (the rebuilt image).
  Licences are the same for every common row. The working-tree fixture (the tester's,
  uncommitted) already equals the SBOM exactly (0 differences). I did not edit it.
- postgres SBOM vs committed postgres fixture: 0 differences. (ke-gateway and valkey differ only in
  the image-root digest; the neo4j and phoenix fixtures model other inputs and their diffs
  are older than this change. Not in scope.)

## 5. Is +deb12u1 a security update: YES
- debian/changelog in the .debian.tar.xz: `cyrus-sasl2 (2.1.28+dfsg-10+deb12u1)
  bookworm-security; urgency=high`, LTS Team NMU, "CVE-2026-107161 ... heap-based buffer
  overflow ... in the DIGEST-MD5 plugin"; patch `debian/patches/0036-CVE-2026-107161.patch`.
- Debian security tracker (https://security-tracker.debian.org/tracker/CVE-2026-107161, fetched
  2026-11-02): bookworm 2.1.28+dfsg-10 vulnerable; bookworm (security)
  2.1.28+dfsg-10+deb12u1 fixed, via DLA-4871-1; Debian bug 1150516. This is the
  scan gate's finding (`ci/orchestrator-verify-full-docs-20261102.txt` l.2455-2456, High).

## 6. Redaction: nothing to redact
- No profile paths (`Users\adam`, AppData, `.claude` dirs) and no SIDs (`S-1-5-...`) in
  relock-20261102/* or the three new ci/ files; sboms.md already writes `<scratch>`.
  `/home/runner/...` in the CI log is the GitHub runner, not a profile. The checkout
  header there is masked (`AUTHORIZATION: basic ***`). No tokens, keys or model-host values.

## Findings
- **L-1 (low, not blocking, pre-existing, not in this diff):** the postgres vendor image
  (digest-pinned) still ships libsasl2-2 / libsasl2-modules-db 2.1.28+dfsg-10, which is
  vulnerable to CVE-2026-107161. `scripts/scan.sh` scans only ke-app, so no gate flags it.
  Exposure: a client-side overflow reached through libldap's SASL DIGEST-MD5 to a hostile
  server, so only if LDAP auth is set up in postgres, which this stack does not do as far as
  I saw. Follow-up: bump the postgres digest when upstream rebuilds on
  +deb12u1 (that is a re-lock, and the -10 key then loses amd64), and decide whether the scan
  should cover vendor images. For the orchestrator/human.
- **L-2 (low, supply-chain hygiene, part of Q83 (b)):** libpq5's apt-added dependencies are
  unpinned, so the image content depends on build date and cache (the cause of this drift).
  Q83 (b) already covers it. Not blocking.
- **I-1 (info):** Q83's context (open-questions, "Without --refresh" bullet) predicted that
  `deb:cyrus-sasl2@2.1.28+dfsg-10` "is dropped". It correctly stays, because postgres still needs it
  (sboms.md note). The analyst may want to amend the text. sboms.md's "run in the sboms
  directory" commands (jq/sha256sum) are low risk, but running tools from outside an untrusted
  dir is the documented practice.

## Commands (reproducible)
- `git show HEAD:docker/sources.lock.json` vs working copy, compared structurally with `python -I`.
- `curl -sS --proto =https` for .dsc, srcfiles?fileinfo=1, orig/debian tarballs, tracker pages;
  `sha1sum`/`sha256sum`; `tar -xJf ... debian/changelog` into an empty dir.
- `sha256sum`/`stat` on the SBOMs; `python -I` extraction of the purl/version/licence rows
  and comparison with `git show HEAD:tests/fixtures/sbom-u3/<img>.pkgs.tsv`.
