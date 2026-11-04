# platform-sbom part 9

Plan item: platform-sbom. U5 gate detail: review and security rounds 0 and 1.
Live handoff: [../platform-sbom.md](../platform-sbom.md).

## 2026-10-24 — tester (U5 RED), removed bullets
- Asked: the U5 RED (classifier, L-4/L-5/R2, tree size, scanner continuation line, smoke -xdev) per orchestrator rulings 1-9, its additions 1-6, and design-notes "N8 amendment, U5".
- Tests: new `tests/test_sbom_classifier.py` (26 methods: GplId, NeedsSource, LicenceInput, ClassifyPackage, ClassifyDocument, Escaping); in `tests/test_neo4j_image.py`, Neo4jTreeCheckTest has 2 new methods and SmokeNoFleetPluginTest gains /sys, /dev, /data and /logs cases plus an argv check; `tests/test_engine_hardcoded.py` gains `test_dockerfile_exemption_skips_continuation_lines`.
- Contradictions resolved in this RED (CLAUDE.md): Neo4jTreeCheckTest drops the 5-tuple for (type, mode, uid, gid, size, link) (ruling 6, amendment item 4), and its U4b hard-link passing case moves to tar-based tests. SmokeNoFleetPluginTest's "-xdev" passing case (/proc) is now "pruned" (ruling 8, item 6).
- R3 done: `u4/u4_controls.py` docstring marks it superseded by r1_controls.py.
- For the architect:
  - amendment item 2 still says "needs source iff the token rule hits it ... (listing only)"; the tests follow orchestrator addition 3 (a hash id in junk needs source), so the text needs amending.
  - N16 l.1560 still says `-xdev`.
  - `u4b/u4b_controls.py` smoke row "no -xdev" and its 5-tuple tree rows go stale at GREEN, so mark that file superseded as R3 did.
- Pinned beyond the brief, all fail-closed (flag if wrong): junk text uses the token rule (`the LGPL, version 2.1` needs source); a hard link keeps its own mode and takes only its target's size; trailing blanks after `\` still continue the line; 3000-deep parentheses do not raise. `test_psycopg_problems_escape` is a guard, green before U5, because repr already escapes. One mutant is equivalent and not a row: classify the joined text instead of each part (the token and hash rules over the whole text make it the same).
- Next: developer GREEN, loop `fast`. Item 8 (smoke) is green only under `verify.sh full`.

## 2026-10-24 — developer (U5 GREEN), removed bullets
- Asked: GREEN for the 30 U5 RED methods; no commit. Copied the tester's targets to `scripts/sbom_check.py`, `tests/hardcoded_scan.py`, `scripts/smoke.sh`, `scripts/offline_check.sh`; read the diff (classifier is pure stdlib, WITH>AND>OR, both-set `(d) AND (c)`, `fullmatch`, 6-tuple tree); no refactor needed.
- Also: `u4b/u4b_controls.py` docstring marked SUPERSEDED by `u5/u5_controls.py` (orchestrator ruling).
- Evidence: `u5/green-verify-fast.txt`, `u5/green-verify-full.txt` (redacted).
- Not committed. Throwaway `.env` removed. Archive files part1/part6 show edits not made by me.

