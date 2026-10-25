# platform-sbom U7a rework round 1 review (reviewer, 2026-10-25)

Scope: `git diff --no-index u7a/target-sbom_check.py scripts/sbom_check.py`.
scripts/sbom_check.py equals `u7a/r1-target-sbom_check.py`. Tests: ReworkR1* in
tests/test_sources_lock.py. Rulings: design-notes "N5 amendment, U7" > "Rework round 1",
l.1163-1298.

Verdict: **CHANGES REQUESTED** (R1-B1).

Evidence:
- `u7a/reviewer-r1-controls.txt`: `r1_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7a): 84 rows, 78 must-fail, 6 must-pass, 0 unexpected (reproduced).
- `u7a/reviewer-r1-probes.txt`, from `u7a/reviewer-probes/probe_u7a_r1.py`. It uses the
  committed policy (no pgdg host) and the tests' `small_docs()`. Profile paths are
  redacted.
- tests/test_sources_lock.py on the host: OK.

## Closed
- **B1.** A neo4j entry now needs exactly one file, `alg` sha256, and a value equal to
  the file's sha256. All three round-0 inputs (sha1, sha512, two files) are refused.
- **B2.** Every string field must be printable ASCII (0x21-0x7e; `from` 0x20-0x7e)
  before any parsing. A tab in the host, or an LF or space in the path, is refused. The
  url must also round-trip through `urlsplit`/`urlunsplit` and begin with a literal
  lower-case `https://`, so `HTTPS://` is refused.
- **N1.** Per-kind hosts (`KIND_HOSTS`) and path/name binding:
  - deb, apk, neo4j and maven match an exact path;
  - pypi must be `<dist>-<ver>.tar.gz`, with `<dist>` PEP 503-equal to the key's name;
  - temurin keeps a prefix, the name regex and `from`;
  - pgdg is always a problem.

  Every round-0 input is refused: the maven jar on pythonhosted, the evil maven name,
  temurin on maven, and neo4j at an attacker repo.
- **N2.** A deb entry with only the `.dsc` is refused.
- **N4.** Entry, file and upstream key sets are exact; `skip` is refused.
- **N5.** Wrong types are problems, never exceptions. `lock-check` catches everything
  and prints one line with no traceback (tests pin deep nesting in the lock and in the
  SBOM).
- **N7.** Each row asserts its own substring.
- **Security L-3.** Keys are printed through `_clean`; an ESC in a key is refused as
  non-printable.
- **I-2.** The size cap is 4 GiB: 4294967297 is refused and exactly 4 GiB passes, as
  ruled.
- **182 keys.** `lock_needs` on the fixtures still gives exactly `FIXTURE_KEYS`, with no
  problems.
- **`unlicensed_report`, the classifier and `exempt_matches`** are untouched (only
  scripts/sbom_check.py's lock section changed).

## Blocking

**R1-B1. Encoded or backslash dot-segments bypass the "no `..` segment" rule** (ruling 3
"The url path has no `..` segment"; `_url_problems` checks only a literal `..` between
`/`, sbom_check.py l.1170).
- temurin is bound only by the prefix `/adoptium/temurin<N>-binaries/releases/download/`
  plus the last segment. pypi is bound only by its last segment. So these pass with
  every other field good:
  - `https://github.com/adoptium/temurin21-binaries/releases/download/%2e%2e/%2e%2e/%2e%2e/%2e%2e/attacker/repo/releases/download/x/OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`;
  - the same with `%2E%2E`;
  - `.../download/..%2F..%2F..%2F..%2Fattacker/OpenJDK21U-...`;
  - `.../download/x\..\..\..\..\attacker\repo/OpenJDK21U-...` (a literal backslash,
    0x5c, is printable and passes);
  - `https://files.pythonhosted.org/%2e%2e/psycopg_c-3.3.6.tar.gz`.
- RFC 3986 treats `%2E` as `.`, and WHATWG parsers and many servers treat `\` as `/`.
  A server or proxy that normalises either could resolve the temurin URL outside
  `adoptium/` on the multi-tenant `github.com`, which is the risk security's I-1 named.
  U8's opener sends the bytes as written, so the lock check is the place to refuse them.
- Fix: in every url path, refuse `\`, `%2e`, `%2f` and `%5c` (any case), and `.` and
  `..` segments, as one "not a plain path" problem. No legitimate URL in the design
  uses any of these: temurin's tag needs only `%2B`. Add rows for each spelling above.

## Nits
- **R1-N1.** The temurin tag segment and asset version are not bound to the key (ruled
  prefix-only). These pass:
  - a tag segment `jdk-17.0.1%2B1`;
  - an asset `OpenJDK17U-jdk-sources_17.0.1_1.tar.gz` with a matching `from`, under the
    temurin21 prefix;
  - extra subdirectories;
  - a `/./` segment (the last two are also covered by R1-B1's fix).

  Item 4 already gives the exact form
  (`/download/<urlquote(tag)>/OpenJDK<N>U-jdk-sources_<ver with + as _>.tar.gz`, "confirm
  at U7b"). Bind it exactly when U7b confirms it.
- **R1-N2.** Ruling 11 gives the CLI exception line as `lock-check: FAIL (<exception
  class>: <message>)`. The code prints `sbom_check: lock-check: the check failed:
  <class>: <message>`, and the read path prints `sbom_check: lock-check: <class>:
  <message>`. It is one line with no traceback, as required, but the text differs and no
  test pins it. Align the text, or have the architect amend the ruling.

## Checked
- `_binding_problems` returns early on non-str or unparsable values; those are reported
  by `_file_problems`/`_url_problems`.
- `_kind_problems` runs only when no entry key is missing.
- The neo4j count uses the raw `files` list, so a non-dict extra file still counts.
- The miss and stale messages are unchanged except for `_clean(key)`.
- `sample_keys`' docstring says it is called only on a passed lock (I-4).
- The pgdg tests use `pgdg_free`, with a dedicated row showing that both pgdg files are
  problems.
- Observability: pure build-time functions; no spans needed.
