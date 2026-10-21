# Re-review: platform-offline unit 1 (L-5), rework round 1/5, 2026-10-19

Reviewer, read-only. Base 4b19971, working tree on agent/platform-offline (uncommitted).
Verdict: **APPROVED** (0 blocking, 4 nits). Commit still waits on the orchestrator's pre-commit full run with a throwaway `.env` (N8 / security L-5).

Inputs read: review-l5.md, security-l5.md, the developer rework section of the handoff, rework1-l5-verify-full.txt
(PASS 161s, 435 unit + 11 integration), rework1-l5-mutant-m1.txt, and `git diff 4b19971` plus the untracked files.
I did not run verify: the orchestrator's full run was in progress on the shared `ke-gates` tag, and a fast run would rebuild that tag.
One read-only probe: `COMPOSE_PROJECT_NAME=ke-review-l5r1 COMPOSE_FILE=docker-compose.yml:docker-compose.gates-mask.yml docker compose ... config gates gates-it`.
It showed the merged config: user 10001:10001, cap_drop ALL, no-new-privileges, tmpfs /tmp exec 1777, /work read_only (long syntax), /work/.env bound to docker/empty read_only,
gates network_mode none, gates-it networks [backend] only. The long-syntax base and the short-syntax overlay merge correctly.

## Prior findings
| ID | Status | Where / why |
|---|---|---|
| B1 | Fixed | `docker-compose.gates-mask.yml` holds only the two mask volumes. `tests/test_stack_compose.py:39-42` `_find_service` reads the base. `:214` classifies overlay entries by their base service. `tests/test_gate_least_privilege.py:220-231` pins the overlay content exactly. M1 is now killed: `test_gates_it_internal_only_and_no_socket` fails on `network='edge'` and on the missing `network_mode` (mutant evidence lines 392-393, 591-605). |
| B2 | Fixed | `pyproject.toml:39-44` adds `parallel = true` and corrects the comment. `tests/test_gate_least_privilege.py:339-365` runs the real `coverage erase` with the repo's run table (only data_file redirected) and asserts that a planted `.coverage.*` and the main file are gone. It fails if `parallel` is dropped (direct assert, plus the P1 probe showed erase keeps the file without it). Architecture §2.2:474-478 corrected (architect-l5-fix.md). The followups test (`tests/test_harness_followups.py:309-334`) keeps the erase-before-run ordering and cross-references the behavioural test, so it is not weakened in net. |
| N1 | Fixed | integration `:72-78` uses `skipTest` with a named reason (seen in the run log at line 854). |
| N2 | Fixed | `_try_write` uses append mode (`:33-44`); the mask and checkout assertions require `errno.EROFS`. |
| N3 | Fixed | `:120-124` regex narrowed to the two real uv messages. Asserts UV_FROZEN and UV_NO_SYNC are unset. Temp `UV_PROJECT_ENVIRONMENT` per case. Extra-dependency (`six`) case added (DR38). Known limit (accepted): offline it cannot tell `--locked` from a plain run; static tests pin `--locked`. |
| N4 | Fixed (nit below) | `:56-67` probes `.git/hooks` only when `.git` is a directory, and asserts `.git` is a file otherwise. |
| N5 | Fixed | `docker-compose.yml:48-52` long syntax `read_only: true`, plus `test_gate_services_use_long_syntax_read_only_checkout`. |
| N6 | Fixed | `docker/gates.Dockerfile` chown is in the same RUN as `uv sync`. The static test (`:297-312`) requires exactly one recursive chown 10001:10001 of /opt/venv and the cache, after the sync. |
| N7 | Fixed | Closed by M-1: fast mode always exports COMPOSE_FILE and the separator (`scripts/verify.sh:32-35`). |
| N8 | Open (orchestrator) | orchestrator-l5-env-verify-full.txt was still being written at review time. |
| N9 | Open (documenter) | quickstart umask note, routed to the docs step. |

## Security items as implemented
- M-1: implemented. `scripts/verify.sh:27-35` always pins `docker-compose.yml[:mask]` with `:` in fast mode; full mode is unchanged, with the mask appended.
  `tests/test_stack_scripts.py:873-898` covers both modes, with and without `.env`, a hostile caller `COMPOSE_FILE`/`;` separator, and a planted override.
- L-1: implemented. `user: "10001:10001"`, `USER 10001:10001`, `chown -R 10001:10001`, and `test_gate_services_run_as_uid_and_gid_10001`.
- L-2: implemented. `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]` on the x-gates anchor (both services, confirmed by config), and `test_gate_services_drop_capabilities_and_new_privileges` (also forbids `cap_add`).

## Mutant collateral: test_no_model_calls_in_unit_suite
Expected and correct. M1 deleted `network_mode: none` from `gates` in the base file. `tests/test_stack_model_skip.py:150-155` reads `cs.services()["gates"]["network_mode"]`, the base file only (PS-2.7),
so it independently kills the network_mode half of the mutant. It says nothing about the gates-it `edge` half. That half is the part that survived in round 0, and it is now killed by the `network='edge'` subtest. No other test failed, so the fix adds no unrelated breakage.

## Weakening check
Every changed assertion was checked against base:
- `_find_service` now reads the base, the authoritative definition. All-file loops still cover overlays for bind mounts and the socket.
- The followups test lost its stub-level combine assertion, but the hazard is now exercised by the real-erase test.
No test was skipped, deleted or loosened. Coverage TOTAL is unchanged at 89%. "Combined 3 files, skipped 2" is coverage de-duplicating identical data files, the same as before (green run: skipped 4).

## Nits (optional)
- n1 `tests/integration/test_gate_least_privilege.py:56-67`: in a worktree the `.git/hooks` target is dropped silently, and the test reports ok with no record. Prefer a subTest that calls `skipTest("….git is a file (worktree)")` so the run log shows it.
- n2 `tests/test_stack_scripts.py:876-877`: the planted `docker-compose.override.yml` is never read by the fake docker. The test proves the override is not loaded only through compose's rule that a set COMPOSE_FILE disables the auto-load. A one-line comment saying so would help, or a `docker compose config` check if the gates ever allow it.
- n3 `tests/test_gate_least_privilege.py:201`: `users[-1]` without the guard used at `:189`. It still fails (IndexError), but with a less clear message.
- n4 `tests/test_harness_followups.py:309`: the name `..._is_not_combined` now describes behaviour proven in another module. The comment says so; renaming is optional.
