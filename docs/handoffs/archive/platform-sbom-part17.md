# platform-sbom handoff archive, part 17 (U9c: criteria, design, RED, GREEN)

Moved from docs/handoffs/platform-sbom.md by the orchestrator on 2026-10-30 before the U9c review. Nothing is rewritten.

## 2026-10-30 — analyst (U9c criteria, A81 option 3)
- Asked: testable criteria for U9c (Q81 ruled A81 = option 3). Wrote requirements.md "U9c precision" U9c-1..U9c-9 (l.4733-4933, under PSC-24 after U9 precision); pointers at U8-3 (l.4131), U8-8 (l.4250), U9-5 (l.4512), U9-6 (l.4545); status line l.3306. No PS-3.x line names Q81, so none changed.
- Criteria: U9c-1 sample plan (apk = distfiles files only, never empty, other kinds and full unchanged); U9c-2 record/sources-check (partial apk accepted in sample; pre-U9c sample, partial full and extra GitLab file refused); U9c-3 APKBUILD check not run for apk in sample, printed, no fail-open in full; U9c-4 partial row (no `path` on unfetched files, not `shipped`, never in full, notices wording to security); U9c-5 expected numbers appended before any run; U9c-6 hosts/lock/CLAUDE.md unchanged, README + U8-8 wording; U9c-7 proof with GitLab unreachable (fake, real hop lines, closure probe, CI extract); U9c-8 out of scope; U9c-9 tests/gate/evidence (`u9c/`).
- Facts (lock 12eebc8c, read-only): every apk key has 1-2 distfiles files (21 total). Key unchanged: sample 7 keys, 10 files, 136,553,898 B (was 25 / 136,571,547; GitLab part 17,649 B); u9: 6 shipped, 1 partial, 176 not-shipped. Full unchanged (876 rows / 716 files / 1,180,936,586 B).
- For the architect (not criteria):
  - QA-1: does the apk sample key change (today 2 plain files, 15,957 B; e.g. pax-utils@1.3.8-r2 has one 123,556 B tarball)? A63's "smallest entry" rule for apk is touched either way.
  - QA-2: where the partial-row rule lives (`fetch_plan`-derived in `source_index`?) and its encoding (a status value or a flag).
  - QA-3: skip or replace the APKBUILD name check in the sample; the printed line.
  - QA-4: the Q81 mitigation (a recorded GitLab-route fetch before each operator bundle, or the operator full fetch alone); which upstream URL the partial row's notices cell gives.
  - QA-5: how distfiles files are selected (lock URL host or the upstream `from`), given U8-4's "hosts from the policy, never a literal"; whether A34 applies (N15).
- Next: architect (QA-1..QA-5), then the orchestrator's plan gate; the orchestrator writes the U9c-5 expected sections before any real run.

## 2026-10-30 — architect (U9c design, A81)
- Wrote design-notes "N9 amendment, U9c" (l.5005-5292, items 1-17) and ADR-KE-016 "Amended U9c". QA-1 key unchanged (A63 reads as before; alt rule picks the same key); QA-2 `status` "partial", per-file `path`, full refuses; QA-3 skip + one printed line, keyed on set+kind only; QA-4 no extra fetch, row URL = lock URL of the first unfetched file (APKBUILD); QA-5 `APK_DISTFILES_HOST` checker constant shared with `KIND_HOSTS`, no policy change.
- For the orchestrator: O-19 (U9c-2 (c) line names the file, not the key) and O-20 (the existing APKBUILD row runs in sample, so it gains `which="full"`; U9c-3's "unedited" cannot hold). Gate `full`, A34 no.
- Next: plan gate; U9c sections of u8/ and u9/expected.md (item 9 numbers) before any real run; tester RED from item 14 (first: sample plan rows, the skip line).

## 2026-10-30 — tester (U9c RED)
- Asked: failing tests for U9c (A81) per design item 14, plus the named re-pins; no production file touched (sha256 unchanged, `u9c/controls.txt`).
- New module `tests/test_sources_sample_apk.py` (15 rows). Red, each for its ruled reason: `test_sample_plan_apk_is_distfiles_only`, `test_sample_plan_refuses_an_apk_key_without_distfiles`, `test_sample_fetch_skips_the_apkbuild_check_only_for_apk`, `test_sample_fetch_passes_with_gitlab_unreachable`, `test_sample_record_accepts_the_partial_apk_entry`, `test_sample_index_marks_the_partial_apk_key`, `test_full_index_refuses_a_partial_key`, `test_index_refuses_a_partial_key_of_another_kind`, `test_notices_partial_row`, `test_partial_files_without_path_are_not_on_disk`. Green controls, each shown by a mutation: `test_sample_plan_other_kinds_unchanged`, `test_full_plan_unchanged`, `test_full_fetch_apkbuild_mismatch_still_fails` (no fail-open, incl. a full plan without the APKBUILD), `test_sample_fetch_dsc_check_still_runs`, `test_full_fetch_fails_with_gitlab_unreachable`.
- Rows U9c-2 (a), (b) added in `FetchRecordProblemsTest.test_bundle_refuses_a_mismatched_fetch_record`; (a)-(c) in `SourcesCheckCliTest`'s (c names the file, O-21); (b) green (full is unchanged).
- Re-pins R1-R5 as named (`plan_of` + `sample_files` mirror; `test_fetch_plan_rows`; APKBUILD row `which="full"`; `test_sample_bundle_ships_exactly_the_sample`; `test_notices_source_code_section_rows`). **R6, not in the brief:** `test_source_fetch_stops_at_the_run_deadline` used the sample plan for its full subtests, so after R1 its (full, 10801) subtest could never pass; it now takes `plan_of(b, ARCH, which)` per subtest, with no assertion changed (A81/U9c-1). Shown in attempt 1.
- Note for the orchestrator: "the other 1328 green" does not hold. 22 unedited tests that read the re-pinned helpers are red at RED (design item 14 says "transitively"): 3 in test_sources_fetch, 13 in test_source_index, 6 in test_bundle_fetch, all listed in controls.txt. The candidate run [1] turns all of them green (373 tests; the 2 failures there come from the copy having no `.git`).
- Gate: `scripts/verify.sh fast` → Ran 1343, failures=48 (38 tests), skipped=8, rc 1 (expected RED). Evidence `docs/evidence/platform-sbom/u9c/red-verify-fast.txt` (attempt 1: `red-verify-fast-attempt1.txt`), `u9c/controls.txt` (candidate + 16 mutations, all as expected).
- For the developer: the interface pins are in the new module's docstring (items 2, 3, 5, 6, 7). The candidate in controls.txt is control-only and not binding. Gate for GREEN is `verify full` (scripts/, client, checker).

## 2026-10-30 — developer (U9c GREEN)
- Changed `scripts/sbom_check.py` (`APK_DISTFILES_HOST`, `KIND_HOSTS`, `fetch_plan` sample apk filter + ValueError, `source_index` per-file partial status + 2 refusals, `source_section` partial row) and `scripts/sources_fetch.py` (`_name_check(..., which)` skip line, `_run` ValueError -> stage lock, docstring). No test edited.
- `verify fast` Ran 1343 OK skipped=8 (the 38 reds green); `verify full` PASS 1358 s. Sample: 10 files, 136553898 B, 7 components, no gitlab hop, skip line once. GitLab probe 200 before and after, so not the closure proof.
- Evidence: `docs/evidence/platform-sbom/u9c/green-verify-fast.txt`, `green-verify-full.txt`, `sample-run.txt`. Not staged. Next: reviewer + security.
