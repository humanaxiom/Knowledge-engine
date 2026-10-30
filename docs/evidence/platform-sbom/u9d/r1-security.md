# platform-sbom U9d rework 1: security re-audit (security, 2026-10-30)

**Verdict: PASS.** No critical or high finding. L-1, L-2 and I-1 are closed. There is one new low finding (L-3)
and four informational items (I-3 carried; I-5, I-6, I-7 new). None blocks the merge.

Scope: `git diff HEAD -- scripts/offline_check.sh tests/test_offline_check.py tests/fake_docker.py`
(189+/3-, 946+/0-, 225+/5-; offline_check.sh sha256 110586a6...01fa at audit). It is checked against the O-23
precision, the "Amendment, rework 1 (O-23)" A1-A3, A7 and A8 (design-notes l.5777-6183), and the first audit
`u9d/security.md`. Probes are in `u9d/security-probes.txt`, section "rework 1" (RA-RH). They ran in ke-gates with
`--network none` and uid 10001. The real-Docker probes ran on Docker 29.5.2 (CLI 29.9.1) against throwaway
containers labelled `ke-sec-u9dr1=1`; all were removed (0 left).

## Status of the first audit's findings

- **L-1: closed.** offline_check.sh:180 replaces control characters in name and svc right after the `read`.
  Logs are fetched only when svc matches `^[A-Za-z0-9][A-Za-z0-9._-]*$` (l.195), and svc is passed as
  `-- "$svc"` (l.198). Probe RA:
  - `--follow`, `-f`, `;rm -rf /`, `neo4j;rm -rf /`, `##[group]svc` and a CR/ESC label: each printed one named
    "not a service name, so no logs" line. None made a logs call.
  - The CR/ESC label and name printed as `?`, and the name's `##[` printed as `#?[`.
  - A valid 10 KiB name made one logs call after `--` and no option.
  - Output: 0 unprefixed or raw-control lines, 0 lines holding `##[`, no sentinel.
  - The real compose CLI accepts `logs ... -- svc1` and returns the service's lines (RG R4).
- **L-2: closed.** `neutralise` (l.85) rewrites `##[` to `#?[` in `diag`, `diag_print` and `m`, after the
  control-character pass and the 2000-character cut. Probe RB found 0 lines holding `##[` across:
  - Health.Log output (`##[section]`, a mid-line `##[error]`, `###[` (printed `##?[`), `##<CR>[`);
  - a compose log line; State.Error; an event name and exitCode; a `docker system df` row.

  On the real daemon (RG R2), a start error whose path holds CR and `##[` printed as one JSON-quoted line with
  `#?[`.
- **I-1: closed.** l.48 reads `timeout 5 head -c 65536`. Probe RC, against the first audit's times:
  - a 200 MiB one-line file: 0.00 s (was 227.1 s);
  - `/dev/urandom`: 0.01 s (was 35.9 s);
  - a FIFO: 5.00 s (bounded);
  - whole client run: 0.3 s, `not measured` at C1 and C3, exit 0.

  Residual, seam only: a NUL-bearing seam file makes bash print "ignored null byte" on stderr. The real
  `/proc/meminfo` has no NUL. No action.

## Re-audit checks

1. **Event format and call: pass.** l.135 is A2's `events_fmt`: `.Time .Action .Actor.Attributes.name`, plus
   `exitCode` and `signal` read through `index`. The client half (comments stripped) holds:
   - exactly one `docker events` call (l.139), with the five filters and `--since "$(date +%s)"`;
   - no `--until`, `.Actor.ID`, `{{json .}}`, `json .Actor`, `.From` or `.Actor.Attributes.image`.

   The stream:
   - runs under `timeout 900` and reads `< /dev/null`;
   - writes only to a `mktemp /tmp/ke-offline-events.XXXXXX` file in the client's tmpfs (`/tmp`, mode 1777,
     docker-compose.offline.yml);
   - has its stderr sent to `/dev/null`.
