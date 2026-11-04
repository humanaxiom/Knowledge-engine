# platform-sbom U9b rework 2 of 5: reviewer re-read (2026-10-29)

Scope: the rework-2 delta of scripts/bundle.sh, i.e. `git diff --no-index <rework-1 GREEN bundle.sh> scripts/bundle.sh`. The
rework-1 file is a scratch copy whose sha256 is b6ec465b..., the "today" hash in u9b-r2-controls.txt. I also read
`git diff HEAD -- scripts/bundle.sh` for context, the new rows in tests/test_bundle_sources.py, design-notes O-17 (1)-(6),
my u9b-r1-review.md, the rework-2 tester and developer sections of docs/handoffs/platform-sbom.md, u9b-r2-controls.txt
and the RED and GREEN evidence. Line numbers are those of the working tree.

Checked, no finding:
- GREEN changed no test. These files equal the controls file's hashes:
  - tests/test_bundle_sources.py d9273a20... (the RED "after" hash);
  - test_offline_bundle.py ea89a8b6..., test_sbom_generator.py 33d673db..., test_offline_check.py 577e6f28...,
    test_sbom_bundle.py 7eeb7f9f..., test_sbom_obligations.py 16a34a4a..., test_bundle_fetch.py 14617f31...,
    fake_docker.py a72679ac...;
  - offline_check.sh 48be0cb0..., sbom_check.py b7c93389..., NOTICE.md 0aee6bb8..., README.md 6ec75407...,
    CLAUDE.md 49505b65....
  Only scripts/bundle.sh changed (b6ec465b... -> 9624710b...).
- Evidence:
  - RED (u9b-r2-red-verify-fast.txt:1958-2106): the 4 O-17 rows fail (5 failures; the I-14 row has 2 subTests), plus the
    NEXT-SESSION cap, which was not this RED's file. Ran 1328.
  - GREEN fast: `== verify fast: PASS ==`.
  - GREEN full: Ran 1328, OK (skipped=8) (:2230-2232), then `== offline_check: PASS (237s) ==` and
    `== verify full: PASS (1365s) ==`.
  - The offline check ran the real success path with this bundle.sh (sample set, created --out): `bundle written` /
    `release record` (:2854-2856), then install, launch and smoke.
- B-1 is closed as O-17 (1) says.
  - Single decision point: `created=1` at :146 and `created=0` inside `if [ -e "$out" ]` at :148, the block where
    emptiness is checked. The old `created=0` and the re-test `if [ ! -e "$out" ]; then created=1; fi` (rework-1
    :446/:449) are gone. `created` is not assigned anywhere else (grep).
  - Both link variants are refused:
    - A created --out that has since appeared, as a directory or as a link to one, fails `mkdir --` (EEXIST; also on a
      dangling link) at :485.
    - A given --out replaced by a link fails `[ ! -L ] && [ -d ]` at :487.
    - Both refusals come before `wrote=1` (:489), so the cleanup removes nothing.
  - Rows:
    - test_bundle_refuses_an_out_that_appears_after_its_check (dir; runs on Windows too) and
      ..._a_link_that_appears_at_an_absent_out (gates): red at RED. Each asserts one `bundle: FAIL` line, A4 `stage out`,
      no tag or save, no record, no `.ke-sbom.*`, the operator file intact and the only entry, and the link kept with
      nothing written through it.
    - ..._a_given_out_replaced_by_a_link_before_the_first_write (gates): the given re-check.
  - Mutation controls: [2] pins "decided once" (a re-tested `created` fails the dir row); [3] pins the given re-check.
- I-14 is closed as O-17 (2) says. :687 is `chmod 0644 -- "$record" || die "cannot set the mode of the release record
  $record; ..."`, and `record_made=1` comes after it at :688.
  - test_bundle_leaves_a_non_regular_record_link_in_place (created and given; gates, uid != 0) was red at RED.
  - Mutations: [4] pins the order, [5] pins `|| die`.
  - The probe confirms uid 10001: the noclobber write goes through a link to /dev/null and the chmod fails with EPERM,
    so the run dies.
- The three O-16 controls left unpinned in rework 1 are now pinned:
  - the trailing `..` subTest at test_bundle_sources.py:625-632 (mutation [6]);
  - N-4, the cleanup warning row, :1395-1425 (mutations [7] and [8], created and given);
  - N-5, the empty sources-check listing row, :521-534 (mutation [9]).
  Each was green at RED as a pin of existing behaviour, as the controls file declares.
- N-3 and N-4 are done.
  - The dead `[ "${#source_shas[@]}" -ge 1 ]` check is removed (it was after :435). :434 still guards the empty output,
    and :436-438 refuse any empty or non-sha line inside the output.
  - The jq comment at :122-123 now reads "the path rule above runs first", which is true: :82-117 run before :124.
