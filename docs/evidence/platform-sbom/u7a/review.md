# platform-sbom U7a review (reviewer, 2026-10-25)

Scope: `git diff HEAD` (66781a9 = U6) of scripts/sbom_check.py (which equals
`u7a/target-sbom_check.py`), new tests/test_sources_lock.py, and the carry rows in
tests/test_sbom_obligations.py and tests/test_sbom_classifier.py. Checked against
design-notes "N5 amendment, U7" (l.709-1123) and the resolution-endpoints note.

Verdict: **CHANGES REQUESTED** (B1, B2).

Evidence:
- `u7a/reviewer-controls.txt`: `u7a_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7a): 45 rows, 40 must-fail, 5 must-pass, 0 unexpected (reproduced).
- `u7a/reviewer-probes.txt`, from `u7a/reviewer-probes/probe_u7a.py`. Inputs are
  mutations of the tests' own `good_lock(SMALL_KEYS)`, with the tests' policy (committed
  plus the pgdg host) and docs.
- tests/test_sources_lock.py on the host: OK.

## Blocking

**B1. The neo4j second fetch is not bound to the file's sha256** (`_kind_problems`
neo4j branch, sbom_check.py l.1210-1224).
- Item 4 fixes the entry as `upstream {sha256, <same>, "second fetch: security
  <date>, ...sources-provenance.md"}`. The check reads only `from`.
- `_file_problems` ties `value` to `sha256` only when `alg` is sha256. So an entry with
  `upstream {alg: "sha1", value: "0"*40, from: "second fetch: security 2026-10-25, ..."}`
  passes, and so does alg sha512 with 128 zeros. Security's independent hash is then
  never compared with the hash the lock ships.
- This is the one hand-written entry (`origin: manual`), so lock-check is its only
  machine guard.
- A neo4j entry with two files also passes. "Not one file" is enforced for temurin,
  pypi and maven, but not for neo4j.
- Fix: in the neo4j branch, require exactly one file and `upstream.alg == "sha256"`.
  `_file_problems` then enforces `value == sha256`. Add a bad-shape row for each.

**B2. A URL with whitespace or control characters passes, and the host check sees a
different host from the stored string** (`_url_problems`, l.1112-1135).
- `urllib.parse.urlsplit` deletes tab, CR and LF anywhere in the URL (WHATWG
  behaviour, Python 3.11+). So a pypi URL whose host is written `files.py<TAB>thon.org`
  is checked as host `files.pythonhosted.org` and passes, while the lock keeps the tab.
  A newline or a space in the path also passes.
- The allowlist (N4, Q61) is the security control, and it should hold for the literal
  string that U8 will request. A checker that normalises its input differently from the
  consumer is a classic bypass. U8's opener would most likely refuse such a URL
  (http.client rejects control characters), but the U7a gate should not depend on that.
- Fix: before `urlsplit`, refuse any URL that is not printable ASCII without spaces
  (every character in the range 0x21-0x7e). Add bad-shape rows for a tab in the host
  and for a space or newline in the path.

## Nits (non-blocking)

- **N1. The per-kind URL host and file name are not bound to the key.** Only `deb`
  binds its URL (snapshot `/file/<sha1>`) and its `.dsc` name. These pass:
  - a maven sources jar named `evil-1.0-sources.jar` served from `files.pythonhosted.org`;
  - a pypi sdist named for another package;
  - a temurin asset on `repo1.maven.org`;
  - a neo4j tarball at `github.com/attacker/...`;
  - a path with `../..`.

  The design (6 (c)) does not require binding; security's review of every lock diff and
  U8's per-file sha256 are the controls. But N10 am. U6 item 2 already names each kind's
  hosts, and the names follow from the key. A per-kind host map, plus name rules
  (`<a>-<v>-sources.jar`, `<name>-<ver>.tar.gz`, `<ver>.tar.gz`), would be cheap and
  would shrink what the reviewer must catch by eye. For the architect, before U7b.
- **N2. A `deb` entry with only the `.dsc` passes** (no orig or debian tar), so the
  shipped source could be incomplete. 6 (c) does not require more files. Recommend: at
  least one non-`.dsc` file at U7a. U7c's tool (or U8's fetch) should check that the
  fetched `.dsc`'s `Files` list equals the entry's other files. (An apk entry with only
  the APKBUILD is legitimate for source-less APKBUILDs.)
