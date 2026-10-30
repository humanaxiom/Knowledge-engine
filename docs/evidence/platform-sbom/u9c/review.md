# U9c review (reviewer, 2026-10-30)

Plan item platform-sbom, unit U9c (A81 = Q81 option 3). Merge-blocking review of the integrated diff.

**Verdict: APPROVED** (no blocking finding; 4 optional nits).

## What was read
- Handoff `docs/handoffs/platform-sbom.md` U9c block; `docs/handoffs/archive/platform-sbom-part17.md` (analyst, architect, tester, developer).
- `docs/requirements.md` "U9c precision" U9c-1..U9c-9 (l.4733-4940) with the O-21 amendments to U9c-2 (c) and U9c-3.
- `docs/evidence/platform-sbom/design-notes.md` "N9 amendment, U9c" items 1-17 (l.5005-5299), O-19/O-20/O-21.
- `u9/expected.md` "U9c", `u8/expected.md` "U9c amendment".
- `u9c/` evidence: red-verify-fast.txt, controls.txt (candidate [1] + mutations [2]..[17]), green-verify-fast.txt, green-verify-full.txt, sample-run.txt.
- The diff: `git diff HEAD -- scripts/sbom_check.py scripts/sources_fetch.py tests/test_sources_fetch.py tests/test_source_index.py` and the untracked `tests/test_sources_sample_apk.py` (read in full).

## GREEN changed no test (hash check, recomputed 2026-10-30)
| File | controls.txt (end of RED) | now |
|---|---|---|
| tests/test_sources_sample_apk.py | 4681406c...d3e3 | 4681406c...d3e3 |
| tests/test_sources_fetch.py | 44170d73...5821 | 44170d73...5821 |
| tests/test_source_index.py | eb6b6322...d68a | eb6b6322...d68a |
| test_bundle_sources, test_offline_check, test_bundle_fetch, test_offline_bundle, test_sources_lock, test_sources_lock_committed, test_sbom_obligations, test_sbom_bundle, fake_docker | as listed l.14-22 | all equal |
| docker/sources.lock.json, docker/source-policy.json, bundle.sh, bundle_fetch.sh, offline_check.sh, sources_resolve.py, README.md, CLAUDE.md, NOTICE.md | as listed | all equal |

Only `scripts/sbom_check.py` (fa987723...) and `scripts/sources_fetch.py` (6fa13085...) differ from RED; both were last written (20:41 local) before green-verify-fast (20:58) and green-verify-full (21:21), so the green runs cover the current production text.

## Design conformance, item by item
| Item | Code | Verdict |
|---|---|---|
| 2 `APK_DISTFILES_HOST`, `KIND_HOSTS` refactor | sbom_check.py:1186-1192: both constants defined above `KIND_HOSTS`, `APK_API_HOST` moved up (old definition at the U7c comment removed), `KIND_HOSTS["apk"] = (APK_API_HOST, APK_DISTFILES_HOST)`. Pure refactor: lock-rule tests (`test_sources_lock.py`, `test_sources_lock_committed.py`) unedited and green. | conforms |
| 2 / U8-4 no literal in the fetch client | `sources_fetch.py` holds no host literal (grep: only the word "distfiles" in the docstring); `allow` is still the policy's `hosts`; the filter only removes rows. | conforms |
| 3 `fetch_plan` | sbom_check.py:1739-1760: signature unchanged; sample apk keys filtered by `_split(url).hostname == APK_DISTFILES_HOST` in file order; ValueError text exactly as design item 3; the `full` path is the old comprehension. Docstrings of `sample_keys` and `fetch_plan` cite A81. | conforms |
| 3 client stage lock | sources_fetch.py:229-232: `except ValueError -> Fail("lock", str(exc)) from None`; pinned by the zero-request row and mutation [9]. `sources-check` (l.2436) and `index` reach the same ValueError only through their existing catch-alls (fail closed), as designed. | conforms |
| 4 record / sources-check, no code | No change to `_write_record`, `fetch_record_problems`, `listing_problems`. U9c-2 (a)/(b) give the "lists N files" line; (c) gives `<sha256>: not in the lock's plan` per O-21. | conforms |
| 5 skip, no fail-open | sources_fetch.py:158-166: `if kind == "apk" and which == "sample": print(...); return` is the first statement after `kind`; it reads only `which` and the key's kind, never the plan, the listing or `--out`. `_run` passes `args.which` (l.263). Full path unchanged. Module docstring amended. | conforms (U9c-3) |
| 6 `source_index` per-file status | sbom_check.py:2192, 2211-2226: `planned` per (key, name); `status` shipped/partial/not-shipped by all/any; `path` per file flag; refusals `index: <key> is partial in a full bundle` and `index: <key> is partial, and only the apk sample key may be (A81)` (text exact). No new field. U9-6 left to stage 5 `listing_problems` (no new code), as designed. | conforms |
| 7 `source_section` partial row | sbom_check.py:2297-2311: key, images and URL checked as the other rows (`markdown=False` for key and URL); URL = first file with `path` null; refusals for a non-sample index and for no fetched / no unfetched file; row text exact to design item 7; never carries the shipped claim ("source in sources/"); banner order unchanged. | conforms |
| 13 security properties | No new host, URL or request; the plan only shrinks; a partial key never passes a full bundle (index and notices both refuse). | conforms (security reviews the row wording separately) |
| Spans | Build-time tool, not an agent step (N3; design header "No spans"). | n/a |

