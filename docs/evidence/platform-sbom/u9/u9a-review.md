# U9a review (reviewer, 2026-10-29)

Scope: `git diff HEAD -- scripts/sbom_check.py tests/test_offline_bundle.py` (+503 / +86 lines) and the new
`tests/test_source_index.py` (1336 lines, 48 tests). There are no new files under `tests/fixtures/`: the install
fixture's SBOM, `index.json` and the two `files/<sha256>` are written by `_make_fixture` in code. The U8c part 2
docs are out of scope. Read first: handoff U9 sections, requirements U9-1..U9-15, design notes "N9 amendment, U9"
items 1-18, the Q78-Q80 and O-9..O-13 rulings, and the evidence `u9a-red-verify-fast.txt`, `u9a-controls.txt` and
`u9a-green-verify-fast.txt` (Ran 1251, OK skipped=8; all 48 `test_source_index` rows ok; none of the 8 skips are
U9a rows).

## Verdict: CHANGES REQUESTED (2 blocking, test-only; the production code needs no change for them)

## Design conformance, item by item
- Item 1 (boundaries): pure `fetch_record_problems`, `listing_problems`, `source_index` and `source_section`;
  `exempt_matches` multi-match; three subcommands. Exit 0/1/2, first 20 problems, one FAIL line. Conforms. Extra:
  `listing_problems(..., where=".")`; harmless.
- Item 3, order a-f: `_record_text` (lstat regular, 4 MiB, UTF-8), then a (JSON, canonical `lock_text`, exact keys,
  `format` int 1), b (set, arch, `lock_sha256` over the newline="" text, encoded UTF-8; equal to
  `sources_fetch._write_record`), c (`lock_entry_problems`, first problem only), d (`fetch_plan` grouped, missing
  or extra key, then per file count, shape and typed equality), e (`_lstat_listing` via scandir+lstat; OSError
  gives `<dir>: cannot list`), f (`_sha256_of`, O_NOFOLLOW, 1 MiB chunks). Success: sorted distinct sha256 on
  stdout, ok line counting distinct files and bytes (O-13 (1)). Conforms.
- Item 5, stages 1-6: read/shape, then `validate` of every SBOM before any classification, `lock_problems`,
  always/exempt per image, `listing_problems(record=False)` against `fetch_plan` (O-13 (5)), then the build with
  the stage-6 full/not-shipped assert. Conforms. The schema matches item 5 (top keys, lock-key components sorted
  and first, `path` null iff not shipped, exempt components after them sorted by (image, package), `reason` and
  `reviewed` verbatim, the listing string, unparsed and unidentified with needs either way, `unlicensed` =
  `unlicensed_report`). Output is `lock_text` with no timestamp.
- Item 6: multi-match problem text and SPDXIDs in document order (O-13 (3)); flags unchanged, so
  `classify_document` is unchanged. Exempt rules unchanged otherwise. Conforms.
- Item 7: refuse, never escape. Keys and images are checked with PRINTABLE_RE and URLs with PRINTABLE_RE.
  `reviewed` and listing are checked with FROM_PRINTABLE_RE. All of them are checked against UNSAFE_CELL_RE
  (pipe, backtick, lt, gt, backslash). No generator text is printed. Order: heading, banner (sample only), I-3
  sentence, intro, table (O-13 (4)). Conforms.
- O-13 (1)-(8): all eight confirmed in the code and by probe. (2) prints `fetch.json is 4194305 bytes, over
  4 MiB`. (6) a bad `--git-sha` exits 2. (7) prints `index: ke-neo4j: pkg:maven/...: exempt, reviewed ...`.
  (8) a lazy OSError in the pure function gives `<where>: cannot list`, and the CLI does the scanning.
- Scope: no bundle.sh, NOTICE, README or installer change (O-9). `tests/test_sbom_classifier.py` is unchanged
  and l.1134 ("flagged by always and exempt") is intact.

## Blocking
- **B-1: the O-13 rulings and U9-7's "starts with" are not pinned by any test.** The tester's RED predates
  O-13, and GREEN edited no test, so these ruled behaviours pass today but nothing stops them regressing:
  - (4)/U9-7: `test_sample_bundle_notices_say_do_not_distribute` only checks that the banner comes before the
    table. Nothing checks that it is the first line after the heading or that the I-3 sentence follows it.
  - (2): the oversize row accepts `4 MiB|4194304|too large|size`, not the ruled `fetch.json is <n> bytes, over
    4 MiB`.
  - (6): no row passes a malformed `--git-sha`. `test_index_cli_exit_2_on_a_bad_argument` has none.
  - (7): `assertIn(f"ke-neo4j: {JNA}: ...")` also matches without the `index: ` prefix.
  - The module docstring's "Tester's readings" still says the banner place "is not pinned" and the 4 MiB text is
    open. Update it to cite O-13.

  Fix (tester): add the four pins and refresh the docstring. Each new pin should get a scratch-copy mutation
  control in `u9a-controls.txt`, as for the install pins.