## 2026-10-24 — reviewer (U5)
- Asked: review the U5 diff (classifier, escaping, tree size, scanner, smoke prune) against N8/N8a and the U5 amendment. Verdict: **CHANGES REQUESTED**. Detail: `u5/review.md`.
- B1 (tester/developer): the per-part rule in `classify_package` is not pinned. The "classify the joined text" mutant passes all 26 tests and fails open on `declared "Public Domain"` + `concluded "MIT AND NOASSERTION"` (`u5/reviewer-probes.txt`). It is not equivalent. Add the test rows and a control row.
- B2 (orchestrator ruling first): in unparseable text, NONE/NOASSERTION gives needs=False and not unidentified (`Public Domain AND NOASSERTION`, `MIT NOASSERTION`). The hash case was ruled fail-closed. Proposed: treat an exact NONE/NOASSERTION run like a hash id.
- B3 (developer): `sbom_check.py:587` (drift's success line) prints SBOM CPython versions without `_clean`. A namespaced `pkg:generic/x/python@...%1b...` gives rc 0 and a raw ESC (amendment item 7).
- Nits N1-N8 in review.md. Highlights: a GPL id in the WITH exception slot is not read or listed; `str.upper()` makes U+0131 an operator; the scanner rule misses comment or blank lines inside a continuation (for security PS-1.2); `green-controls.txt` is only a tail.
- Conformant: (a) apart from B2, (c) apart from B3, (d), (f), (g). Controls re-run in the gates image: 66/58/8, 0 unexpected (`u5/reviewer-controls.txt`).
- Next: orchestrator rules B2; developer and tester fix B1 and B3 (verify fast loop), then re-review.

## 2026-10-24 — security (U5)
- Asked: audit the U5 diff (classifier, escaping, scanner continuation, smoke prune); close U4 L-4/L-5/I-4, U4b I-2/L-1. Verdict: **PASS** (no critical/high/medium). Detail: `u5/security.md`; probes `u5/security-probes.txt` (scripts `u5/security_probes.py`, `u5/security_probes_drift_ok.py`; gates image, `python -I`, own `--network none` containers).
- Closed: U4 L-4 (hash-only declared + MIT concluded, NONE/NOASSERTION/hash leaves, `<hash> WITH e`: need source, unidentified); U4b I-2 continuation half; U4b L-1 (planted jars in /data, /logs, a tmpfs are seen; old `-xdev` missed them; rc and whole-output compare fail closed). `unlicensed_report` unchanged (source-identical; same reports for all six images). No ReDoS or raise (depth 100000, 1 MB inputs). Evidence clean.
- U4 L-5 closed except **L-5a (low)** = reviewer B3, confirmed: `scripts/sbom_check.py:587` drift ok line prints SBOM CPython versions raw on stdout (`pkg:generic/x/python@3.12.15%1b%5d0%3bOWNED%07...` gives rc 0 and an OSC sequence). Fix: `_clean` it, and take `py` from the non-namespaced set.
- New low, non-blocking (no real U3 row; fix before U9 consumes the classifier): L-1 GPL names spelled out without a `gpl` token (`LicenseRef-GNU-General-Public-License-v2`, silent); L-2 odd-case `noassertion` and NONE/NOASSERTION in junk (= reviewer B2); L-3 non-ASCII look-alikes (`G` + Cyrillic ER + `L-3.0-only`); L-4 WITH exception slot unread (`MIT WITH GPL-3.0-only`). Info: I-1 type rule / files order as ruled; I-2 /dev/shm pruned, `cap_drop: ALL` would fail the smoke closed; I-3 raw echo of find output; I-4b deep nesting takes the unparseable path; U4 I-4 carried.
- Next: developer fixes L-5a with B1/B3; orchestrator rules B2 (covers L-2) and whether L-1/L-3/L-4 land now or at U6. Security re-checks the rework diff.

## 2026-10-24 — security (U5 rework r1)
- Asked: re-check L-1..L-4 and L-5a against rework round 1 (design-notes l.1083-1125). Verdict: **PASS** (no critical/high/medium; no new finding). Detail: `u5/security-r1.md`; probes `u5/security-r1-probes.txt` (scripts `u5/security_r1_probes.py`, `u5/security_r1_probes_drift.py`, U5 set re-run).
- Closed: L-1 (spelled-out, plural `Licenses`, `Licence`, Affero, `GPLv2orlater`), L-2 (any-case NONE/NOASSERTION leaves and junk runs), L-3 (non-ASCII incl. dotless-i `wıth`), L-4 (GPL-family exception: unparsed; `MIT WITH <hash>`/NONE/noassertion: unidentified), L-5a (drift ok line from `_cpython`, `_clean`ed; namespaced python no longer printed).
- Checks: 60000 random expressions, 0 that needed source at U5 GREEN and not now; 1015 real rows unchanged; `unlicensed_report` source-identical, six fixtures equal; no ReDoS (worst 0.66 s at 200k terms); r1 evidence clean.
- Info only: U4 I-4 carried (upper-hex hash, also in the WITH slot); I-5 adversarial token residuals (camel `GNUGeneralPublicLicense`, `G.P.L.`; the gnu.org copyleft URL is listed unparsed); I-6 `MIT OR Apache-2.0 WITH GPL-3.0-only` no source but unparsed (as pinned).
- Next: nothing from security for U5; orchestrator's commit-gate `verify.sh full`.

## 2026-10-24 — reviewer (U5 rework r1)
- Asked: re-check rework round 1 (rulings design-notes l.1083-1125). Verdict: **CHANGES REQUESTED**. Detail: `u5/review-r1.md`.
- Closed: B1 (`test_each_part_is_classified_alone` kills the joined-text mutant: 3 failures, 0 before), B2 (ruling 1), B3 (`_cpython` + `_clean`), N1/N2 (rulings 3/4/10), N5-N7. The U4 report block, `MISSING` and `HASH_ID_RE` are byte-identical to HEAD.
- R1-B1 (new, ruling first; present since round 0): an unknown id joined to other text by punctuation passes silently, with needs, unparsed and unidentified all false (not listed). Examples: `MIT/NOASSERTION`, `"NOASSERTION"`, `MIT,LicenseRef-<hash>`, `DocumentRef-x:LicenseRef-<hash>`. Proposed: leaves must fullmatch the SPDX idstring, else unparseable; the unknown-run split also breaks on characters outside `[A-Za-z0-9.+:-]`; DocumentRef prefix accepted on hash ids. All 7572 real fixture leaves already fullmatch, so no real row changes.
- Nits: R1-N1 (a http LicenseRef in the WITH slot is not listed), R1-N2 (literal invisible chars in the test file).
- Controls re-run in gates image: 103/92/11, 0 unexpected (`u5/reviewer-r1-controls.txt`); probes `u5/reviewer-r1-probes.txt`.
- Next: orchestrator rules R1-B1; then the tester runs RED, the developer runs GREEN, and it comes back for re-review.

## 2026-10-24 — tester (U5 rework r1 RED)
- Asked: the round-1 RED for review B1-B3 and security L-1..L-4, L-5a: orchestrator rulings 1-7 and additions a (plural phrase) and b (unknown exception ids); design-notes "Rework round 1" (l.1083 on).
- Tests: `tests/test_sbom_classifier.py` gains 6 `ReworkR1*` classes (11 methods): UnknownLeaves, TokenRule, NonAscii, WithException, PerPart, DriftLine.
- Superseded old assertions (CLAUDE.md *Contradictions*):
  - `MIT AND noassertion` is now unidentified (ruling 1);
  - `is_gpl_id("GPLX")` is now true (ruling 2).
- RED: `scripts/verify.sh fast`, 911 ran. 11 methods fail (59 incl. subtests): the 9 new R1 methods plus the 2 superseded assertions. 0 errors; sentinel ok (`u5/r1-red-verify-fast.txt`). The 2 PerPart methods pass on the U5 code: B1 was a test gap; the controls prove the rows are live.
- Reach: r1 target overlaid, verify fast PASS, 911 OK, sentinel ok; repo restored (`u5/r1-target-reach-verify-fast.txt`). Target: `u5/r1-target-sbom_check.py` (only `scripts/sbom_check.py` changes).
- Controls: 103 rows (92 must fail, 11 must pass), 0 unexpected, gates image. Full output (N6): `u5/r1-red-mutants.txt`. Script: `u5/r1_controls.py`, which supersedes `u5_controls.py` for the classifier rows; the scanner, smoke and offline rows are kept as regressions.
- Correction to my U5 RED note "one mutant is equivalent" (ruling 6): wrong, as review B1 showed; B1's rows killed the joined-text mutant.
  - Under ruling 1 the B1 rows alone no longer kill it: the joined text does not parse, and its NOASSERTION run now counts.
  - So `test_each_part_is_classified_alone` pins per-part elections beside a junk part (`MIT OR GPL-2.0-only` + `Public Domain`: no source, unparsed).
  - Controls: that mutant is must-fail there. A documented must-pass row shows it survives the B1 rows alone; a must-fail row shows those rows killed it on the U5 checker.
- Equivalent mutant, not a row: drift's ok line without `_clean`. With the non-namespaced set, the line holds only the version that equals the licence files' `CPython X.Y.Z:`. The row kept is "raw AND from `_named`".
- Pinned beyond the brief (fail closed; flag if wrong):
  - `LicenseRef-NONE` and `NOASSERTIONS` are ordinary ids, and `see NONE.txt here` holds no unknown run;
  - `LGPL2` hits the anchored pattern (not unparsed);
  - `MIT OR Apache-2.0 WITH GPL-3.0-only` needs no source (MIT elected) but is listed unparsed;
  - `LicenseRef-General-Public-Domain-License` is not a phrase hit.
- Next: developer GREEN (copy the r1 target or equivalent), loop `fast`; then re-review and security re-check.

## 2026-10-24 — developer (U5 rework r1 GREEN)
- Asked: round-1 GREEN for review B1-B3 and security L-1..L-5a. Only `scripts/sbom_check.py` changed: copied `u5/r1-target-sbom_check.py` over it; diff read against the U5 GREEN, no refactor needed (matches rulings 1-5, additions a/b; `unlicensed_report`/`_missing` untouched).
- Change: `GPL_TOKEN_RE` -> token-contains-`gpl`/`affero` + plural phrase regex; `_unknown_id`/`_unknown_in_text` (any-case NONE/NOASSERTION, hash); ASCII-only `kw()` for AND/OR/WITH; `("with", leaf, exc)` node with exception read; non-ASCII expression => needs + unparsed; `_cpython()` feeds `drift_problems` and the ok line (through `_clean`).
- `scripts/verify.sh fast`: PASS, 911 ran OK (skipped=8), sentinel ok (`u5/r1-green-verify-fast.txt`).
- `scripts/verify.sh full`: PASS (1033 s) (`u5/r1-green-verify-full.txt`). A first full run failed only because jq was not on PATH (bundle.sh); rerun with jq on PATH.
- Controls: 103 rows, 92 must-fail, 11 must-pass, 0 unexpected (`u5/r1-green-controls.txt`).
- Next: reviewer and security re-check the rework diff. Nothing committed.

## 2026-10-24 — tester (U5 rework r2 RED)
- Asked: round-2 RED for review R1-B1, R1-N1, R1-N2 (orchestrator rulings a-e).
- Tests: `tests/test_sbom_classifier.py` gains 5 `ReworkR2*` classes (10 methods): LeafCharset, DocumentRef, WithUrl, RealRows, Source. The file's non-ASCII test characters are now `\u` escapes (ruling e), and `test_classifier_tests_are_ascii` guards that.
- RED: `scripts/verify.sh fast`, 921 ran. 5 methods fail (24 incl. subtests), 0 errors, sentinel ok (`u5/r2-red-verify-fast.txt`).
  - Guards, green on round 1: the idstring-still-parses rows, the hash-anywhere rows, the real-row checks (7572 runs, 0 outside the idstring; per-image classification snapshot with no `always`, unchanged under r2) and the ASCII source check.
- Reach: r2 target overlaid, verify fast PASS, 921 OK; repo restored (`u5/r2-target-reach-verify-fast.txt`). Target: `u5/r2-target-sbom_check.py` (only `scripts/sbom_check.py` changes).
- Controls: `u5/r2_controls.py`, which supersedes r1_controls.py. 123 rows (108 must fail, 15 must pass), 0 unexpected, gates image. Full output: `u5/r2-red-mutants.txt`.
  - It includes the mutants asked for: no leaf charset check, no DocumentRef handling (3 forms), and runs split on whitespace only or on whitespace and parentheses.
  - It also includes the exception-slot charset, idstring without `+`, and idstring without `.` (caught by the real-row snapshot).
- Pinned beyond the brief (fail closed; flag if wrong):
  - the exception id after WITH must be an idstring too (`MIT WITH Classpath-exception-2.0;NOASSERTION` needs source and is unidentified);
  - the http listing and the GPL pattern read through a `DocumentRef-x:` prefix (`DocumentRef-x:LicenseRef-https---example.org-x` is listed unparsed);
  - a hash id glued inside a run still counts (`see:<hash>`), as ruled in round 0.
- Next: developer GREEN (copy the r2 target or equivalent), loop `fast`; then re-review and security re-check.

## 2026-10-24 — developer (U5 rework r2 GREEN)
- Asked: round-2 GREEN for review R1-B1/N1/N2 (design-notes "Rework round 2"). Only `scripts/sbom_check.py` changed: copied `u5/r2-target-sbom_check.py`; diff against the r1 target read, no refactor (LEAF_RE on leaves and exception id, RUN_SPLIT_RE, `_bare` DocumentRef prefix in `_unknown_id`/GPL pattern/`_url_ref`, http exception listed). `unlicensed_report`/`_missing` untouched.
- `scripts/verify.sh fast`: PASS (`u5/r2-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u5/r2-green-verify-full.txt`). Controls: `u5/r2-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.

## 2026-10-24 — security (U5 rework r2)
- Asked: re-check round 2 (leaf charset `LEAF_RE`, `RUN_SPLIT_RE`, `_bare` DocumentRef prefix, http ref in WITH; design-notes "Rework round 2"). Verdict: **PASS** (no critical/high/medium). Detail: `u5/security-r2.md`; probes `u5/security-r2-probes.txt` (script `u5/security_r2_probes.py`).
- Closed: review R1-B1 (`MIT,NOASSERTION`, `MIT/NOASSERTION`, `"NOASSERTION"`, `<hash>;`, `DocumentRef-x:<hash>`: need source, unidentified). Not weaker than r1: 100000 random expressions, 0 regressions and 0 lost listings; 1015 real rows unchanged (all 3731 leaves fullmatch `LEAF_RE`); `unlicensed_report` source-identical, six fixtures equal; no ReDoS (worst 0.22 s); r2 evidence clean, test file pure ASCII.
- New **R2-L1 (low, non-blocking, not a regression)**: idstring-valid decorations of unknown ids are read as known ids, no source, not listed: `<hash>+`, `MIT WITH <hash>+`, `<hash>.x`, `x<hash>`, `MIT AND NOASSERTION.`, `MIT AND -NONE`. Fix: strip one trailing `+` in `_unknown_id`; a leaf holding a hash id (search) is unknown. Info: I-7 lower-case or double DocumentRef prefix with NONE (listed, no source); I-8 DocumentRef GPL ids now pattern hits (not flagged unparsed).
- Next: orchestrator decides whether R2-L1 lands now or at U6; otherwise nothing from security for U5.

## 2026-10-24 — reviewer (U5 rework r2)
- Asked: re-check rework round 2 (rulings design-notes l.1127-1147). Verdict: **CHANGES REQUESTED**. Detail: `u5/review-r2.md`.
- Closed: R1-B1, R1-N1, R1-N2. The real-row classification is identical to round 1, row by row, on all six fixtures. The U4 report block is byte-identical to HEAD. r2 controls re-run: 123/108/15, 0 unexpected (`u5/reviewer-r2-controls.txt`).
- R2-B1 (silent): a `+` suffix hides an unknown id. `NOASSERTION+`, `none+`, `LicenseRef-<hash>+`, `MIT WITH NOASSERTION+` give needs, unparsed and unidentified all false. Cause: `_unknown_id` does not strip the `+` that `LEAF_RE` allows.
- R2-B2 (listed, needs=False): `RUN_SPLIT_RE` keeps `:` and `+` inside runs, so `MIT:NOASSERTION`, `MIT+NOASSERTION` and `NOASSERTION:` are not unknown.
- Both items come from the regexes I proposed in R1-B1 (mine to own). Proposed fix: `RUN_SPLIT_RE = [^A-Za-z0-9.-]+` and strip one trailing `+` in `_unknown_id`. Simulated on an in-memory copy: it closes every input, changes no real row, and the 47 existing tests pass (`u5/reviewer-r2-probes.txt`).
- Next: orchestrator ruling (or accept as proposed); then the tester runs RED, the developer runs GREEN, and it comes back for re-review.

## U5 region as it stood at commit d8ffa2d (verbatim from the live doc)

### U5 (PSC-15 classifier; in progress)
- CI for PR #14 run 40046377958: PASS, verify job 32m32s (feeds U11/Q62). Rulings: see design-notes N8 amendment U5.

### 2026-10-24 — architect (U5)
- Recorded orchestrator rulings 1-7 as "N8 amendment, U5" in `docs/evidence/platform-sbom/design-notes.md` l.940-1066 (append only; N8/N8a untouched). It fixes the API (`licence_input`, `is_gpl_id`, `needs_source`, `classify_package`, `classify_document(image, doc, always)`) and lists the first failing tests.
- Precision added: a separate classifier "missing" predicate (`_missing`/report unchanged); `needs` = any() over joined parts; WITH/AND/OR precedence; leaf = run of non-space non-paren chars; tar hard-link size 0, so normalise both listings; anchored `$` regexes only get `fullmatch`.
- Open for the orchestrator: unparseable text holding a hash id (`Public Domain OR <hash>`) still needs no source under the "iff gpl" ruling (it is only listed); not ruled: review R3 (stale controls anchor), the heredoc half of I-2, and the offline_check `drift_work` comment.
- Next: tester RED (classifier table in `fast`; smoke item 6 needs `full`).

### 2026-10-24 — tester (U5 RED)
- RED: `scripts/verify.sh fast`: 900 ran; 30 methods fail, all U5 (138 incl. subtests); 0 errors; sentinel ok (`u5/red-verify-fast.txt`).
- Reach: targets overlaid, verify fast PASS, 900 ran OK, sentinel ok; repo files restored (`u5/target-reach-verify-fast.txt`). Targets for the developer to copy: `u5/target-sbom_check.py`, `target-hardcoded_scan.py`, `target-smoke.sh`, `target-offline_check.sh`.
- Controls: `u5/u5_controls.py`, 66 rows (58 must fail, 8 must pass), 0 unexpected (`u5/red-mutants.txt`; run in the gates image).
  (Other bullets: archive/platform-sbom-part9.md.)

### 2026-10-24 — developer (U5 GREEN)
- Targets copied unchanged (`scripts/sbom_check.py`, `tests/hardcoded_scan.py`, `scripts/smoke.sh`, `scripts/offline_check.sh`); not committed. Rest: archive/platform-sbom-part9.md.
- Verify: `scripts/verify.sh fast` PASS (900 ran, OK skipped=8); `scripts/verify.sh full` PASS (1008 s; 900 + 15 integration). Evidence: `u5/green-verify-fast.txt`, `u5/green-verify-full.txt` (redacted).
- Controls `--base repo`: 66 rows, 58 must-fail, 8 must-pass, 0 unexpected (`u5/green-controls.txt`).

### 2026-10-24 — reviewer (U5)
- CHANGES REQUESTED: B1-B3, nits N1-N8.
- Detail: archive/platform-sbom-part9.md; evidence u5/review.md

### 2026-10-24 — security (U5)
- PASS: L-4/L-5/I-2/L-1 closed; new lows L-1..L-4, L-5a.
- Detail: archive/platform-sbom-part9.md; evidence u5/security.md

### 2026-10-24 — tester (U5 rework r1 RED)
- r1 RED: 11 failing, reach PASS, controls 103 (0 unexpected).
- Ruling 6 correction: my U5 RED note "one mutant is equivalent" was wrong, as review B1 showed; B1's rows killed the joined-text mutant. Under ruling 1 the B1 rows alone no longer kill it (the joined text does not parse and its NOASSERTION run now counts), so `test_each_part_is_classified_alone` pins per-part elections beside a junk part (`MIT OR GPL-2.0-only` + `Public Domain`: no source, unparsed).
- Detail: archive/platform-sbom-part9.md; evidence u5/r1-red-verify-fast.txt, u5/r1-target-reach-verify-fast.txt, u5/r1-red-mutants.txt

### 2026-10-24 — developer (U5 rework r1 GREEN)
- r1 GREEN: verify fast + full PASS 1033 s; controls 0 unexpected.
- Detail: archive/platform-sbom-part9.md; evidence u5/r1-green-verify-fast.txt, u5/r1-green-verify-full.txt, u5/r1-green-controls.txt

### 2026-10-24 — security (U5 rework r1)
- PASS: L-1..L-5a closed, no new finding.
- Detail: archive/platform-sbom-part9.md; evidence u5/security-r1.md

### 2026-10-24 — reviewer (U5 rework r1)
- CHANGES REQUESTED: B1-B3 closed; new R1-B1 leaf charset fail-open; nits R1-N1/N2.
- Detail: archive/platform-sbom-part9.md; evidence u5/review-r1.md

### 2026-10-24 — tester (U5 rework r2 RED)
- r2 RED: 5 failing, reach PASS, controls 123 (0 unexpected).
- Detail: archive/platform-sbom-part9.md; evidence u5/r2-red-verify-fast.txt, u5/r2-target-reach-verify-fast.txt, u5/r2-red-mutants.txt

### 2026-10-24 — developer (U5 rework r2 GREEN)
- r2 GREEN: verify fast + full PASS 969 s.
- Detail: archive/platform-sbom-part9.md; evidence u5/r2-green-verify-fast.txt, u5/r2-green-verify-full.txt, u5/r2-green-controls.txt

### 2026-10-24 — security (U5 rework r2)
- PASS: R1-B1 closed; new low R2-L1.
- Detail: archive/platform-sbom-part9.md; evidence u5/security-r2.md, u5/security-r2-probes.txt

### 2026-10-24 — reviewer (U5 rework r2)
- CHANGES REQUESTED: R1-B1/N1/N2 closed; new R2-B1/R2-B2 `+` suffix and `:`/`+` joiners hide an unknown id.
- Detail: archive/platform-sbom-part9.md; evidence u5/review-r2.md, u5/reviewer-r2-controls.txt, u5/reviewer-r2-probes.txt

### 2026-10-25 — tester (U5 rework r3 RED)
- Asked: round-3 RED for review R2-B1/B2 and security R2-L1 (orchestrator rulings 1-5).
- Tests: `tests/test_sbom_classifier.py` gains `ReworkR3DecoratedIdsTest` (4 methods) and `ReworkR3RunSplitTest` (1), with all the ruled rows. The file stays ASCII.
- RED: `scripts/verify.sh fast`, 926 ran. 3 methods fail (20 incl. subtests): trimmed unknown leaves, a hash anywhere in a leaf, joiners split runs. 0 errors, sentinel ok (`u5/r3-red-verify-fast.txt`). Guards, green on r2: the near-misses and 65-hex rows, and the junk 65-hex row.
- Reach: r3 target overlaid, verify fast PASS, 926 OK; repo restored (`u5/r3-target-reach-verify-fast.txt`). Target: `u5/r3-target-sbom_check.py` (only `scripts/sbom_check.py`). The real-row snapshot is unchanged, checked row by row against r2.
- Controls: `u5/r3_controls.py`, which supersedes r2_controls.py. 135 rows (118 must fail, 17 must pass), 0 unexpected, gates image. Full output: `u5/r3-red-mutants.txt`.
  - Mutants asked for: the round-2 `RUN_SPLIT_RE`, no `+` trim, no trim, and fullmatch instead of search.
  - Also: trailing-only trim, 65 hex counted as a hash, and NONE as a substring of the bare id.
- Flag (rulings 3 vs 4): `HASH_ID_RE.search` alone finds a 64-hex hash inside a 65-hex string. The target uses a separate `HASH_IN_RE` with a `(?![0-9a-f])` lookahead for leaves and runs, so a 65-hex leaf stays ordinary (ruling 4); `HASH_ID_RE` itself is unchanged (the U4 report).
  - Read as "unchanged", the round-0 whole-text `HASH_ID_RE.search` over unparseable text still counts a 65-hex id there. That is pinned as `test_hash_search_in_unparseable_text_unchanged` (`Public Domain <65 hex>` needs source); without it, the "junk hash ignored" mutant survived.
  - Orchestrator: confirm, or rule that junk uses the lookahead too.
- Unparsed is pinned only where the text cannot parse. Decorated idstring leaves (`NOASSERTION+`, `<hash>.x`) are left open.
- Next: developer GREEN (copy the r3 target or equivalent), loop `fast`; then re-review and security re-check.

### 2026-10-24 — developer (U5 rework r3 GREEN)
- Asked: round-3 GREEN for review R2-B1/B2, security R2-L1 (design-notes "Rework round 3"). Only `scripts/sbom_check.py` changed: copied `u5/r3-target-sbom_check.py`; diff against the r2 target read, no refactor (`RUN_SPLIT_RE` = `[^A-Za-z0-9.-]+`, `HASH_IN_RE`, `_unknown_id` trims `.-+` after the DocumentRef strip). `unlicensed_report`/`_missing`/`HASH_ID_RE` untouched.
- `scripts/verify.sh fast`: PASS (`u5/r3-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u5/r3-green-verify-full.txt`). Controls: `u5/r3-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.

### 2026-10-25 — security (U5 rework r3)
- Asked: re-check round 3 (`RUN_SPLIT_RE` `[^A-Za-z0-9.-]+`, `HASH_IN_RE`, trimmed bare id; design-notes "Rework round 3"). Verdict: **PASS** (no critical/high/medium; no new finding). Detail: `u5/security-r3.md`; probes `u5/security-r3-probes.txt` (script `u5/security_r3_probes.py`).
- Closed: R2-L1 (`<hash>+`, `MIT WITH <hash>+`, `<hash>.x`, `x<hash>`, `NOASSERTION.`, `NOASSERTION+`, `-NONE`: need source, unidentified; 65 hex stays ordinary) and I-7 (lower-case/double/empty DocumentRef prefix with NONE, `NONE:`). Review R2-B1/B2 inputs (`MIT:NOASSERTION`, `MIT+NOASSERTION`, `DocumentRef-x:NONE+`) need source.
- Not weaker than r2: 150000 random expressions, 0 regressions, 0 lost listings; 1015 real rows unchanged; `unlicensed_report` and `HASH_ID_RE` identical to HEAD, six fixtures equal; no ReDoS (worst 0.14 s); r3 evidence clean.
- Info only: I-9 `NONE.NONE`, pinned `MIT-NOASSERTION`/`LicenseRef-NONE`, uppercase-hex hash (U4 I-4) stay ordinary. Next: nothing from security for U5.

### 2026-10-25 — reviewer (U5 rework r3)
- Asked: re-check rework round 3 (rulings design-notes l.1149-1171). Verdict: **APPROVED**. Detail: `u5/review-r3.md`.
- Closed: R2-B1 (`+` and `.`/`-` trim, hash anywhere in a leaf), R2-B2 (`:`/`+` split runs), security R2-L1. Every round-2 input now needs source and is unidentified. The pinned near-misses are unchanged.
- Real rows: `classify_document` is identical row by row to r1 and to r2 on all six fixtures. The U4 report block, `MISSING` and `HASH_ID_RE` are byte-identical to HEAD. r3 controls re-run: 135/118/17, 0 unexpected (`u5/reviewer-r3-controls.txt`). Host classifier tests: 52 OK.
- Not blocking: I-r3-1. Opaque idstrings with a joined keyword stay ordinary: `NOASSERTION.NONE`, `NOASSERTION-2.0`, `LicenseRef-NOASSERTION`. This is the same shape as ruled-ordinary `MIT-NOASSERTION`. There is no caller until U9 and no real row has the shape. If wanted, it becomes U6's first test row.
- I-r3-2: upper-hex hash ids stay ordinary (U4 I-4 carried).
- Next: orchestrator commit gate (`verify.sh full`, diff read).

### 2026-10-25 — orchestrator (U5 commit gate)
- Rework rounds used: 3 of 5 (r1 B1-B3 + security L-1..L-5a; r2 R1-B1 leaf charset; r3 R2-B1/B2 `+`/`:` joiners and hash anywhere). Rulings: design-notes N8 amendment U5 l.940-1171.
- Review APPROVED (r3; I-r3-1 keyword joined by `.`/`-` inside a valid id is U6's first test row, ruled boundary), security PASS (r3; no new finding; U4 I-4 upper-hex hash carried, generator digest bump = re-review trigger).
- Orchestrator verify full PASS 999 s (926 unit + 15 integration, sentinel ok; `u5/orchestrator-verify-full.txt`). Diff read: sbom_check.py (4 rounds), smoke.sh, offline_check.sh, hardcoded_scan.py, tests. Sentinel untouched.
- Also rides: Q69/Q70 records (analyst), requirements status line (N7), handoff splits (archive part1/3/5/6/8/9), u4/u4b controls marked superseded.
- No CHANGELOG line for U5 (no user-visible behaviour until U9); the smoke step now walks volumes (L-1). Commit APPROVED. Next: U6 (`hosts` + `exempt`, jna/javassist, security-reviewed; first test row I-r3-1).

## U6 region as it stood at commit 66781a9 (verbatim from the live doc)

### U6 (hosts + exempt; in progress)
Rulings: design-notes N10 amendment U6.

### 2026-10-25 — analyst (U6)
- Asked: PSC-22 wording for the generator-digest trigger and U5's landing; U6 `exempt`/`hosts` criteria; status line. Only `docs/requirements.md` changed (all marked "Amended 2026-10-25, analyst, U6").
- Already recorded, confirmed by quote: PSC-22 "A new syft image digest in `docker-compose.sbom.yml` triggers a PSC-22 re-review by security" (U4 R1). Added the reason (exact, case-sensitive `LicenseRef-<64 hex>`; I-r3-2) and a pointer saying U5 landed (N8 amendment U5).
- Not there before; added as PSC-22 bullets (no new PSC number): exactly three keys; a versioned purl, with no duplicate image+purl; an entry not catalogued at that exact version fails the bundle (pure check at U6, wired at U9); the reason gives the text read and where, the artifact's SHA-256 and, for an OR correction, the elected branch; `reviewed` is `^security \d{4}-\d{2}-\d{2}$`, written only after security's audit. On `hosts`: lower-case, no wildcard; U8 refuses any unlisted host on every hop, failing closed (Q61); every lock host is listed. First test row: I-r3-1. PSC-15 gained a pointer: an exemption means a PSC-22 `exempt` entry.
- Status line: "U0-U5 committed (U5 d8ffa2d, not yet pushed) ... U6 in progress". In the table, PSC-15's row now names U5.
- OPEN (for the orchestrator): "`always` beats `exempt`" conflicts with the recorded text. PSC-22 bullet 1 and its "`always` additions" ("Each needs a `sources/` entry (U7) or an exemption whose reason security has reviewed (U6)"), the libldap/libsasl2 bullet, and N10's human-call GCC fallback ("one `exempt` entry per versioned purl and image") all let a reviewed exemption clear an `always` package. Not written as a criterion; the requirements mark it open. Rule one of these: (a) `always` beats the classifier only (the recorded reading); (b) `exempt` can never clear `always`, which needs PSC-22 amended and closes off the GCC fallback.
- Interpretation to confirm: I-r3-1's "ruled boundary" was written as "the cases stay ordinary, as `MIT-NOASSERTION` does".
- Not changed (outside the brief): the status table's PSC-26 row still says PENDING/U4b, although U4b is committed as c300d88.
- Next: architect (N10 amendment U6, not yet in design-notes when I read it), then tester RED.
- Rulings recorded (orchestrator, 2026-10-25) in `docs/requirements.md` PSC-22: (1) option (a). `always` overrides only the classifier, and a reviewed exact-purl `exempt` entry still clears the package; the U9 index lists such rows as "always, cleared by exemption <reviewed>" (the open marker is closed). (2) I-r3-1 closes the boundary. If the bare id is not `licenseref-`, a `.`/`-` segment of NONE/NOASSERTION (case-fold) makes it unknown. `MIT-NOASSERTION`'s round-3 pin flips; the `LicenseRef-NONE` forms stay ordinary. (3) The PSC-26 row now reads MET, U4b (c300d88).

### 2026-10-25 — architect (U6)
- Wrote design-notes "N10 amendment, U6" (l.1530-1731; it ends before N11), with a dated correction for `always`+`exempt` (l.1691 on).
- API: `exempt_matches(image, doc, exempt) -> (flagged, problems)`. The match drops the purl's `?`/`#` and compares the string exactly; an entry with no match, or one that is not a versioned purl, is a problem. `classify_document(..., exempt=())`: an exempt row gets `needs=False`, also when `always` matches (correction).
- `hosts`: the nine N4 names (item 2). Schema test (item 3) maps fixture `neo4j.pkgs.tsv` to image `ke-neo4j` (the reverse of `U4B_POLICY_NAME`). The lock-host check moves to U7.
- Entries: `pkg:maven/com.sun.jna/jna@5.15.0` and `pkg:maven/org.javassist/javassist@3.30.2-GA`. `reviewed` is set only after a separate security review of the entries, recorded in `u6/security-exempt.md`.
- I-r3-1 also flips `see NONE.txt here` (run `NONE.txt`) to needs source; to be confirmed. Simulated real-row effect: 1015 rows, 0 changed.
- Next: orchestrator confirms the `see NONE.txt here` flip; tester RED in item order (a)-(e); loop `fast`, then full before the gate.

### 2026-10-25 — security (U6 exempt review)
- Asked: review the two `ke-neo4j` `exempt` entries (jna 5.15.0, javassist 3.30.2-GA) and the nine `hosts`, between RED and GREEN. Verdict: **exempt review PASS** for both entries; hosts PASS. Detail: `u6/security-exempt.md`; probes `u6/security-exempt-probes.txt` (jars `docker cp`'d from `ke-neo4j:bundle-c300d881cd94`, nothing run).
- **Developer writes `"reviewed": "security 2026-10-25"` on both entries.** Reason texts in `u6/target-source-policy.json` are accurate as written.
- jna: sha256 matches; `META-INF/LICENSE` is a genuine OR ("LGPL 2.1 or later, or ... Apache 2.0. You can freely decide"); all 28 `libjnidispatch` builds have no GPL strings and are JNA's own (dual) code plus libffi (MIT-style). javassist: sha256 matches; pom `<licenses>` MPL 1.1 / LGPL 2.1 / Apache 2.0 (any one, Maven), no shaded or native code. Neo4j's own LICENSES.txt/NOTICE.txt list both under Apache-2.0.
- Hosts: all public source hosts, fetch-time only (not runtime egress). Info I-1: the GitHub hosts are multi-tenant, so provenance rests on N4's hop rules and U7's per-file sha256 lock.
- L-1 (low, non-blocking, not an exempt issue): libffi's MIT notice is absent from Neo4j's NOTICE/LICENSES and from the jar; route to ke-neo4j NOTICE work. I-2: a base-digest bump re-triggers this review.
- Next: developer GREEN with the value above; security's U6 gate audit on the integrated diff.

### 2026-10-25 — tester (U6 RED)
- Asked: the U6 RED per orchestrator rulings 1-5 (with the correction that exempt clears `always` too), and the "N10 amendment, U6" (l.1530 on).
- Tests:
  - `tests/test_sbom_obligations.py` PolicyU6SchemaTest (4 methods) holds the schema oracle, the nine N4 hosts, the jna/javassist entries, and the oracle's own bad-shape controls.
  - `tests/test_sbom_classifier.py`: U6ExemptMatchesTest (2), U6ClassifyDocumentExemptTest (2, real rows of all six images), U6SegmentRuleTest (2).
  - Fixture mapping: `ke-neo4j` reads `neo4j.pkgs.tsv` (the reverse of `U4B_POLICY_NAME`).
- Pins flipped by ruling 5, recorded in the test file: `MIT-NOASSERTION` and `see NONE.txt here` (in two places) are now unknown.
- RED: `scripts/verify.sh fast`, 936 ran. 9 methods fail (19 incl. subtests), 0 errors, sentinel ok (`u6/red-verify-fast.txt`). The oracle's bad-shapes test is green, as a guard.
- Reach: u6 targets overlaid (checker + policy), verify fast PASS, 936 OK; repo restored (`u6/target-reach-verify-fast.txt`). Targets: `u6/target-sbom_check.py`, `u6/target-source-policy.json`. The target `reviewed` value equals security's (`security 2026-10-25`). The real-row snapshot is unchanged.
- Controls: `u6/u6_controls.py`, 44 rows (40 must fail, 4 must pass), 0 unexpected, gates image. Full output: `u6/red-mutants.txt`.
  - Checker mutants: version ignored or prefix-matched, case fold, void problem silenced, other images' entries applied, `always` beating `exempt`, exempt not clearing needs, `always` not forcing needs, and the segment rule dropped, inside LicenseRef, `-` only, case-sensitive, or on leaves only.
  - Policy mutants: a host with a scheme, path or wildcard; a tenth or a missing host; a fourth key; `reviewed` loosened or impossible; jna bumped; a reason without the sha256; javassist dropped; jaxb-api or openjdk exempted; image `neo4j`.
  - One equivalent mutant, not a row: accepting a qualifier-bearing entry. It never equals a stripped purl, so it still matches nothing and is a problem.
- Followed over the architect's text where they differ:
  - both-match gives `needs: False` (your correction; amendment item 1 still says True);
  - literal purl compare, and an entry with qualifiers is a problem (amendment item 1; the brief said qualifiers are ignored).
- Not pinned: the exact problem message texts.
- Next: developer GREEN, loop `fast`, `full` before the gate (scripts/ touched).

### 2026-10-25 — developer (U6 GREEN)
- Asked: U6 GREEN (`hosts` + `exempt` in `docker/source-policy.json`, `exempt_matches`, `classify_document(..., exempt=())`, I-r3-1 segment rule). Copied `u6/target-sbom_check.py` -> `scripts/sbom_check.py` and `u6/target-source-policy.json` -> `docker/source-policy.json`; diff against HEAD read, no refactor. `always` entries unchanged; both exempt entries carry `reviewed: "security 2026-10-25"`; `unlicensed_report`/`_missing` untouched; row matched by both gets always True, exempt True, needs False.
- `scripts/verify.sh fast`: PASS (`u6/green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u6/green-verify-full.txt`). Controls: `u6/green-controls.txt`.
- Next: reviewer and security. Nothing committed.

### 2026-10-25 — reviewer (U6)
- Asked: review the U6 diff (`hosts`, `exempt`, `exempt_matches`, `classify_document(..., exempt=())`, segment rule) against N10 amendment U6 and its correction (l.1691). Verdict: **APPROVED**. Detail: `u6/review.md`.
- Conformant:
  - Match: exact string compare after stripping qualifiers/subpath on the package side only; no case fold; a bump or a non-versioned entry is a problem (void).
  - Flags: exempt clears needs, also under `always` (both flags set); `always` alone forces needs; the default adds `exempt: False` only.
  - Policy: nine hosts; jna/javassist entries with `reviewed: security 2026-10-25`.
  - `unlicensed_report` is untouched.
- Segment rule: only adds unknowns. 200k random expressions against U5: 0 lost needs, 0 lost listings.
- Real rows: identical row by row to U5 with `exempt=()`. With the committed `exempt`, only ke-neo4j jna and javassist change (`needs`, `exempt`).
- Controls re-run in the gates image: 44/40/4, 0 unexpected (`u6/reviewer-controls.txt`).
- Nits:
  - N1 (U9 precondition): a duplicate SPDXID shared with an exempt package clears it too. `validate` refuses such docs; U9's `index` must validate first. Carry it as a U9 test row.
  - N2: the real-row test still asserts "never always+exempt" (withdrawn bullet).
  - N3: a future `reviewed` date is accepted.
  - N4: there are 29 bad shapes, not 31.
  - N5: no test has a `#subpath` package purl.
- Next: security's U6 gate audit; orchestrator commit gate.

### 2026-10-25 — security (U6)
- Asked: gate audit of U6 (`hosts`, `exempt`, `exempt_matches`, `_purl_base`, `classify_document(..., exempt)`, segment rule). Verdict: **PASS** (no critical/high/medium). Detail: `u6/security.md`; probes `u6/security-probes.txt` (script `u6/security_probes.py`).
- `exempt_matches` is exact: only jna's purl plus qualifiers/subpath clears it; version prefix/suffix, percent-encoding, case, `@` in namespace, other type, whitespace, NUL do not (each "matches nothing"). Schema oracle rejects the tester's 29 shapes and 24 of my 26 more. Segment rule: 150000 random expressions, 0 weaker than U5; ReDoS worst 0.52 s; real rows change only for jna and javassist (needs False, exempt True). `unlicensed_report` identical. Reasons equal what I reviewed; evidence clean.
- L-1 (low, for U9 or now): an entry clears every package at its purl (`[jna, jna?type=jar]` both cleared, no problem); report >1 match, and compare the SBOM checksum at U9. L-2 (low, U9): rows keyed by SPDXID, so a duplicate of an exempted SPDXID is cleared; U9's `index` must `validate()` first (finish already refuses duplicates).
- Info: I-1 future `reviewed` date accepted; I-2 the host regex accepts `evil.github.com`/punycode (the exact-set test rejects them); I-3 carried from the entry review.
- Next: orchestrator commit gate.

### 2026-10-25 — orchestrator (U6 commit gate)
- Rework rounds used: 0 of 5. Review APPROVED (nits N1-N5), security PASS (lows L-1, L-2), security exempt review PASS (`u6/security-exempt.md`; `reviewed: security 2026-10-25`).
- Orchestrator verify full PASS 962 s (936 unit + 15 integration, sentinel ok; `u6/orchestrator-verify-full.txt`). Diff read: source-policy.json (hosts, exempt), sbom_check.py (exempt_matches, classify_document exempt, segment rule), tests. Sentinel untouched.
- Rulings recorded here: (a) `always` overrides only the classifier; an exact-version `exempt` still clears (PSC-22 amended; GCC fallback stays open); (b) libffi notice (security exempt L-1) goes to the ke-neo4j NOTICE section at U9; (c) a base-image digest bump re-triggers the exempt review (security I-2).
- Carried as first test rows: U7: reviewer N3 / security I-1 future `reviewed` date rejected; N5 a `#subpath` purl row. U9: security L-1 an exempt entry matching more than one package is a problem; security L-2 / reviewer N1 `index` runs `validate` before `classify_document`; reviewer N2 drop the "no row both always and exempt" assertion when the first such entry lands; `index` lists "always, cleared by exemption <reviewed>".
- Commit APPROVED. Next: U7 (source lock: `docker/sources.lock.json`, `scripts/sources_lock.sh`, `maven` kind for jaxb-api, `deb` gcc-12/gcc-14 per Q69; security second fetch for provenance).

## U5/U6 live-doc summaries as they stood 2026-10-26

### U5 (PSC-15 classifier; committed d8ffa2d; detail: archive/platform-sbom-part9.md)
- Outcome: pure classifier functions in `scripts/sbom_check.py`, fail-closed rules (N8 amendment U5, design-notes l.940-1171); also escaping, tree size, scanner continuation lines and the smoke prune.
- Rework rounds 3 of 5: r1 B1-B3 + security lows, r2 leaf charset, r3 joiners/hash anywhere.
- Review APPROVED r3, security PASS r3, orchestrator verify full PASS 999 s. CI run 40046377958 PASS 32m32s (feeds U11/Q62).
- Carried to U6: I-r3-1 segment rule (first test row); security I-4 upper-hex hash (generator digest bump = re-review).
- Watch at U11: review N8 smoke flake risk.
- No CHANGELOG line until U9.

### U6 (hosts + exempt; committed 66781a9; detail: archive/platform-sbom-part9.md)
- Outcome: `hosts` holds the nine N4 hosts; `exempt` holds jna and javassist (reviewed `security 2026-10-25`); `exempt_matches`, `classify_document` exempt and the segment rule landed. PSC-22 amended: `always` overrides only the classifier, and an exact-version exempt entry still clears.
- Rework 0 of 5; review APPROVED, security PASS + exempt review PASS, orchestrator verify full PASS 962 s.
- Rulings: libffi notice goes to the ke-neo4j NOTICE section at U9; a base-image digest bump re-triggers the exempt review.
- First test rows carried to U7: a future `reviewed` date is rejected; a `#subpath` purl row.
- First test rows carried to U9: an exempt entry matching more than one package is a problem; `index` runs `validate` first.
- Also U9: drop the "no row both always and exempt" assertion when the first such entry lands; list "always, cleared by exemption".

