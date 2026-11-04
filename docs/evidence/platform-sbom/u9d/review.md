# U9d review (reviewer, 2026-10-30)

**Verdict: CHANGES REQUESTED.** One blocking finding (B-1). The code builds the design faithfully, but the
design's diagnostic will most likely print `ExitCode: 0` / `OOMKilled: false` for a neo4j that was OOM-killed or
crashed: every stack service has `restart: unless-stopped`, and Docker resets both fields when it restarts the
container. That defeats the unit's only purpose (U9d-6: name the cause) on the OOM-vs-crash question. Everything
else conforms.

Scope read: `git diff HEAD -- scripts/offline_check.sh tests/test_offline_check.py tests/fake_docker.py`;
requirements "U9d precision" U9d-1..U9d-8; design-notes "N9 amendment, U9d" items 1-16 and O-22; `u9d/` evidence.
Live probes on Docker 29.5.2 (throwaway project `ke-rev-u9d`, `network_mode: none`, local `ke-gates:local`, no
pull, torn down): `docs/evidence/platform-sbom/u9d/review-probes.txt`.

## Tests unchanged by GREEN
The working-tree sha256 (LF) of `tests/test_offline_check.py` is 5ba4255c...0a0e and of `tests/fake_docker.py` is
83f7a647...c5a54, equal to the tester's "after" hashes in `controls.txt`. GREEN edited no test.
The `offline_check.sh` HEAD blob is 5e7b1d39..., the hash `controls.txt` lists as unchanged; bundle.sh and
sbom_check.py are unchanged.

## Design conformance, item by item
| Item | Result |
|---|---|
| 5 helpers `meminfo_line`, `df_line` (offline_check.sh:42-70) | verbatim (mechanical line-by-line check against the design blocks) |
| 6 `measure C1/C2/C3` (:80-101), seam `KE_OFFLINE_MEMINFO` (:80; header :29-30) | verbatim; the seam is client-only (host :284-294 reads `/proc/meminfo` only), per O-22 (3) |
| 7 `diag`/`diag_print`/`diag_tpl`/`diag_launch` (:103-156) | verbatim, except that the `if/elif` at :128-133 is split over separate lines (same behaviour). Template = `fake_docker.DIAG_TEMPLATE` (pinned by `test_offline_diag_template_prints_only_allowed_fields`); fields only `.State.Status/.ExitCode/.OOMKilled/.Health(.Status/.Log[].End/.ExitCode/.Output)`; the listing reads `.ID .Names .Label "com.docker.compose.service"` |
| 8 client flow (:200-211) | verbatim: C1 after install; `launch_rc=0; bash scripts/launch.sh || launch_rc=$?`; C2, diag, `exit "$launch_rc"`; C3 after smoke |
| 9 host H1-H3 (:284-294, :483, :488-489) | verbatim; FAIL line byte-identical (stderr row pins it); H2 inside the `|| { }` |
| 10 `::` hardening | holds on real Docker: `::error::forged\r::warning::x` printed as `... sick | <ts> ::error::forged?::warning::x`; ESC printed as `?`; every line starts `offline-client: diag:` (review-probes.txt P2) |
| 11 wording | no banned word in any new line (static and dynamic rows) |
| 12 timeouts | cat/df 5 s, system df 10 s, ps 10 s, inspect 10 s, logs 20 s, as tabled; the static row pins every docker call |

## Shell correctness
- `set -e`: every new command that can fail sits in `if`, `|| return 1` or `|| rc=$?`. `measure` and
  `diag_launch` run with `set -e` live, and the "every source fails" row (mutant M07) proves no command is
  unguarded. H2 runs in a `||` list, so it cannot hide the FAIL. `|| launch_rc=$?` keeps launch's status, and
  launch.sh's own `set -e` is intact because it runs in a child bash. `exit "$launch_rc"` is non-zero by construction.
- `read` loop: `done <<< "$(... | LC_ALL=C sort -k 2)"`; every docker call in the loop reads `< /dev/null`
  (design pitfall pinned). An empty list gives one empty line, which `[ -z "$id" ]` skips.
