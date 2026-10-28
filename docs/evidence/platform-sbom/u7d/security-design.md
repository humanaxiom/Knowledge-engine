# platform-sbom U7d: security design review (pgdg kind, the tenth host, the Q72 retry)

Date: 2026-10-26 (UTC). Auditor: security. Scope: design-notes "U7d precision" (l.2107-2306:
P1-P6, R1-R6) with orchestrator rulings P-R1 (no Release signature check) and P-R2 (a mid-body
timeout is retried as a full restart). Real requests went to `apt-archive.postgresql.org` only;
see `u7d/security-design-probes.txt`. The tester probe `u7d/suite-probe.txt` was read alongside.
No code exists yet.

## Verdict: design review PASS, with one required amendment and five recommendations

The host is acceptable as the tenth egress host, and the trust chain without signature
verification is acceptable under P-R1. One fact breaks the design as written: **there is no
`Sources.gz`** (A-1, required; the tester found the same). The recommendations are R-1 to R-5
below. None blocks the RED once A-1 is amended.

## 1. `apt-archive.postgresql.org` as an egress host
- **Operator:**
  - The apt repository of the PostgreSQL Global Development Group (Origin
    `apt-archive.postgresql.org`, Label "PostgreSQL for Debian/Ubuntu archive repository").
  - It is served from AWS S3 behind CloudFront (`Server: AmazonS3`, `X-Cache` from cloudfront,
    CloudFront IPv6 addresses).
  - So the effective operators are PGDG (content) and AWS (hosting, TLS, CDN). PGDG is the
    project whose packages are already in the bundled `postgres` image.
- **TLS:** TLSv1.3, an Amazon RSA 2048 M01 certificate, SAN exactly
  `apt-archive.postgresql.org`, valid to 2027-01-12. All four probes answered directly, with no
  redirect, so the hop rules are trivially met. `KIND_HOSTS["pgdg"]` = this host alone is right.
- **Immutability:**
  - The `-archive` suites keep every version ever published, and pool files persist while the
    index is rebuilt: the probed `.dsc` is dated 2026-07-17, the Release 2026-10-21.
  - There is **no formal immutability promise**: the operator can overwrite or delete S3
    objects, and the Release has no `Valid-Until`.
  - Treat it like snapshot.debian.org: a vanished or changed file fails U8 closed (Q61), never
    silently.
- **Pool paths:** Debian layout, confirmed: `pool/main/p/postgresql-common/<name>`. The tester
  stanzas give `Directory: pool/main/p/postgresql-16` and `-18`, which matches the P2 pool rule
  (`p` for `postgresql-*`).
- `bookworm-pgdg` (non-archive) has no Release on this host (404, tester). The `-archive` suite
  is the only form, as P1 says.

## 2. The trust chain without signature verification (P3, P-R1)
- **What an attacker can do at resolution time** if they control the host, the bucket, the CDN
  or a mis-issued certificate: serve a different `.dsc` and a Sources index consistent with it.
  The resolver would record the hashes of the attacker files, and the lock would pin them.
  - The impact is a wrong "corresponding source" for GPL binaries, which is a compliance failure.
  - It is not code execution: the files are never unpacked, built or run.
- **What bounds it:**
  - The window is the resolution run only. After commit, U8 checks every file against the
    pinned sha256, so later tampering fails closed.
  - The lock is reviewed. Security re-fetches a sample from another network path (S8), and the
    human approves the diff.
  - There are only three pgdg keys (3 `.dsc`, about 7 files), so a full re-fetch is cheap.
