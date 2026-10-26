# platform-sbom U5 review (reviewer, 2026-10-24)

Scope: `git diff HEAD` (HEAD c300d88) of scripts/sbom_check.py, scripts/smoke.sh,
scripts/offline_check.sh, tests/hardcoded_scan.py, tests/test_engine_hardcoded.py,
tests/test_neo4j_image.py, and new tests/test_sbom_classifier.py, against design-notes
N8/N8a and "N8 amendment, U5" (l.940-1081).

Verdict: **CHANGES REQUESTED** (B1, B3 for the developer/tester; B2 needs an orchestrator ruling first).

Evidence produced by this review:
- `u5/reviewer-controls.txt`: full re-run of `u5_controls.py --base repo` in the gates
  image (project ke-reviewer-u5): 66 rows, 58 must-fail, 8 must-pass, 0 unexpected (reproduced).
- `u5/reviewer-probes.txt`: probe output; scripts in `u5/reviewer-probes/`
  (`probe.py`, `probe_drift.py`, `mutant_joined.py`; host `python -I`).

## Blocking

**B1. Test gap: per-part classification (amendment item 2 precision) is unpinned; a
surviving mutant fails open.** `classify_package` (scripts/sbom_check.py:457-466) runs
`needs_source` on each part. The precision bullet exists to stop "one unparseable part
from hiding a hash or GPL part beside it". The tester recorded "classify the joined text"
as an equivalent mutant (handoff, tester U5 RED, last bullet). It is not equivalent: a
NONE/NOASSERTION leaf in a parseable part is hidden when the joined text does not parse.
- Input: `{"licenseDeclared": "Public Domain", "licenseConcluded": "MIT AND NOASSERTION"}`.
  Code: needs=True, unidentified=True. Joined-text mutant: needs=False, unidentified=False.
  Same with `licenseInfoFromFiles: ["Public Domain", "MIT AND NONE"]`.
- `mutant_joined.py`: the mutant passes all 26 tests in tests/test_sbom_classifier.py.
  Control: a broken classify_package gives 18 failures and 7 errors, so the patch is live.
- Fix: add both rows to `ClassifyPackageTest.test_both_fields_set` / `test_files_list`,
  and a mutant row to `u5_controls.py`; correct the "equivalent" note.

**B2. NONE/NOASSERTION leaves in unparseable text need no source and are not
unidentified (design gap; orchestrator ruling first).** `needs_source`'s except branch
(sbom_check.py:451-453) needs source only on a token hit or a hash id (orchestrator
correction, amendment item 2). These inputs all give needs=False, unidentified=False,
unparsed=True: `Public Domain AND NOASSERTION`, `MIT NOASSERTION`, `MIT AND (NOASSERTION`,
`(NOASSERTION) WITH x`, `NOASSERTION NONE`. The code matches the ruling's literal text.
But item 1 makes these leaves "unknown id, exact and case-sensitive like the hash rule",
and the correction made `Public Domain OR <hash>` fail closed. The same text with
NOASSERTION in place of the hash fails open. Proposed ruling: in unparseable text, a
whitespace/parenthesis-separated run exactly `NONE` or `NOASSERTION` (case-sensitive)
counts as a hash id does (needs source, unidentified), then one test row per input
above. If the orchestrator rules "listing only", this closes with a recorded ruling.

**B3. drift's success line prints SBOM text raw (amendment item 7, "every").**
sbom_check.py:587 prints `', '.join(py)` without `_clean`. `py` is
`_named(docs[0], "generic")["python"]` from the ke-app SBOM. `_named` also takes
namespaced `pkg:generic/<ns>/python` rows, which `drift_problems` ignores (it requires
no namespace). So they never reach a problem line, but they do reach the success line.
- Input: `ss.ke_app_doc(extra=({"purl": "pkg:generic/x/python@3.12.15%1b%5b2J", "declared": "MIT"},))`
  with the real base, licence files and lock. `main(["drift", ...])` returns 0 and prints
  `CPython 3.12.15, 3.12.15<ESC>[2J` with a raw ESC (`probe_drift.py`).
- Fix: `_clean` there. Ideally build the success line's CPython set with the same
  no-namespace rule as `drift_problems`. Add a test in `EscapingTest` and a mutant row.

## Nits

