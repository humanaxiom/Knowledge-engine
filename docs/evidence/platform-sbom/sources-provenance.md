# platform-sbom: source provenance (second fetches)

Q48 form, per N5 (`neo4j` kind) and the "N5 amendment, U7" items 3-4. Each record gives who, when
(UTC), the command, every hop host, the sha256 and size, and what the record proves. The files
were fetched into an empty scratch directory (`<scratch>/sec-u7b-fetch`) and never unpacked,
built or run.

## 2026-10-25: security, Neo4j 5.26.32 source tarball (lock key `neo4j:neo4j@5.26.32`)

**Version, from the image itself.** `ke-neo4j:bundle-c300d881cd94` (sha256:d4c9e9b6...7a24),
read with `docker run --rm --network none`:
- `NEO4J_TARBALL=neo4j-community-5.26.32-unix.tar.gz`, and `/var/lib/neo4j/lib` holds
  `neo4j-5.26.32.jar`.
- The fixture agrees: `tests/fixtures/sbom-u3/neo4j.pkgs.tsv` l.192 has
  `pkg:maven/org.neo4j/neo4j@5.26.32`.

**Fetch.** Host: the x86 Windows dev box (Git Bash, curl 8.19.0 Schannel). Redirects were
followed by hand; there was no `-L`.
```
curl -q --proto '=https' --proto-redir '=https' --tlsv1.2 -sS --max-time 60 \
  -o hop1.body -D hop1.headers -w 'hop1: %{http_code} %{remote_ip} %{redirect_url}\n' \
  https://github.com/neo4j/neo4j/archive/refs/tags/5.26.32.tar.gz
curl -q --proto '=https' --proto-redir '=https' --tlsv1.2 -sS --fail --max-time 600 \
  -o neo4j-5.26.32.tar.gz.part -D hop2.headers -w 'hop2: %{http_code} %{remote_ip} ...' \
  https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32
sha256sum 5.26.32.tar.gz; stat -c '%s' 5.26.32.tar.gz
```

**Hops.**

| Hop | Time (UTC) | Host | Result |
|---|---|---|---|
| 1 | 2026-10-25T07:50:21Z | `github.com` (140.82.114.4) | 302, `Location: https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32`, `Server: github.com` |
| 2 | 2026-10-25T07:50:28Z | `codeload.github.com` (140.82.112.10) | 200, `application/x-gzip`, `content-disposition: attachment; filename=neo4j-5.26.32.tar.gz`, ETag `"d1280bf87b076795453facbdb35ce5191fe2083adb90c3e964f001eda173883f"` |

Both hosts are in `docker/source-policy.json` `hosts`, and every hop is https.

**Result.**
- **sha256 `182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3`**
- **size 20907800 bytes**
- sha1 (information only): `2bc3d98f1b316b4fbbf47dfc312adc806c3fb27e`
- `file`: gzip compressed data, from Unix, original size modulo 2^32 115875840

**Commit.**
```
git ls-remote https://github.com/neo4j/neo4j refs/tags/5.26.32 'refs/tags/5.26.32^{}'
d766af19fdef5520fc7b148d5d77b9297ea1315d	refs/tags/5.26.32        (annotated tag object)
27f24499b751708815d42c8cf26bfb6597b3516c	refs/tags/5.26.32^{}     (the commit)
```
The tarball global pax header, read in place with Python `tarfile` (first header only, nothing
extracted), says `comment = 27f24499b751708815d42c8cf26bfb6597b3516c`. It is git-archive output
of that commit, with prefix `neo4j-5.26.32/`.

**The lock entry this supports** (the developer writes it by hand, `origin: manual`; U7a binding):
```
"neo4j:neo4j@5.26.32": {"kind": "neo4j", "origin": "manual", "arches": [...],
  "files": [{"name": "5.26.32.tar.gz",
             "url": "https://github.com/neo4j/neo4j/archive/refs/tags/5.26.32.tar.gz",
             "sha256": "182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3",
             "size": 20907800,
             "upstream": {"alg": "sha256",
                          "value": "182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3",
                          "from": "second fetch: security 2026-10-25, docs/evidence/platform-sbom/sources-provenance.md"}}]}
```
Write it only if the candidate from the developer tool (sha256 and size) equals the values above.
A disagreement goes to the orchestrator (N5). Today no candidate exists: U7b is in RED.

