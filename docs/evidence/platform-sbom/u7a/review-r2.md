# platform-sbom U7a rework round 2 review (reviewer, 2026-10-25)

Scope: `git diff --no-index u7a/r1-target-sbom_check.py scripts/sbom_check.py`.
scripts/sbom_check.py equals `u7a/r2-target-sbom_check.py`. Tests: ReworkR2*. Rulings:
design-notes "N5 amendment, U7" > "Rework round 2", l.1300-1382.

Verdict: **APPROVED.** No blocking findings.

Evidence:
- `u7a/reviewer-r2-controls.txt`: `r2_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7a): 106 rows, 100 must-fail, 6 must-pass, 0 unexpected (reproduced).
- `u7a/reviewer-r2-probes.txt`, from `u7a/reviewer-probes/probe_u7a_r2.py`. It uses the
  committed policy and the tests' `small_docs()`. One temp path is redacted.
- tests/test_sources_lock.py on the host: OK.

## Closed
- **R1-B1.** `_plain_path` refuses:
  - a backslash anywhere in the url;
  - an empty segment (`//`, a trailing `/`, an empty path);
  - a `.` or `..` segment;
  - any `%` in the path, except a literal `%2B` in temurin's tag segment.

  All five R1-B1 inputs are refused with `url path is not a plain path`:
  - temurin `%2e%2e`;
  - temurin `%2E%2E`;
  - temurin `..%2F`;
  - temurin with backslashes;
  - pypi `/%2e%2e/<name>`.

  So are `/./`, a gitlab path holding `%2F`, a deb `/file/<sha1>/` and a neo4j `//`.
- **R1-N1.** temurin is bound exactly:
  `/adoptium/temurin<N>-binaries/releases/download/jdk-<ver, + as %2B>/OpenJDK<N>U-jdk-sources_<ver, + as _>.tar.gz`,
  with `name` equal to the asset and `from` equal to `<asset>.sha256.txt`. All four
  ruled shapes are refused: another tag, an unencoded `+`, a lower-case `%2b`, and a
  JRE asset.
- **R1-N2.** Every caught exception prints exactly `lock-check: FAIL (<Class>: <msg>)`
  and exits 1, as ruled. Checked: a missing file (`FileNotFoundError`), invalid JSON
  (`JSONDecodeError`), nesting 100000 deep (`RecursionError`), and an exception inside
  the check (`TypeError`).
- **Security R1-L1.**
  - `_binding_problems` returns before any regex when the name fails
    `LOCK_FILE_NAME_RE`.
  - `_pypi_parts` splits at the last `-` with string operations, and `PYPI_DIST_RE` is
    anchored with one star, so it is linear.
  - A 255-character adversarial name takes 0.001 s, and so does a 50008-character one.
- **pypi path (item 5).** The path must be `/packages/<2 hex>/<2 hex>/<60 hex>/<name>`
  in lower-case hex; upper-case hex is refused.
- **182 keys.** Unchanged, with no mapping problems.
- **Untouched.** `unlicensed_report`, the classifier and `exempt_matches`; only the
  lock section of scripts/sbom_check.py changed.

## Fail-open search
Every kind's url path is now exact or a full-match pattern built from validated key
and entry fields:
- deb: `/file/<40 hex>`;
- apk: the exact GitLab or distfiles path;
- neo4j, temurin and maven: exact paths;
- pypi: the Warehouse layout plus the name;
- pgdg: always a problem.

The host is checked against the policy and against the kind, both exactly. I found no
remaining path or binding fail-open. Further probes, all refused:
- Java `..;` matrix parameters on the maven path (exact compare);
- `;x` appended to a pypi name and url (the name rule);
- a host with a trailing dot;
- a url with no path.

## Notes for U7b (not findings)
- U7b's real run confirms temurin's asset and tag form. Per ruling 2, a mismatch goes to
  the architect for an exact amendment, never a loosened rule.
- The pypi 2/2/60 segments are not checked against the file. Warehouse derives them from
  the BLAKE2b-256 of the content, but the lock records no BLAKE2b, so `uv.lock`'s URL
  and the sha256 bind it. This is as ruled.
- Observability: pure build-time functions; no spans needed.
