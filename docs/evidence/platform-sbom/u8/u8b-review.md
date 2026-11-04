# U8b review (reviewer, 2026-10-28)

Scope: `git diff HEAD` on `agent/platform-sbom` (HEAD 780d523) plus the staged
`scripts/bundle_fetch.sh` (100755 in the index) and the untracked
`tests/test_bundle_fetch.py`. U8a's client `scripts/sources_fetch.py` at HEAD was
read for the FAIL-line question only. Read first: the handoff (U8a summary,
tester U8b RED, developer U8b GREEN); design-notes "N4 amendment, U8" items
1-15 and O-1..O-7; PSC-23 U8-1..U8-14; ADR-KE-016 "Amended U8"; Q73/A73.

**Verdict: CHANGES REQUESTED** (2 blocking, both small, each needs a RED row first).

Probes (read-only, fake docker, ke-gates:local, network none):
`u8/u8b-review-probes.txt`. The U8b rows pass read-only (61 tests OK); 150
random argument lists show no exit-2 or injection defect; the edge probes, run
as non-root uid 10001, found B-1.

## Blocking

**B-1. The `--out` emptiness check fails open when `ls` fails** (`scripts/bundle_fetch.sh` l.80).
The check runs `ls -A` inside a command substitution inside a bracket test.
A failing `ls` leaves the substitution empty, and the bracket test's status is
all that `set -e` sees. Probe (uid 10001): a non-empty directory with mode 0300
(writable and searchable, not listable) is accepted as `--out`:
- With a good fetch: exit 0; the fetched files and `fetch.json` sit beside the operator's `operator.txt`.
- With a failing fetch: exit 1; six verified sha256-named files are left beside
  `operator.txt`, because the trap's `find ... || true` (l.103) cannot list the
  directory.

This breaks U8-1 (a non-empty directory exits 1, untouched) and U8-6 (a given
`--out` is returned empty, nothing of the run remains). No operator data is
lost, and U9 would refuse a directory with no `fetch.json`. But it is a
fail-open guard at a boundary, and the fix is one line: assign the listing to a
variable with `|| fail "stage out: cannot list <out>"`, then test the variable.
RED row (tester): add an unlistable non-empty directory to
`test_bundle_fetch_refuses_an_unsafe_out`, expecting exit 1, one FAIL line and
the directory untouched. Root bypasses the mode bits, so use a named skipTest
when uid 0; the gates image runs uid 10001. `bundle.sh` l.85 has the same
pattern: see N-9, not U8b's scope.

