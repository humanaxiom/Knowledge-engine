# platform-sbom U9b rework 1 of 5: reviewer re-read (2026-10-29)

Scope: `git diff HEAD -- scripts/bundle.sh scripts/offline_check.sh README.md tests/test_offline_bundle.py
tests/test_sbom_generator.py` and the untracked tests/test_bundle_sources.py on agent/platform-sbom (HEAD 1a7a9e2).
Read against design-notes O-16 (1)-(9) and the "O-16 precision" (a)(b), my u9b-review.md, the rework-1 tester and
developer sections of docs/handoffs/platform-sbom.md, u9b-r1-controls.txt and the GREEN evidence.

Checked, no finding:
- GREEN changed no test. tests/test_bundle_sources.py c9219538..., tests/test_offline_bundle.py ea89a8b6...,
  tests/test_sbom_generator.py 33d673db... equal the controls file's after-hashes. tests/fake_docker.py,
  test_offline_check.py, test_sbom_bundle.py, test_sbom_obligations.py, test_bundle_fetch.py, scripts/sbom_check.py
  and NOTICE.md equal its "unchanged" hashes. bundle.sh, offline_check.sh (N-9) and README.md changed, as reported.
- Evidence: u9b-r1-green-verify-fast.txt `== verify fast: PASS ==` rc=0. u9b-r1-green-verify-full.txt: Ran 1322,
  OK (skipped=8), offline_check PASS 249 s, `== verify full: PASS (1422s) ==`, rc=0.
- `segment_bad` (bundle.sh:102-107) is correct and complete for absolute paths with no trailing slash. Probe below:
  `/a/.b`, `/a/b.`, `/a/..b`, `/a/b..`, `/a/...` pass. `/.`, `/..`, `/./a`, `/../a`, `//a`, `/a//b`, `/a/./b`,
  `/a/../b`, `/a/.`, `/a/..` are refused. It refuses nothing U9-1 allows, apart from the two lexical forms in N-2.
- Placement: the path rule runs before `jq` and `docker info`, so a path refusal makes no docker call. The A3 pin
  `_assert_info_only` (test_bundle_sources.py:217-220) filters out the `info` calls and requires the rest to be
  empty, so zero calls passes. Nothing pinned conflicts with this.
- The `_bundle` -> `_bundle_cmd` split (test_offline_bundle.py) preserves behaviour. With `raw_out=None` the argv,
  the parent mkdir, the env, cwd, timeout=180 and `fake_docker.records(self.json)` are as before. `_bundle(out, **kw)`
  takes `out` positionally or by keyword, as callers use it, and `raw_out` is used only by the O-16 rows.
- The `_strip_messages` widening (test_sbom_generator.py:336) is honest. The pattern strips only a stage_die message
  (`stage_die <stage> "..."` to end of line), the same way it already stripped die/echo/printf messages. Code that
  calls or names bundle_fetch.sh still survives the strip: test_strip_messages_strips_the_text_of_stage_die line 3
  checks this, and mutation [18] shows the old pattern fails it.
- Rework lines:
  - The quoting is sound.
  - `( set -C; printf ... > "$record" ) || die`: under `set -e` the subshell's failure goes to `die`, and
    `record_made=1` is set only after it succeeds (O-16 (3), pinned by the bytes-preserved row).
  - Cleanup (bundle.sh:450-472): every removal is `|| echo "bundle: warning: ..."`, and no command can abort the trap
    under `set -e` (N-4).
  - `mkdir -- "$out"` comes before `wrote=1`, so a failed claim removes nothing. That order is right.
- O-16 (4), (5), (6) and the B-2 docstring are done as ruled.
  - tag/save `|| die "... no bundle written"` (:487-488); `app/` copies `|| stage_die copy` (:633-640); manifest
    refusals `stage_die manifest` (:645, :653).
  - The pre-U9 --out/record refusals keep `die` (:141, :144, :148, :154). The `out` stage holds only :108, :146 and
    :481.
  - Each of these has a row that was red at RED or a mutation control ([1]-[18] in u9b-r1-controls.txt).