- Quoting: `"$diag_tpl"`, `"$id"`, `"$svc"`, `"$root"`, `"$meminfo"` all quoted; the label is printed via `%s`.
- Here-strings/temp files: the client's `/tmp` and `/install` are tmpfs (docker-compose.offline.yml), so a full
  runner disk cannot break the measurement (design item 16 holds).
- bash 3.2: nothing newer than 3.2 (`[[ =~ ]]`, `${v//}`, `${v:0:n}`, `<<<`, `local`); both halves run in the gates image anyway.
- Real Docker (29.5.2): the template parses and renders all branches (`<absent>` for no healthcheck and for never
  started; an unhealthy container with an empty Health.Log prints `State.Health.Log: <absent>`). `{{json}}` gives
  `"Connection refused\nUnable to connect \"q\"\n"` on one line. `compose logs --tail 50` gives exactly 50 lines
  and keeps the container's stderr. A healthy container gets no logs; a never-started one gets an empty logs section.
- `launch.sh` leaves the containers in place on a failed `--wait` (no trap, no down). Plain `docker compose` in the
  installed tree resolves the same project (`name: knowledge-engine`; `KE_ENV_FILE` unset; no profiles).
- The diagnostic runs only on the launch-failure path; on a pass the call record shows no ps, inspect or logs call
  (`test_offline_measure_points_on_a_pass`).

## Test adequacy
Every U9d criterion has a row:
- U9d-1: `..._prints_diag_on_launch_failure` and `..._diag_survives_a_failing_inspect` (3 cases).
- U9d-2: `..._measure_points_on_a_pass`, `..._on_a_launch_failure` (including the smoke, teardown, image-name and
  not-clean scope cases) and `..._never_changes_the_outcome`.
- U9d-3: `..._has_no_ci_only_branch`, and a sentinel secret in Config.Env, Args, Mounts and a label.
- U9d-4: the call record shows no diagnostic call on a pass; the static timeout row.
- U9d-5: both control rows, green at RED by design.

17/17 mutants killed. The fake's knobs are inert unless set: the U9d paths are gated on dict States in
`FAKE_DOCKER_CONTAINERS`, `FAKE_COMPOSE_LOGS` and `FAKE_DF_FAIL`, and `system df` had no earlier caller. No test
name holds a count. No new row reads `docs/evidence/**`; the only matches are pre-existing comments.
Gap: see B-1 (no row models a restarted container, the state the real stack produces).

## Cost (U9d-4)
`measure-lines.txt`: C1 1 s, C3 0 s, H1 0 s, H3 0 s, sum 1 s (bound 5 s per point, 15 s per run). Within bound.
The gate run's `measure-lines-gate.txt` is still to come (orchestrator).

## U9d-6: is a CI failure's output enough to tell disk-full from OOM from a crash?
- **Disk-full: yes.** C2 `df /` (the runner's `/dev/root`, read through the client's overlay), the C1 to C2
  trend, the inner `docker system df` sizes and neo4j's logs tail together name it. A JVM that dies of a full disk
  writes "No space left on device" first.
- **OOM vs crash: no, as designed.** Every stack service has `restart: unless-stopped` (docker-compose.yml:24 via
  `x-app`, :64, :120, :141 neo4j, :156, :169).
  - Probe P3 (a real cgroup OOM kill on Docker 29.5.2): `ExitCode 137 / OOMKilled true` shows only in the
    `restarting` window. Once Docker restarts the container, both read `0 / false` and Health.Status reads `starting`.
  - Timing: neo4j ran about 40 s (Q82 facts 1-2), so its restart backoff is reset and it restarts after about
    100 ms. The diagnostic reads it only after the compose failure, launch.sh's exit and C2, about 1 s or more later.
  - Expected CI reading: `State.Status: running / ExitCode: 0 / OOMKilled: false / Health.Status: starting`, which
    reads as "nothing died".
  - A SIGKILLed JVM writes no last words, so the logs tail shows only a second startup sequence. C2 memory is read
    after the kill has freed the memory, so it cannot show the pressure either.
  - Design item 16 names `OOMKilled` and neo4j's last lines as the source of the order. Under the restart policy
    the first is reset, and an OOM leaves no second.
