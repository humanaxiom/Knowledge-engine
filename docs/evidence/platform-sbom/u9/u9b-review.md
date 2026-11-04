# platform-sbom U9b review (reviewer, 2026-10-29)

Scope: `git diff HEAD` on agent/platform-sbom (HEAD 1a7a9e2): scripts/bundle.sh, scripts/offline_check.sh,
NOTICE.md, README.md, tests/test_offline_bundle.py, tests/test_offline_check.py, tests/test_sbom_bundle.py,
tests/test_sbom_obligations.py, the new tests/test_bundle_sources.py and the intent-to-add
licenses/libffi-jna-5.15.0.txt. Read against design-notes "N9 amendment, U9" items 1-18 and O-9..O-15,
requirements "U9 precision" U9-1..U9-15, u9/expected.md and u9/u9a-review.md.

Checked, no finding: the test files are byte-equal to the after-hashes in u9b-controls.txt, so GREEN changed
no test; scripts/sbom_check.py and tests/fake_docker.py are unchanged. The libffi file is LF only, its body is
1132 B with sha256 2c9c2acb...c388 (the R7 value), and `.gitattributes` `licenses/* -text` covers it.
Green evidence: u9b-green-verify-fast.txt (Ran 1302, OK, skipped=8; these are the eight U9a Windows and ownership
skips) and u9b-green-verify-full.txt (PASS 1273 s). The unlistable --out and --sources rows ran in gates and
were not skipped.

## Verdict: CHANGES REQUESTED (3 blocking, 11 non-blocking)

## Blocking

- **B-1: unnormalised paths get past the U9-1 overlap guard and the U9-2 symlink refusal.**
  scripts/bundle.sh:82-92, :144, :155-170. Fails U9-1 ("never writes ... under --sources"), U9-2 (symlink
  refused) and design item 2. Probe (ke-gates:local, `--network none`, bundle.sh l.153-170 run verbatim; see
  "Probes" below):
  - `--out <W>/nonexist/../s/ke-bundle-amd64` with `--sources <W>/s` passes the check. The out-ancestor walk
    stops at `<W>` and keeps `nonexist/../s/...` as a literal string, so the comparison sees no overlap.
    `mkdir -p` then creates `<W>/nonexist` and writes the bundle into `<W>/s/ke-bundle-amd64`, inside --sources.
  - `--sources <link>//` or `<link>/.` defeats `[ -L ]`, because `${sources%/}` strips only one slash. The
    symlinked set is then mounted and copied through the link.

  Fix (developer):
  - After making --sources and --out absolute, refuse (exit 2 usage, or a `bundle: FAIL (stage
    sources-check|out: ...)` line) any path that holds an empty, `.` or `..` segment. Alternatively,
    canonicalise lexically before every check. Strip all trailing slashes, not one.

  Tests (tester), added to test_bundle_refuses_sources_overlapping_out and test_bundle_refuses_a_bad_sources_dir:
  - a `..` row (a missing component, then `..`, into --sources);
  - a `<link>//` row and a `<link>/.` row;
  - a symlinked-ancestor row (--out under a link that points into --sources), which pins the `cd -P`;
  - a segment-wise negative control (--sources `<t>/fetch`, --out `<t>/fetch2/bundle-amd64` must pass). That
    control pins the trailing `/` in both `case` patterns.

  Today no row fails if the patterns lose their `/` or if `real_dir` loses `-P`.

- **B-2: the O-15 rulings have no pins** (the same gap as U9a B-1 with O-13). tests/test_bundle_sources.py.
  - A2: MARKER_RE (l.69) matches any line that holds `sources:` and the four stage words. It does not require
    the ruled `bundle: sources: check <a> s, copy <b> s, index <c> s, notices <d> s`. Dropping the `bundle: `
    prefix, or adding text, stays green. Fix: fullmatch the ruled form.
  - A3: `_assert_refused_untouched` (l.178-195) checks only that no tag or save ran. The module docstring
    (l.20-22) says "the rows assert no call but `info`", which is not true. The shell refusals could move after
    the floor, the compose config, `image inspect` or even after sources-check and stay green. Fix: for the
    item-2 shell refusals (absent, symlink, not a directory, unlistable, no or non-regular fetch.json, overlap),
    assert that every recorded docker call is `info`.
  - A4: no row asserts the `bundle: FAIL (stage <stage>: <why>)` form. The stage regexes at l.698-704 match
    free text (`\bindex\b`, `\bnotices\b`, `copying source file`), so a plain `die` passes. Fix: for each
    refusal whose stage A4 names (sources-check, copy, index, notices, manifest, out), assert a line matching
    `^bundle: FAIL \(stage <stage>: .+\)$`.
  - A8: `--sources ""` has no row. test_bundle_requires_sources (l.244-256) has no empty-value case; only
    `--sources-set ""` is pinned (l.267). Fix: add the `--sources ""` usage row, exit 2 and no docker call.
  - Also: the module docstring (l.18-35) still lists the marker form and the docker-call order as "not
    resolved here". O-15 resolved both. Update it to cite O-15.

  Mutation controls for each new pin go in a u9b controls file (the u9a-r1-controls pattern).

