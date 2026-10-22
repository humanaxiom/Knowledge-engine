# Re-review: platform-supply-chain unit 2 (scanner), rework round 1/5

- Reviewer, 2026-10-21. Branch `agent/platform-supply-chain` at 8900766 plus the uncommitted unit 2.
- Prior review: `review-u2.md` (B1, N1 to N6).
- Read this round:
  - `scripts/scan.sh` in full;
  - `tests/test_image_scan.py` lines 525-1141: the 9 new tests and the fixtures at :281-360;
  - `git diff 8900766 -- tests/fake_docker.py`.
- Producer evidence read:
  - `u2-rework1-mutants.txt`: 8/8 on the old scan.sh and 28/28 on the green copy, all killed;
  - `u2-rework1-green-verify-full.txt`: PASS 572 s, and all 20 test_image_scan tests report `ok`, none skipped;
  - `u2-rework1-green-verify-fast.txt`: PASS;
  - `u2-rework1-real-scan.txt`: exit 1 on certifi and quinn-proto; teardown removed the volume and the network; 0
    containers, volumes, networks or dist directories left.

## Verdict: APPROVED (0 blocking; 3 new nits; N1 still open for PSC-4)

## B1: closed

**Code** (`scripts/scan.sh`). The cleanup order is correct:
- :45 `status=$?`;
- :46 `trap - EXIT`;
- :48 `trap '' INT TERM`;
- :51-57 `docker ps -aq --filter "label=com.docker.compose.project=$project"`, then `docker rm -f` of those IDs; a
  failure here sets status=1;
- :58-61 `scripts/teardown.sh --volumes`; a failure here sets status=1;
- :62 `rm -rf -- "$KE_SCAN_IN"`;
- :63 `exit "$status"`.

The traps are set at :65-67: EXIT runs cleanup, INT runs `exit 130`, TERM runs `exit 143`. These are set after the
tag check at :22-27, so a refused tag leaves nothing behind.

**Real engine** (`review-u2-r1-term-during-scan-db.txt`). Setup:
- a scratch copy whose only change is the project prefix `ke-reviewer-psc-` (scan.sh:31);
- `timeout --preserve-status -s TERM 25`, which signals the whole process group;
- two decoy containers still running, labelled `com.docker.compose.project=ke-reviewer-psc-1` and
  `ke-reviewer-psc-other`.

Result:
- The scan-db run container was polled `running` up to the signal, and the compose client was `Terminated`.
- Cleanup force-removed the container, and teardown then removed the volume and the network.
- `exit=143`. 0 containers, volumes, networks and dist entries left.
- The random project was `ke-reviewer-psc-157529546`, so the decoy label `ke-reviewer-psc-1` is a string prefix of
  it. Both decoys were still running after the run. Docker matches `label=K=V` exactly.
- This is the same harness that, in `review-u2-term-during-scan-db.txt`, leaked the container, the volume and the
  network (exit 124).

**INT on the real engine** (`review-u2-r1-int-during-scan-db.txt`):
- `exit=130`, clean, decoys untouched.
- As in round 0, on Git Bash the compose client finishes the database fetch before the trap runs (73 s).

**Fake docker** (`review-u2-r1-gates-scanscript.txt`). The reviewer ran `tests.test_image_scan.ScanScriptTest` in
the Linux gates image: 14/14 ok, including the signal tests that use killpg.
- `test_scan_interrupt_removes_own_project_containers_before_teardown` (test_image_scan.py:843-891), TERM and INT:
  - every own container, the running one and the created one, is removed with `rm -f` before teardown.sh (:871-879);
  - no call names a decoy, there is no `prune`, every project-label filter equals the scan's own project, and every
    rm target is its own (:880-890).
- The fixtures at :340-360 cover a decoy from the verify project, a `ke-scan-1` prefix decoy, and a decoy with a
  look-alike name under another label.
- The tester's mutants `b1_filter_by_name`, `b1_filter_by_scan_prefix`, `b1_no_filter`, `b1_ps_running_only`,
  `b1_rm_without_force` and `b1_removal_after_teardown` are all killed.

**Can `docker rm -f` hit another project?** No. It removes only the IDs returned by an exact label filter on the
scan's own `ke-scan-<random><random>` project. The only residual case is two scans that run at the same time and
draw the same random name, about 1 in 10^9. Those two would already share one compose project, so this is not new
with this change.

