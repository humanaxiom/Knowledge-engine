# platform-sbom U7d: rework round 1 code re-check and S8 lock review

Date: 2026-10-26 (UTC). Auditor: security. Code: `sources_resolve.py`, `sbom_check.py` and
`sources_lock.sh` equal `u7d/r1-target-*` (design-notes l.2492-2721). Lock:
`docker/sources.lock.json` as written by `u7d/lock-run-4.txt` (uncommitted). Evidence:
`u7d/security-r1-probes.txt` (parts A code, B lock review, C network checks; scripts
`u7d/security_r1_probes.py`, `u7d/security_s8_review.py`).

## Verdicts
- **Code (round 1): PASS.** No critical, high or medium finding; L-1 is closed; no new finding.
- **Item 13 (scanner skips the lock): design acceptable**, with one optional addition.
- **S8 lock review: PASS.** One gate remains: the **third, network-independent Neo4j fetch is
  still blocked on the human, so the commit waits** (U7b ruling).

## A. Code re-check (part A)
| Item | Status | Evidence |
|---|---|---|
| security L-1 | **Closed** | `-L` entries fail ("is a link"), non-regular files fail, `cp -P`, a failed copy fails, and all of this happens before the lock `mv` (copy l.179, move l.188), to `--evidence-dir` (must exist, writable, quoted) |
| review B1 | Holds | Real opener on loopback: a TLS handshake to a silent server raises `TimeoutError` (unwrapped from URLError; retried). A plain-text answer to TLS raises `SSLError`, a closed port `ConnectionRefusedError`, an unknown name `gaierror`: none of these is retried |
| review B2 | Holds | `docker save -o "$(hostpath ...)"`, quoted |
| review N1 | Holds | A `trixie-pgdg-archive` suite on the bookworm entry is refused (`suite ... is not bookworm-pgdg-archive (from postgres distro ...)`); this closes my U7d I-2 |
| item 8 (symlinks) | Holds | Skipped only for a sibling regular blob. Refused: another directory, `../`, a path, a missing name, `.`, NUL, non-ASCII, non-strict base64, a `content_sha256` mismatch, size 0 or over 1 KiB, encoding other than base64, a link named in sha512sums, a link name equal to a blob name, a link where the caller passes no links map |
| item 10 (leading underscore) | Holds | `_service` and `_` are accepted. `_..x` and `-x` are refused |
| item 12 (size 0) | Holds | Size 0 is accepted only for an apk GitLab API-raw file with the empty sha256 (and the empty sha512 if sha512). Refused: another sha256, a wrong sha512, size -1, size 0 on distfiles or deb |

**Item 13 (design):** acceptable as PS-1.2. The skip is path-exact (an allowed-file entry, never a
line exemption), and the compensating committed-lock test pins the exact key sets plus "every
integer is a `size` or `format`". With U7a rules (no port, hosts from the ten), nothing port-like
can hide.
- Optional: run the scanner declared-value tokens over the lock string values in the same test.
  A declared value could otherwise sit unscanned in a file name or path segment. Every such
  segment is bound to an upstream name today, so this is defence in depth only.

## B. S8 lock review (parts B and C)
- **`lock_problems` is `[]`** for the committed lock, the committed policy (10 hosts) and the six
  fixtures. The text is canonical, LF only, 472945 B.
- **Shape:**
  - 182 entries (deb 152, apk 19, pgdg 3, pypi 5, maven 1, temurin 1, neo4j 1) and 872 files.
  - Arches are `amd64` for all. Origin is `generated`, except neo4j, which is `manual`.
  - Every (kind, host) pair is the allowed one, and every URL has its kind template.
    Queries appear only on the 344 apk GitLab API-raw URLs (`ref=<commit>`). No signed-query
    marker appears anywhere.
  - `from` texts are exactly the 11 templates (the U7a, U7c and U7d forms).
  - Sizes run from 14 to 151589656 B, totalling 1327035158 B. No size 0, and no empty-hash file.
- **Duplicates:**
  - 11 URLs are shared by two deb keys: an orig tarball common to two Debian revisions
    (bzip2, dash, db5.3, keyutils, libnsl, perl x2, readline, sed, xz-utils). Each shares the same
    sha256, and no URL carries two different sha256s.
  - 147 sha256 values appear under several URLs, all apk: the same file at two aports commits
    (alpine-baselayout 3.7.1 and 3.7.2). Both are legitimate.
- **pgdg chain:**
  - `gpgv` on the saved InRelease (sha256 `ed9bd2c7...12ec`, identical to my design-review fetch)
    with key `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8`, taken from the pinned postgres image:
    **Good signature**.
  - The signed `main/source/Sources` sha256 is `9550c528...fe722` (5043212 B), which equals the
    re-fetched Sources.
  - For each of the 3 keys: one stanza, the Directory pool rule holds, the lock files equal the
    stanza files (names, sha256, sizes), and the re-fetched `.dsc` equals the lock.
- **Spot re-fetches** (one per kind, all equal to the lock in sha256, size and the upstream
  hash):
  - deb: `netbase_6.4.dsc` from snapshot `/file/66c74bb2...`, sha1 included.
  - apk: `klogd.confd` through the GitLab API raw form, 200, no bot challenge.
  - apk distfiles: `protocols-6.4`.
  - maven: `jaxb-api-2.2.12-sources.jar`; the `.sha1` body equals its sha1.
  - pypi: `autocommand-2.2.2.tar.gz`.
  - temurin: the `.sha256.txt` sidecar, with 1 redirect to `release-assets.githubusercontent.com`.
- **Neo4j manual entry:** name `5.26.32.tar.gz`, sha256 `182ae2e5...91e3`, size 20907800, `from`
  `second fetch: security 2026-10-25, docs/evidence/platform-sbom/sources-provenance.md`.
  This equals the provenance record. **Third fetch: blocked**; the commit waits on the human
  (see `sources-provenance.md`).
- **Hygiene:** `docker/sources.lock.json`, `lock-run-0/2/3/4.txt`, `lock-run-1.raw`,
  `lock-sizes.txt` and `drift.txt` contain no signed queries, profile paths, SIDs, secrets or
  model-host name.
