# platform-sbom U6 review (reviewer, 2026-10-25)

Scope: `git diff HEAD` (d8ffa2d = U5) of scripts/sbom_check.py, docker/source-policy.json,
tests/test_sbom_classifier.py and tests/test_sbom_obligations.py, against design-notes
"N10 amendment, U6" (l.1530-1731, with the correction at l.1691) and the PSC-22 U6 bullets.

Verdict: **APPROVED.** No blocking findings.

Evidence:
- `u6/reviewer-controls.txt`: `u6_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u6): 44 rows, 40 must-fail, 4 must-pass, 0 unexpected (reproduced).
- `u6/reviewer-probes.txt`, from `u6/reviewer-probes/probe_u6.py` (host `python -I`).
- The U6 classifier tests and PolicyU6SchemaTest pass on the host.

## Design conformance
- **`exempt_matches(image, doc, exempt) -> (flagged, problems)`** has the shape of
  `always_matches` and skips other images' entries.
  - Match rule: `_purl_base` drops `?` and `#` on the package side only, then compares
    `key == want` as strings, with no case fold and no percent-decoding.
  - An entry with qualifiers or a subpath, or one that is not a versioned purl, is a
    problem and matches nothing.
  - An entry that matches no package is the problem "matches nothing ... review again",
    so a version bump voids it. Problem text goes through `_clean`.
  - Probes: a subpath on the package side is stripped. A prefix, a suffix and a bumped
    version all miss and raise a problem.
- **`classify_document(..., exempt=())`** follows the correction (l.1691):
  - exempt only gives needs False;
  - always and exempt together give always True, exempt True, needs False;
  - always only gives needs True;
  - with the default, every row gains `exempt: False` and nothing else changes;
  - `unparsed`, `unidentified` and `expression` are left as computed (javassist stays
    unparsed).
- **Policy.**
  - `hosts` is exactly the nine names of item 2.
  - `exempt` holds the two ke-neo4j entries, with the jar sha256 values from N8a and
    `reviewed: security 2026-10-25`, matching `u6/security-exempt.md`.
  - The `always` entries are unchanged.
- **Segment rule (item 5).** The rule only adds unknowns: the new code returns True in
  every case the U5 `_unknown_id` did, plus segments, and is skipped for `licenseref-`
  bare ids. The pin flips (`MIT-NOASSERTION`, `see NONE.txt here`) follow the ruling and
  are recorded in the test file.
- **`unlicensed_report`/`_missing`** are untouched (not in the diff).

## Fail-open search
- **Segment rule: none found.** I ran 200,000 random expressions built from keyword,
  idstring and joiner atoms through U5's `needs_source` and through U6's. None lost
  `needs` and none lost a listing (unparsed or unidentified); 90,450 changed, all in the
  fail-closed direction. AND/OR/WITH evaluation is monotone in leaf `needs`, so adding
  unknowns cannot clear a package.
  - Info: an id that both the token rule and the segment rule hit (`LGPL-NONE`) now
    reports unidentified instead of unparsed. It still needs source and is still listed,
    as round-3 ruling 7 allows.
- **Real-row snapshot.** With `exempt=()`, all six fixtures (1015 rows) are identical row
  by row to the HEAD (U5) checker, apart from the added `exempt: False`. With the
  committed `exempt`, only ke-neo4j's jna and javassist change, and only `needs` and
  `exempt`.

## Nits (non-blocking)
- **N1. A duplicate SPDXID turns an exemption into a fail-open; this is a U9
  precondition.** `classify_document` keys `exempt` (and `always`) by SPDXID string.
  - Input: a ke-neo4j doc where `pkg:deb/debian/bash@5.2.15-2` (GPL-3.0-or-later) has the
    same SPDXID as jna@5.15.0. Both rows get exempt True and needs False.
  - `validate` refuses the doc ("SPDXID ... is not unique") and every bundled SBOM passes
    `validate` at `finish`, so no bundle reaches this today. U9's `index` should still
    run `validate` first, or refuse duplicate SPDXIDs, before it trusts `classify_document`.
  - Carry it as a U9 test row. For `always` the same keying fails closed.
- **N2.** `test_real_rows_with_the_committed_exempt` asserts that no real row is flagged
  by both `always` and `exempt`. The correction withdrew that bullet (both is legal), so
  the assertion pins a U6 fact, not a rule. Say so in its message, or drop it when the
  first `always`+`exempt` entry lands (for example the GCC fallback).
- **N3.** The schema oracle accepts a future `reviewed` date (`security 2099-01-01`).
  Consider requiring `<= date.today()`.
- **N4.** The bad-shape table has 29 refused shapes plus 2 valid controls (the good
  policy and an empty `exempt`), not 31.
- **N5.** No test has a package purl carrying a `#subpath` (only `?type=jar`). A
  `_purl_base` that dropped only qualifiers would survive, though it would fail closed.
  The probe shows the current code strips it.

## Test adequacy and mutants
- The schema test refuses each bad shape, and the committed file passes. The controls
  cover:
  - version ignored or prefix-matched, and case fold;
  - the void problem silenced, and other images' entries applied;
  - `always` beating `exempt`, exempt not clearing needs, and `always` no longer forcing it;
  - the segment rule dropped, applied inside LicenseRef, `-`-only, case-sensitive, or on
    leaves only;
  - the policy host, key, `reviewed`, bump, reason, entry-set and image-name mutants.
- The equivalent mutant the tester names (accepting a qualifier-bearing entry) is
  correctly equivalent: such an entry can never equal a stripped package purl.
- Observability: pure functions and a JSON file; no spans needed.