## Test adequacy
- Every criterion's named proof exists: U9c-1 (`test_sample_plan_apk_is_distfiles_only`, `test_sample_plan_other_kinds_unchanged`, `test_full_plan_unchanged`, `test_sample_plan_refuses_an_apk_key_without_distfiles`); U9c-2 (rows (a)-(c) in both `test_bundle_refuses_a_mismatched_fetch_record` methods, `test_sample_record_accepts_the_partial_apk_entry`); U9c-3 (`test_sample_fetch_skips_the_apkbuild_check_only_for_apk`, `test_full_fetch_apkbuild_mismatch_still_fails` incl. the no-fail-open plan-without-APKBUILD case, `test_sample_fetch_dsc_check_still_runs`); U9c-4 (`test_sample_index_marks_the_partial_apk_key`, `test_partial_files_without_path_are_not_on_disk`, `test_full_index_refuses_a_partial_key`, `test_index_refuses_a_partial_key_of_another_kind`, `test_notices_partial_row`, R4); U9c-7 fast (`test_sample_fetch_passes_with_gitlab_unreachable`, `test_full_fetch_fails_with_gitlab_unreachable`).
- Each green-from-the-start pin has a mutation that turns it red: [2] full filtered too, [3] every kind filtered, [5] skip on kind only, [6] skip for .dsc too, [8] skip on APKBUILD absence (the fail-open mutation). The red rows' distinct behaviours each have one too: [4] no refusal, [7] silent skip, [9] no stage-lock, [10] full partial allowed, [11] other-kind partial allowed, [12] path per sha256, [13] shipped claim, [14] wrong URL, [15] notices full not refused, [16] partial reported shipped, [17] no empty-side refusal. 16 mutations, each failing exactly its own pins.
- Re-pins R1-R6 match the diff and nothing else: R1 `plan_of` + new mirror `sample_files` (never calls `fetch_plan`); R2 `want` filtered; R3 adds `which="full"` and a comment only (O-20/O-21: every case and assertion kept); R4 shipped = sample minus APK_KEY, partial = {APK_KEY}, path per planned (key, name), shared-sha256 subtest kept; R5 partial branch in `want`, the no-claim loop covers partial rows, plus one added assertion (partial rows in a sample only), disclosed at controls.txt l.42-44; R6 `plan` moved into the loop as `plan_of(b, ARCH, which)`, no assertion changed, reason recorded (the (full, 10801) subtest could not pass after R1 under any implementation). Additions inside existing tests (rows (a)-(c), `pre_u9c_sample_record`, `PARTIAL_CELL`) are rows, not edits to existing expectations.
- No test name holds a count. No test reads docs/evidence (grep). Counts in bodies (7/10/10/136553898; 183/876/716/1180936586) are the U9c-1 / U9c-5 mandated pins against the committed lock.
- Transitive reds explained: 22 unedited tests reading the re-pinned helpers (controls.txt l.114-129), all green in green-verify-fast (Ran 1343, OK, skipped=8).
- Full-set behaviour unchanged: `test_full_plan_unchanged` green, and mutation [2] shows it bites; `test_fetch_plan_rows` full subtest untouched; lock-rule tests green unedited.

