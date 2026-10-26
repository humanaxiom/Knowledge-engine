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