- **Missing:**
  - (a) `RestartCount`, `State.StartedAt`, `State.FinishedAt` (and `State.Error`). These survive the restart and
    show "died at T, restarted N times".
  - (b) The death's own exit code and OOM flag. Only a live `docker events --filter event=die --filter event=oom`
    stream started before launch records these reliably. The events *history* does not: it is a bounded ring that
    healthcheck `exec_*` events fill, and probe P5 lost 8 of 9 deaths.

## Findings
- **B-1 (blocking; route: analyst + architect, then tester RED, developer).**
  - Where: offline_check.sh:114-122 (`diag_tpl`) and :200-207 (launch branch); U9d-1's field list; design items 7
    and 16.
  - Problem: under the stack's `restart: unless-stopped`, the diagnostic will most likely print a restarted
    neo4j's reset `ExitCode 0 / OOMKilled false` (review-probes.txt P3, P4). U9d-6 then cannot tell an OOM from a
    crash, and the output may read as "no death".
  - Who decides: the analyst amends U9d-1's allowed fields, the architect picks the mechanism, and security
    re-checks the never-printed list.
  - Fix (1): add `RestartCount: {{.RestartCount}}`, `State.StartedAt`, `State.FinishedAt` and `State.Error` to
    both the template and `DIAG_TEMPLATE`.
  - Fix (2): record the death itself. For example, before `bash scripts/launch.sh`, start
    `timeout <launch budget> docker events --filter label=com.docker.compose.project --filter event=die --filter event=oom --format '{{.TimeNano}} {{.Action}} {{.Actor.Attributes.name}} exitCode={{index .Actor.Attributes "exitCode"}}'`
    in the background, writing to a tmpfs file, and stop it after launch. On the failure path only, print the file
    as scrubbed `diag:` lines. The format must print no other attribute, because event attributes carry labels and
    the image.
  - Tests: a fake container in a restarted state (`running`, `ExitCode 0`, `OOMKilled false`, `RestartCount 2`,
    FinishedAt set) plus fake die and oom event lines, asserting that the death's exit code, the oom event and the
    restart count print. A second assertion: the stream is stopped on a pass and prints nothing there.
  - Why the current rows miss it: the U9d-5 fixture's worker (tests/test_offline_check.py:1925) is
    `exited / 137 / OOMKilled true`, a state this stack shows only inside the backoff window.
- **N-1 (nit).** offline_check.sh:144-145: `sed -n '/^State\.Status: /{s///p;q}'` runs under `pipefail` with `set -e`
  live. If an inspect output exceeds the 64 KiB pipe buffer, `sed` quits, `printf` gets SIGPIPE and the assignment
  returns 141. The client then exits mid-diagnostic and loses the remaining blocks, against U9d-1's "remaining
  blocks still run". Docker caps each probe output at 4 KiB and keeps 5 entries, so this is unlikely. Fix: drop
  `;q` so sed reads to EOF, and keep the first match in the shell (`status="${status%%$'\n'*}"`).
- **N-2 (nit).** offline_check.sh:154: `sort -k 2` sorts by container name (field 2 to the end of the line), while
  design item 7 says "sorted by service name". The order is the same for compose's `<project>-<svc>-<n>` names.
  Fix the design text, or sort on `-k 3,3`. Not pinned by a test (tester's choice).

## Carried (untouched by U9d)
| Item | Origin | Status | Check |
|---|---|---|---|
| I-15 / N-8 (given `--out` re-check, bundle.sh:486-487) | U9b r2 | deferred to U10 by O-18 | bundle.sh unchanged (sha256 9624710b...) |
| I-16 / N-7 (uid-0 link case, bundle.sh:685-688) | U9b r2 | deferred to U10 by O-18 | bundle.sh unchanged |
| U9c security I-1 (`notices` partial-row apk guard) | U9c security | deferred to U10 | sbom_check.py unchanged |
| U9c review N-1 (`source_index` docstring `partial`) | U9c review | carried to U10 | sbom_check.py unchanged |