- Each O-17 rule has a row and a mutation control:
  - (1) dir [2], given link [3], created link: by the row (mkdir EEXIST; no separate mutation is needed, since the dir
    row's mutation [2] covers the same `created` path);
  - (2) [4] and [5];
  - (3) N-3 and N-4: text only, and the trailing `..` / N-4 / N-5 pins [6]-[9].
- The two developer-worded messages are one `bundle: FAIL (stage out: ...)` line each (stage_die at :485 and :487). They
  match A4 `^bundle: FAIL \(stage out: .+\)$` (the nested parentheses are fine). On the mkdir path, mkdir's own
  `mkdir: cannot create directory ...: File exists` line comes first. It is not a `bundle:` line, and it was the same in
  rework 1. The rows count only `bundle: FAIL` lines.
- Header :32-34 describes O-17 (1) and (2) correctly. The comment at :479-483 matches the code.
- Quoting and `set -e`: `{ ...; } || stage_die` and `chmod ... || die` are both safe under `set -euo pipefail`. No
  new unquoted expansion.

## Success-path lines changed (for O-17 (5))

Lines the success path runs that the rework-2 diff touches, in working-tree numbering:

| Line | Change | Runs on the Q79 path (created --out)? | Effect on a successful run |
|---|---|---|---|
| :146 | `created=1` added (was `created=0` at old :446 plus the re-test at old :449) | yes | same value: --out was absent at both points |
| :148 | `created=0` added in the given-out branch | no (given only) | same value as the old re-test |
| old :431 | the `-ge 1` count check removed | yes (it was) | none: always true after :434 |
| :485 | the mkdir failure message only; `mkdir -- "$out"` is unchanged | yes | none |
| :486-487 | new `else` branch: `[ ! -L "$out" ] && [ -d "$out" ]` | no (given only) | none: the test is true, with no side effect |
| :687-688 | `chmod` gains an or-die and moves before `record_made=1` | yes | none: same chmod, same flag; `record_made` is read only by the cleanup, which does nothing at rc=0 |
| :32-34, :122-123, :479-483 | comments | - | none |

No tag, save, copy, index, notices or manifest line changed. The developer handoff line (:174) is right in substance.
It does not list :146/:148 (the moved assignments) or the removed always-true check.

On behaviour, the Q79 record stands: every changed line on its path gives the same value or effect. The verify-full
offline check ran this exact file's success path green.

By the letter of O-17 (5), though, the diff does "reach a line the success path runs" (:146, :485, :687-688), so its
own condition for re-running R10 is met. Whether to re-run (about 3 minutes; dist/ke-q79-sources is kept) or to accept
this equivalence argument is the orchestrator's call. I do not block on it.

## Verdict: APPROVED (developer rework closed; 0 blocking developer findings)

The commit is still blocked on documenter items (B-2, N-2, N-11); see "Ready for commit" below. Two new non-blocking
findings follow (N-9 withdrawn).

## Findings in the rework-2 lines (non-blocking)

- **N-7 (info, for security; pre-existing, not a regression). scripts/bundle.sh:685-688.** As uid 0, a link to a
  non-regular file planted at the record path in the window is written through: noclobber's exception for non-regular
  files lets the write open it, and the `chmod` then succeeds and changes the target's mode.
  - Probe, ke-gates image as root: /dev/null goes from `crw-rw-rw-` to `crw-r--r--`. The run then sets `record_made=1`,
    exits 0 and prints `release record: <path>`, which is a link to /dev/null.
  - The I-14 row skips at uid 0 by design.
  - Only someone who can write the parent of --out can plant the link, and that person can replace the record after the
    run anyway. So this is same-trust; the only extra effect is root changing a device's mode.
  - Optional fix: before the chmod, refuse a record that is not a regular non-link file:
    `{ [ -f "$record" ] && [ ! -L "$record" ]; } || die "the release record $record is not a regular file; no bundle written"`.
    `record_made` stays 0, so the link is left (O-17 (2)).
  - Rework-1 ran the same chmod with no guard.
- **N-8 (nit, optional). scripts/bundle.sh:486-487.** The given-out re-check does not re-check that --out is still empty.
  - Probe: files that appear in a given --out between :151 and the first write are adopted. On failure the O-10 cleanup
    removes them (:461); on success they reach the manifest walk.
  - It is the operator's own given directory, and O-17 (1) rules only "a real directory (not a link)", so no action is
    required.
  - Optional fix: append `&& [ -z "$(ls -A -- "$out")" ]` to the re-check, with the same `stage out` line.
- **N-9 withdrawn.** The tester's rework-2 heading date, 2026-10-30, is the UTC date: log_event stamped this review
  2026-10-30T01:10Z. No action.

## Rulings checked (O-17)

| Rule | Done as ruled | Pin / control |
|---|---|---|
| (1) `created` decided once in the early block; re-test gone; given re-check (real dir, not link); late dir or link refused `stage out`, nothing written; trailing `..`, N-4, N-5 rows | yes | dir row + [2]; created-link row; given-link row + [3]; [6] [7] [8] [9] |
| (2) `record_made=1` after `chmod`; `chmod` or-die; the cleanup never removes an unwritten record | yes | I-14 row (2 subTests) + [4] [5]; root case N-7 (info) |
| (3) N-3 dead check, N-4 jq comment; N-5/N-6 info | yes | text |
| (4) B-2, N-2, N-11 documenter at close; R14 names quickstart.md | pending (documenter) | see carried |
| (5) Q79 record stands if the success path is untouched | behaviour untouched; letter of (5) met (see table) | orchestrator's call |

## Carried items

| Item | Status | Note |
|---|---|---|
| r1 B-1 (`created` re-tested) = security I-13 | **closed** | O-17 (1); :146/:148, :484-488; rows + [2] [3] |
| r1 B-2 (docs/quickstart.md :69, :78 `bundle.sh --out ...` exits 2; no fetch step, no `--sources`, no `mkdir -p dist`) | **open, documenter at close; commit-blocking** | O-17 (4); quickstart.md is unchanged (no `git status` entry) |
| r1 N-1 (trailing `..`, N-4, N-5 unpinned) | closed | [6] [7] [8] [9] |
| r1 N-2 (`./x` and `..` relative forms, cwd `/` -> `//x` refused; README silent) | **open, documenter at close** | O-17 (4); README:126 now says the parent must exist, but nothing on `.`/`..` segments or cwd `/` |
| r1 N-3 (dead `-ge 1`) | closed | removed after :435 |
| r1 N-4 (jq comment) | closed | :122-123 |
| r1 N-5 (partial record on ENOSPC left) | info, no action | O-17 (3) |
| r1 N-6 (signal between mkdir and `wrote=1`) | info, no action | O-17 (3) |
| security I-14 (non-regular record link) | closed | O-17 (2); uid-0 residue N-7 (info) |
| U9b N-11 (README "(Updated 2026-10-27, documenter, status)") | **open, documenter at close** | still at README.md:47 |
| U9b N-8 = security I-7 (FIFO/device swap in --sources) | deferred | O-16 (8) |
| U9b N-10 (size.md, index counts) | closed by the Q79 bundle half | u9/full-bundle-run.txt, size.md (O-17 (5) caveat above) |
| security I-11 (path-only overlap, bind-mount alias) | deferred | O-16 (8) |
| security I-12 (sample warning at install) | deferred | O-16 (8), U10 |
| U9a N-1, N-2 (sbom_check policy entries) | deferred | O-16 (8), U10 with a design row |
| U9a N-6, N-8, R1-N1, R1-N2 | open, optional | out of U9b scope (sbom_check.py unchanged) |
| U9a R1-N3 = security I-5 | open, security | unchanged |

## Ready for commit

From the reviewer's side, the rework-2 code and tests are ready. There is no further developer round, and N-7/N-8 are
optional.

Before the U9b commit:
- The documenter must:
  - (B-2) Rewrite docs/quickstart.md:69 and :78 to the U9 order: `mkdir -p dist`, `bash scripts/build.sh`,
    `bash scripts/bundle_fetch.sh --set full --out dist/sources-<arch>`, then
    `bash scripts/bundle.sh --out dist/bundle-<arch> --sources dist/sources-<arch>`. State that the parent of --out
    must exist.
  - (N-2) Add one README and quickstart sentence: relative --out/--sources resolve against the cwd and may not contain
    `.` or `..` segments (write `dist/x`, not `./dist/x`; do not run from `/`).
  - (N-11) Replace the stale "(Updated 2026-10-27, documenter, status)" at README.md:47.
- The orchestrator also decides the O-17 (5) R10 question above, runs A34 (R13) and its own `scripts/verify.sh full`.
  The quickstart edit re-enters the shipped `app/docs/` tree, so that run covers it.

## Probe (read-only; ke-gates:wt-33a132fbfdd7, `--network none`, scratch mounted read-only, nothing on the host)

The script is session scratch `rev-u9br2/probe.sh`. It reproduces the shapes at bundle.sh :685-687 and :484-488.

    == uid 0: record link -> /dev/null, noclobber write + chmod (bundle.sh:685-687) ==
    before: crw-rw-rw-
    noclobber write through the link: ok
    chmod: ok (record_made=1 next; run exits 0, release record printed)
    after:  crw-r--r--
    == given --out, emptied check passes, then refilled before the first write (bundle.sh:484-488) ==
    early check: empty
    re-check passed; wrote=1 with operator.txt in --out
    == created --out, mkdir onto a planted link: stderr lines ==
    mkdir: cannot create directory /tmp/tmp.MudoNDQHCx/c-amd64: File exists
    bundle: FAIL (stage out: --out appeared after its check (...): /tmp/tmp.MudoNDQHCx/c-amd64; no bundle written)
    --- as uid 10001
    noclobber write through the link: ok
    chmod: changing permissions of rec: Operation not permitted
    chmod failed -> die
    after:  crw-rw-rw-
