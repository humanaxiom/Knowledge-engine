# Review: platform-offline unit 1 (L-5, PS-3.5), 2026-10-19

Reviewer, read-only. Base 4b19971, working tree on agent/platform-offline (uncommitted).
Verdict: **CHANGES REQUESTED** (2 blocking, 9 non-blocking).

Command run: `COMPOSE_PROJECT_NAME=ke-review-l5 scripts/verify.sh fast`, PASS, 429 tests
(`docs/evidence/platform-offline/review-l5-verify-fast.txt`). No `.env` on this host, so the mask path did not run there.
I also ran these read-only probes in throwaway `docker run --rm --network none --user 10001` containers on `ke-gates:latest`, with no compose project:
P1 coverage erase, P2 uv drift, P3 the mask on Docker Desktop. Mutant M1 ran in-process by monkeypatching `cs.load`, with no files edited.

## Conformance
- §2.2 L-5 / PS-3.5: uid 10001 (compose + last `USER`), read-only `/work`, exec tmpfs `/tmp` mode 1777,
  `MYPY_CACHE_DIR`/`PYTHONDONTWRITEBYTECODE`/`GIT_OPTIONAL_LOCKS` on both services (gates-it through a merged gates-env + model-env anchor),
  `UV_CACHE_DIR=/opt/uv-cache` set before sync, `chown -R 10001:0` after the last sync, `data_file=/tmp/.coverage`,
  `rm -f .coverage.*` dropped, no `UV_NO_SYNC`/`COVERAGE_FILE`. All conform.
- `docker compose config` with the mask merges correctly: `/work/.env` gets the bind `docker/empty` read-only, and networks and profiles stay unchanged.
- P3: on Docker Desktop (Windows), an empty file bound read-only over an existing file in a read-only bind mount reads as 0 bytes, and appending to it gives EROFS. The design works on the Windows path.

## Blocking

### B1. The mask overlay hides the PS-2.7 gates-it network test
- `tests/compose_support.py:28-31` sorts the compose files. `docker-compose.gates-mask.yml` therefore comes before `docker-compose.yml`, and
  `tests/test_stack_compose.py:39-43 _find_service` returns the partial definition in the **overlay** for `gates` and `gates-it`.
- `test_gates_it_internal_only_and_no_socket` (`tests/test_stack_compose.py:180-194`) now checks the copied overlay keys
  `networks: [backend]` and `network_mode: none`, not the base file.
- Mutant M1: in base `docker-compose.yml`, gates-it networks = `[backend, edge]` and gates `network_mode` removed.
  - With the overlay present, `NetworksTest` has **0 failures**, and the whole `tests.test_stack_compose` module passes (24 tests).
  - With the overlay excluded from `compose_files()`, there are 2 failures (`network=edge`).
  - No other test checks the gates-it networks. Compose merges `networks` as a union, so the runtime config would really be on `edge`.
- The keys copied into `docker-compose.gates-mask.yml:9-10,14-15` (profiles/network_mode/networks) exist only to satisfy these
  tests. They are a second copy of the base config that will drift.
- Fix:
  - The overlay carries only the mask `volumes` (plus `profiles` only if compose requires it; it does not).
  - Fix the test helpers so they read the base definition (`cs.services()`) for per-service properties. Classify overlay entries by
    their base service, not by the `profiles` of the overlay entry (`test_stack_services_have_no_bind_mounts`,
    `test_compose_services_have_restart_policy` one-shot loop).
  - Add a test that the mask overlay defines only the `/work/.env` read-only bind for the two gate services. Re-run M1 to show it is killed.

### B2. The rewrite of `test_stale_parallel_coverage_data_is_not_combined` weakens it
- File: `tests/test_harness_followups.py:309-332`, and the comment at `pyproject.toml:39-40`.
- The test now rests on a false premise. Its comment, and architecture §2.2, say that `coverage erase` "honours data_file and removes the parallel files". It does not.
  - coverage 7.16.2 `Coverage.erase()` calls `CoverageData.erase(parallel=self.config.parallel)`, and only `parallel=True` globs `data_file.*`.
  - `[tool.coverage.run]` has no `parallel = true`; `-p` on `coverage run` does not change what erase does.
  - Probe P1, as uid 10001 in the gates image: planted `/tmp/.coverage.stale-host.pid1.x1y2z3`, then ran `uv run --locked python -m coverage erase` (rc 0).
    **The file is still there.**
- The new assertions are:
  1. `data_file` is under `/tmp`;
  2. `erase` runs before the first `coverage run` (true before this change too);
  3. a file planted in the checkout survives.
  None of them exercises "stale parallel data is not combined", the B5 behaviour the test is named for.
