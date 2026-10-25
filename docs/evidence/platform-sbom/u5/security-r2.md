# platform-sbom U5 rework round 2: security re-check

Date: 2026-10-24. Auditor: security. Scope: rework round 2 GREEN; only `scripts/sbom_check.py`
changed since r1, and it is byte-identical to `u5/r2-target-sbom_check.py`. Diff read:
`git diff --no-index docs/evidence/platform-sbom/u5/r1-target-sbom_check.py scripts/sbom_check.py`
(`LEAF_RE`, `DOCREF_RE`, `RUN_SPLIT_RE`, `_bare`, `_url_ref`, leaf and WITH-exception charset
check). Rulings: design-notes "Rework round 2" items 1-5. Probes: `u5/security-r2-probes.txt`
(script `u5/security_r2_probes.py`; gates image, `python -I`). verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. Review R1-B1 is closed. Nothing became weaker than r1. One
new low residual (R2-L1), non-blocking; two informational notes.

| ID | Severity | Status | Finding / input |
|---|---|---|---|
| R1-B1 | (review) | **Closed** | `MIT,NOASSERTION`, `MIT/NOASSERTION`, `"NOASSERTION"`, `<hash>;`, `MIT OR <hash>#`, `MIT OR (x=NOASSERTION)`, NUL-separated `MIT OR NONE`: need source, unparsed, unidentified (r1: no source, not listed). `DocumentRef-x:<hash>`, `MIT WITH DocumentRef-x:<hash>`, `MIT AND DocumentRef-x:noassertion`: need source, unidentified. `MIT OR DocumentRef-x:NONE`: MIT elected, unidentified |
| R2-L1 | low | New | A leaf that is still a valid idstring but decorates an unknown id is read as a known id: no source, **not listed**. Inputs: `<hash>+`, `MIT WITH <hash>+`, `<hash>.x`, `x<hash>`, `<hash>0` (65 hex), `MIT AND NOASSERTION.`, `MIT AND NOASSERTION+`, `MIT AND -NONE`. Same result in r1 and U5 (not a regression); syft writes none of them; 0 of the 3731 real leaves. Fix (cheap, fail closed): in `_unknown_id`, drop one trailing `+` before matching, and treat any leaf in which `HASH_ID_RE.search` hits as unknown |
| I-7 | info | New | Listed unparsed but no source: `documentref-x:NONE` (lower-case prefix), `DocumentRef-a:DocumentRef-b:NONE` (only one prefix is read), `DocumentRef-:NONE`, `MIT AND NONE:`, `DocumentRef-x:` alone. Visible to review. A hash after two prefixes needs source (the hash search finds it) |
| I-8 | info | New | `DocumentRef-x:GPL-2.0-only` and `DocumentRef-x:LicenseRef-GPL-2.0` now hit the anchored pattern through `_bare`, so they need source without the unparsed flag (r1 listed them via the token rule). This is ruling 3; `needs` is unchanged |

Carried and unchanged: U4 I-4 (upper-hex hash), I-5 (camel `GNUGeneralPublicLicense`, `G.P.L.`),
I-6 (`MIT OR Apache-2.0 WITH GPL-3.0-only` listed unparsed).

## Checks
- **Monotone vs r1 (R2-B):** 100000 seeded random expressions over 42 tokens (punctuation
  `, ; / : . + " = _ # @ -`, DocumentRef prefixes, hashes with `+`, NONE/NOASSERTION in all cases,
  all operator cases): needs r1-only 0, r2-only 3841. Inputs r1 flagged or listed that r2 neither
  needs nor lists: 0. By construction too: every leaf that made r1 need source (hash, NONE or
  NOASSERTION, GPL pattern or token) is found again by the fallback's hash search, run split or
  token rule when its text becomes unparseable, and only OR elections can lower a parsed result.
- **Real rows (R2-C):** all 3731 leaves in the 1015 real U3 rows fullmatch `LEAF_RE`; 0 rows change
  (needs 102/17/166/33/130/12).
- **`unlicensed_report` untouched (R2-D):** it and `_missing`, `_hash_only`, `report_lines`,
  `_clean`, `_packages`, `_roots`, `_purl` are source-identical to HEAD; counts 19/0/28/35/25/1
  and printed lines equal on all six fixtures.
- **ReDoS / cost (R2-E):** `LEAF_RE.fullmatch` on 1 MB near-misses (DocumentRef run with no colon,
  `!` or `++` tail, `-.` runs) at most 0.011 s; `DOCREF_RE.match` and `_bare` at most 0.002 s;
  `RUN_SPLIT_RE.split` at most 0.020 s; `_unknown_in_text` at most 0.124 s (500k runs);
  `needs_source` on 1 MB punctuation junk 0.106 s, 200k terms 0.223 s; depth 100000 with a
  DocumentRef leaf does not raise.
- **Kept behaviour:** `GPL-2.0+` needs source, `MIT+ OR Apache-2.0+` none, jna's
  `Apache-2.0 AND LGPL-2.1-only` needs source, `MIT OR GPL-2.0-only AND Apache-2.0` MIT elected,
  tab separators parse. An http `LicenseRef-` in the WITH slot is listed (ruling 4).
- **Evidence hygiene:** `u5/r2-*` (controls, mutants, verify fast/full, reach, target),
  `u5/r2_controls.py` and `tests/test_sbom_classifier.py`: no keys, tokens, private keys, JWTs,
  credential URLs, password values, profile paths, SIDs, model-host name or port, or
  `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST` values. IPs: 127.0.0.1, the stack gateway's internal
  address in the smoke's no-route lines, a Temurin version. The test file is now pure ASCII
  (ruling 5). `r2_controls.py` works in `mkdtemp` dirs; no network, no repository write.
