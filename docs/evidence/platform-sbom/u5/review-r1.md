# platform-sbom U5 rework round 1 review (reviewer, 2026-10-24)

Scope: `git diff --no-index u5/target-sbom_check.py scripts/sbom_check.py` (U5 GREEN to r1),
tests/test_sbom_classifier.py ReworkR1*, and rulings design-notes l.1083-1125. The other
U5 files equal their U5 GREEN targets, and `scripts/sbom_check.py` equals `u5/r1-target-sbom_check.py`.

Verdict: **CHANGES REQUESTED.** B1-B3 of `u5/review.md` are closed. R1-B1 below is a
silent fail-open from round 0 that I missed then. It needs a ruling before the developer fixes it.

Evidence:
- `u5/reviewer-r1-controls.txt`: `r1_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u5): 103 rows, 92 must-fail, 11 must-pass, 0 unexpected (reproduces `r1-green-controls.txt`).
- `u5/reviewer-r1-probes.txt`, with the scripts in `u5/reviewer-probes/` (`probe_r1.py`, `mutant_joined.py`).
- tests/test_sbom_classifier.py on the host: 37 tests OK.

## Round-0 findings
- B1 closed. `ReworkR1PerPartTest` pins the B1 rows, and `test_each_part_is_classified_alone`
  kills the joined-text mutant: my `mutant_joined.py` now gives 3 failures, where it gave 0 before.
  The tester's correction is right: under ruling 1 the B1 rows alone no longer separate the two.
- B2 closed by ruling 1. The NONE/NOASSERTION leaf check is ASCII any-case
  (`_unknown_id`), and `_unknown_in_text` handles runs inside unparseable text.
  Every input I gave now needs source and is unidentified (test rows l.619-628).
- B3 closed. `_cpython()` is shared by `drift_problems` and `drift`, and the success line
  goes through `_clean`. `ReworkR1DriftLineTest` uses my probe row, security's row, and a
  plain namespaced version.
- N1/N2 closed by rulings 3, 4 and 10: non-ASCII text needs source and is listed unparsed,
  operators are ASCII-only via `kw()`, and the exception id is read. N5, N6 and N7 are done.
  N3, N4 and N8 were ruled no change.
- `_hash_only`..`report_lines`, `MISSING` and `HASH_ID_RE` are byte-identical to HEAD, so
  the U4 report counts do not move. Test l.615-617 pins that a `none` field stays licensed there.

## Blocking

**R1-B1. An unknown id inside a leaf with non-SPDX characters is not flagged or listed
(sbom_check.py `_leaf`/`_unknown_id`, `_unknown_in_text`).** A leaf is any run of
characters other than whitespace and parentheses (the architect's "no charset check;
the token rule covers odd ids"). The token rule covers only GPL. `_unknown_id` uses
`fullmatch`, and `_unknown_in_text` splits only on whitespace and parentheses. So an
unknown id joined to other text by punctuation passes with needs=False, unparsed=False,
unidentified=False, and nothing lists it for security:
- `MIT/NOASSERTION`, `"NOASSERTION"`, `NOASSERTION,`, `MIT,NOASSERTION`, `NOASSERTION;MIT`, `MIT\x00NOASSERTION`
- `LicenseRef-<hash>;`, `MIT,LicenseRef-<hash>`
- `DocumentRef-spdx:LicenseRef-<hash>` and `MIT AND DocumentRef-x:LicenseRef-<hash>`.
  This is valid SPDX 2.3 syntax for a hash ref.

By rulings 1 and 10 these ids are unknown and fail closed (compare `MIT NOASSERTION`,
which now needs source). Here they pass silently, which is worse than round-0 B2, where
the text was at least listed unparsed. Syft writes none of these today: all 7572 leaves
in the six U3 fixtures fullmatch the SPDX idstring, so a fix changes no real row.

Proposed ruling:
- (a) A leaf must fullmatch `(DocumentRef-[A-Za-z0-9.-]+:)?[A-Za-z0-9.-]+\+?` (SPDX 2.3
  Annex D idstring, plus the `+` suffix). Any other leaf makes the text unparseable, which
  falls to the token-or-unknown fallback.
- (b) `_unknown_in_text` also splits runs on characters outside `[A-Za-z0-9.+:-]`.
- (c) `_unknown_id` accepts a `DocumentRef-...:` prefix before the hash id.

Add test rows for the inputs above and control rows.

## Nits
- R1-N1. A LicenseRef in the WITH exception slot that contains `http` but no GPL token is
  not listed unparsed: `MIT WITH LicenseRef-https---example.org-x` gives needs=False with
  no flags. N8 says every LicenseRef id containing http is listed. Fold into R1-B1's ruling.
- R1-N2. tests/test_sbom_classifier.py l.594 holds NBSP, ZWJ, CYR_ER and DOTLESS_I as
  literal characters (UTF-8 bytes in the file), invisible in review. Write them as the
  escapes `\u00a0`, `\u200d`, `\u0420`, `\u0131` so they survive editors that normalise text.

## Checked
- Ruling 2: `_token_hit` matches a token containing `gpl`, the token `affero`, and the
  phrase `general public licen[cs]es?` on space-joined tokens with boundaries. `lesser`
  alone does not match. It is used by `is_gpl_id`, the leaf test, the exception slot and
  the fallback.
- Ruling 3: `not expr.isascii()` returns early, before parsing, with needs and unparsed
  set. `kw()` returns "" for non-ASCII tokens.
- Rulings 4 and 10: the ("with", leaf, exc) node. An unknown exc gives needs and
  unidentified. A GPL-family exc gives needs and unparsed. Otherwise the result is the
  leaf's. Deep nesting with WITH is still caught.
- Observability: still pure functions, no spans needed.