## Evidence checked
- red-verify-fast.txt: Ran 1343, FAILED (failures=48, skipped=8) = 38 tests, each for its ruled reason (controls.txt l.87-129).
- green-verify-fast.txt: Ran 1343, OK (skipped=8), `== verify fast: PASS ==`, rc 0.
- green-verify-full.txt: unit Ran 1343 OK (skipped=8), integration Ran 15 OK (skipped=5), offline_check PASS, `== verify full: PASS (1358s) ==`, rc 0; 0 `hops=` lines naming gitlab.alpinelinux.org.
- sample-run.txt equals `u9/expected.md` "U9c" and `u8/expected.md` "U9c amendment": 10 files, 136553898 B, 7 components; the apk rows `protocols-6.4` 3144 B and `services-6.4` 12813 B on distfiles only; the skip line once, after the key's files; `sources-check: ok 10 files, 136553898 bytes, 7 components (sample, amd64)`. Index counts 6/1/176 are not printed by verify; tests assert the rule at fixture level and the bundle step's `index` passed.
- Closure (U9c-7): GitLab probes answered 200 before and after the developer's run, so that run is not the closure proof; the proof is the fake-transport rows (sample: zero GitLab calls, rc 0; full: one attempt, the U8-4 line, no retry). The orchestrator's gate run still owes `u9c/gitlab-probe.txt` (design items 11, 16 R7) and the CI fetch extract after a push (R8).

## Findings

### Blocking
None.

### Nits (optional)
- **N-1 (docstring gap; nit, not blocking).** scripts/sbom_check.py:2153-2156 (`source_index` docstring) and :69-72 (header `index`/`notices` paragraph) do not mention the `partial` status. Not blocking: design item 10 assigns the developer only the docstrings of items 3 and 5 (done); neither docstring ever listed the earlier two status values, so nothing in the file now says something false; the rule is pinned by tests and recorded in U9c-4 and design item 6. It is a discoverability gap. Fix: one sentence in `source_index`'s docstring ("status is `shipped` (every file planned), `partial` (some; only the apk sample key of a sample, A81) or `not-shipped`; a file's `path` is set iff its (key, name) is planned") and "a partial apk row in a sample" in the header's `notices` sentence. Developer, if re-dispatched before commit; otherwise carry to U10.
- **N-2 (cosmetic).** scripts/sources_fetch.py:24-26: the amended docstring sentence was not reflowed (one 102-character line among ~73-character lines). Fix: reflow the paragraph.
- **N-3 (test, optional).** No row shows `sources-check` and `index` failing closed (one FAIL line, exit 1) on a lock whose apk sample key has no distfiles file. Design item 3 relies on the existing catch-alls (sbom_check.py:2453-2454 and `source_index`'s), which are generic and already exercised for other exceptions, and the case is unreachable in practice because the fetch refuses first at stage lock. Fix if wanted: one subtest per CLI using `apk_without_distfiles()`.
- **N-4 (handoff text).** docs/handoffs/platform-sbom.md:157 says the new module has "10 rows"; it has 15 (10 red, 5 green controls), as archive part 17 l.24 and controls.txt l.69 say. Fix (orchestrator's line): "15 rows (10 red, 5 controls)".

## Carried (untouched by U9c)
| Item | Origin | State | Why untouched |
|---|---|---|---|
| I-15 / N-8 (given `--out` re-check does not re-check emptiness; bundle.sh:486-487) | U9b r2 review / security | deferred to U10 by O-18 | bundle.sh unchanged (sha256 9624710b... equal) |
| I-16 / N-7 (uid-0 link case, bundle.sh:685-688) | U9b r2 review / security | deferred to U10 by O-18 | bundle.sh unchanged |
| U9a N-6, N-8 (N-8: images checked with PRINTABLE_RE, not NAME_RE) | U9a review | open, optional | the new partial branch reuses the same image check as the other rows; consistent, not widened |
| README l.234, offline_check.sh l.238 "one entry per kind"; CHANGELOG line | design item 10, U9c-6 | documenter, marketer | after review |
| R7 `gitlab-probe.txt` + orchestrator verify full; R8 CI fetch extract | design item 16, U9c-7 | orchestrator | not the reviewer's |