- **B-3: the O-10 removal rows do not cover each item-9 stage, and the signal path has no pin.** Fails
  design items 9 and 14 ("a fault at each write stage of item 9") and U9-10 ("one `bundle:` line naming the
  stage and the image or file").
  - Signals (bundle.sh:456-459): the INT, TERM and HUP traps carry the removal. Probe: with the EXIT trap
    alone, SIGTERM and SIGHUP run it with `$?` = 0, so `bundle_cleanup` removes nothing and a partial bundle
    stays. No test sends a signal or pins the traps, so deleting l.457-459 stays green. Fix (tester): add a
    runtime row that sends SIGTERM to bundle.sh at a fake-docker hook after the first write (the install.sh
    signal rows in test_offline_bundle.py l.1103 and l.1153 are the pattern). Expect non-zero, --out
    removed or emptied, and no record. Also add the static trap-order pin that bundle_fetch.sh has
    (test_bundle_fetch_cleanup_ignores_signals_before_clearing_exit_trap).
  - The save fault, an `app/` notice-copy fault and the given-`--out` variant of the I-4 name check have no
    rows. Fix: add rows with `FAKE_DOCKER_FAIL` on `save` and with the cp shim on `app/NOTICE.md` or
    `app/licenses/`, each with created and given --out.
  - Code (developer): `docker tag`/`docker save` (l.464-465) and the `app/` copies (l.608-614) end the run
    through `set -e` with no `bundle:` line. Add `|| die "saving image <name> failed; no bundle written"` (and
    the same for tag), and `|| stage_die copy "<file>: ..."` on each `app/` copy.

## Non-blocking

- N-1 (bundle.sh:148-152): the `echo` for the no-fetch.json refusal does not game
  test_bundle_fetch_is_a_host_tool_only.
  - The only `bundle_fetch` mention in the code is inside the message string, and the printed line is the
    stage_die form exactly. The test still fails if any code calls or copies the script.
  - The real cause is `_strip_messages` (tests/test_sbom_generator.py:333): its `\bdie` does not match
    `stage_die`, because `_` is a word character. Optional: the tester widens it to `(?:stage_die\s+\S+|die|echo|printf)`
    and the special case goes.
- N-2 (bundle.sh:608-614): the `app/` copies read NOTICE.md, LICENSE and a second `git ls-files` listing from
  the tree, minutes after the root copies (l.490-499), and the second listing has no `licenses_found` check.
  Copy from `$out/NOTICE.md`, `$out/LICENSE` and `$out/licenses/` instead, so U9-8 "byte-identical" holds by
  construction.
- N-3 (bundle.sh:126-133, :433, :461): `created` is set at l.433, but the emptiness check runs at l.126. An
  --out that appears between the two (created=0, never checked for emptiness) has its contents removed on
  failure. `mkdir -p` also creates missing ancestors of --out, which O-10's removal leaves behind. Fix: keep
  the l.126 result, and create --out with a plain `mkdir` at the first write (refuse if it fails).
- N-4 (bundle.sh:441-443): cleanup failures are silent (`find ... > /dev/null 2>&1 || true`). Under the
  inherited `set -e`, a failing `rm -rf -- "$out"` ends the trap before compose `down` and the work-dir removal.
  Print `bundle: warning: could not remove ...` and carry on.
- N-5 (bundle.sh:414-415): `mapfile <<< ""` yields one empty element, so the `-ge 1` check cannot fire, and empty
  output is reported as "not a sha256". Test `[ -n "$check_text" ]` instead.
- N-6 (bundle.sh:618-619, :627, :124-137): A4 is applied only to the new lines. The manifest-stage refusals
  (the link check that catches an I-4 link swap, and the path pattern) and the existing --out refusals keep
  the `die` form. The orchestrator says whether A4 covers them.
- N-7: there is no row for the I-4 link-swap variant (a symlink put in place of a checked file after
  sources-check, copied by `cp -P` and refused at l.618). Add one through a fake-docker hook in gates.
- N-8 (bundle.sh:576): a fifo swapped in after the check makes `cp -P` block (cp reads a fifo). This is the
  operator's own directory, so it is low risk. For security's judgement.
- N-9 (offline_check.sh:268): three spaces before `||`.
- N-10 (evidence, for the orchestrator): u9/size.md lacks the MANIFEST.sha256 bytes and lines, and its bundle
  bytes with and without `app/sources/` are estimates from `df`, while U9-13 asks for both from the real run.
  The index status counts in expected.md (7 shipped, 176 not-shipped, lock_sha256) were not checked against
  a real index.json. Record them at R10/R11.
- N-11 (README.md l.47): "(Updated 2026-10-27, documenter, status)" is now stale. For the documenter at R14.

## Carried reviewer items (u9a-review.md)

| Item | Status after U9b | Note |
|---|---|---|
| N-1 (policy entries naming an un-passed image are skipped silently) | still open | sbom_check.py is unchanged. O-14 carried it to U9b for the architect, and no disposition is recorded. bundle.sh passes all six images, so it is not reachable from the bundle. The orchestrator records "defer" or a fix before U9b closes. |
| N-2 (`always` entry field types unchecked) | still open | Same as N-1. Test-time u6_policy_problems guards the committed policy. |
| N-6 (`next(iter(sorted(...)))` readability) | still open, optional | Out of U9b's scope (no sbom_check.py change). |
| N-8 (image cell checked with PRINTABLE_RE, not NAME_RE) | still open, optional | Not reachable from bundle.sh: every `--sbom` name is `ref_name` (`^[a-z0-9._-]+$`, bundle.sh:256). Out of scope. |
| R1-N1 (`_cell_problem` long line) | still open, optional | Out of scope. |
| R1-N2 (module docstring, key column) | still open, optional | Out of scope. |
| R1-N3 (`notices --index` reads past the fstat cap) | still open, for security (= I-5) | bundle.sh writes index.json itself just before `notices` reads it (:592, :599), so growth needs a concurrent writer in --out. |
| (U8b N-9, `ls -A` fails open) | closed by U9b | bundle.sh:129, with test_bundle_refuses_an_unlistable_out and test_bundle_refuses_an_unlistable_sources_dir, both run in gates. |
| (security I-4, sources-check/copy window) | closed by U9b for bytes | bundle.sh:629-633, with test_a_source_file_changed_after_the_check_is_refused. The link variant is N-7. |
| O-10 removal row | present but incomplete | 6 stages x created/given in test_bundle_writes_no_manifest_when_sbom_or_source_fails. The save, app/ copy and signal rows are missing (B-3). |

## Conformance notes (no finding)
- CLI: --sources mandatory; absent, valueless or repeated exits 2; --sources-set full|sample, default full,
  bad, empty or repeated exits 2; the header and usage name both (U9-1, Q78).
- Order: arguments, jq, `docker info` (A3), --out checks with N-9, record, --sources shell checks, floor ...
  `engine.notices`, sources-check, dirty, first write. sources-check runs in ke-app with
  `--network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never --user`, its own
  label, `:ro` mounts and MSYS_NO_PATHCONV (item 1).
- Copy `cp -P --` only; index then notices; `app/` copies; manifest name==hash, count and the 1 MiB cap;
  record last; `bundle written` only after the record (items 4, 5, 7, 8, 9).
- offline_check passes `--sources "$fetch_rel" --sources-set sample` (U9-12); README gives the operator order
  and the sample warning; NOTICE.md has the I-3 sentence first and the libffi paragraph (U9-9); no
  docs/evidence read by any test, and no count in a test name.

## Probes (read-only; scripts in session scratch `rev-u9b/`, run in ke-gates:local with `--network none`, the
scratch dir mounted `:ro`; symlinks only inside the container's /tmp)
```
== control: out inside sources (absent) ==
REFUSED (stage sources-check: --out /tmp/tmp.X/s/ke-bundle-amd64 is inside --sources (/tmp/tmp.X/s); no write may land under --sources)
== out = <nonexistent>/../s/ke-bundle-amd64 (lexically outside, really inside --sources) ==
PASSED overlap check: sources=/tmp/tmp.X/s out=/tmp/tmp.X/nonexist/../s/ke-bundle-amd64
-- what mkdir -p would create:
fetch.json
ke-bundle-amd64
/tmp/tmp.X/nonexist
== sources given with a trailing // to a symlinked dir ==
symlink NOT detected: [ -L /tmp/tmp.X/slink/ ] is false

with traps, SIGTERM: exit 143, trap: cleanup rc=143
with traps, SIGHUP: exit 129, trap: cleanup rc=129
without traps, SIGTERM: exit 143, trap: cleanup rc=0
without traps, SIGHUP: exit 129, trap: cleanup rc=0
```
(The SIGINT rows are not meaningful: an async job in a non-interactive bash ignores SIGINT.)
