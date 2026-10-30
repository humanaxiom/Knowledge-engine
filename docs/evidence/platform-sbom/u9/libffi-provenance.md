# platform-sbom U9b R7: provenance of the libffi licence text (`licenses/libffi-jna-5.15.0.txt`)

Date: 2026-10-29, fetches 19:42:57Z-19:43:52Z (UTC). Recorded by security under rule G5
(provenance before use), before the tester's U9b RED and before the developer commits the file.
Asked by: design-notes "N9 amendment, U9" item 7 (libffi, "Confirm at RED") and R7; requirements
U9-9; U6 ruling (b) (security U6 exempt review L-1). Every network step was an https GET from
the dev box (Git Bash, `curl -sS --proto =https --tlsv1.2 -fL`); no profile path is recorded.
Downloads went to a new empty scratch directory outside the repo, were read with `python -I`
(scripts kept in a separate directory), and were deleted at 19:43:52Z. Nothing downloaded was run.

## Verdict: PASS. The design's source is confirmed.

`https://raw.githubusercontent.com/java-native-access/jna/5.15.0/native/libffi/LICENSE` exists at
tag `5.15.0`, is the licence of the libffi that jna 5.15.0 vendors (libffi **3.4.4**), and is
byte-identical to upstream libffi's `LICENSE` at tag `v3.4.4`. No other source is needed, so no
design amendment is needed.

## 1. The text (the source U9-9 names)
| field | value |
|---|---|
| URL | `https://raw.githubusercontent.com/java-native-access/jna/5.15.0/native/libffi/LICENSE` |
| HTTP | 200, 0 redirects |
| size | 1132 B, 21 lines, ASCII, LF only (0 CR), ends with one `\n` |
| sha256 | `2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388` |
| git blob | `75d1bce11f9118ccfd96b24a2e49af078da1b469` (local `git hash-object --no-filters`) |
| first line | `libffi - Copyright (c) 1996-2022  Anthony Green, Red Hat, Inc and others.` (two spaces before "Anthony"; keep them) |
| last line | `SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.` |

Line 2 is `See source files for details.`; lines 4-21 are the MIT/Expat-style permission notice and
warranty disclaimer (the "``Software''" quoting is upstream's).

## 2. The tag is pinned
- `GET https://api.github.com/repos/java-native-access/jna/git/ref/tags/5.15.0`: `refs/tags/5.15.0`
  -> commit `fad4d1dc4e791f8083d6a3afa28a3ea8bdcbe0ee` (lightweight tag; commit "Release 5.15.0",
  2024-09-15T15:58:00Z).
- `GET .../contents/native/libffi/LICENSE?ref=5.15.0`: blob `75d1bce11f9118ccfd96b24a2e49af078da1b469`,
  size 1132. Equal to the local blob hash of the raw fetch, so the raw route served the tag's file.
- Tags can move. If a later re-fetch differs from the sha256 above, the committed file stays the
  record; re-fetch from `https://raw.githubusercontent.com/java-native-access/jna/fad4d1dc4e791f8083d6a3afa28a3ea8bdcbe0ee/native/libffi/LICENSE` to check.

## 3. The libffi version jna 5.15.0 bundles: 3.4.4
- `native/libffi/configure.ac` at tag 5.15.0 (sha256 `b78dbea3292cbe4454c778009dda02b0a41a39fea218f850fd40949e1454e86a`),
  line 5: `AC_INIT([libffi],[3.4.4],[http://github.com/libffi/libffi/issues])`.
- `CHANGES.md` at tag 5.15.0: the first libffi line is l.62, under "Release 5.13.0" (l.51):
  `#1491: Update libffi to v3.4.4`. The 5.14.0 and 5.15.0 sections have no libffi line.
- The binary jar's native builds were compiled from jna's vendored tree: 4 of 28 `libjnidispatch`
  builds keep `native/libffi/src/...` path strings (`prep_cif.c`, `closures.c`, `x86/unix64.S`, ...);
  U6 found libffi symbols in all 28. No build carries a `libffi-3.x` version string (0 of 28), so
  the version rests on the tag's source tree and changelog.

## 4. Cross-checks
- **Upstream libffi** `https://raw.githubusercontent.com/libffi/libffi/v3.4.4/LICENSE` (tag `v3.4.4`
  -> commit `f24180be1367f942824365b131ae894b9c769c7d`; `configure.ac` there: `AC_INIT([libffi],[3.4.4],...)`):
  1132 B, sha256 `2c9c2acb...8c388`, blob `75d1bce1...b469`. `cmp`: **identical** to jna's copy.
- **Correction to the brief:** `docker/sources.lock.json` has no jna key (jna is cleared by the
  `exempt` entry of `docker/source-policy.json`; Apache-2.0 elected, no source fetched), so there is
  no locked sources-jar URL or sha256. The pinned value is the binary jar's sha256 in that exempt
  entry. Maven Central's coordinates are `net.java.dev.jna:jna:5.15.0` (syft's purl says `com.sun.jna`).