**What the check proves, and what it does not.**
- Neo4j publishes no checksum for this tarball. The lock pins the bytes that GitHub served on
  2026-10-25 under trust on first use, and this second fetch confirms them. When U8 fetches the
  file later and finds a matching sha256, that proves the bytes are identical to what was
  reviewed here. It does not prove the bytes are Neo4j's own. The tie to upstream is indirect:
  the archive names commit `27f24499...`, which the tag `5.26.32` points to today.
- GitHub generates tag tarballs on demand and does not promise they stay byte-stable (the gzip
  or tar layer can change). If the bytes change, U8 fails closed (Q61). The fix is a new first
  fetch plus a new second fetch, never a skip. The content can be re-derived from the commit:
  `git archive --prefix=neo4j-5.26.32/ 27f24499b751708815d42c8cf26bfb6597b3516c`. The gzip bytes
  may then differ, while the tree is the same.
- The tag is annotated (`d766af19...`) and upstream could move it. The commit id above is the
  stable reference; if `ls-remote` later shows another commit, the entry needs a new review.
- **Independence (flag for the orchestrator).** N5 asks for the second fetch "from another host
  or network". This fetch ran on the same dev box and the same network as the developer
  workflow. It is independent in process (my own curl, not the resolver tool) but not in
  network path. If the orchestrator wants network independence, it needs a third fetch from
  another network (for example a CI runner or another host), compared with the sha256 above.

## 2026-10-25: security, Temurin 21.0.12.1+1 sources sidecar (lock key `temurin:jdk-21.0.12.1+1`), pre-recorded for U7b

**Version, from the image.** `/opt/java/openjdk/release` reads
`IMPLEMENTOR_VERSION="Temurin-21.0.12.1+1"`, `JAVA_RUNTIME_VERSION="21.0.12.1+1-LTS"` and
`SOURCE_REPO="https://github.com/adoptium/jdk21u.git"`. The fixture agrees: l.296
`pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS`.

**Derivation (design, U7a round 2 item 2).**
- Repo: `adoptium/temurin21-binaries`.
- Tag: `jdk-21.0.12.1+1`, encoded as `jdk-21.0.12.1%2B1`.
- Asset: `OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`.
- Only the `.sha256.txt` sidecar was fetched; the asset itself was not.
```
curl -q --proto '=https' --proto-redir '=https' --tlsv1.2 -sS --max-time 60 -o hopN.body -D hopN.headers \
  -w '%{http_code} %{redirect_url}' <url>      # by hand, at most 5 hops, https only
url = https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz.sha256.txt
```

**Hops** (2026-10-25T07:50:55Z):

| Hop | Host | Result |
|---|---|---|
| 1 | `github.com` | 302 to `release-assets.githubusercontent.com` |
| 2 | `release-assets.githubusercontent.com` | 200, path `/github-production-release-asset/602574963/87e45212-21e7-4c2c-80e9-0eb146df1a0a`; the signed query is a short-lived token and is not recorded |

Both hosts are in `hosts`. `objects.githubusercontent.com` was not used, which is input for the U8
*confirm at GREEN* of the redirect targets (N4).

**Sidecar content** (108 bytes, one line, LF-terminated; sha256 of the sidecar file itself
`a67c8b520c5a2bfe42405fe1b7baef468e7855795e52458222841d388c07d7b2`):
```
573057d03584ae793fb7ec9a14c76d826d9187a53efeefd99da47403a5308234  OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz
```
- The sidecar has the shape the design expects: exactly one line, 64 lower-case hex, whitespace,
  then the asset name. The name it carries equals the derived asset name, and the tag exists (hop
  1 was a 302, not a 404). This supports the U7b confirmation of the tag and asset form.
- For U7b: the resolver must report `upstream {sha256, 573057d03584ae793fb7ec9a14c76d826d9187a53efeefd99da47403a5308234,
  "OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz.sha256.txt"}`, and the streamed asset must hash to
  the same value. This record is a comparison point only. The Temurin entry is `generated`,
  checked against the published sidecar; it is not trust on first use.

## 2026-10-26: security, third fetch of the Neo4j 5.26.32 tarball (U7d S8, network-independent): NOT DONE, blocked