- The behaviour still holds today, but only because `/tmp` is a fresh tmpfs for each `docker compose run` container. No test or comment names that as the guarantee.
- Ruling: the intent is a legitimate rework. The old assertion needed a delete in the now read-only checkout. As written, though, it replaces a behavioural check with assertions that cannot fail on the hazard, so it is a weakening.
- Fix, either of:
  - (a) add `parallel = true` to `[tool.coverage.run]`, so erase really removes `/tmp/.coverage.*`. Then add a behavioural fast test: run the real
    `python -m coverage erase` with the `[tool.coverage.run]` table of the repo (`data_file` redirected to a temp dir) and assert a planted
    stale parallel file beside that data file is gone.
  - (b) keep the config, state the per-container tmpfs as the guarantee in the test and the pyproject comment, and assert it.
  - (a) is preferred, because it does not depend on how test.sh is invoked.
  - Either way, correct the pyproject comment. Architecture §2.2 also states the erase claim; route that to the architect.

## Non-blocking
- N1 `tests/integration/test_gate_least_privilege.py:64-67`: with no host `.env` the test returns and reports ok while asserting nothing.
  That is what happens on CI and on this machine. Use `self.skipTest(...)` with a named reason.
- N2 same file, `:71-72`: `_try_write(env)` opens with mode `x`, which fails with EEXIST on any existing file whether or not it is read-only.
  P3 confirmed this: `FileExistsError` where append gave EROFS. The read-only mask assertion is vacuous. Open with mode `a` and assert `errno.EROFS`.
- N3 same file, `:98`, the drift test. The regex `(?i)lock|no solution found|network was disabled` passes almost any uv error, because "lock" matches `uv.lock` and the venv `.lock` path.
  - Tighten it to the two real messages.
  - What the test proves (probe P2, drifted pyproject, offline, uid 10001):
    - `--locked` gives rc 1 ("No solution found ... network was disabled").
    - Plain `uv run` gives the **same** rc 1 and message.
    - `--frozen` gives **rc 0**, and it re-installs the project into `/opt/venv`.
  - So it proves more than the control: it catches an env-level bypass (UV_FROZEN/UV_NO_SYNC). It cannot tell `--locked` from a plain run offline, but that is pinned statically (`tests/test_engine_quality.py:147`, `tests/test_harness_port.py:223`).
  - Also assert `UV_FROZEN` is unset. Point `UV_PROJECT_ENVIRONMENT` at a temp dir for the drift case, so a bypass mutant cannot re-point the shared `/opt/venv` at a deleted temp dir mid-run.
  - DR38 asks for a recorded red run with an extra dependency; this uses a version bump and no red-run evidence file exists. That is for the orchestrator to rule on.
- N4 same file, `:51`: in a git worktree `/work/.git` is a file, so the `.git/hooks` probe fails with ENOTDIR, not EROFS, and the test goes red. Verify runs in worktrees use the per-worktree tag (§2.1).
  Skip that target with a reason when `.git` is not a directory.
- N5 `docker-compose.yml:46`: architecture §2.2 says long syntax `read_only: true`, but short `:ro` is used. They are equivalent. Either amend the text or switch.
- N6 `docker/gates.Dockerfile:69`: a separate `RUN chown -R` layer stores the whole venv and cache a second time. Do the chown in the same RUN as `uv sync`, or create
  the dirs owned by 10001 and sync as `USER 10001`. Gates image only (not bundled, R7).
- N7 `scripts/verify.sh:33-35`: fast mode now overrides a `COMPOSE_FILE` set by the caller only when `.env` exists. That is harmless, but its behaviour now depends on whether `.env` exists.
  In full mode the mask also reaches build/launch/smoke/teardown through the exported `COMPOSE_FILE`. That is harmless because both services are profile-only (checked with `config`).
- N8: the runtime mask path is not exercised by any recorded run. The planned throwaway-`.env` full run by the orchestrator must save its output under this directory.
- N9: architecture §2.2 promises a `docs/quickstart.md` note on `umask 077` checkouts. It is not in this diff (documenter).

## Regressions checked
- Smoke, launch and teardown: the overlay only adds the profile-only gate services, so they are unaffected. The developer full run passed (green-l5-verify-full.txt).
- Windows: `MSYS_NO_PATHCONV` is exported before `COMPOSE_FILE`, and `COMPOSE_PATH_SEPARATOR=":"` matches the full-mode precedent. Fast mode PASSES here, and P3 shows the
  mask works on Docker Desktop.