2. **Stop, cleanup, signals: pass (I-3 carried).** `events_stop` (l.144) runs `kill`, then `wait`, then
   `head -n 100`, then `rm -f`.
   - Between `events_start` and `events_stop` the only command is `bash scripts/launch.sh || launch_rc=$?`, which
     cannot exit the client. So the stop runs on both branches, and also when launch.sh dies of a signal (128+n
     is captured).
   - Real CLI (RG R1): stopped in 0.01 s, state `stopped`, rc 143, 0 bytes on stderr, 0 files left. The real
     `verify full` pass log has no job notice between `launch` and `smoke`.
   - Fake: no file was left on the fail path, the pass path, the flood, or the ended-early path (RA-RF). When
     mktemp fails, the named line "events: not recorded" prints (RF).
   - SIGTERM to the client: the client is `bash` as PID 1 of `offline-client` (`command: ["bash", ...]`, no
     init), so the kernel ignores the SIGTERM (RG R5: still `running`). The host's EXIT trap then tears the
     project down. `docker stop` sends SIGKILL after the grace period, and every process in the PID namespace
     dies with it, the stream included (R5: `exited 137`, nothing left). The events file goes with the tmpfs,
     and the stream's daemon (dind) is torn down with it. Nothing outlives the container, and `timeout 900`
     bounds it in any case.
   - Residual (I-3): see Findings.
3. **100-line cap: pass.** A 10000-event flood (RE): exactly 100 `events | ` lines, the first 100 in order, then
   `events: 9900 more lines not printed`. The stream was killed (`ready`, `stopped`) and the run took 0.5 s.
   On a pass with a live stream (RD), stdout minus the `measure:` lines equals the pre-U9d pass, stderr is
   empty, and no event text prints.
4. **Event lines through the sanitiser: pass.** A name holding CR, `::error::`, OSC/BEL and `##[` printed as
   one prefixed line with `?` and `#?[` (RB, RD). The attribute map's image, label sentinels and 64-hex actor ID
   did not print (RD; real daemon RG R1: 0). **Exception:** labels named `exitCode` or `signal` (L-3).
