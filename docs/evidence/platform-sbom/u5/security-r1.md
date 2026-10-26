# platform-sbom U5 rework round 1: security re-check

Date: 2026-10-24. Auditor: security. Scope: rework round 1 GREEN in the working tree.
`scripts/sbom_check.py` is byte-identical to `u5/r1-target-sbom_check.py`. Diff read:
`git diff --no-index docs/evidence/platform-sbom/u5/target-sbom_check.py scripts/sbom_check.py`.
Rulings: design-notes "Rework round 1" (items 1-10). Probes: `u5/security-r1-probes.txt`
(scripts `u5/security_r1_probes.py`, `u5/security_r1_probes_drift.py`, and the U5 set
`u5/security_probes.py` re-run; gates image, `python -I`). verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. L-1, L-2, L-3, L-4 and L-5a from `u5/security.md` are
closed. No new finding; three informational residuals.

| ID | Status | Evidence (part 1 unless noted) |
|---|---|---|
| L-1 | **Closed** | `LicenseRef-GNU-General-Public-License-v2`, `...-Affero-General-Public-License`, junk `GNU General Public License v2`, `GPLv2orlater`, plural `...-Licenses`, `...-Licence`, Lesser/Library forms and `GNU_GENERAL_PUBLIC_LICENSE` all need source, unparsed. Not hits, as pinned: `General-Public-Domain-License`, `Mozilla-Public-License-2.0` |
| L-2 | **Closed** | `noassertion` and `NoAssertion AND MIT` need source, unidentified; `MIT OR none` needs none, unidentified; junk `MIT AND AND noassertion`, `MIT NOASSERTION`, `Public Domain AND (NoAssertion` and 3000-deep `none` need source, unidentified. `LicenseRef-NONE` and `NOASSERTIONS` stay ordinary ids |
| L-3 | **Closed** | Cyrillic ER, fullwidth, ZWJ, NEL and NBSP expressions need source, unparsed. `MIT` + `w` + dotless-i + `th` + `GPL-3.0-only` (and + `Classpath-exception-2.0`) need source: non-ASCII returns before the parser, and `kw()` reads AND/OR/WITH only from ASCII |
| L-4 | **Closed** | `MIT WITH GPL-3.0-only`, `...WITH GPL-3.0-linking-exception`, `...WITH LicenseRef-General-Public-License`, `...WITH affero`, lower-case `with GPL-2.0`: need source, unparsed. `MIT WITH <hash>`, `MIT WITH NONE`, `MIT WITH noassertion`: need source, unidentified (addition b). `Apache-2.0 WITH LLVM-exception` still needs none |
| L-5a | **Closed** | Part 3: a namespaced `pkg:generic/x/python@3.12.15%1b%5d0%3bOWNED%07%1b%5b2J` beside the real row now gives rc 0 and an ok line with `CPython 3.12.15` only (no control byte). A non-namespaced version with ESC fails the drift check (rc 1) and prints it escaped. `_cpython` is the one set both paths use |
| U4 I-4 | Carried (info) | Upper-hex hash, bare or as `MIT WITH <upper-hex hash>`, is still a known id: no source. By ruling (case-sensitive; syft digest bump = PSC-22 re-review) |
| I-5 | New (info) | Token-rule residuals, all adversarial spellings, none in real data: camel `LicenseRef-GNUGeneralPublicLicense` (one token; silent), `LicenseRef-G.P.L.-v2` (silent), and `LicenseRef-https---www.gnu.org-copyleft-lesser.html` (no source but listed unparsed for review) |
| I-6 | New (info) | `MIT OR Apache-2.0 WITH GPL-3.0-only` needs no source (MIT elected) but is listed unparsed, as the tester pinned: the malformed exception is visible to review |

## Checks
- **Monotone (part 1, R1-B):** 60000 seeded random expressions over 33 tokens (operators in all
  cases, dotless-i `with`, hashes, NONE/NOASSERTION, GPL phrases, Cyrillic): 0 inputs need source
  under U5 GREEN but not under r1; 19454 need source only under r1. Every rework change only
  widens "needs source".
- **Real rows (R1-C):** all 1015 U3 rows classify identically under U5 GREEN and r1 (0 changed
  rows; needs 102/17/166/33/130/12). The 17 no-source rows with GPL-ish words are the same as in
  `security.md` section 1 (2 OR elections, 14 EPL/classpath URL ids listed unparsed, libpsl
  gnulib = FSF all-permissive).
- **`unlicensed_report` unchanged (R1-D):** `unlicensed_report`, `_missing`, `_hash_only`,
  `report_lines`, `_clean`, `_packages`, `_roots`, `_purl` are source-identical to HEAD; counts
  19/0/28/35/25/1 and printed lines equal on all six fixtures.
- **ReDoS / cost (R1-E, part 2):** `_token_hit` on 1-2 MB of `general public ...` near-misses
  takes at most 0.07 s; `GPL_PHRASE_RE` at most 0.01 s; `_unknown_in_text` at most 0.006 s;
  1 MB non-ASCII 0.009 s; `_cpython` on a 1 MB slash-run purl 0.015 s and on 100k packages 0.10 s;
  `PURL_RE` near-misses at most 0.02 s. Widest case: 200k `MIT WITH x OR` terms, 0.66 s. Depth
  100000 with a WITH leaf does not raise.
- **U5 probe set re-run (part 2):** escaping (`validate`, drift, psycopg, finish CLI) still 0 raw
  control lines; scanner and anchors unchanged; the A-rows that failed open at U5 (A13, A14,
  A17, A18, A21-A25, A30, A49, A50) now need source.
- **Evidence hygiene:** `u5/r1-*` (controls, mutants, verify fast/full, reach, target) and
  `u5/r1_controls.py`, plus `tests/test_sbom_classifier.py`: no keys, tokens, private keys, JWTs,
  credential URLs, password values, profile paths, SIDs, model-host name or port, or
  `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST` values. IPs: 127.0.0.1, the stack gateway's
  internal address in the smoke's no-route lines, and a Temurin version. `r1_controls.py` runs
  `git show` and harnesses in a `mkdtemp` checkout it removes; no network, no repository write.