## Verdict: CHANGES REQUESTED (2 blocking, 6 non-blocking)

## Blocking

- **B-1 (O-16 (2) not done as ruled; N-3 and the L-4 race stay open). scripts/bundle.sh:446-449.**
  - What O-16 (2) says: "`created` is decided from the l.126 check, not re-tested".
  - What the code does: it re-tests with `if [ ! -e "$out" ]; then created=1; fi` at :449. That is minutes after the
    emptiness check at :140-150, with sources-check, `engine.notices` and the image inspects in between.
  - The failure: an --out that appears in that window, for example with an operator's files in it, gets `created=0`.
    It is then treated as a given, empty --out:
    - the plain `mkdir` is skipped;
    - the run writes into a directory that was never checked for emptiness;
    - on any later failure, the O-10 cleanup removes all of its contents (`find -mindepth 1 ... rm -rf`);
    - on success, the stranger's files ship under the manifest.
  - Probe (ke-gates:local, `--network none`; bundle.sh :139-150 and :444-483 run verbatim, then a stage fails):
    `--out appears (with an operator file) between the check and :449` -> `created=0 wrote=1`, rc=1,
    `left in --out:` (nothing). The operator file was deleted.
  - Not pinned: no row creates --out after the check (grep `appear` finds only the record row), and the developer's
    section does not mention the l.126 decision.
  - Fix (developer):
    - Record the decision in the --out block: `out_given=0` before :140, `out_given=1` inside `if [ -e "$out" ]`.
    - Replace :449 with `if [ "$out_given" -eq 0 ]; then created=1; fi`.
    - Then `mkdir --` at :481 refuses an --out that has appeared since the check (`stage out`, nothing written).
    - Optional, given case: `[ -d "$out" ] && [ ! -L "$out" ] || stage_die out "--out changed since its check: $out"`.
      This stops `mkdir -p "$out/images"` from re-creating a given --out that was deleted in the window.
  - Test (tester), in BundleSourcesPathRuleTest or NoPartialTest:
    - A FAKE_DOCKER_HOOKS `write` on the `sbom_check.py sources-check` run creates `<out>/operator.txt`, with --out
      absent at the start.
    - Expect exit 1, one `bundle: FAIL (stage out: ...)` line, `operator.txt` intact and the only entry, no tag or
      save, no record and no `.ke-sbom.*`.
    - This row is red today. Its mutation control is the re-test at :449.

- **B-2 (docs; for the documenter at R14, before the U9b commit; no developer round needed). docs/quickstart.md:69, :78.**
  - The operator quickstart still says `bash scripts/bundle.sh --out dist/bundle-amd64` (and `-arm64`). It has no
    `scripts/bundle_fetch.sh` step and no `--sources`.
  - Since U9b (Q78) that command exits 2 with the usage line. The file ships inside every bundle as
    `app/docs/quickstart.md`.
  - `dist/` must also exist first: bundle_fetch.sh (:124) and now bundle.sh (:481) both claim --out with a plain
    `mkdir`. On a fresh clone `dist/` is ignored and absent.
  - My u9b-review.md missed this.
  - Fix: give the U9 order in both blocks: `mkdir -p dist`, `bash scripts/build.sh`,
    `bash scripts/bundle_fetch.sh --set full --out dist/sources-<arch>`, then
    `bash scripts/bundle.sh --out dist/bundle-<arch> --sources dist/sources-<arch>`. State that the parent of `--out`
    must exist. test_quickstart_offline_commands_run_as_written already accepts `bash scripts/bundle.sh ...`.
  - R14 in design-notes names README only. The orchestrator adds quickstart.md to R14.

## Non-blocking