The third fetch has to come from a network path other than the dev box. I tried the two ARM model
hosts over ssh, non-interactively (`ssh -o BatchMode=yes -o StrictHostKeyChecking=yes <host>`),
at 2026-10-26 about 03:45Z:
- `aria-gb10`: "No ED25519 host key is known for aria-gb10 and you have requested strict
  checking. Host key verification failed." I did not accept an unknown host key on the user's
  behalf: that is a trust decision for the human.
- `aria-gb10-2`: "Permission denied (publickey,password)": no key login is set up for this
  session.

No command ran on either host. The second-fetch values stand:
sha256 `182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3`, size 20907800 bytes.

**To complete it (the human chooses one):**
1. On a model host (or any machine off this network), run this read-only command. It writes
   nothing, follows redirects over https only, and prints the sha256 (stderr) and the byte count:
   ```
   curl -q --proto '=https' --proto-redir '=https' --tlsv1.2 -sSL --max-time 600 https://github.com/neo4j/neo4j/archive/refs/tags/5.26.32.tar.gz | tee >(sha256sum >&2) | wc -c
   ```
   Paste the sha256, the size and the host name into this file, or give security key access, or
   confirm the `aria-gb10` host key so security can run it.
2. A one-off CI step on the GitHub runner, a different network. This is a repo change and needs
   the human approval for a push or PR.

A mismatch with the second fetch blocks the commit (U7b ruling). Until one of these is done, the
`neo4j:neo4j@5.26.32` manual entry rests on two fetches from one network path.

**Update, 2026-10-27 (security; orchestrator ruling refinement, design-notes U7d item 14): the
third fetch is deferred to U8 CI. The U7d lock commit no longer waits.**
- The third, network-independent fetch is satisfied by the **first bundle-time sample fetch of
  U8 on the GitHub CI runner**, which is a different network path from the dev box.
  - The tarball is always in that sample. The sample takes one entry per kind (`sample_keys`),
    and `neo4j:neo4j@5.26.32` is the only `neo4j` key, so it is chosen while it stays the only
    one.
  - The fetch checks sha256 and size against the lock and fails closed on a mismatch.
- The one-liner above, run by the human on an ARM host, stays an accepted earlier alternative.
- **What U8 must cite here when it lands** (append a dated section; do not edit this one):
  - the CI run id (and its URL)
  - the runner host (the runner name and image from the job log)
  - the UTC date
  - the hop hosts (`github.com` -> `codeload.github.com`)
  - the measured sha256 and size, compared with `182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3`
    and 20907800 B
- **On a mismatch at U8:** a new first fetch and a new second fetch, and a new manual entry
  after review, never a skip (Q61).
- **The `from` text does not change.** The lock entry stays `upstream {sha256,
  182ae2e5...91e3, "second fetch: security 2026-10-25,
  docs/evidence/platform-sbom/sources-provenance.md"}`. The U8 record is evidence added to this
  file, not a lock change.

## 2026-10-26: security, S8 lock review of `docker/sources.lock.json` (uncommitted, from `u7d/lock-run-4.txt`)

- `lock_problems == []` (committed policy, six fixtures, amd64). There are 182 entries and 872
  files, canonical LF text. Detail: `u7d/security-r1.md`, `u7d/security-r1-probes.txt`.
- **pgdg:**
  - `gpgv` on `u7d/pgdg-bookworm-pgdg-archive.InRelease` (sha256 `ed9bd2c7f72b2f01e4d05c9be0c5683611cef1e9a1e58ff40b3e473a44e512ec`)
    with `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8` (from the pinned postgres image): Good
    signature, made 2026-10-21.
  - The signed Sources sha256 `9550c528bc74dc1ebfdc799385e0e8c9f211dc4bed5dbbb6bee5962b016fe722`
    (5043212 B) equals the Sources re-fetched at 2026-10-26T06:21:33Z.
  - The 3 stanzas equal the lock files, and the 3 `.dsc` re-fetched at 06:21:48Z equal the lock
    (`d98708df...`, `76fda1b6...`, `fc1b2290...`).
- **Spot re-fetches** (06:23Z), one per kind, all equal to the lock: deb `netbase_6.4.dsc`
  (snapshot), apk `klogd.confd` (GitLab API raw), apk `protocols-6.4` (distfiles), maven
  `jaxb-api-2.2.12-sources.jar` with `.sha1`, pypi `autocommand-2.2.2.tar.gz`, and the temurin
  `.sha256.txt`.
