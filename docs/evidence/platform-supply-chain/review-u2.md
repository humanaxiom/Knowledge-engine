# Review: platform-supply-chain unit 2 (scanner; PSC-1, 2, 3, 5, 8)

- Reviewer, 2026-10-21. Branch `agent/platform-supply-chain` at 8900766 plus the uncommitted unit 2.
- Read: `git diff 8900766` (docs/architecture.md, docs/requirements.md, tests/test_stack_compose.py), the new
  `docker-compose.scan.yml`, `scripts/scan.sh`, `docker/scan-ignore.yaml` and `tests/test_image_scan.py`.
  Checked against ADR-KE-013 amendment 1, D1 to D5 and section 2.6 items 3 to 5, and against PSC-1 to PSC-8.
- Producer evidence read: u2-green-verify-full.txt (PASS 556 s, all 11 test_image_scan tests ok,
  shellcheck 0.9.0 lint PASS), u2-green-real-scan.txt, u2-green-confirm-d3-d5.txt, scanner-provenance.md,
  u2-red*-mutants.txt.

## Verdict: CHANGES REQUESTED (1 blocking, 6 non-blocking)

| PSC | Result |
|---|---|
| PSC-1 | Met. One anchored digest pin; the D2 step 3 fallback is recorded by security; the test ties the digest and tag to the provenance file. |
| PSC-2 | Met. The order is save, pull, db, scan. Only ke-app is saved, with no --platform. /in is read-only. The tag is refused before any docker call. No socket and no DOCKER_HOST. |
| PSC-3 | **Not met.** The scan-db volume is not removed on every exit path: TERM leaks it (B1). Every other part is met, including the recorded red run (below). |
| PSC-5 | Met. The file is `ignore: []`. The checker has 8 valid and 24 invalid controls. D5 is confirmed live: grype accepts `until`, and a planted ignore suppresses the row. |
| PSC-8 | Met. The renamed-copy limit is already noted by the orchestrator. |

The real-scan evidence shows the gate working: it fails closed with grype exit 2 on 2 fixed findings at or above High
(certifi Critical, quinn-proto High; by design, fixed separately). The table prints the suppressed unfixed rows, the
stage markers and timings are present, and teardown removed the volume and the network.

## Blocking

**B1. TERM during `scan-db` leaves the project behind. Location: scripts/scan.sh:44-53 (cleanup), :74-76 (`compose run scan-db`).**

Reproduced on a scratch copy, project prefix `ke-reviewer-psc-` (`review-u2-term-during-scan-db.txt`):
1. `timeout -s TERM 25 bash scripts/scan.sh` (Git Bash; TERM sent to the process group) killed the
   `compose run` client.
2. The one-off container `<project>-scan-db-run-<id>` (AutoRemove=true) kept running.
3. `teardown.sh --volumes` correctly reported it and failed, and scan.sh named the project. So the failure is
   reported loudly; it does not let a bad scan pass.
4. Left behind: the container, the `<project>_scan-db` volume and the `<project>_default` network.

This breaks PSC-3, which requires that the own `teardown.sh --volumes` of scan.sh removes the volume on every exit
path. It also breaks the D4 INT/TERM promise.

The printed hand command (`down --volumes`, and `--remove-orphans` too) exits 0 and removes nothing while that
container runs. It works only after the container exits (`review-u2-hand-command.txt`).

The INT run in the same harness was clean (`review-u2-int-during-scan-db.txt`): the trap waited for the client.

Fix direction (architect to confirm, since teardown.sh stays report-only per F3/L-9):
- Before calling teardown.sh, cleanup removes or awaits the containers labelled
  `com.docker.compose.project=$project`. That is the random project of scan.sh itself, so the action is scoped.
- The hand command names that step.
- Regression test: a fake-docker case where `compose run` is interrupted and leaves a container. Cleanup must issue
  the project-scoped removal before teardown. This can be folded into the PSC-6 test
  `test_scan_removes_tar_on_every_exit`, but the code fix belongs to this unit because PSC-3 claims it.
- The same `compose run` plus TERM pattern probably exists in scripts/offline_check.sh. That code was already there
  and is out of scope; it needs a follow-up item.

## Non-blocking

**N1 (should; required before PSC-6 wires the scan). The `scan` command row of D1 is unpinned. Location: docker-compose.scan.yml:34-43.**
- These mutants all survive: `c_no_fail_on`, `c_fail_on_critical`, `c_no_only_fixed`, `c_no_config`,
  `c_no_show_suppressed`, `c_output_json`.
- Without `--fail-on high`, grype always exits 0, so the gate passes everything without any error.
- Section 2.6 item 4 (PSC-4) plans a static check for four of these flags. Make it an exact-list equality, as the
  scan-db command `["db","update"]` already is, so that `-o table` and the input are covered too.