- **N3. `pgdg` has no per-kind rule** (no `.dsc` count, name or alg). Today any pgdg
  entry fails the host check, because Q71's host is not in `hosts`, so it fails closed.
  Carry the rules to U7c with O1.
- **N4. Entry key sets are not exact.** A `deb` entry with `"skip": true` passes. Files
  and `upstream` are checked as exact sets. Make entries exact per kind: `kind`,
  `arches`, `origin`, `files`, plus `commit`/`branch`/`repo` for apk.
- **N5. Non-string `arches` crash `lock_problems`.** A list holding a list raises
  "unhashable type"; a list holding an int and a str raises TypeError from `sorted`.
  The CLI exits non-zero with a traceback, so it fails closed, but every other field
  follows the "wrong type is a problem, never a crash" rule. Check that every item is a
  str first.
- **N6. CRLF checkout (U7d carry).** `core.autocrlf=true` on this host and no
  `.gitattributes` rule for `*.json`. A committed `docker/sources.lock.json` would be
  checked out with CRLF, and `lock-check` reads with `newline=""`, so it would report
  "not in canonical form" on Windows (A34). Add `docker/sources.lock.json text eol=lf`
  with the U7d commit.
- **N7.** Design 6 (c) says "each bad shape gives one problem", but the test asserts
  only that problems is non-empty. One bad shape could be masked by an unrelated
  problem from the same mutation. Pinning one problem, or a substring per row, would
  make the 87 rows sharper.

## Conformant
- **Mapping (item 2).** I derived the keys independently from the fixtures with my own
  mapping code over `classify_document(image, doc, always, exempt)` and got the same 182
  keys as `FIXTURE_KEYS`: deb 152, pgdg 3, apk 19, neo4j 1 (73 packages), temurin 1,
  maven 1, pypi 5.
  - deb: `upstream=<src>@<srcver>`, else the binary version; epoch kept and percent
    decoded; `.pgdg` gives `pgdg:`.
  - apk: origin from `upstream`, else the name.
  - neo4j groups at the image's version; other versions fall to `maven:`, and a group
    row with no `org.neo4j/neo4j` row is a problem.
  - temurin: `-LTS` stripped, and jrt-fs is checked against the openjdk build.
  - pypi: PEP 503 names.
  - Anything else with needs, or a row with no purl, is the "maps to no lock kind: back
    to the architect" problem.
- **Messages.** The miss text, the stale text and the jrt-fs text match item 6 (d) and
  item 2 exactly.
- **Schema.**
  - Canonical text: indent 1, sorted keys, ensure_ascii, plus a final newline.
    Duplicate JSON keys fail it.
  - The key grammars match item 6 (c), and pgdg is required exactly when the key has
    `.pgdg`.
  - Arches, origin rules, neo4j `from` and the UTC date check (`today` is a parameter).
  - File name regex, https, userinfo, port, query, fragment, and an exact,
    case-sensitive host.
  - sha256, size (bool excluded), and upstream alg, length, `sha256 == value`, `from`.
  - deb, apk, maven, temurin and pypi file rules.
- **Coverage** in both directions, per arch. **`sample_keys`**: smallest total per
  kind, ties by key, filtered by arch.
- **CLI.** Argv paths only, first 20 problems, exit codes 0, 1 and 2.
- **PS-1.2.** No scheme-and-host URL literal in the sbom_check.py diff; the snapshot
  URL is checked through `urlsplit`.
- **Carry rows.**
  - (g) The future `reviewed` date is checked against the UTC date, with `today`
    parameterised and a fixed-date control.
  - (h) `#sub/path` and `?type=jar#sub` both match.
- **Untouched.** `unlicensed_report`, the classifier and `exempt_matches`.
- **Controls.** They cover the asked mutants: host check dropped, http, userinfo,
  stale, miss key and miss count, arch, sample, `.pgdg`, percent-decoding, epoch,
  upstream, jrt-fs, neo4j group, unknown type, PEP 503, exempt, canonical form, sort,
  size, `.dsc` epoch, future date, CLI cut and exit code. None covers B1 or B2, because
  those are gaps in the code, not mutations of it.
- **Observability.** No spans needed: build-time pure functions (N3).
