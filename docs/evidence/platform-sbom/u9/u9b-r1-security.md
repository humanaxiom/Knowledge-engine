# U9b rework 1 of 5: security re-audit of the L-4 scope (security, 2026-10-29)

Scope: the L-4 scope of `git diff HEAD -- scripts/bundle.sh scripts/offline_check.sh README.md` on
`agent/platform-sbom` (HEAD 1a7a9e2), read against design-notes O-16 (1)-(4), (6), (7) and the "O-16 precision"
paragraph. Also read: the new rows in `tests/test_bundle_sources.py`, the `_strip_messages` change in
`tests/test_sbom_generator.py`, my `u9b-security.md`, and the rework-1 tester and developer sections of the handoff.
Probes are appended to `u9b-security-probes.txt` under "rework 1". They ran in ke-gates:wt-33a132fbfdd7 with
`--network none` and uid 10001, against the real script and `tests/fake_docker.py`. Symlinks were made only in the
container's /tmp. The Git Bash probes on the host used plain directories only.

## Verdict: PASS (L-4 closed; no open critical or high)

L-4 is closed. Every `..`, `.` and empty-segment form is refused before any docker call except `info`. That covers
my P7, P9 and P1c, the reviewer's forms, and the new edge cases below. Nothing is created and no watched tree
changes. One residual of the I-10 race is open (**I-13, medium, non-blocking**). It is the same root cause as
reviewer B-1 in `u9b-r1-review.md`, which already sends the rework back, and the same one-line fix closes both.

## L-4: closed

- **Path rule (O-16 (1); l.96-109).** Every trailing slash is stripped by the loop. A value that is empty after
  that gets the usage line with exit 2 (`--out /`, `///`, `--sources //`: P10 is now exit 2, per O-16 precision
  (b)). `segment_bad` then refuses `*//*`, `*/./*`, `*/.`, `*/../*` and `*/..`. `--out` is refused as
  `stage out` and `--sources` as `stage sources-check`, both exit 1, before `docker info`.
  - Probe R1 used the real script. Every case below exited 1 with `docker-beyond-info=0` and `writes=0`. No
    watched tree (victim, --sources, its copy, `b-amd64`, the link target) changed, and no directory was created:
    - P7 `<missing>/../victim-amd64` (the victim and its record are unchanged)
    - P9 `<missing>/../src/x-amd64`
    - P1c `<missing>/../b-amd64`
    - `<existing>/../y-amd64`
    - `<t>//x`, a leading `//`
    - trailing `/.`, `/./`, `/..`
    - `<link>/.`
    - relative `./x`, `../x`, `.`, `..`
  - For `--sources`:
    - `<holder>/../<fetch>`, `<t>/./<fetch>`, `<t>//<fetch>`, `<link>/.` and `<fetch>/..` are refused as
      `stage sources-check`.
    - P13 `<link>//` and `<link>///` are now refused as "is a symlink" (I-9 closed).
    - `//` gets the usage line, exit 2 (I-8 closed).
  - `--out <link>//` is refused "is a symlink". `--out <victim>//` is refused "not empty".
  - Control: `--out <dir>///` with `--sources <fetch>///` bundles to `<dir>`.
