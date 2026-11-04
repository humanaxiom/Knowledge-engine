# U9b rework 2 of 5: security re-read of the O-17 scope (security, 2026-10-29)

Scope: `git diff HEAD -- scripts/bundle.sh` on `agent/platform-sbom` (HEAD 1a7a9e2, bundle.sh sha256 `9624710b...`).
The rework-2 lines are l.30-34 (header), l.146-148 (`created` decided once), l.479-489 (the claim and the re-check),
and l.687-688 (`chmod || die`, then `record_made=1`). I read them against design-notes O-17 (1)-(3). Also read: the
four new rows in `tests/test_bundle_sources.py` (l.1286-1393), the rework-2 tester and developer sections of the
handoff, and my `u9b-r1-security.md`. The probes are appended to `u9b-security-probes.txt` under "rework 2". They ran
in ke-gates:wt-33a132fbfdd7 with `--network none` and `--cap-drop ALL`, against the real script and
`tests/fake_docker.py`. There were two runs: uid 10001, and uid 0 with CHOWN, FOWNER and DAC_OVERRIDE. Every link and
FIFO was made only in the container's /tmp.

## Verdict: PASS (I-13 closed; I-14 closed as filed; no open critical or high)

Two new findings are non-blocking:

- **I-15 (low).** A given `--out` is re-checked for type but not for emptiness.
- **I-16 (medium).** If the record's `chmod` succeeds (the running uid owns the target, or the run is root), a link
  to a non-regular file at the record path is written through and its target's mode changed. Under root, with a
  parent of `--out` that another user can write, that crosses a privilege boundary.

I-16 is older than rework 2: the write and the `chmod` came with O-16 (3). Rework 2 did not introduce it.

## I-13: closed (R4, real script)

`created` is now set once, at l.146-148, and the l.449 re-test is gone. Every object planted at the
`sources-check` call (the last docker call before the first write) was refused. Each refusal printed exactly one
`bundle: FAIL (stage out: ...)` line and exited 1. There were 0 tag or save calls, no record and no `.ke-sbom.*`
left, and the planted object and its target kept their bytes:

| --out | planted | line | state after |
|---|---|---|---|
| absent | dir + operator.txt | "appeared after its check" | dir holds only operator.txt, bytes unchanged |
| absent | link to a dir | "appeared after its check" | link kept; target snapshot unchanged |
| absent | dangling link | "appeared after its check" | link kept; target never created |
| absent | regular file | "appeared after its check" | file bytes unchanged |
| given | replaced by a link to a dir | "was replaced after its check" | link kept; target unchanged |
| given | replaced by a link to a file | "was replaced after its check" | link kept; target unchanged |
| given | replaced by a regular file | "was replaced after its check" | file unchanged |
| given | removed | "was replaced after its check" | nothing created |

The controls (absent and given, no race) exit 0 with a manifest and a record. The cleanup cannot fire on these
refusals, because `stage_die` runs before `wrote=1`.

## I-14: closed as filed (R5, uid 10001)

- **Record planted as a link to /dev/null.** Both a created and a given `--out` were run.
  - The run exits 1 with `bundle: cannot set the mode of the release record <path>; no bundle written`.
  - The link is kept, so the cleanup no longer removes it (`record_made=1` now comes after the `chmod`).
  - /dev/null's mode and rdev are the same before and after.
  - `--out` is removed (created) or emptied (given).
- **Record planted as a link to a regular file.** noclobber refuses it with `bundle: cannot write the release record
  ...`. The link is kept, the target keeps its bytes, and `--out` is removed or emptied.
- **Line format.** Neither line uses the A4 `FAIL (stage ...)` form. Both are a `bundle:` line naming the record,
  which is what O-17 (2) and the tester's reading ask for.

## The window between the re-check and the first write

`mkdir` is not a bash builtin. After the `[ ! -L ] && [ -d ]` test (builtins), the script runs `wrote=1` and then
forks and execs `/usr/bin/mkdir -p -- "$out/images"`. That leaves a window of about 1 ms in which a swapped
`--out` link would be followed. On the created branch the same window sits between `mkdir -- "$out"` and that call.
The window is **acceptable**:

1. The accident this guards against cannot hit it. A second `bundle.sh` run or an operator never creates a link,
   and a same-name directory is refused by the plain `mkdir` or by the early emptiness check. Only a deliberate
   racer can hit a 1 ms window.
2. Narrowing it further buys nothing. Every later write re-resolves `$out` by path for the whole run, which lasts
   minutes (R7). A racer who can rename entries in the parent can redirect writes at any point, not only in this
   window. Only fd-relative I/O (openat with O_NOFOLLOW) would close that, and bash does not have it. The re-check
   closes the slow window, which is the realistic case.
3. The cleanup never follows a link (R7, a swap at the first `tag`, then a later failure):
   - created: `rm -rf -- "$out"` removes only the link. The target keeps its `keep.txt`.
   - given: `find` does not descend a link given as its start point, so the link and the target are left.
   - In both, files the run wrote through the link stay in the racer's target. That is the racer's own directory.
4. For a racer with the same uid, no boundary is crossed. A racer with a different uid against a root run is I-16.

## New findings

### I-15 (low, non-blocking): a given --out is re-checked for type, not for emptiness or a claim

- **R4.** A file written into a given `--out` at `sources-check`, or a fresh real directory with a file that
  replaces it, passes the re-check and is adopted:
  - with no later failure, the run exits 0, and `other.txt` ships in the bundle and is listed in
    `MANIFEST.sha256`;
  - with a later failure (`notices`), the O-10 cleanup's `find` deletes `other.txt`.