**B-2. The cleanup clears INT/TERM/HUP instead of ignoring them** (l.95 `trap - EXIT INT TERM HUP`).
A second signal during `compose down` or the `rm -rf` (a double Ctrl-C, or a
supervisor's TERM after INT) kills the cleanup:
- The `ke-fetch-<hex>_default` network and the run container can leak. This is
  the class of leftover that exhausted the Docker address pools and blocked
  U8a's full verify.
- A created `--out` can be left with verified files in it.

Design item 3 says the trap is "as scan.sh, D4". `scan.sh` l.55-56 ignores INT
and TERM, then clears EXIT (security I-4), and pins this with
`test_scan_cleanup_ignores_signals_before_clearing_exit_trap`. Fix: in the
cleanup, ignore INT, TERM and HUP first (empty-string trap), then clear EXIT.
RED row: mirror the scan.sh row (static order, or a second signal sent during a
slow fake `down`).

## Non-blocking

- **N-1 (the developer's errno question): does not block.** The client's FAIL
  line reads `<host>: <file>: OSError: <url>`, which meets U8-4's
  `<host>: <file name>: <why>`. The run fails closed, by name, with no retry.
  The text is U7b's reviewed `sources_resolve._transport` form, shared with the
  lock tool. The errno (101 here) cost a hand diagnosis.
  - Follow-up: append `errno=<int>` when the exception is an OSError with an int
    errno. Use the int only, never strerror or str(exc), which can carry paths.
  - Do it in `_transport`, through RED and a security look, because it is shared
    network code. Not in U8b.
- **N-2.** Also unset `DOCKER_DEFAULT_PLATFORM` and `COMPOSE_ENV_FILES`, as `scan.sh` l.41 does.
  - A caller's `DOCKER_DEFAULT_PLATFORM` set to the other arch makes the
    generator pull take that arch under the index digest.
  - `bundle.sh` then refuses it, so this fails closed, but the refusal names a
    different step.
  - It fits "takes no caller key". It can ride the B-1/B-2 round.
- **N-3.** Cleanup race on a "given" `--out`. The cleanup empties any existing
  directory that is not a link when created=0. That includes an `--out` that was
  absent at stage 2 and appeared before the `mkdir` (l.114): the `mkdir` fails,
  the script exits 1, and the cleanup empties a directory it never checked. The
  window is narrow. Record given=1 at stage 2 and empty only then; this fits
  naturally with B-1.
- **N-4.** Argument handling, all failing closed or harmless and all the same as
  `bundle.sh`:
  - An explicit empty `--arch` is taken as absent (A75 says another value exits 2).
  - A repeated flag silently takes the last value.
  - `--out /` fails with "cannot create" and an empty name, because the trailing
    slash is stripped.
  - Optional.
- **N-5.** Test gaps.
  - O-5's "exits with that code" is pinned only for rc 1. A row where the run
    exits with another code (2, or a compose 125) would pin the pass-through.
  - The script's line names `sources_fetch.py` as the one that exited also when
    compose itself failed. That is a wording nit.
- **N-6.** `sources_lock.sh` l.180 reports every `mkdir` failure (EACCES, a
  vanished evidence dir) as "sboms exists". A truer text needs a re-pin of
  `test_sources_lock_refuses_an_existing_sboms_dir`. Optional.
- **N-7 (process, orchestrator).**
  - R8's `u8/expected.md` (expected values recorded from the committed lock
    "before any real run") does not exist. R7's full verify has already made one
    real fetch attempt, which failed on the first file, so nothing could be
    compared. Record it before the rerun.
  - Still outstanding for the gate (not for this review):
    - a real sample run with `ok` lines (U8-14 / R9);
    - the O-1 full-set run;
    - `size.md` and `hop-hosts.md` (O-2);
    - security R11, A34 R12, the orchestrator's full verify.
- **N-8 (scope).** The untracked `docs/knowledge-engine-claude-code-prompt.md`
  and `docs/handoffs/NEXT-SESSION.md` are not U8b. Keep them out of the U8b
  commit unless the orchestrator means them to ride.
- **N-9 (carry to U9).** `bundle.sh` l.85 has the same fail-open `ls -A` as B-1.
  U9 reworks `bundle.sh`'s directory handling (`--sources`), so fix it there with
  its own row.
- Observation, not a finding: the real run shows a blank line between the
  client's FAIL line and the script's line. It comes from compose's progress
  output on stderr. On fake docker the script adds exactly one line (probe part 4).

## Conformance, by number

- **Item 3 / U8-1, U8-2, U8-6.**
  - Arguments: exit 2 with a usage line and no docker call; the random probe
    gave 143/143 invalid lists exit 2 with no `--out`.
  - Order: docker on PATH, then arch, then `--out`, then images and uid:gid,
    then pull, fetch and record.
  - The `ke-fetch-<8 hex>` project, the dummies, `--env-file .env.example`, and
    `-f` and `-p` the script's own; COMPOSE_PROFILES, COMPOSE_PATH_SEPARATOR and
    COMPOSE_FILE unset.
  - No URL or host literal; no `-e` on any docker line; `--pull never`; the
    markers; `fetch.json` a regular file.
  - Trap on EXIT/INT/TERM/HUP: removes a created `--out` and empties a given
    one, except the B-1 and B-2 cases.
  - set -euo pipefail, quoting OK, printf %q on daemon strings.
- **O-4: met.** Exit 1 naming both arches, before `--out` and before any pull.
- **O-5: met.** The client's line, then exactly one script line, then the
  client's code as the exit status (probe part 4; test row).
- **O-6: met.** README: "what the bundle ships from the source-shipping step on
  (platform-sbom U9); bundle.sh does not read it yet". `bundle.sh` header: "from
  U9 on". Neither claims sources ship now.
- **O-7: met.** RED fast evidence. O-1 and O-2 are pending on the real runs
  (N-7). O-3 is the client's (U8a).
- **Item 3 service / U8-7: met.** Same hardening keys as `sources-resolve`
  (image, pull_policy never, user with the required-variable form, read_only,
  tmpfs /tmp, cap_drop ALL, no-new-privileges, literal env), with no
  network/ports/socket/extra keys. Exactly the five read-only binds plus /out;
  no checkout, no uv.lock, no /in. Header names both starters; bind-rule
  exemption exact.
- **Item 8 / U8-8: met.** Only the interim generator pull is replaced, at the
  same place; the base pulls are unchanged. `die` stops before `bundle.sh`. The
  directory is `dist/<project>-sources`, and the EXIT trap removes it on pass
  and fail. df is logged after the fetch; header stage list updated.
- **Item 9 / U8-9, U8-12: met.**
  - The `bundle.sh` refusal text and header.
  - `sources_lock.sh` copies the six SBOMs after lock-check decides (0 or 3),
    before the InRelease copies and the lock move. Links and non-regular files
    are refused, a failed copy fails, and the lock is unchanged.
- **A73: met.** The only CLAUDE.md change is the host-half sentence, verbatim
  from Q73 option 2.
- **Item 12 / U8-13: tests adequate apart from B-1, B-2 and N-5.**
  - Every U8b row named in item 12 exists.
  - The controls `u8b-controls.txt` show only the two renames plus new rows.
    Every test file's sha256 now equals the AFTER hash, so the developer edited
    no test.
  - Nothing is weaker than U8a: `test_sources_fetch.py` is unchanged, and the
    re-pins keep their events and substrings.
  - No test reads docs/evidence, and no test name holds a count.

## Rework round 1 (reviewer, 2026-10-28)

**Verdict: APPROVED** (code and tests; the real-run items R9/O-1/O-2, A34 and N-7 stay pending and are outside this verdict).

Scope (orchestrator): review B-1, B-2, N-2, N-3, N-5; security L-1, L-2; O-8.
Diff: `git diff HEAD -- scripts/bundle_fetch.sh` (staged, 100755), plus
`tests/test_bundle_fetch.py`. Re-run read-only as uid 10001: probes R1-1..R1-5
in `u8/u8b-review-probes.txt`.

- **B-1 closed.** Stage 2 assigns the `ls -A` output to a variable with
  `|| fail "stage out: cannot list ..."`, then tests the variable. Probe: the
  0300 directory is refused (exit 1, one FAIL line, only `docker info` called),
  and `operator.txt` is untouched, both with and without a failing fetch.
  Row: `test_bundle_fetch_refuses_an_unlistable_out` (ran in the gates image).
- **B-2 closed.** The cleanup now ignores INT, TERM and HUP first
  (empty-string trap), then clears EXIT, as scan.sh I-4 does. Rows: the static
  order (`..._cleanup_ignores_signals_before_clearing_exit_trap`) and a live
  second INT/TERM/HUP during a slow `down` (`..._cleanup_survives_a_second_signal`).
- **N-2 closed.** `DOCKER_DEFAULT_PLATFORM` and `COMPOSE_ENV_FILES` are unset;
  row `..._keeps_the_callers_platform_and_env_files_out`.
- **N-3 closed.** `given=1` is recorded only when stage 2 saw an empty
  directory. The cleanup empties only then, and a plain `mkdir` fails on a
  directory that appeared in between. Row `..._leaves_an_out_that_appears_after_the_check`.
- **N-5 / O-8 closed.** The compose exit code passes through unchanged. The
  script's line names compose for 125-127 and `sources_fetch.py` otherwise, and
  the client's output is never parsed. Rows: exit 2 passed through with exactly
  one script line; 125 named as compose.
- **L-1 closed.** Every trailing `/` is stripped, and a last component of `.`
  or `..` is refused before any docker call. Row covers `link//`, `link///`,
  `link/.`, `link/./` and `dir/.`.
- **L-2 closed.** `fetch_service_problems` gains an allowlist of the service
  keys and of each bind's keys. The denylist and every earlier check stay, so
  the oracle only gets stricter. Row `test_hardening_check_rejects_extra_service_and_bind_keys`.
- **Nothing weaker.**
  - Test-file diff against the pre-rework copy (sha256 `d3f84895...`) is
    additions only.
  - The tester's four hunks match `u8b-r1-controls.txt` (no test removed).
  - The one other hunk is the 8-line allowlist in `fetch_service_problems`.
  - Every other test file's sha256 is unchanged from the r1 controls,
    `fake_docker.py` included.
  - Random-argument probes, all invalid lists exit 2 with no docker call and no
    `--out`, no injection:
    - seed 20261028: 114 invalid lists of 120;
    - seed 4242: 187 invalid lists of 200.
  - Valid lists still fetch, and O-5 still yields exactly one script line after
    the client's FAIL line.
  - GREEN `u8b-r1-green-verify-fast.txt`: 1195 tests OK, 8 skips, all
    Windows-only rows. Every new row ran.
- **Header comment matches the code:** the stage 2 rules (stripping, `.`/`..`,
  unlistable, plain `mkdir`), the 125-127 naming, the cleanup's "given at
  stage 2" rule, and ignoring further signals.

Non-blocking, new:
- **R1-N1.** `..._names_compose_when_compose_itself_fails` asserts a non-zero
  exit, not exactly 125; O-8's pass-through is pinned only by the exit-2 row.
  126 and 127 are not exercised. Optional.
- **R1-N2.** The `mkdir` failure text says "it appeared after the check, or the
  parent is not writable" also when the parent is missing. `--out /` still
  fails with an empty name (N-4). Optional.

Carried, unchanged:
- N-1: the errno follow-up in `_transport`, outside U8b.
- N-4 and N-6: optional.
- N-7: the real runs; `u8/expected.md` now exists, but checking it is the
  orchestrator's.
- N-8: the untracked docs stay out of the U8b commit.
- N-9: `bundle.sh` l.85's `ls -A`, to U9.