**N2 (should; PSC-6). The teardown-failure path is untested. Location: scripts/scan.sh:47-50.**
- Mutant `s_teardown_failure_ignored` (drop `status=1`) survives.
- This path is not in the section 2.6 item 5 list. Add a subtest: the stub teardown exits 1, so scan.sh must exit
  non-zero and name the project and the hand command.

**N3 (should; PSC-4/PSC-6). Interrupt and stage-failure paths are untested. Location: scripts/scan.sh:54-56, 66-67, 82-85.**
- Survivors: `s_no_int_term_traps`, `s_trap_after_save`, `s_save_failure_ignored` and `s_scan_failure_ignored`.
- The planned tests cover them: `test_scan_fails_on_fixed_high` and `test_scan_removes_tar_on_every_exit` ("a
  failure at each stage, INT, TERM").
- The save-failure subtest must assert three things: exit non-zero, `stage save` in the message, and no compose call
  afterwards. With `|| true` the run would otherwise go on to scan-db.

**N4 (nit). Caller-environment isolation is only partly enforced. Location: scripts/scan.sh:29-34.**
- Survivors: `s_caller_env_file_wins`, `s_no_env_file_flag` and `s_no_unset`.
- They survive because the caller env in the test sets `KE_ENV_FILE=.env.example`, the same as the default, and sets
  no `COMPOSE_PROFILES` or `COMPOSE_ENV_FILES`.
- The impact today is low: only `KE_SCAN_IN` is interpolated, and the exported value wins.
- To enforce the D4 rule "no caller value reaches the scan": add `KE_ENV_FILE=.env`, `COMPOSE_PROFILES` and
  `COMPOSE_ENV_FILES` to the hostile environment in `test_scan_updates_db_every_run`. Then assert
  `--env-file .env.example` on each compose call and in the teardown env.

**N5 (nit). Gaps in the evidence.**
- u2-green-real-scan.txt does not record the exit status of scan.sh or a post-run leftover listing.
- The handoff says no dist/ was left, but an empty `dist/` remains at the repo root. It is gitignored and harmless.
- The PSC-3 recorded red run (unresolvable host; DR38) was missing. The reviewer recorded one in
  `review-u2-red-unresolvable-host.txt`:
  - exit 1;
  - the message names `stage scan-db` and `scan-db.invalid`;
  - the scan never ran, and teardown was clean;
  - it also proves the `-e GRYPE_DB_UPDATE_URL` constant reaches grype.
- The orchestrator can accept that run or have the tester re-record it.

**N6 (nit; at commit). Staging.**
- Stage `scripts/scan.sh` with `git add --chmod=+x`. No test enforces the mode.
- Do not stage the untracked `docs/knowledge-engine-claude-code-prompt.md`. It dates from Oct 18 and is not part of
  this unit.

## Checked and fine
- **scan.sh tag check:**
  - The tag check runs first: LC_ALL=C, anchored, `%q` echo. It runs before mkdir and before the trap, so a refusal
    leaves nothing behind.
- **scan.sh project and environment:**
  - The project is `ke-scan-${RANDOM}${RANDOM}`, so a new volume is used each run.
  - COMPOSE_FILE, COMPOSE_PROJECT_NAME, KE_ENV_FILE and KE_SCAN_IN are set unconditionally.
  - `SCAN_DB_URL` is a literal, passed only by `-e` (D3 confirmed equal to the pinned default).
- **scan.sh failure handling:**
  - Pull and fetch are each called once with the D3 messages, followed by `--pull never` runs.
  - The cleanup status propagates.
  - The script is shellcheck clean.
- **Compose:** every row of the D1 table is as designed (read_only, tmpfs /tmp, cap_drop ALL,
  no-new-privileges, literal env, no profiles, restart or ports). `scan` has network_mode none and read-only db, /in
  and the cfg bind. The image is 423 MB, so the in-memory /tmp is not a concern.
- **test_stack_compose carve-out:** exempts exactly `scan-db` and `scan` in docker-compose.scan.yml. Widening it to the
  whole file (`t_carveout_whole_file`) has no effect, because test_image_scan pins the file to exactly those two
  services with the D1 mounts.
- **Docs:** the moves from config/ to docker/ are consistent. Only past handoff entries still say `config/`.
- **Controls:** all three reviewer controls were killed (`ctl_cleanup_exit0`, `ctl_no_pull`,
  `ctl_scan_network_bridge`).

## Reviewer evidence (this directory)
- `review-u2-mutants.txt` (driver `review-u2-mutants.py.txt`): 21 mutants of the developer's real files, run in the
  gates image, project `ke-reviewer-psc`, on a scratch copy. 3 controls were killed and 18 gap mutants survived, as
  listed above.
- `review-u2-red-unresolvable-host.txt`, `review-u2-term-during-scan-db.txt`, `review-u2-int-during-scan-db.txt`,
  `review-u2-hand-command.txt`: real runs on scratch copies, project prefix `ke-reviewer-psc-`. Every reviewer
  container, volume and network was removed afterwards (verified: 0 left).