- N-1: rules with no pin or mutation control (O-16 asks for one per rule).
  - O-16 (1): the trailing `..` segment. No row gives `<path>/..`, so deleting `| */..` from segment_bad
    (bundle.sh:104) stays green. For --out a trailing `..` fails the name check anyway, but for --sources it would
    resolve.
    - Fix (tester): in test_bundle_refuses_a_sources_path_with_a_dot_dot_dot_or_empty_segment (test_bundle_sources.py:573-578),
      add a `<copy of the fetch with a sub dir>/sub/..` case.
    - Under the mutation the shell checks pass and sources-check runs, so the info-only pin catches it.
  - O-16 (7) N-4 (the cleanup warnings, bundle.sh:457-469) and N-5 (`[ -n "$check_text" ]`, :429) have no row.
    Optional:
    - a given --out whose entry cannot be removed (a hook chmods a subdir 0500 at a late stage), expecting the
      warning line and exit 1;
    - a fake `sources-check` that prints nothing and exits 0, expecting `stage sources-check: the check listed no
      source file`.
  - O-16 precision (b): `--sources //` is exit 2, but the row accepts 1 or 2 (as ruled). Deleting :97 stays green
    (the run then exits 1 at "does not exist"). Recorded, no action.
- N-2 (bundle.sh:86-109, README.md:126): two lexical forms are refused that an operator may type.
  - `--out ./dist/bundle-amd64` becomes `$PWD/./dist/...` and is refused (probe: `/tmp/./rel-amd64`). Relative paths
    with `..` are refused the same way.
  - Any relative path run from cwd `/` becomes `//rel` and is refused (probe: `//rel-amd64`).
  - The first is what O-16 (1) says, but README and quickstart do not tell the operator.
  - Fix:
    - documenter: one sentence, "--out and --sources may not contain `.` or `..` segments (write `dist/x`, not
      `./dist/x`)";
    - developer, optional: join as `${PWD%/}/$x`.
- N-3 (bundle.sh:430-431): after N-5 the `[ "${#source_shas[@]}" -ge 1 ]` check is dead, because `mapfile` of a
  non-empty string always yields at least one element. Drop it.
- N-4 (bundle.sh:119-120): the comment says jq is "checked before anything else runs". The path rule now runs first.
  Fix: "checked before any docker call".
- N-5 (bundle.sh:679-681, info): if the noclobber write creates the record and then fails part-way (ENOSPC), the
  subshell fails and `record_made` stays 0. A partial record this run made is then left beside the removed bundle.
  It fails closed (the next run refuses "record already exists"). O-16 (3) chose this order; for security's notes
  only.
- N-6 (bundle.sh:480-483, info): a signal between a successful `mkdir -- "$out"` and `wrote=1` leaves an empty
  --out. The window is one builtin. No action.

## Rulings checked (O-16)

| Rule | Done as ruled | Pin / control |
|---|---|---|
| (1) strip every trailing slash; empty after strip = usage 2; `.`/`..`/empty segment refused, `stage out` / `stage sources-check`, exit 1, before any check | yes | rows red at RED (5 out cases, 4+1 sources cases, 3 link cases, strip row); `cd -P` [11]; segment-wise [12][13]. Trailing `..` unpinned (N-1). `//` exit 1-or-2 by ruling (b) |
| (2) plain `mkdir --` at first write; missing parent = `stage out`, nothing written; `created` from the check | **partly**: mkdir yes, `created` re-tested | missing-parent row red at RED; the `created` decision unpinned (**B-1**) |
| (3) record under noclobber; `record_made=1` after the write | yes | record-appears row red at RED (bytes kept, given and created) |
| (4) tag/save `die`, `app/` copies `stage_die copy`; SIGTERM row, trap order, save fault, `app/` copy fault, I-4 given | yes | tag/save and app-copy rows red at RED; SIGTERM [15]; trap order [14]; I-4 given [16] |
| (5) A2 fullmatch, A3 info-only, A4 per stage, A8 `--sources ""`, docstring cites O-15 | yes | [1], [2], [3]-[9], [10]; docstring l.18-58 |
| (6) manifest refusals `stage_die manifest`; pre-U9 --out/record keep `die`; `out` stage = N-9 + (1) + (2) | yes | path-pattern and non-regular rows red at RED; [7] |
| (7) N-2 copies from `$out`; N-4 warnings; N-5 `-n`; N-9; N-1 widen + stage_die; N-7 link row | yes | N-2 row red at RED; N-1 [18] + stage_die row red at RED; N-7 [17] (`index`, precision (a)); N-4, N-5 unpinned (N-1 above); N-9 whitespace |