5. **Template (A1): pass.** The diff adds only `RestartCount`, `State.StartedAt`, `State.FinishedAt` and
   `State.Error`, with `{{json .State.Error}}`. Real renders of four containers (RG R2):
   - oom: `137/true`; crash: `3`; running: `FinishedAt <absent>`; never started: both `<absent>`;
   - the start error prints on one line: CR as `\r`, `##[` as `#?[`.

   The label, env and mount sentinels: 0 hits. State.Error carries the daemon's message, which can name the
   entrypoint path (runc's `exec: "<path>"`). Accepted by O-23 ("the daemon's own start error"); no args or env
   were seen.
6. **Never-printed list, end to end on the real CLI: pass for the template.** For the event format, see L-3.
   - In the attribute map of a real `die` event (R1 contrast), keys are: every label,
     `com.docker.compose.*`, `image`, `name`, `execDuration`, `exitCode`, `signal`.
   - The script's format printed none of `image`, `com.example.secret`, the actor ID or env.
   - It did print the values of the labels named `exitCode` and `signal`, in place of the daemon's own values.
7. **No gate or test weakened: pass.**
   - tests/test_offline_check.py: 946+/0- against HEAD. Its sha256 (d3961c07...) and fake_docker.py's
     (d661f33d...) equal the tester's RED "after" hashes (`controls-r1.txt`), so GREEN edited no test.
   - The two re-pinned rows only add checks: events allow-list, N == 900, exact filters, one call. The other
     kinds keep N <= 30.
   - fake_docker.py's 5 removed lines route `State` through `_u9d_state` (first audit) and write
     `EVENTS_FORMAT` into the installed fake.
   - Evidence `u9d/*`: no profile path, SID, key, token, private key or connection string. The only sentinel is
     the fixture `u9d-sentinel-secret-7f3a9c`. Outside the diff, see I-7.

## Findings

- **L-3 (low) A container label named `exitCode` or `signal` shadows the event's own field.**
  - Where: offline_check.sh:135 (`index .Actor.Attributes "exitCode"` / `"signal"`), printed at l.161.
  - Cause: the daemon builds an event's attribute map by copying the container's labels over the action's
    attributes (`exitCode` on `die`, `signal` on `kill`).
  - Effect, real Docker 29.5.2 (RG R1): every line read `exitCode=LBL-EXITCODE-SENTINEL
    signal=LBL-SIGNAL-SENTINEL`. This covered the OOM die (137) and the crash (3), and an `oom` line, which
    normally has neither.
  - Two consequences: (a) a label value prints, contrary to A7 and U9d-1 ("of an event, nothing but the five
    fields ... no labels"); (b) the analyst's cause (A6) can be falsified. A label can hide `exitCode=137` or
    fake a Docker `kill`.
  - Exposure today: none. No compose service and no local stack image (ke-app, ke-neo4j, ke-gateway, postgres,
    valkey, phoenix) defines either label (RH R6; compose and Dockerfile grep: 0). Labels come from the bundle's
    compose file and its digest-pinned images; an upstream image `LABEL` is the less-trusted route. Values are
    still sanitised: control characters become `?`, `##[` becomes `#?[`, and lines are cut at 2000.
  - Fix:
    - In the events branch of `diag_launch`, print an event line only if it matches
      `^[0-9]+ (die|oom|kill) [A-Za-z0-9][A-Za-z0-9_.-]* exitCode=[0-9]* signal=[0-9]*$`. Otherwise print one
      fixed line, for example `events: a line not in the expected form, not printed (a container label named
      exitCode or signal shadows the event's own field)`.
    - Add a sentence to A6 that a numeric label of those names would still shadow the field.
    - Optionally, a static row that no service in docker-compose.yml sets those label names.
    - Test row: a FAKE_DOCKER_EVENTS `die` whose `exitCode` attribute is `LBL-SENTINEL ##[x`.
- **I-3 (info, carried) `timeout` without `-k`.** l.139. `events_stop`'s `wait` relies on the stream exiting on
  SIGTERM. GNU timeout forwards TERM, and at 900 s sends TERM again, never KILL. A stream that ignores TERM held
  the client until it exited on its own (RE: 20 s). The pinned docker CLI exits at once (R1: 0.01 s). Optional:
  `timeout -k 5 900` (and `-k 5` on the 10/20 s calls).
- **I-5 (info) A newline in a label still forges a `ps` row.** l.178/183.
  - The docker CLI strips a newline from `--label`. The Engine API stores it (compose's route), and
    `ps --format` prints it raw (RH R3b), so the row splits.
  - The forged row's first field reaches `docker container inspect --format "$diag_tpl" "$id"` before any `--`.
    On the real CLI, `--format={{.Config.Env}}` and `--size` give "requires at least 1 argument" (exit 1, env
    not printed). `--help` prints 13 help lines through `diag_print`.
  - Its name and svc are sanitised, and its logs are fetched only for a valid service name. No command runs and
    no secret prints.
  - Optional: skip a row whose id does not match `^[0-9a-f]{64}$` (the list uses `--no-trunc`), or pass
    `-- "$id"`.
- **I-6 (info) Lines built by `diag` are not cut.** l.181, l.196, and the `diag_print` prefix at l.199. A valid
  10 KiB service label printed three lines of ~10.3 KiB each (RA). Log volume only. Optional: cut name and svc
  to about 200 characters after sanitising.
- **I-7 (info, outside this diff)** `docs/handoffs/NEXT-SESSION.md:155` (untracked) holds a Windows profile path
  (`C:\Users\<user>\AppData\...`). Redact it before that file is committed (the user's evidence-redaction
  ruling).

## Next

Nothing blocks the merge. L-3 is a few lines in `diag_launch` plus one test row. The orchestrator may fold it in
now (rework 2) or record it for U10, as it did with L-1 and L-2. I-3, I-5 and I-6 are optional hardening. I-7
belongs to whoever commits NEXT-SESSION.md.