- **Is `segment_bad` complete? Yes, for what it is for.**
  - F1 tested it verbatim. A leading `./` or `../` becomes `$PWD/./` or `$PWD/../`, which is refused. A final
    `..`, a lone `.` and `/.` / `/..` are refused.
  - `...`, `.b`, `b.`, `..b` and `b..` are names, and pass. A segment `..<newline>` is a name, not `..`, and
    passes; on the real script it then fails the plain `mkdir` because its parent is missing.
  - The rule fails closed in two cases:
    - From `PWD=/`, a relative `--out` becomes `//x` and is refused (an operator nuisance, not a risk).
    - On Git Bash, `C:/...` is not absolute to the script. It becomes `$PWD/C:/...`, whose parent is missing, and
      the plain `mkdir` refuses it.
  - Backslash forms on Git Bash (W1, W2). MSYS treats `\` as a separator and resolves `..` lexically, the same
    way for `-e`, `cd -P`, `dirname` and `mkdir`. The checks therefore see the same directory the writes reach:
    `<S>/missing\..\existing-amd64` tests as existing, and the plain `mkdir` lands there. The overlap fragment run
    verbatim refuses all three backslash forms aimed into `--sources`. There is no check/write mismatch, so the
    L-4 class does not occur. `segment_bad` does not see `\` segments, and on Linux `\` is a literal character.
- **The claim (O-16 (2); l.480-483).**
  - A plain `mkdir --` refuses an existing directory, a link to a directory, a dangling link, a file and a missing
    parent (F3, verbatim).
  - The real script refuses a missing parent as `stage out` with no write and no ancestor created (R1
    `a/.../b`). A dangling link that appears at `--out` is refused the same way, and its target is never created
    (R2).
  - The window between the `created` test and the `mkdir` is now a few lines with no docker call. A directory
    that appears there is refused, not adopted. See I-13 for the window before the `created` test.
- **The record under noclobber (O-16 (3); l.679-681).** R3 used the real script, with an object planted at the
  record path while `notices` runs, for both a created and a given `--out`:
  - Planted as a regular file, a link to a regular file, a dangling link or a directory: the write is refused.
    The run exits 1 with `bundle: cannot write the release record ...`. The planted object and the link's target
    keep their bytes, the dangling target is never created, and `--out` is removed or emptied.
  - Bash's `noclobber_open` uses O_EXCL when stat fails, so a dangling link cannot be followed into a new file.
  - M-3 and L-4 (c) are closed. The remaining non-regular-target case is I-14.
- **Cleanup bound (l.450-470).**
  - `rm -rf -- "$out"` runs only when `created=1` and this run's `mkdir` succeeded. If the `mkdir` fails, the run
    calls `stage_die` before `wrote=1`, and the cleanup does nothing.
  - The given-out branch removes only the contents of `--out`. `find` does not follow a start-point link.
  - The record is removed only when `record_made=1`.
  - Failures print `bundle: warning: ...` and carry on (N-4).
  - Apart from I-13 and I-14, nothing outside the run's own writes was touched in R1-R3.
- **Tag, save and copy (O-16 (4)).** Each now ends in `die` or `stage_die`, after `wrote=1`, so the O-10 cleanup
  runs. No new path reaches `rm`.

## New findings

### I-13 (medium, non-blocking): I-10 narrowed, not closed; `created` is re-tested at l.449, against O-16 (2)

- **The rule.** O-16 (2) says "`created` is decided from the l.126 check, not re-tested". The code instead
  re-tests with `if [ ! -e "$out" ]; then created=1; fi` at l.449. That is after the licence-notices run and
  after `sources-check` re-hashes the whole set (about 1.18 GB for `full`), so the window lasts seconds to minutes.
- **What R2 showed on the real script.** A directory, or a link to a directory, that appears at `--out` in this
  window gets `created=0`. It is adopted as a given `--out`, with no new symlink, empty or overlap check:
  - Directory plus a file, no later failure: the run passes. The other process's `other.txt` ships in the bundle
    and is listed in `MANIFEST.sha256`, and the record is written.
  - Directory plus a file, with a later failure (`notices`): the cleanup's `find` deletes `other.txt`, a file
    this run did not write.
  - Link to a directory, no later failure: the whole bundle is written through the link into its target, the
    record is written, and the l.140 symlink refusal and the U9-1 overlap check never apply. The target could be
    `--sources`.
  - Link to a directory, with a later failure: a partial bundle (`LICENSE`, `NOTICE.md`, `app/`, `bundle.json`)
    is left in the link's target. The `find` does not follow the link, so "a failure leaves no bundle behind"
    does not hold.
- **Why medium, not high.** It needs a second same-uid actor during the run, and no privilege boundary is
  crossed. The likely accident is two `bundle.sh` runs with the same `--out`. The second run adopts the first's
  directory. If the second run then fails (for example, noclobber refuses the record the first run wrote), it
  empties the first run's bundle and leaves that run's record pointing at nothing.
- **Fix (= reviewer B-1).** Decide `created` in the l.140-150 `--out` block, from the same `-e` test, and delete
  l.449. A directory, link, dangling link or file that appears at any point before the claim is then refused by
  the plain `mkdir` (F3), with nothing written.
- **Rows to add.** One row is a directory that appears at `sources-check`: refused as `stage out`, its file
  untouched, nothing written. The other is the same for a link to a directory: the target untouched.
- Re-audit after the fix: only l.140-150 and l.446-483.

### I-14 (low, info): a non-regular object planted at the record path is written through, then removed by the cleanup

- **The case.** R3, "link->/dev/null". `set -C` opens an existing non-regular file without O_EXCL; this is
  bash's documented noclobber exception. The write succeeds and `record_made=1` is set. Then `chmod 0644` (l.682)
  fails with EPERM on the link's target, and `set -e` ends the run with exit 1 and no `bundle:` line. The
  cleanup's `rm -f -- "$record"` removes the planted link, which this run did not create.
- **Impact.** No regular file is overwritten or deleted. It needs a same-uid racer.
- **Optional fix.** Write the record to a `mktemp` file beside `--out`, then `ln` it to `$record` (atomic, fails
  if the name exists) and remove the temp file. Or set `record_made=1` only after the `chmod`, and add
  `|| die` to the `chmod`.

## Checked and holding

- **No new URL or host literal in `scripts/`.** The only hits on lines the diff adds are `bundle.sh` and
  `bundle_fetch.sh`, which a `.sh` TLD pattern matches by mistake.
- **No gate or test weakened.**
  - The `_strip_messages` widening (`stage_die\s+\S+` added to the alternation) applies the existing "strip to end
    of line" rule to one more message helper. On the current `bundle.sh` it strips 124 lines, against 93 before.
    Every stripped tail containing `docker`, `pull` or `$(` is message text: `printf '%q'`, `dirname`,
    `basename`, or prose such as "pull it first". So the PSC-20 host-tool and no-pull scan still sees all code.
  - A `pull` before a `stage_die` on the same line survives the strip, and
    `test_strip_messages_strips_the_text_of_stage_die` pins this.
  - The reviewer confirms GREEN changed no test (hash match with `u9b-r1-controls.txt`). `scripts/verify.sh` and
    CI are unchanged.
- **Secrets.** I grepped the whole `git diff HEAD`, `tests/test_bundle_sources.py` and every `u9b-r1-*` evidence
  file for AWS, GitHub, Slack and OpenAI-style keys, private-key blocks, credentialed URLs, `password=`,
  `api_key=`, bearer tokens and signed query strings. Nothing matched.
- **Profile paths and SIDs.** The rework evidence (`u9b-r1-*.txt`, `u9b-r1-controls.txt`, `u9b-r1-review.md`,
  `sample-bundle-run.txt`) and the appended probe transcript hold no profile path or SID. The host scratch path is
  redacted to `<S>`. They also hold no `KE_MODEL_UPSTREAM` or `KE_EGRESS_ALLOWLIST` value: the full run skipped
  the model tests. Hosts and addresses in them:
  - loopback, the docker bridge (172.20.0.2), the public build-time download URLs, and a Temurin version string.
- **offline_check.sh** passes `--sources "$fetch_rel" --sources-set sample` with plain `dist/` paths (no `./`),
  which the path rule accepts. The full verify passed with it (`u9b-r1-green-verify-full.txt`).

## Carried items

| Item | Status |
|---|---|
| L-4 (unnormalised --out/--sources, adoption + rm -rf, record overwrite, overlap bypass) | **closed** (R1, F1-F3, R3) |
| I-8 (`--sources //`) | closed: usage, exit 2 |
| I-9 (`<link>//`) | closed: "is a symlink" |
| I-10 (concurrent --out adopted) | narrowed to I-13 (open, medium) |
| I-7 (FIFO/device swap in --sources), I-11 (bind-mount alias), I-12 (sample warning in install) | open, deferred by O-16 (8) |
| U9a I-5, I-6 | open (info), unchanged |
| M-3 (record overwrite) | closed by noclobber; I-14 is the non-regular remainder |

## For the orchestrator and the developer

- Security does not block. Reviewer B-1 still sends the rework back, and its fix also closes I-13.
- After the fix, security re-checks only l.140-150 and l.446-483, together with the two R2-style rows above.
- I-14 is optional.