- **The realistic case.** Two runs are given the same empty directory. Both pass the early check, both write, and
  the one that loses the noclobber record empties the directory: the other run's bundle goes, and its record is left
  pointing at nothing.
- **Why low.** This is within O-17 (1) ("real directory, not a link") and the O-10 contract (the run owns the given
  directory's contents). No link is followed, the impact stays inside the directory the operator handed over, and a
  same-uid writer can add files to `--out` at any point of a run anyway.
- **Optional fix.** In the given branch, before `wrote=1`:
  - repeat the `ls -A` emptiness test;
  - claim with a plain `mkdir -- "$out/images"`, which fails if a concurrent run claimed first;
  - make the existing `mkdir -p -- "$out/images"` conditional.

### I-16 (medium, non-blocking; older than this rework): the record write and `chmod` follow a link to a non-regular file when the `chmod` can succeed

- **How it happens.** bash's noclobber opens an existing non-regular file without O_EXCL, with O_TRUNC. O-17 (2)
  relies on the `chmod` then failing, and it fails only when the running uid neither owns the target nor is root.
- **R5 (uid 10001).** A link to a FIFO this uid owns, with a reader attached:
  - The run exits 0 (`bundle written`). The record bytes go to the reader.
  - The FIFO's mode goes from 0600 to 0644.
  - The "release record" is a link to a FIFO.
  - Without a reader, the open blocks and the run hangs.
- **R6 (uid 0).** A link to a FIFO owned by uid 10002, mode 0600, gives exit 0. Root wrote the record into it and
  changed its mode to 0644.
- **What it takes.** On a build host where `bundle.sh` runs as root (for example with `sudo` for the docker
  socket), another local user who can write in the parent of `--out` can plant the link at any time during the
  minutes-long run. Root then truncate-writes about 90 bytes into, and sets mode 0644 on, any FIFO or device. A block
  device would be corrupted at offset 0 and left world-readable. The same precondition lets that user swap `--out`
  after the re-check (R7), so root writes the bundle's fixed-name files into any directory.
- **Why medium.**
  - Likelihood is low: no doc tells the operator to run as root, `--out` normally sits under the operator's own
    `dist/`, and `fs.protected_symlinks=1` (set in the gates VM) blocks the link in sticky world-writable
    directories such as /tmp.
  - Impact is high: root writes to an arbitrary device.
- **Fix, to rule at U9 close or as a U9b item.**
  - (a) Write the record to a `mktemp` file beside `--out`, `chmod` that file, then
    `ln -- "$tmp" "$record"`. link(2) never follows the new name and fails if it exists. Remove the temp file afterwards.
  - (b) Refuse a parent of `--out` that is not owned by the running uid, or that is group- or world-writable, or
    refuse uid 0 outright. (b) also covers the R7 swap.
  - Test rows: a FIFO link at the record path (refused, link kept), and a run as uid 0, or a parent writable by
    another uid (refused before any docker call but `info`).

## Checked and holding

- **The new rows.** They pin what R4 and R5 showed: the directory, the link at an absent `--out`, the given
  `--out` replaced by a link, and the /dev/null record link with both subtests. The I-14 row skips under uid 0,
  correctly. These cases have no row, but the same l.487 expression refuses them in R4: a given `--out` replaced by
  a link to a file, removed, or replaced by a regular file. That is information only.
- **No gate or test weakened.**
  - Every test file and `tests/fake_docker.py` has the same sha256 as the tester's RED (`u9b-r2-controls.txt`).
    Only `scripts/bundle.sh` changed at GREEN.
  - `scripts/verify.sh` and `.github/workflows/ci.yml` are unchanged against HEAD.
- **No new URL or host literal in `scripts/`.** The only pattern hits on added lines are the file names
  `bundle.sh`, `bundle_fetch.sh` and `offline_check.sh`.
- **Secrets, profile paths and SIDs.** I grepped `git diff HEAD -- scripts/ tests/`,
  `tests/test_bundle_sources.py` and every `u9b-r2-*` evidence file for AWS, GitHub, Slack and OpenAI-style keys,
  private-key blocks, credentialed URLs, `password=`, `api_key=`, bearer tokens, `KE_MODEL_UPSTREAM` and
  `KE_EGRESS_ALLOWLIST` values, profile paths and SIDs. Nothing matched. The URLs in the verify logs are the public
  build-time downloads and loopback. The appended probe transcript holds no host path: the scratch dir is
  `<scratch>` and the container temp dir is `<t>`.
- **N-3 and N-4.**
  - N-3: the dead `-ge 1` is gone. The empty-listing guard is l.434, `[ -n "$check_text" ]`.
  - N-4: the comment edit is text only.
  - No new path reaches `rm`.

## Carried items

| Item | Status |
|---|---|
| I-13 (created re-tested; late dir or link adopted) | **closed** (R4) |
| I-14 (link to /dev/null at the record written through, cleanup removes it) | **closed as filed** (R5); remainder is I-16 |
| I-15 (given --out: no emptiness re-check or claim) | new, low, open |
| I-16 (record write and chmod through a link to a non-regular file when chmod can succeed; root case) | new, medium, open |
| I-7, I-11, I-12 | open, deferred by O-16 (8) |
| U9a I-5, I-6 | open (info), unchanged |
