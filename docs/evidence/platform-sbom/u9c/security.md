# U9c security audit (security, 2026-10-30)

**Verdict: PASS.** No blocking (L) finding. Three informational notes (I-1..I-3), none merge-blocking.

Scope: `git diff HEAD -- scripts/sbom_check.py scripts/sources_fetch.py tests/test_sources_fetch.py tests/test_source_index.py`
plus the untracked `tests/test_sources_sample_apk.py`, on agent/platform-sbom at 90db4b8. Read: handoff U9c block,
archive part 17, requirements "U9c precision" U9c-3/-4/-6/-7, design-notes "N9 amendment, U9c" items 2, 3, 5-7, 12
(O-19..O-21), 13, 17. Probes: `docs/evidence/platform-sbom/u9c/security-probes.txt` (22 + 2 probe rows, all OK;
`python -I` on the host from the session scratchpad, fake transport only, no symlink, no network).

## Checks

| # | Property | Result | Evidence |
|---|---|---|---|
| 1 | No fail-open: the skip reads set and kind only | Holds. `sources_fetch.py:164` `if kind == "apk" and which == "sample"` is the only skip; exact string match (`Sample`, `SAMPLE`, `"sample "`, `""`, `None`, `partial` all go on to read the APKBUILD and raise). Full run with the APKBUILD dropped from the plan: rc 1, no record, no skip line (P1a). Full run with APKBUILD 404: rc 1, one GitLab call (P1b). Full run whose sha512sums digest differs (same names): U8-5 line, rc 1 (P1c). Names differ: U8-5 line (P1d). `.dsc` check still raises in the sample (P1h). | P1a-P1d, P1h |
| 1b | Distfiles files still get size, sha256 and sha512 before placement | Holds (`_place` unchanged). Sample: swapped bytes, same size -> sha256 FAIL; lock sha512 false of the bytes -> sha512 FAIL; one byte longer -> size FAIL; nothing placed, no `fetch.json`. | P1e-P1g |
| 2 | No new host, URL or request | Holds. `APK_API_HOST` moved, `APK_DISTFILES_HOST` names the literal that was already in `KIND_HOSTS["apk"]` (`sbom_check.py:1188-1190`); no URL or host literal added anywhere in `scripts/` (diff grep); `sources_fetch.py` holds none. The filter only removes rows (every committed sample row is a full row; sample hosts are a subset of the policy's 9 hosts; no gitlab). Odd distfiles URL forms (upper case, userinfo, port, http, trailing dot, other host, github for apk) are refused by the lock rules before any plan. `git diff --stat HEAD -- docker/` empty; lock sha256 `12eebc8cd09e5effc6934a1a3b67decc053cda923720dda07a8909a137fc761b`, policy `6261355f...ef21`, both equal to HEAD. | P2a-P2c |
| 3 | A partial key never passes a full bundle; only the apk sample key may be partial | Holds. `index` full with the apk GitLab files dropped, or with one deb file dropped: refused, `is partial in a full bundle` (`sbom_check.py:2216-2217`). `index` sample with a partial deb key: refused (`:2218-2219`). Sample `--files` that also holds a GitLab file: refused, `not in the lock's plan` (O-19). `notices` on a full index with a partial row: refused (`:2304-2305`). Control: sample index 6 shipped / 1 partial (wide fixture). | P3a-P3e |
| 4 | Partial row: refuse, never escape | Holds. The branch (`sbom_check.py:2297-2311`) uses the same `check()` as the U9a rows: key and URL with `markdown=False`, images with markdown. 23 hostile index values refused (pipe, backtick, `<script>`, backslash, space, newline row injection, CR, U+202E, empty, non-string, None; key pipe/backtick/newline/int; image link/star/pipe; no packages; files not a list; all or no file pathed). Hostile values in a synthetic lock (pipe in the APKBUILD URL, backtick or pipe in the key) never reach the index: lock rules refuse. | P4a, P4b, P4d |
| 5 | Stage-lock FAIL makes zero requests | Holds. `bundle_fetch: FAIL (stage lock: apk:...: the apk sample key has no file on distfiles.alpinelinux.org; the sample needs one (A81); no retry)`, 0 calls, empty `--out`; it is raised before the disk stage (`sources_fetch.py:229-232`). Control: full of the same lock fetches. | P5 |
| 6 | The proof rows assert what they claim | Holds. `test_sample_fetch_passes_with_gitlab_unreachable` asserts no GitLab URL in `run.net.calls` (`tests/test_sources_sample_apk.py:307`); `test_full_fetch_fails_with_gitlab_unreachable` asserts `run.net.calls == [first]` and `sleeps == []` with `_ACTIVE_RETRIES` forced to 3 (`:323-327`). Reproduced independently (P6). | P6 |
| 7 | No gate or test weakened | Holds. Test counts unchanged (49, 67); every removed line in `tests/` is replaced by an equal or stricter one: R1/R2 narrow only the sample branch (`plan_of`, `test_fetch_plan_rows`; full unchanged); R3 (O-20) adds `which="full"` and nothing else, every case kept; R4 splits "shipped == sample" into shipped == sample - apk and partial == {apk}, `path` per planned (key, name); R5 adds a partial branch and a new assertion, and widens the no-source-claim loop; R6 moves `plan` into the loop, assertions unchanged. `test_source_fetch_has_no_url_host_or_environment_literal` untouched. | diff read |
| 8 | Evidence clean | Holds. No profile path, SID or secret pattern in `u9c/` (txt, md), in the diff, in the new test module or in `NEXT-SESSION.md`. The `ci/` attempt-2 log holds only GitHub's masked `AUTHORIZATION: basic ***`. The probe output had one temp path under the profile; redacted to `<PROFILE>`. | grep |

Also: no dependency change (`pyproject.toml`, `uv.lock` unchanged), no compose, Dockerfile, CI, `bundle.sh` or
`bundle_fetch.sh` change; a build-time tool, so no spans are due (design-notes item "No spans").

## Findings

Blocking (L): none.

- **I-1 (low, informational) `notices` does not re-check that a partial row is apk.** `sbom_check.py:2297-2311`
  accepts a hand-made `sample` index with a partial `deb` row (P3f). It cannot be reached in a bundle: `bundle.sh`
  feeds `notices` only the index that `index` wrote a moment earlier in the same run, and `index` refuses it
  (`:2218-2219`, P3b). Fix (optional, defence in depth): in the partial branch, add
  `if c.get("kind") != "apk" or not str(key).startswith("apk:"): p.append(f"notices: {_show(key)} is partial, and only the apk sample key may be (A81)")`
  plus one test row. Can ride with U10.
- **I-2 (informational) The sample no longer re-reads the APKBUILD,** so a distfile whose lock sha512 disagrees
  with the live APKBUILD passes a sample run (P1c, sample) while a full run fails (P1c, full). This is the ruled A81
  trade-off (design-notes item 17): the distfile still must match the committed, reviewed lock's sha256 and sha512,
  so integrity is unchanged; only the live provenance cross-check moves to `--set full`. No action.
- **I-3 (informational) The row's URL is the first unfetched file's** (the APKBUILD at the pinned commit), while
  "the rest" can be several GitLab files. Every one of them is listed with its URL in `index.json`, and the row
  points there. No action; see the wording decision.

## Wording decision (U9c-4, U9-7)

Approved as written (`sbom_check.py:2309-2311`):

```
| `<key>` | <images> | partial source (verification sample): only the files that `sources/index.json` lists with a path are in `sources/files/`; Upstream source of the rest: <url> |
```

It does not use the shipped claim ("source in `sources/`", which the section intro reserves for complete source),
says "partial" first, says which files are present and where to find that list, and names an upstream URL at the
pinned commit, the same URL form the not-shipped apk rows already print. The do-not-distribute banner stays the
first line of the section (P4c). An optional sharper tail, not required: "Upstream source of the rest: each file's
`url` in `sources/index.json`, starting with <url>".

## Next

Nothing blocks merge from security. The orchestrator's gate run still needs its closure probe (U9c-7) and the
documenter's README/offline_check.sh wording (U9c-6).