- **B-2: U9-2's "Text from the record printed in a refusal is escaped as PSC-22 L-3" has no test.**
  `test_wrong_types_are_problems_never_exceptions` only asserts that a problem exists, and `assertOneFailLine`
  covers FAIL lines, not refusal lines. The code is right (`_show` -> `_clean`; probe: a set value of "full" + ESC
  + "[31m" is printed with the ESC as the escaped text x1b). Fix (tester): add a pure row and a CLI row with a
  C0/C1 byte in a record field (set, a file name) asserting the escaped form and no raw control byte on stderr.

## Nits (optional; the first two are for the architect or orchestrator)
- N-1: `source_index` checks always and exempt entries only for images passed as `--sbom`. An entry naming another
  image (`always` image "ghost", or `exempt` image "ghost") is skipped silently and the index is built (probe).
  Read literally, U9-4 says "an always entry with no match" fails the bundle. Test-time `u6_policy_problems`
  ("an image that is not bundled") guards the committed policy, so this is defence in depth only. Suggest a
  stage-4 problem for an entry whose image is not among the bundle's SBOMs.
- N-2: `_policy_shape_problems` checks exempt entry fields but not `always` entry `image`/`match` types. With
  `image: ["valkey"]` the entry is ignored silently. With `match: 5` the message reads `expected component not
  catalogued: 5 ()`.
- N-3: `fetch_record_problems` raises AttributeError on a non-object policy (probe: `[]`, `None`), while
  `source_index` returns a problem. The CLI catches it as one FAIL line, exit 1 (fail closed), but the two pure
  functions behave differently.
- N-4 (TOCTOU, operator's own dir): `_record_text` lstats and then uses plain `open` (follows a link swapped in
  between). `_sha256_of` uses O_NOFOLLOW but has no `fstat` S_ISREG check and no O_NONBLOCK, so a fifo swapped in
  after the listing blocks the run. One `_open_regular()` helper (O_NOFOLLOW|O_NONBLOCK, fstat S_ISREG) for
  both. Items 4/8 (re-hash of the shipped bytes) remain the real guard.
- N-5 (duplication): the lock sha256 expression is written twice here (and once in `sources_fetch`), so a
  `lock_sha256(text)` helper would help. `--sbom IMAGE=PATH` parsing is now its third copy (`lock_check`,
  `lock_needs_cli`, `index_cli`), and only the new one refuses a repeated image. `_read_text`/`_fail`/`_refuse`
  repeat `lock_check`'s inline form. Do not refactor the old callers in U9a.
- N-6: `for key in sorted(...): return [...]` used as "first if any" in stage d. `next(iter(sorted(...)), None)`
  reads clearer.
- N-7: from the pure path, `source_index`'s listing failure reads `.: cannot list` (`where` defaults to `.`).
  Pass `"--files"`.
- N-8: `source_section` checks the image with PRINTABLE_RE, while item 7 says image names are NAME_RE. A
  hand-edited index can put Markdown link syntax, `*` or `_` into the non-code Images cell. This is not reachable
  from the CLI (`--sbom` is NAME_RE; lock URLs follow host rules). Security may weigh it.
- N-9: no index test checks that stage 3 stops before stage 4 or stage 4 before stage 5 (only that validate runs
  first).

## Test adequacy (beyond B-1/B-2)
- The RED rows cover item 14 rows 1-11. Validate-first uses a raising `classify_document` mock and checks
  `.called`, so it holds even though `source_index` swallows exceptions. The multi-match control runs on the
  committed policy and fixtures. Real-data `test_every_gpl_package_has_source` is present. Refuse-form rows cover
  key, URL, image, package and reviewed with pipe, backtick, lt, gt, backslash, LF, CR, C0, C1 and DEL, plus a
  space and a non-ASCII letter.
- Nothing is weaker than U8: the failed listing is a refusal (CLI, mode 0300, skipped only under root/Windows,
  and it ran in gates). No `docs/evidence` read (grep: docstring only). No count in a test name (`exit_2` is an
  exit code). The install pins add 12 `_tamper_cases` rows after the dict and before the nt filter, splitting no
  loop. Names are additions only (+2).
- The mutation controls are real: each disabled rule (hash, missing, unlisted, link x sh/ps1) fails exactly its
  three rows, and the control fails none (`u9a-controls.txt`).

## Probes (read-only, host .venv python -I, scripts in session scratch, nothing written to the repo)
- fetch_record_problems: 15 hostile shapes (format 1.0, True and 10 to the 400th; set as a dict, a control
  string or a surrogate; components null or a string; a file null or a list; size float or bool; deep nesting;
  a duplicate key; a BOM; 100000-deep; empty) all give problems and none raise. 3000 random mutations of one to
  three characters: the only 4 accepted were byte-equal to the control. A non-object policy raises (N-3).
