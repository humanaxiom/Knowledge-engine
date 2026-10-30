# U9d rework 1 review (reviewer, 2026-10-30)

**Verdict: APPROVED.** B-1 is closed as the amendment (A1-A4, O-23 and its precision) says. N-1 and N-2 are done,
and so are security's L-1, L-2 and I-1 as ruled. The stream's process handling is correct on every path I could
drive. One test-gap nit (N-1) is optional.

Scope read: the "Q82 / U9d" block and the rework-1 sections of `docs/handoffs/platform-sbom.md`; O-23, "Amendment,
rework 1 (O-23)" A1-A11 and the O-23 precision (design-notes l.5759-6183); requirements U9d-1/4/6 as amended
(l.4966-5027, 5095-5110, 5156-5160); `git diff HEAD -- scripts/offline_check.sh tests/test_offline_check.py
tests/fake_docker.py` (the whole U9d diff against 9c3183d); `u9d/controls-r1.txt`, `r1-red-verify-fast.txt`,
`r1-green-verify-fast.txt` (Ran 1359, OK, skipped=8), `r1-green-verify-full.txt` (PASS 1373 s, offline_check PASS
225 s), `measure-lines.txt`. Probes: `docs/evidence/platform-sbom/u9d/r1-review-probes.txt` (R1-R4).

## Tests unchanged by GREEN
The working-tree sha256 values (LF) are `tests/test_offline_check.py` d3961c07...4737125 and `tests/fake_docker.py`
d661f33d...9302f4. Both equal the "after" hashes in `controls-r1.txt` l.14-15. GREEN edited no test. The diff
touches only `scripts/offline_check.sh` and the two test files, plus docs.

## B-1: closed
| Amendment point | Where | Result |
|---|---|---|
| Template: RestartCount, StartedAt, FinishedAt, Error; `<absent>` for "", the zero time and an empty Error; Error JSON-quoted | offline_check.sh:121-134 | verbatim A1 (R4); `RestartCount` always a number; equals `fake_docker.DIAG_TEMPLATE` (allowed-fields row) |
| Stream started before launch | :250 `events_start`, then :251 launch | verbatim flow (R4); pass row: `events` call after STUB install.sh, before STUB launch.sh |
| Stopped on every path, before both branches | :252 `events_stop`, before the `launch_rc` test | only the launch line (with its `launch_rc=$?` guard) sits between start and stop; restarted row: `EVENTS stopped` before the first `ps`; pass row: after launch, before smoke |
| `--since`, no `--until`, one `events` call | :139 | static rows pin `--since`, no `--until`, exactly one call |
| The five filters | :139-140 | `type=container`, `label=com.docker.compose.project`, `event=die/oom/kill`; pinned exactly (`_assert_events_call`); live R3 |
| Fixed format: time, action, name, exitCode, signal | :135 | `== fake_docker.EVENTS_FORMAT`; live R3: the sentinel label and the image never print |
| 100-line cap and named lines (`none`, `N more`, `ended (exit N; 124 ...)`, `not recorded`) | :145-153, :157-169 | verbatim A2/A3; the cap, none and ended cases are pinned; `not recorded` is static only (no mktemp seam, controls-r1 l.117) |
| Nothing printed on a pass | variables read only in `diag_launch` | pass row: no `events`/`diag:` line, stdout = U9D_CLIENT_PASS + measure lines, stderr empty; real full run: no events text |
| Bound 900 s; cost on a pass | :139 | static N == 900; offline_check 228 s -> 225 s; C1/C3/H1/H3 0 s |

## N-1, N-2, L-1, L-2, I-1
- **N-1 (previous): done.** :189-191: `sed` without `;q`, and the first match is kept with a `%%` newline trim
  (verbatim A4).
