# platform-sbom U5 rework round 2 review (reviewer, 2026-10-24)

Scope: `git diff --no-index u5/r1-target-sbom_check.py scripts/sbom_check.py`, which
equals `u5/r2-target-sbom_check.py`; tests ReworkR2* in tests/test_sbom_classifier.py;
and rulings design-notes l.1127-1147.

Verdict: **CHANGES REQUESTED.** R1-B1, R1-N1 and R1-N2 are closed as ruled. Two
residual fail-opens remain in the same class: unknown ids that the leaf and run rules
still do not separate. Both come from the regexes I proposed in R1-B1(a)/(b), which
keep `+` and `:` inside an id. I should have caught this in round 1.

Evidence:
- `u5/reviewer-r2-controls.txt`: `r2_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u5): 123 rows, 108 must-fail, 15 must-pass, 0 unexpected (reproduced).
- `u5/reviewer-r2-probes.txt`, with scripts in `u5/reviewer-probes/` (`probe_r2.py`, `probe_r2_fix.py`).
- tests/test_sbom_classifier.py on the host: OK.

## Closed
- **R1-B1.** `LEAF_RE` is checked on every leaf and on the exception id; `RUN_SPLIT_RE`
  is used in the fallback; `_bare()` strips the DocumentRef prefix for `_unknown_id`,
  `_pattern_hit` and `_url_ref`. Every R1-B1 input now needs source and is unidentified
  (ReworkR2LeafCharsetTest l.813-820, ReworkR2DocumentRefTest).
- **R1-N1.** `_url_ref(exc)` lists an http LicenseRef in the WITH slot (ReworkR2WithUrlTest).
- **R1-N2.** The test file is ASCII (checked with `grep -P`), and ReworkR2SourceTest guards it.
- **Real-row snapshot unchanged.** I compared the round-1 checker (`r1-target-sbom_check.py`)
  with the current one row by row: `classify_document` output is identical for all six
  fixtures (ke-app 153/102/3/18/1, ke-gateway 71/17/0/0/0, neo4j 341/164/52/9/19,
  phoenix 277/30/4/10/25, postgres 149/130/6/22/3, valkey 24/12/0/0/1). This matches
  `ReworkR2RealRowsTest.SNAPSHOT`.
- **`unlicensed_report` untouched.** The `_hash_only`..`report_lines` block is
  byte-identical to HEAD, and so are `MISSING` and `HASH_ID_RE`.

## Blocking

**R2-B1. A `+` suffix hides an unknown id, and nothing lists it** (`_unknown_id`,
sbom_check.py l.375-379). `LEAF_RE` accepts a trailing `+` on any leaf. `_unknown_id`
strips the DocumentRef prefix but not the `+`. These inputs each return needs=False,
unparsed=False, unidentified=False:
- `NOASSERTION+`, `none+`, `DocumentRef-x:NONE+`
- `LicenseRef-<hash>+`, `MIT AND LicenseRef-<hash>+`, `DocumentRef-x:LicenseRef-<hash>+`
- `MIT WITH NOASSERTION+`, `MIT WITH LicenseRef-<hash>+`

SPDX 2.3 Annex D allows `+` only after a license-id, never after a LicenseRef.
Fix: `_unknown_id` drops one trailing `+` before the hash and NONE/NOASSERTION tests.

**R2-B2. `:` and `+` stay inside fallback runs, so an unknown id there needs no source**
(`RUN_SPLIT_RE`, l.328). Ruling 2 splits on characters outside `[A-Za-z0-9.+:-]`.
`+` and `:` are in that set, so `MIT:NOASSERTION` stays one run. These inputs are listed
unparsed but return needs=False, unidentified=False: `MIT:NOASSERTION`, `MIT+NOASSERTION`,
`NOASSERTION+MIT`, `NOASSERTION:`, `DocumentRef-:NONE`, `Public Domain MIT:NOASSERTION`.
This is the same shape as round-0 B2 (`MIT NOASSERTION`), which ruling 1 made fail closed.
Fix: split runs on characters outside `[A-Za-z0-9.-]`. That drops `+` and `:`; the
`+` is handled by R2-B1's strip, and the DocumentRef prefix splits off as its own run.

Proposed fix, both items: `RUN_SPLIT_RE = [^A-Za-z0-9.-]+`, plus the `+` strip in
`_unknown_id`. I simulated it on an in-memory copy of the module (`probe_r2_fix.py`;
no repo file changed):
- every input above needs source and is unidentified;
- the near-misses keep their pinned results: `see NONE.txt here` needs no source,
  `NOASSERTIONS apply` is not unknown, `MIT-NOASSERTION` is an opaque id;
- `classify_document` is unchanged on all six real fixtures;
- all 47 existing classifier tests pass.

Then add test and control rows for the inputs above.

## Nits
- None new. Still by design: an SPDX-valid opaque id is never unknown
  (`MIT-NOASSERTION`, `LicenseRef-NONE`, upper-hex hash, I-4). This is consistent with
  the pinned `LicenseRef-NONE` row.

## Checked
- `LEAF_RE` is applied before the WITH check, and to the exception id.
  `DocumentRef-x:DocumentRef-y:<hash>` is not a valid leaf, so the fallback's hash
  search catches it.
- Non-ASCII text still returns early (round-1 rule 3).
- Observability: still pure functions; no spans needed.