- listing_problems: a generator or mapping raising OSError lazily gives "/files: cannot list".
- source_index: hostile policy shapes give problems (or the N-1/N-2 silent cases). Upper-case git sha, a bad set
  and docs as a list give problems. A lazy listing gives ".: cannot list" (N-7). Duplicate exempt entries (same
  package, different reason) build with the first entry: test-time u6_policy_problems refuses that policy.
- source_section: 400 SBOMs with random hostile strings (pipe, backtick, lt/gt, backslash, CR/LF, NUL, ESC, NEL,
  U+2028, U+202E, NBSP, Markdown metacharacters) in name, licences, version, supplier and copyright: no
  generator text reached any section. 5000 random single-field index mutations: none raised, and 4114 sections
  produced all had exactly one row per component, 4 pipes per row and no C0/C1 byte.
- CLI: the O-13 (2), (6) and (7) forms and the (4) order are as ruled (see above). A repeated --sbom image exits
  2. A non-object policy to sources-check gives one FAIL line, exit 1.

## Rework round 1 (reviewer, 2026-10-29; scope O-14 and "O-14 precision")

### Verdict: APPROVED (0 blocking)

- B-1 is closed. Each O-13 pin now exists:
  - (2) `test_oversize_record_refusal_reads_as_ruled` (line ends with the ruled text).
  - (4)/U9-7 `test_sample_banner_is_the_first_line_after_the_heading` (heading, banner, I-3; full: heading, I-3).
  - (6) `test_index_cli_exit_2_on_a_malformed_git_sha` (7 cases, no stdout, no raw byte).
  - (7) `test_index_cli_exempt_lines_carry_the_index_prefix` (exact line, both listing forms).
  - The docstring now cites O-13 and O-14.
  - The mutation controls in `u9a-r1-controls.txt` fail exactly their own pin, while the three old loose rows stay green under the same mutations.
- B-2 is closed. `test_record_text_in_a_refusal_is_escaped` (pure: ESC in set, C1 in a name, BEL in a key) and `test_record_text_in_a_cli_refusal_is_escaped` have a control (`_show` made raw fails both).
- N-3, N-4/L-1, N-7, N-9, I-3, L-2, L-3 and N-5 are done as ruled:
  - `_open_regular` opens with O_RDONLY, O_NOFOLLOW, O_NONBLOCK and O_BINARY, checks `fstat` S_ISREG and closes the fd on error. It is used for fetch.json (after lstat, size checked again on the fd), every planned file and `notices --index` (16 MiB cap).
  - MARKDOWN_RE applies to image, package, reviewed and listing, not to the key or URL (O-14 precision).
  - `_lock_sha256`, the `--files` name, the RecursionError guard and the non-object policy are all in.
  - The swap rows (decoy lstat driver, 10 s bound, 768 MiB RLIMIT_AS) ran in gates. `u9a-r1-green-verify-fast.txt`: Ran 1270, OK skipped=8, and all 19 new rows ran `ok`.
- Nothing is weaker:
  - `test_source_index.py` has 67 names = 48 + 19 added, none removed or renamed. The sha256 ea4b63a4... equals the controls file.
  - I spot-checked the old rows (banner, 4 MiB regex, mismatched record): their text is unchanged.
  - test_offline_bundle, test_sbom_classifier, test_sources_lock, test_sources_fetch, test_sbom_bundle, test_sources_lock_committed and test_sbom_obligations all match the controls hashes.
  - No count in a name. `docs/evidence` appears only in the docstring.
- The probes were re-run (session scratch `reviewer-r1/`, host python -I):
  - fetch_record_problems: the hostile shapes, depths 100/1000/5000/20000 (canonical / "nested too deeply" / "not valid JSON"), non-object policies ([], None, "x", 5) and 3000 random mutations all give problems. None raise, and nothing differing from the control is accepted.
  - source_index: a lazy listing gives `--files: cannot list`.
  - source_section: 5000 index mutations produced no exception. All 4099 sections produced had one row per component, 4 pipes per row and no C0/C1 byte. The 9 apparent "Markdown leaks" were single characters already in the fixed text, from fields that are never printed.
  - 300 hostile SBOMs leaked no generator text.
  - Keys with `_` and `!` print, and a backtick is refused.

### Nits (optional)
- R1-N1: `_cell_problem`'s condition (sbom_check.py l.2233) is one 154-character line with a 13-space gap where a line continuation was lost. Reflow it in parentheses.
- R1-N2: the module docstring's round-1 paragraph says the Markdown set is "refused in every printed field except the URL". After O-14 precision the key column is exempt too.
- R1-N3: `notices --index` caps on the fstat size and then `json.load`s the whole stream. Reading `INDEX_MAX + 1` bytes, as `_record_text` does, would bound a file that grows after the fstat. This is a local, own-tree input; for security's judgement.
- Carried as ruled: N-1, N-2 and I-4 to U9b (architect). N-6 and N-8 are optional and not done.
