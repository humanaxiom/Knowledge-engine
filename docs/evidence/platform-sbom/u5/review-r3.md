# platform-sbom U5 rework round 3 review (reviewer, 2026-10-25)

Scope: `git diff --no-index u5/r2-target-sbom_check.py scripts/sbom_check.py`, which equals
`u5/r3-target-sbom_check.py`; tests ReworkR3* in tests/test_sbom_classifier.py; rulings
design-notes l.1149-1171.

Verdict: **APPROVED.** No blocking findings.

Evidence:
- `u5/reviewer-r3-controls.txt`: `r3_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u5): 135 rows, 118 must-fail, 17 must-pass, 0 unexpected (reproduced).
- `u5/reviewer-r3-probes.txt`, from `u5/reviewer-probes/probe_r3.py`.
- tests/test_sbom_classifier.py on the host: 52 tests OK. The file is ASCII-only (`grep -P`: 0 lines).

## Closed
- **R2-B1.** `_unknown_id` strips the DocumentRef prefix, then trims `.`, `-` and `+`
  from both ends, and also uses `HASH_IN_RE.search`. Every R2-B1 input now gives
  needs=True, unidentified=True: `NOASSERTION+`, `none+`, `DocumentRef-x:NONE+`,
  `<hash>+`, `MIT AND <hash>+`, `DocumentRef-x:<hash>+`, `MIT WITH NOASSERTION+`,
  `MIT WITH <hash>+`. `MIT OR NONE+` needs no source (MIT is elected) but is unidentified.
- **R2-B2.** `RUN_SPLIT_RE` is now `[^A-Za-z0-9.-]+`. `MIT:NOASSERTION`,
  `MIT+NOASSERTION`, `NOASSERTION+MIT`, `NOASSERTION:`, `DocumentRef-:NONE` and
  `Public Domain MIT:NOASSERTION` all give needs, unparsed and unidentified.
- **Security R2-L1.** These now need source and are unidentified: `<hash>.x`,
  `x<hash>`, `MIT AND NOASSERTION.`, `MIT AND -NONE`, `-NONE-`, `NOASSERTION..`, and
  `MIT WITH x<hash>`. Per ruling 7, decorated unknown leaves are listed through
  "unidentified" only. The code and the tests do that: unparsed is left unpinned
  where the text still parses.
- **Pinned near-misses unchanged (ruling 5).** `see NONE.txt here`, `NOASSERTIONS apply`,
  `MIT-NOASSERTION`, `LicenseRef-NONE` and a 65-hex id in a leaf stay ordinary.
  `Public Domain <65-hex>` still needs source through the whole-text search (ruling 6).
- **Real-row snapshot unchanged.** `classify_document` output is identical row by row to
  both the r1 and the r2 checker on all six fixtures (ke-app 153/102/3/18/1, ke-gateway
  71/17/0/0/0, neo4j 341/164/52/9/19, phoenix 277/30/4/10/25, postgres 149/130/6/22/3,
  valkey 24/12/0/0/1).
- **`unlicensed_report` untouched.** The `_hash_only`..`report_lines` block is
  byte-identical to HEAD, and so are `MISSING` and `HASH_ID_RE`.

## Remaining shapes (not blocking; for U6 if wanted)
- **I-r3-1. Opaque idstrings that contain a keyword joined by an idstring character stay
  ordinary**, with needs, unparsed and unidentified all false: `NOASSERTION.NONE`,
  `NOASSERTION-2.0`, `LicenseRef-NOASSERTION`, `DocumentRef-x:LicenseRef-NONE`. This is
  the shape ruling 5 already treats as ordinary (`MIT-NOASSERTION`, `LicenseRef-NONE`).
  They are valid SPDX ids, and the design reads any id that is not GPL-family as an
  ordinary licence, as it does `LicenseRef-Proprietary`. So this is not a new fail-open
  in the family that was ruled closed.
  - Not blocking for U5: the classifier has no caller until U9, no real row has the
    shape (all 7572 real leaves are plain idstrings), and the rule is a ruling, not a
    code gap.
  - If the orchestrator wants it closed, carry it as U6's first test row: "a
    `-`/`.`-separated segment equal to NONE/NOASSERTION is unknown". Exclude the
    `LicenseRef-` body so that the pinned `LicenseRef-NONE` keeps its ruling.
- **I-r3-2.** Upper-case-hex hash ids stay ordinary: U4 I-4 is carried, and a bump of
  the generator digest is the re-review trigger.

## Checked
- `_unknown_in_text` keeps the whole-text `HASH_ID_RE.search` and adds the per-run
  `_unknown_id` with the new split.
- `HASH_IN_RE` (64 hex, then not hex) is used only inside `_unknown_id`; `HASH_ID_RE`
  is unchanged.
- No other code changed since r2.
- Observability: pure functions; no spans needed.