- **N-2 (previous): done.** Design text A5 aligned; code unchanged (`LC_ALL=C sort -k 2`, :201).
- **L-1: done.**
  - :180: the name and label pass through `[[:cntrl:]] -> ?`.
  - :194-195: logs are fetched only for a label matching `^[A-Za-z0-9][A-Za-z0-9._-]*$`.
  - :198: `-- "$svc"`.
  - Row `..._sanitises_container_names_and_service_labels`: CR/ESC print as `?`; a `--follow` label is never an
    option; logs are fetched for `worker` only, after `--`.
- **L-2: done.**
  - :85-88 `neutralise` rewrites `##[` to `#?[`. It runs through `m`, `diag` and `diag_print`, so it reaches every
    `measure:` and `diag:` line.
  - R2: overlapping or adjacent markers leave no `##[`. `&` is safe under `patsub_replacement` because the
    replacement is quoted.
  - The row covers Health.Log, a log line, State.Error, an event line and a system df row.
- **I-1: done.** :48 `timeout 5 head -c 65536 -- "$1"`. The large-file row shows that figures past 64 KiB are not
  read and that the point takes 5 s or less.

## Shell correctness of the background stream (R1, R3)
- **`set -e`:**
  - `kill` sits in an `if`, and `wait` in an `|| events_rc=$?` guard. `awk`, `head` and `rm` are each guarded.
  - A stream killed by TERM (timeout re-raises it) gives 143 with no job notice on stderr. The real full run
    agrees.
  - A launch killed by SIGKILL gives `launch_rc=137`, and `events_stop` still runs.
  - The only stderr line in R1 is the bash foreground notice for a signalled launch. That is existing behaviour
    for any signalled `launch.sh`.
- **Temp file:** it is removed on every path (R1 `tmpfiles_left=0`). A `mktemp` failure leaves no stream and no
  file, and prints `not recorded`. If the client itself dies, `/tmp` is the client's tmpfs.
- **No orphan:**
  - `timeout` runs in its own process group and passes the TERM on to docker. R1 finds no surviving child on any
    path.
  - If `launch.sh` is killed by a signal, the client continues and `events_stop` kills the stream.
  - If the client bash itself dies, it is PID 1 of the offline-client container (the image has no entrypoint;
    compose `command: ["bash", ...]`). Its namespace goes with it, and `timeout 900` bounds the stream anyway.
- **Race between `events_start` and a live subscription:** `--since` closes the subscription gap fully.
  - The daemon replays the events it holds since that second and subscribes in one step. R3: a death before the
    CLI was even started, in the same second, was replayed.
  - The one theoretical residue: `$(date +%s)` is expanded in the forked child, a few ms after launch starts
    (R1: the parent went on after 1 ms). A death is lost only if a stack container is created, started and dies
    before that `date` call, and in an earlier second. Compose cannot do that in milliseconds, so the gap is
    closed in practice. No finding.
- **Info, not a finding:** a stream that exits in the instant between launch's exit and `kill` (not yet reaped)
  reads as `stopped`. Only the `ended` line is lost; its output still prints. If the stream had ended earlier,
  bash has already reaped it, `kill` fails and the line prints.

## U9d-6: can the analyst tell the causes apart from a CI failure's output?
**Yes, for each case:**
- **OOM:** an `oom <name>` line, then `die <name> exitCode=137`, with no `kill` line (R3, cgroup OOM). `RestartCount`
  and `FinishedAt` show it even when the container now reads `running / 0 / false / starting`.
  - Caveat for the analyst's CI read: the stack sets no memory limits, so a CI OOM is the host's global OOM killer.
  - The kernel counts that kill in the victim cgroup's `memory.events` `oom_kill`, which the daemon's `oom` event
    watches, so the line should appear. This was not probed: a host OOM cannot be produced safely here.
  - If the `oom` line is missing, `die exitCode=137` with no `kill` line still separates the case from a crash
    (A6 names it a SIGKILL from outside Docker).