## Earlier findings
| Finding | Status | Where |
|---|---|---|
| N1 the scan command flags are unpinned | **Open** (PSC-4 step) | docker-compose.scan.yml:34-43; no test in tests/test_image_scan.py references `--fail-on`, `--only-fixed` or `--show-suppressed`. |
| N2 teardown failure | Covered | test_image_scan.py:1031-1042: teardown stub exits 1, so the run must exit non-zero, name the project and print `down --volumes`, and dist is removed. scan.sh:58-61. Kills `rv_s_teardown_failure_ignored`. |
| N3 interrupt and stage failures | Covered | test_image_scan.py:1044-1085: pass, then save, pull, fetch and scan failures, each naming its stage, with teardown once and dist gone; save failure means no compose call (:1072-1074); INT gives 130 and TERM gives 143 (:1076-1083). Kills `rv_s_no_int_term_traps`, `_trap_after_save`, `_save_failure_ignored` and `_scan_failure_ignored`. |
| N4 caller env | Covered | test_image_scan.py:1087-1116: a hostile `KE_ENV_FILE=.env`, `COMPOSE_PROFILES`, `COMPOSE_ENV_FILES` and repo `.env`; `--env-file .env.example` on every compose call; no profile; keys unset in the teardown env. Kills `rv_s_caller_env_file_wins`, `_no_env_file_flag` and `_no_unset`. |
| N5 evidence | Closed | The orchestrator accepted the reviewer's PSC-3 red run. `u2-rework1-real-scan.txt` records the exit status and the leftovers. |
| N6 staging | Still applies at commit | Use `git add --chmod=+x scripts/scan.sh`. Do not stage `docs/knowledge-engine-claude-code-prompt.md`, which is still untracked. |

**fake_docker.py: each new feature is inert unless its variable or hook key is set:**
- `FAKE_DOCKER_RECORD_ENV` (:271): an unset variable yields an empty list.
- The `stat` hook (:372) runs only for a hook entry that has the key.
- The container model (:506) applies only when `FAKE_DOCKER_CONTAINERS` is set. When it is not, `ps` and `rm` fall
  through to the old branches unchanged.
- `FAKE_DOCKER_SAVE_MODE` (:900): no chmod is done when it is unset.
- The whole suite is green in verify full, which agrees with this.

## Nits (non-blocking)
- **r1-a, scan.sh:52.** `if mapfile -t ids < <(docker ps ...)` never sees the exit status of `docker ps`, because
  of the process substitution. So the `if` is always true, and a failed `docker ps` is silent.
  - It still fails closed: teardown.sh then reports what is left and status becomes 1.
  - Either drop the `if`, or capture the `docker ps` output in a variable and set status=1 when it fails.
- **r1-b, scan.sh:54 and :59.** The container-removal failure message names the project but gives no hand command.
  The teardown hand command is still only `down --volumes`, which removes nothing while a container of the project
  runs (`review-u2-hand-command.txt`).
  - Suggest adding the label-scoped `docker rm -f` (of `docker ps -aq --filter label=com.docker.compose.project=<p>`)
    to the hand text.
  - The automatic path is now correct, so this matters only when `rm -f` itself fails.
- **r1-c, scan.sh:65 and :70-71.** The EXIT trap is armed before `mkdir -m 0755`. When L-2 refuses a pre-existing
  `dist/<project>`, cleanup then runs `rm -rf` on that pre-existing path (:62).
  - A symlink is unlinked, not followed. The path is in the script's own `ke-scan-*` namespace under gitignored
    dist/. So this is harmless.
  - Still, "an existing path fails the run" (comment :69) then deletes it.
  - Optional: create the directory first, then arm the trap, or skip the `rm` when the mkdir failed.

## Reviewer evidence (this directory)
- `review-u2-r1-term-during-scan-db.txt`, `review-u2-r1-int-during-scan-db.txt`: real engine, scratch copy, project
  prefix `ke-reviewer-psc-`, decoys from other projects.
- `review-u2-r1-gates-scanscript.txt`: ScanScriptTest in the gates image (project `ke-reviewer-psc`). This is a
  reviewer probe, not a gate run.
- After the runs, every reviewer container (decoys included), volume and network was removed (verified: 0 left).
