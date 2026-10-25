# platform-sbom U5 rework round 3: security re-check

Date: 2026-10-25. Auditor: security. Scope: rework round 3 GREEN; only `scripts/sbom_check.py`
changed since r2, and it is byte-identical to `u5/r3-target-sbom_check.py`. Diff read:
`git diff --no-index docs/evidence/platform-sbom/u5/r2-target-sbom_check.py scripts/sbom_check.py`
(`RUN_SPLIT_RE` = `[^A-Za-z0-9.-]+`, `HASH_IN_RE`, trimmed bare id in `_unknown_id`). Rulings:
design-notes "Rework round 3" items 1-7. Probes: `u5/security-r3-probes.txt` (script
`u5/security_r3_probes.py`; gates image, `python -I`). verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. Security R2-L1 is closed, and I-7 with it. Review R2-B1/B2
inputs now need source. Nothing became weaker than r2. No new finding; one informational note.

| ID | Status | Input -> r3 result (r2 gave no source, not unidentified, for every row) |
|---|---|---|
| R2-L1 | **Closed** | `<hash>+`, `MIT WITH <hash>+`, `<hash>.x`, `x<hash>`, `MIT AND NOASSERTION.`, `MIT AND NOASSERTION+`, `MIT AND -NONE`: need source, unidentified. `<hash>` + 65th hex digit stays ordinary (ruling 4); in junk text it still needs source (`Public Domain <65 hex>`, ruling 6) |
| R2-B1/B2 (review) | Inputs need source | `MIT:NOASSERTION`, `MIT+NOASSERTION` (unparsed, unidentified); `DocumentRef-x:NONE+`, `DocumentRef-x:-NONE-`, `MIT AND ..NONE..`, `MIT WITH NONE.` (unidentified); `<hash>F` (uppercase F after 64 hex) unknown |
| I-7 | **Closed** | `documentref-x:NONE`, `DocumentRef-a:DocumentRef-b:NONE`, `DocumentRef-:NONE`, `MIT AND NONE:` now need source, unidentified (`:` splits runs) |
| I-9 | New (info) | Still ordinary, no source, not listed: `MIT AND NONE.NONE` (one idstring; the trim keeps the inner dot), and the pinned `MIT-NOASSERTION`, `LicenseRef-NONE` (ruling 5). A hash with an uppercase hex digit inside stays ordinary (U4 I-4, by ruling). None occurs in real data; syft writes none of them |

Kept: `MIT OR NOASSERTION+` needs no source (MIT elected) but is unidentified; `GPL-2.0+` needs
source; `MIT+ OR Apache-2.0+` needs none; `MIT OR GPL-2.0-only AND Apache-2.0` elects MIT;
`DocumentRef-NONE:MIT` is MIT (the prefix is a document name). Carried info: U4 I-4, I-5, I-6, I-8.

## Checks
- **Nothing weaker than r2 (R3-B):** 150000 seeded random expressions over 41 tokens, joined by
  space, nothing, `-`, `+`, `:` or `.` (hashes with `+`, a 65th hex digit or an `x` prefix, `F`,
  NONE/NOASSERTION in any case, DocumentRef prefixes, punctuation, all operator cases): 0 inputs
  that needed source in r2 but not in r3; 0 that r2 flagged or listed and r3 neither needs nor
  lists; 10088 that need source only in r3. By construction too: `HASH_IN_RE.search(id)`
  covers r2's `HASH_ID_RE.fullmatch(bare)` (a full-string hash is followed by end of text), the
  trimmed bare id covers the untrimmed one, and splitting runs on `+` and `:` as well leaves the
  bare id of every r2-unknown run as its own run.
- **Real rows (R3-C):** 0 of the 1015 U3 rows change (needs 102/17/166/33/130/12).
- **`unlicensed_report` untouched (R3-D):** it, its helpers and `HASH_ID_RE` are identical to HEAD;
  counts 19/0/28/35/25/1 and printed lines equal on all six fixtures.
- **ReDoS / cost (R3-E):** `HASH_IN_RE.search` on 1 MB of repeated `LicenseRef-`, a 1 MB hex run,
  and 13k near-miss hashes of 63 or 65 hex digits: at most 0.001 s each. The trim on a 2 MB
  `.-+` run: 0.005 s. `RUN_SPLIT_RE` on 1 MB of `+:`: 0.001 s. `_unknown_in_text` at most 0.11 s;
  `needs_source` at most 0.14 s at 200k terms; depth 100000 with `NONE+` does not raise.
- **Evidence hygiene:** `u5/r3-*` (controls, mutants, verify fast/full, reach, target),
  `u5/r3_controls.py` and `tests/test_sbom_classifier.py`: no keys, tokens, private keys, JWTs,
  credential URLs, password values, profile paths, SIDs, model-host name or port, or
  `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST` values. IPs: 127.0.0.1, the stack gateway's internal
  address in the smoke's no-route lines, a Temurin version. The test file is pure ASCII.
  `r3_controls.py` works in `mkdtemp` dirs; no network, no repository write.