## Carried items

| Item | Status | Note |
|---|---|---|
| U9b B-1 (unnormalised paths) | closed | O-16 (1); probe and rows. The `created` part moves to the new B-1 |
| U9b B-2 (O-15 pins, docstring) | closed | [1]-[10] |
| U9b B-3 (signal, save, app copy, `bundle:` lines) | closed | rows + [14]-[16] |
| U9b N-1 (`_strip_messages`, echo) | closed | test_sbom_generator.py:336; bundle.sh:166 |
| U9b N-2 (app/ copies from the tree) | closed | bundle.sh:633-640 |
| U9b N-3 (`created` vs l.126; `mkdir -p` ancestors) | **open** | ancestors closed by the plain mkdir; the `created` decision is the new B-1 |
| U9b N-4 (silent cleanup) | closed (unpinned) | bundle.sh:457-469 |
| U9b N-5 (`mapfile <<< ""`) | closed (unpinned) | :429; dead line :431 (N-3) |
| U9b N-6 (A4 scope) | closed | O-16 (6) |
| U9b N-7 (link-swap row) | closed | stage `index` per precision (a); [17] |
| U9b N-8 = security I-7 (fifo/device swap) | deferred | O-16 (8) |
| U9b N-9 (offline_check spaces) | closed | offline_check.sh:268 |
| U9b N-10 (size.md, index counts) | deferred | O-16 (8): Q79 bundle half, R10/R11 |
| U9b N-11 (README "(Updated 2026-10-27 ...)") | open | still at README.md:47; documenter at close |
| security I-11 (path-only overlap, bind-mount alias) | deferred | O-16 (8) |
| security I-12 (sample warning at install) | deferred | O-16 (8), U10 |
| U9a N-1, N-2 (sbom_check policy entries) | deferred | O-16 (8), U10 with a design row |
| U9a N-6, N-8, R1-N1, R1-N2 | open, optional | out of U9b scope (sbom_check.py unchanged) |
| U9a R1-N3 = security I-5 | open, security | unchanged |

## Probes (read-only; ke-gates:local `--network none`, scratch mounted `:ro`, nothing on the host)
Script: session scratch `rev-u9br1/probe.sh`. It sources bundle.sh :139-150 (the --out check), :444-483 (the claim
and cleanup) and :94-109 (strip and segment_bad), each verbatim, then fails.

    == control: --out absent throughout ==
    created=1 wrote=1
    rc=1 ; left in --out:  exists=n
    == --out appears (with an operator file) between the l.143 check and l.449 ==
    created=0 wrote=1
    rc=1 ; left in --out:  exists=y
    == segment_bad on forms ==   (ok = accepted; the rest refused, stderr hidden)
    ok /a/b  ok /a/.b  ok /a/b.  ok /a/..b  ok /a/b..  ok /a/...
    refused: /.  /..  /./a  /../a  //a  /a//b  /a/./b  /a/../b  /a/.  /a/..
    == relative forms from cwd / and with ./ ==
    cwd / -> //rel-amd64
    bundle: FAIL (stage out: --out has an empty, . or .. path segment: //rel-amd64)
    ./ -> /tmp/./rel-amd64
    bundle: FAIL (stage out: --out has an empty, . or .. path segment: /tmp/./rel-amd64)