- **Crash:** `die exitCode=N` with N other than 137 and no `oom` or `kill` line, plus the logs tail (R3: exitCode=3).
- **Docker stopped it:** `kill signal=<S>`, then `die 137/143` (R3).
- **Disk full:** C2 `df /` near 100%, the C1-to-C2 trend, inner `system df`, neo4j's "No space left on device" in
  the logs tail, and `State.Error` JSON-quoted for a restart the daemon could not do.
- **Nothing died:** `events: none` with no `ended` or `not recorded` line, `RestartCount: 0`, and `running` with
  Health `starting` or `unhealthy`, read from Health.Log.
- **Outside U9d:** if the host OOM killer picks the client or dind, no diagnostic prints. The host FAIL line and
  H2 remain.

## Developer's wording deviations
- **The "no logs" line** (:195, "the service label is not a service name, so no logs"): acceptable. No design text
  fixes the wording, the row pins "no logs" only, and the neutral-words row passes.
- **`neutralise` in `diag` and `m` as a superset:** acceptable, and in fact required by the O-23 precision ("`##[`
  rewritten ... in every printed line"). The container header (:181) prints the label through `diag`, and `m` lines
  carry df's filesystem name. There is no double rewrite: `diag_print` calls `neutralise` directly.

## Findings
- **N-1 (nit; tester).** No row pins `##[` on the `diag` path.
  - Where: tests/test_offline_check.py:2340 (`U9D_ODD_LABEL`) and :2120-2150 (L-2 row); code
    offline_check.sh:181.
  - The L-2 row covers `diag_print` and `m`. The `diag` path is the container header with a `##[` service label.
  - A mutant that drops `neutralise` from `diag` (:111) survives. Today's code is correct.
  - Fix: put `##[` in a fixture label, for example `svc##[group]x`, which fails the service-name check. Then assert
    that the header line holds `#?[group]x` and that no stdout line holds `##[`.

No blocking finding. No scope creep, no dead code, no untraced agent step (a gate script; no span required, as A1
states).

## Carried
| Item | Origin | Status | Check |
|---|---|---|---|
| Review N-1 above (`##[` on the `diag` path untested) | U9d r1 review | optional; tester may add before commit or in U10 | code correct (:111) |
| Security I-2 (bidi/zero-width chars pass), I-3 (`timeout` TERM only), I-4 (probe/log output verbatim by design) | U9d security | recorded, no action (O-23 precision) | unchanged |
| I-15 / N-8 (given `--out` re-check, bundle.sh:486-487) | U9b r2 | deferred to U10 (O-18) | bundle.sh not in diff |
| I-16 / N-7 (uid-0 link case, bundle.sh:685-688) | U9b r2 | deferred to U10 (O-18) | bundle.sh not in diff |
| U9c security I-1 (`notices` partial-row apk guard) | U9c security | deferred to U10 | sbom_check.py not in diff |
| U9c review N-1 (`source_index` docstring `partial`) | U9c review | carried to U10 | sbom_check.py not in diff |
| U9d-6 OOM-event caveat (global OOM, no memory limits) | this review | for the analyst's CI read | not probeable locally |

## Ready for commit
From the review side, U9d (GREEN plus rework 1) is ready for commit once these remain: security's re-audit of the
template and `events_fmt` (A1, A2, A7), and the orchestrator's own `scripts/verify.sh full` on the final tree with
its diff read.
- Stage: `scripts/offline_check.sh`, `tests/test_offline_check.py`, `tests/fake_docker.py`, `docs/requirements.md`,
  `docs/evidence/platform-sbom/design-notes.md`, `docs/evidence/platform-sbom/u9d/`, the handoff and the archive
  part, and `docs/log.md`.
- Do not stage: the untracked `docs/knowledge-engine-claude-code-prompt.md`. It predates this review and is not
  U9d's.
- Then push and run one CI job, on the human's word. The analyst reads the CI extract for U9d-6 with the OOM
  caveat above.