- **Binary jar** `https://repo1.maven.org/maven2/net/java/dev/jna/jna/5.15.0/jna-5.15.0.jar`:
  2,001,532 B, sha256 `a564158d28ab5127fc6a958028ed54279fe0999662c46425b6a3b09a2a52094d` = the exempt
  entry's value (and U6's in-image hash); sha1 `01ee1d80...41ac` = Central's `.sha1`. 191 entries;
  licence entries only `META-INF/LICENSE`, `META-INF/AL2.0`, `META-INF/LGPL2.1`. No entry holds the
  libffi LICENSE bytes or "Anthony Green" (U6 L-1 confirmed: the jar ships no libffi notice).
- **Sources jar** `https://repo1.maven.org/maven2/net/java/dev/jna/jna/5.15.0/jna-5.15.0-sources.jar`:
  164,932 B, sha256 `312e388367f406c280d64215dcca8989bce4d6175ae2c4340ab6615652cbd8c7`, sha1
  `f84631ed...6e8d` = Central's `.sha1` (not lock-pinned; see the correction). 76 entries, Java
  sources only: no licence file, no `native/`, no libffi text. So it cannot serve as a source of the
  text. The GitHub tag (section 1) plus upstream libffi (above) is the cross-check.

## 5. For the developer at GREEN (U9-9)
File `licenses/libffi-jna-5.15.0.txt`, tracked, in the Q48 header form of
`licenses/CPython-3.12-incorporated.txt` (header lines, one blank line, then the fetched bytes
unmodified):
```
libffi 3.4.4 (vendored by JNA 5.15.0): native/libffi/LICENSE
Source: https://raw.githubusercontent.com/java-native-access/jna/5.15.0/native/libffi/LICENSE
Source sha256: 2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388

<the 1132 fetched bytes, unmodified>
```
Fetch it yourself over HTTPS from the URL above and check the sha256 before committing; the bytes
after the blank line must hash to that value (a test can assert this). Do not re-wrap, re-quote or
collapse the double space.

Recommended `NOTICE.md` paragraph, appended to "Base image of `ke-neo4j`" (cites no `docs/evidence/`
path, so `test_notice_cites_no_repo_evidence_path` stays green):

> `/var/lib/neo4j/lib/jna-5.15.0.jar` (Java Native Access 5.15.0) carries native `libjnidispatch`
> libraries that include libffi 3.4.4, the copy JNA vendors in its `native/libffi` directory.
> libffi is under an MIT-style licence ("libffi - Copyright (c) 1996-2022  Anthony Green, Red Hat,
> Inc and others."), and its copyright and permission notice is not in Neo4j's notices. The full
> text is `licenses/libffi-jna-5.15.0.txt`: JNA's `native/libffi/LICENSE` at tag 5.15.0,
> unmodified, fetched over HTTPS from
> https://raw.githubusercontent.com/java-native-access/jna/5.15.0/native/libffi/LICENSE
> (sha256 `2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388`); its header gives
> the same sha256.

## 6. Findings (none blocking)
- I-1 (info): the brief's "lock's jna sources-jar entry" does not exist (section 4); nothing to fix.
- I-2 (info): libffi's LICENSE says "See source files for details": some libffi source files carry
  their own copyright lines. Shipping the top-level LICENSE is the usual practice and is what ruling
  (b) and U9-9 ask for; no action.
- I-3 (info): a jna or base-image digest bump re-triggers this record together with the U6 exempt
  review (U6 I-2); the version (3.4.4) and file name are tied to jna 5.15.0.