- **Signature, checked out of band today:**
  - The InRelease is signed by RSA key `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8` ("PostgreSQL
    Debian Repository", 2011). That is **the same key the bundled `postgres` image already
    pins** (`/usr/local/share/keyrings/postgres.gpg.asc`, `signed-by` in its apt source).
  - `gpgv` against that key: "Good signature".
  - The signed Release gives Sources sha256 `9550c528...fe722` (5043212 B) and Sources.bz2
    `b7963a2d...fd3a`, which is the tester download.
  - The tester stanza gives the postgresql-common `.dsc` as `fc1b2290...91da`, 1538 B, which
    equals my independent fetch.
  - So for postgresql-common the whole chain, key to Release to Sources to `.dsc`, verifies
    today.
- **Recommendation R-1 (not a ruling):** keep P-R1 for the tool, but make the lock review
  cryptographic at no code cost.
  - At S8, security runs `gpgv` on the InRelease that the run used, with the key fingerprint
    pinned in the official postgres image. It then checks the Sources hash against the signed
    Release and the three stanza hashes against the lock, and records all of it in
    `sources-provenance.md`.
  - This adds no new trust root, since the image already depends on this key. It turns the one
    unsigned link into a checked one for every pgdg entry.
  - In-tool verification (a pinned fingerprint plus `gpgv`/`sqv` in the gates image, or a
    stdlib OpenPGP verifier) is worth it only if pgdg entries grow; a hand-written verifier is
    the larger risk. Without `Valid-Until`, any in-tool check should also bound the Release
    `Date` (for example, no older than the image build).
  - Note: the `.dsc` files themselves are unsigned, so the InRelease is the only signature in
    this chain.

## 3. The retry policy (R1-R6, P-R2) as an attack surface
Holds:
- Only 5xx and timeouts are retried.
- 4xx, including 418 and 429, and every refusal, cap, deadline, hash, parse or binding failure
  fail on the first occurrence.
- `retries=0` is the default, so U8 cannot opt in by accident.
- No environment knob. `Retry-After` is not honoured, which is right: a server must not choose
  our waits.
- A restart rebuilds hashers and counts from the first URL, so the hop rules apply again.

Recommendations:
- **R-2 (stall budget):** the worst case is 4 x (600 + 60) s + 100 s, about 45 min per logical
  request. A hostile or failing listed host answering 5xx slowly, or timing out, can hold the run
  for hours: snapshot alone is about 304 logical requests. Add a run-wide cap, for example
  20 retries per run and a total wall-clock budget, after which the run fails with the last
  error.
- **R-3 (snapshot load):**
  - The ceiling is 304 x 4 = 1216 requests to snapshot, each preceded by `SNAPSHOT_PAUSE`, plus
    10/30/60 s waits. That is modest per run.
  - A 429 from snapshot fails closed by design, which is correct.
  - Keep the pause applying to every attempt, as R6 says, and do not shorten the waits for
    snapshot.
- **R-4 (printed URLs):** the retry line prints the failing URL with a signed GitHub query. It is
  a short-lived capability URL for a public asset, not a secret of ours. Still, for consistency
  with the provenance records, print the query as `?<query omitted>` and keep the full URL out
  of evidence.
- **R-5 (never retry; pin in tests):**
  - a TLS or certificate failure (an `ssl.SSLError` is an `OSError`; it must stay in the
    "other OSError" class)
  - a connection reset
  - any 3xx anomaly, a redirect-limit breach, a hop refusal
  - the byte cap, the deadline
  - a hash or size mismatch, which is deterministic and must not be re-fetched hoping for
    other bytes

## 4. The index (P2) and the Sources handling
- **A-1 (required amendment):** `main/source/Sources.gz` does not exist (404, also `.xz`). The
  signed Release lists only `Sources` (5043212 B) and `Sources.bz2` (734866 B).
  - Recommendation: fetch the **uncompressed `Sources`**. It is 5 MB, so no decompressor runs at
    all and there is no bomb surface.
  - Use a byte cap sized to the file (for example 64 MiB, not 1 GiB).
  - Check its size and sha256 against the values recorded from the signed Release at review
    (R-1).
  - If bz2 is chosen instead, cap the decompressed size near the real size (for example 64 MiB,
    not 4 GiB) to limit CPU spent on a crafted stream.
- **Stanza rules:**
  - The parse_dsc line rules are right: LF only, no controls, every line a field or a
    continuation.
  - Duplicate detection must be **per stanza**, not per file: in a Sources index, every stanza
    repeats `Package`. The round 1 `parse_dsc` refuses duplicates across paragraphs, which
    would refuse the whole index.
  - Non-ASCII letters in Maintainer or Uploaders must stay allowed: the refused set is C0/C1,
    DEL, U+2028 and U+2029 only, which already allows them.
  - As the tester noted, `Checksums-Sha256`/`Files` carry their first entry on the field line
    itself.
  - Keep only the matching stanza, and refuse a second match, as P2 says.

## 5. Other notes
- I-1: `pgdg` entries gain a fifth key, `suite`, and the U6 host-set test goes to ten hosts.
  Both are reviewed test changes, as intended.
- I-2: the `postgres` image fetches its binaries over plain `http://apt.postgresql.org` with
  `signed-by`. That is upstream; signature-verified apt over http is standard, and not ours to
  change.