- N1. `MIT WITH GPL-2.0-only` (a licence id in the exception slot) gives needs=False and
  is not listed at all, because the exception id is not read (spec-literal). Consider
  listing it unparsed when the exception id gets a token hit. Orchestrator call.
- N2. Operators are compared with `str.upper()`, which maps U+0131 (dotless i) to `I`, so
  `MIT w<U+0131>th GPL-2.0-only` parses as WITH (needs=False, unlisted). Given N1, the
  ASCII form behaves the same. An ASCII-only comparison would make the non-ASCII token a
  leaf: the text would not parse and the token rule would catch it.
- N3. The scanner continuation rule (item 5) checks the previous *physical* line. BuildKit
  skips comment lines and empty lines inside a continuation. So `RUN echo \` then `# x`
  (or a blank line) then `EXPOSE 7473 7474 7687` exempts a line that is part of the RUN.
  Spec-literal; for security's PS-1.2 re-review.
- N4. A whitespace-only field (`"  "`) is set for both the report and the classifier (no
  strip). It gives needs=False and is listed only as unparsed. Spec-literal; noted for security.
- N5. With B1, `classify_package(p)["needs"]` can differ from
  `needs_source(row["expression"])` (B1's input). Say in the docstring that U9's `index`
  must never re-derive needs from `expression`.
- N6. `u5/green-controls.txt` holds only the last 8 lines of the run, not the full
  output (evidence contract item 2). The full run is now in `u5/reviewer-controls.txt`.
- N7. The platform-sbom status in docs/requirements.md still says "CI pending". The
  handoff (U5, l.101) records PR #14 CI as PASS.
- N8. Without `-xdev`, the smoke `find` walks the /data and /logs of a live neo4j. A file
  removed mid-walk makes find exit non-zero and smoke FAILs. That fails closed but can
  flake; watch for it on CI.

## Checked and conformant
- (a) Input selection uses a new `_set` (`_missing` untouched): hash-only is set; both set
  gives `(d) AND (c)`, with one copy when equal; otherwise the set licenseInfoFromFiles
  entries, in order. Grammar is WITH > AND > OR, with parentheses overriding. Leaves are
  `[^\s()]+`, and the unparseable cases are as listed. `needs(X WITH e) = needs(X)`.
  The token rule and the anchored pattern use `fullmatch`, and `licenseref-` is stripped
  after lower-casing. URL-folded `LicenseRef-...http...` leaves are listed unparsed, in
  any case. Hash leaves (by `fullmatch`) and NONE/NOASSERTION leaves need source and are
  unidentified. Unparseable text needs source on the token rule OR `HASH_ID_RE.search`.
  `always` goes through `always_matches`, and DESCRIBES roots are excluded via
  `_packages`. RecursionError is caught around both parse and evaluate.
- (c) `fullmatch` is used for SPDXID_RE, NAMESPACE_RE, RFC3339_UTC, NAME_RE and SHA_RE.
  The prefix patterns (PURL_RE, PURL_TYPE_RE, the `CPython x.y.z:` header) keep `match`.
  `_clean` covers validate, drift_problems and psycopg_problems; the exception is B3.
- (d) `tree_listing` returns the 6-tuple. Hard links are normalised on both listings
  (target via `_rel`; absent or non-file targets stay `hardlink`), keep their own
  mode/uid/gid and take the target's size. The scanner rule is Dockerfile-only and
  right-strips the previous line. Smoke prunes /proc, /sys and /dev with no `-xdev`,
  and the exec status still fails closed. The fake models `-prune`.
- (e) Every amendment rule has a test row, except B1. The 66 control rows cover the
  changed logic and reproduce with 0 unexpected.
- (f) Neo4jTreeCheckTest moves to the 6-tuple with the same failing set plus a size case.
  The U4b "hard link written as file" pass moves to the tar-based test, which also checks
  the reverse direction. The smoke -xdev pass becomes "/proc pruned", and /data and /logs
  now fail. The intent is kept.
- (g) `_missing`, `_hash_only`, `unlicensed_report` and `report_lines` are unchanged in
  the diff. `test_hash_only_package_is_classified_and_still_reported` pins the U4
  report's membership.
- Observability: these are pure functions with no agent loop, model call, retrieval or
  tool call, so no span is needed.