- **Neo4j:** the manual entry equals the second fetch above (`182ae2e5...91e3`, 20907800 B).
  **The third fetch is still blocked (previous section), so the commit waits on the human.**

## 2026-10-29: security, third fetch of the Neo4j 5.26.32 tarball (U8-11; U7d item 14): DONE, from the GitHub CI runner

The U8 sample fetch in PR #15 CI run **40907497118**
(https://github.com/humanaxiom/Knowledge-engine/actions/runs/40907497118) is the third,
network-independent fetch, as ruled by the human (the CI runner is accepted as the third fetch).
It is the first CI run that includes the sample fetch. Source: the saved job log
`u8/ci-40907497118.log` (4954 lines); the R18 extract and the comparison output are in
`u8/ci-40907497118-fetch.txt`.

**Run.** Head `5cf025c` (U8c part 1 included, so the policy is the narrowed one). The checkout is
the PR merge ref: "HEAD is now at c8f3ed8 Merge 5cf025c... into 7f8559a..." (log l.118). The job
ran 2026-10-29 16:01:50-16:33:56 UTC, verify full PASS.

**Runner (log l.1-21).** GitHub-hosted. Runner version 2.338.0. "Runner Image Provisioner: Hosted
Compute Agent, Version 20261021.618, Region westus, Cloud Azure". Operating System Ubuntu 24.04.5
LTS. Runner Image `ubuntu-24.04`, Version 20261025.353.1. Its egress is GitHub's hosted-runner
network on Azure. That is independent of the dev box `aria-alien1`, where the first fetch
(developer) and the second fetch (security, 2026-10-25) both ran.

**The record line (log l.4433):**
```
2026-10-29T16:29:18.4316742Z bundle_fetch: ok neo4j:neo4j@5.26.32 5.26.32.tar.gz sha256=182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3 size=20907800 hops=github.com,codeload.github.com
2026-10-29T16:29:22.0128514Z bundle_fetch: fetched 25 files, 136571547 bytes, 7 components (sample, amd64) in 16.7 s
```
- **sha256 `182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3`, size 20907800 B.**
  This equals the lock entry `neo4j:neo4j@5.26.32` and security's second fetch above. The hops are
  `github.com` -> `codeload.github.com`, the same chain as the second fetch.
- **Three fetches from two networks agree.** The client checks sha256 and size against the lock
  and fails closed, so a mismatch cannot print `ok` (Q61).
- The lock at `5cf025c` is byte-identical to the one `u8/expected.md` was derived from (sha256
  `12eebc8c...761b`; `git diff 780d523 5cf025c -- docker/sources.lock.json` is empty).

**The other 24 sample files.** I sorted the 25 `ok` lines as key|file|size|sha256 and diffed
them against the "sample, amd64" table in `u8/expected.md`: **equal** (25 rows each, no
difference).

**Hop chains on CI, per kind (25 lines):**

| Kind | Files | Hops |
|---|---|---|
| apk | 15 | `gitlab.alpinelinux.org` |
| apk | 2 | `distfiles.alpinelinux.org` |
| deb | 2 | `snapshot.debian.org` |
| maven | 1 | `repo1.maven.org` |
| neo4j | 1 | `github.com` -> `codeload.github.com` |
| pgdg | 2 | `apt-archive.postgresql.org` |
| pypi | 1 | `files.pythonhosted.org` |
| temurin | 1 | `github.com` -> `release-assets.githubusercontent.com` |

`objects.githubusercontent.com` appears 0 times in the whole log. U8c part 1 (U8-10, O-2) dropped
it from `hosts`, and this run fetched under the narrowed policy.

**What this proves, and what it does not.** GitHub served the same bytes to two independent
networks on 2026-10-25 and 2026-10-29. The bytes are still not shown to be Neo4j's own: the tie to
commit `27f24499b751708815d42c8cf26bfb6597b3516c` is the indirect one in the first section. Both
networks reach the same origin (GitHub), so a change made at the origin would be served to both.
The log's secret-pattern scan found no hits; the only masked value is the checkout token
(`***`, 2 occurrences).

**Still open (optional, for the human).** The ARM one-liner in the 2026-10-26 section, run on a
model host before the first operator bundle. It stays an accepted, optional, stronger check
(design-notes U7d item 14 architect's note), and it does not block U9. The "commit waits" note
in the S8 lock review above is overtaken: U7d was committed under the item 14 refinement, and
this section closes its third-fetch condition.
