# ci-speed: where `scripts/verify.sh full` spends its time (architect, 2026-10-20)

Inputs: three green CI runs of `./scripts/verify.sh full` on `ubuntu-24.04`
(private repo, so the standard 2-vCPU / 7 GB runner), a local per-test profile
in the gates image, and five local sharding experiments. Raw files sit next to
this one; nothing here is pasted from memory.

| Source | File |
|---|---|
| CI 39370927416 (platform-offline, 16.6 min) | `docs/evidence/platform-offline/ci-39370927416.log` |
| CI 39465361808 (platform-offline, 19.0 min) | `docs/evidence/platform-offline/ci-39465361808.log` |
| CI 39499437202 (model-roles, 15.1 min) | `ci-39499437202.log` (fetched with `gh run view 39499437202 --log`) |
| Stage and per-test times parsed from all three | `ci-stage-and-test-times.txt` (parser: `experiments/parse_ci.py`) |
| Local unit suite with `unittest --durations 80` | `local-unit-durations.txt` |
| Sharding experiments A–E, pwsh probe, coverage-erase probe | `experiments/` |

## 1. Stage times on CI (seconds)

Times come from the runner's per-line timestamps, between the stage markers
each script prints (`Built`, `stack is up:`, `lint: PASS`, `Ran N tests`,
`smoke: PASS`, `offline: df …`, `== offline_check: PASS`).

| Stage | 39370927416 | 39465361808 | 39499437202 |
|---|---:|---:|---:|
| `build.sh` (ke-app, ke-gateway, ke-gates; no cache) | 50.8 | 37.5 | 48.4 |
| `launch.sh` (pull 4 store images, `up --wait`) | 81.7 | 79.5 | 78.5 |
| gates-it start + `lint.sh` | 7.0 | 8.0 | 6.3 |
| **unit suite (one process)** | **597.1** (679 tests) | **793.3** (685) | **542.0** (689) |
| integration suite | 5.1 | 8.7 | 4.7 |
| coverage combine/report + mypy | 8.2 | 9.4 | 5.9 |
| OTLP smoke (container half) | 1.3 | 2.3 | 1.7 |
| host smoke | 16.8 | 16.3 | 13.5 |
| teardown of the verify project | 10.7 | 7.1 | 9.9 |
| `offline_check.sh` | 207.5 | 170.3 | 191.9 |
| · `bundle.sh` (`docker save`, uncompressed) | 37.8 | 29.1 | 36.1 |
| · dind pull + up | 17.7 | 12.2 | 17.1 |
| · client install (`docker load` ×6) | 68.6 | 43.1 | 60.4 |
| · client launch (`up --wait`) | 49.0 | 52.6 | 48.7 |
| · client smoke | 16.5 | 19.2 | 14.3 |
| · client + dind teardown | 16.5 | 13.2 | 14.4 |
| **verify.sh total** | 986.2 | 1132.2 | 902.8 |
| job total | 991.2 | 1135.0 | 905.6 |

- The unit suite is 60–70 % of the job. Everything else adds up to a nearly
  fixed 340–390 s.
- The unit suite varies 542–793 s between runs of almost the same code, so
  the runner is noisy. The other stages vary by less than 15 %.
- Launch, in both launches: the pulls take about 35–45 s. `up --wait` takes
  42–50 s, because neo4j becomes healthy 34–44 s after it starts (healthcheck
  `interval: 10s`, `start_period: 20s`) and the api then needs about 5.5 s.
- Build, with no cache on the runner: the gates image's pwsh tarball and
  PSScriptAnalyzer step takes about 14 s, apt about 10 s, `uv sync` about 5 s,
  and base-image pulls 5–13 s, in parallel with the app and gateway builds.
  The most a cache could save is about 30–35 s.

## 2. What makes the unit suite slow

Per-test seconds on CI 39499437202 (542 s). The other two runs have the same
ranking (`ci-stage-and-test-times.txt`).

| Module | CI s | share | Heaviest classes (CI s) |
|---|---:|---:|---|
| `test_offline_bundle` (5196 lines) | 279.7 | 51.5 % | `InstallPs1Test` 166.9, `BundleScriptTest` 50.5, `BundleNoticesTest` 31.5, `InstallShTest` 28.1 |
| `test_stack_scripts` | 159.7 | 29.4 % | `LintScriptTest` 107.9, `LaunchPs1ResolvedTest` 20.1, `SmokeStoreStopStartTest` 10.1 |
| `test_block_main_commit_hook` | 21.9 | 4.0 % | the 5 MB and 1 MB hook inputs |
| `test_offline_netprobe` | 19.2 | 3.5 % | `SmokeCiOfflineTest` |
| `test_stack_readiness` | 16.9 | 3.1 % | `ReadinessCliTest` (real `--within` timeouts) |
| `test_harness_followups` | 15.9 | 2.9 % | `IntegrationRunsOnceTest` (nested `test.sh`) |
| the other 26 modules | 28.7 | 5.3 % | |

- Two modules hold 81 % of the time, and two classes hold 51 %
  (`InstallPs1Test` and `LintScriptTest`). Their tests run real `pwsh`,
  `bash`, `install.ps1`/`install.sh`, `bundle.sh` and `lint.sh` against fake
  docker/compose. Every subTest builds a new fixture bundle and starts a new
  installer process. The slowest single test is
  `test_lint_runs_no_code_from_a_powershell_filename`, at 46–67 s on CI: it
  runs real `lint.sh` 10 times (5 quotes × 2 shapes), and each run lints every
  repo script.
- pwsh start-up is **not** the cost. In the gates image, `pwsh -NoProfile`
  starts in 0.13–0.19 s and importing PSScriptAnalyzer takes about 0.3 s,
  whether `HOME` is `/` or writable (`experiments/pwsh-timing.txt`). The cost
  is the number of processes and the work each script does, not the start-up
  of any one tool.
- Locally (24 CPUs, one process) the suite takes 343 s. The top 80 tests take
  246 s, and of that `test_offline_bundle` takes 145 s and `test_stack_scripts`
  55 s (`local-unit-durations.txt`). CI is 1.6–2.3× slower, which fits a
  2-vCPU runner that also hosts the running stack.

## 3. Experiments (local, gates image, `--cpuset-cpus` to model the runner)

These five runs ran at the same time, each on its own CPU set, so they
shared disk and memory bandwidth. Compare them with each other, not with CI.
Scripts: `experiments/run_exp.sh` and `experiments/run_pool.sh` (host side),
`shard_experiment.sh` and `pool_experiment.sh` (in the container).

| Run | CPUs | Shape | Wall | Notes |
|---|---:|---|---:|---|
| A | 2 | one process (today) | 426 s | coverage 90 % |
| B | 2 | 2 fixed shards, modules split by file size (greedy) | 267 s | shards 267/187 s: unbalanced. **Coverage fell to 62 %** |
| C | 2 | 2 fixed shards, classes split by recorded CI seconds | 238 s | balanced, but needs a weights table kept in step with the tests |
| D | 2 | **one process per module, at most 2 at once, largest file first** | **242 s** | critical path `test_offline_bundle` 237 s. **Coverage fell to 77 %** |
| E | 8 | same pool, at most 4 at once | 217 s | bound by `test_offline_bundle` (217 s). **Coverage 83 %** (A gives 90 % for the same tests) |

All five ran 689 tests with no failures. Every per-module log had its
`Ran N` line, and the sentinel line came out whole. On 2 CPUs the pool takes
0.57× the time of one process.

### The coverage drop: a test that reaches the gate's own data

`IntegrationRunsOnceTest.test_coverage_erase_precedes_first_run_and_spares_checkout`
copies the real `pyproject.toml` into its throwaway project and runs the real
`test.sh` there. Its fake `uv` passes `coverage erase` and `coverage run -p`
through to the real interpreter. With `data_file = "/tmp/.coverage"` and
`parallel = true` from the copied file, the nested `erase` deletes **every**
`/tmp/.coverage.*` file in the gate container, and the nested runs add three
of their own. `experiments/coverage-erase-probe.txt` shows the gate's
`pid44` data file gone and `pid72/74/75` files added after that one test.

- **Today:** this is harmless only because of timing. The single unit
  process writes its data at exit, after the erase. The nested files measure
  no `engine` code and count as "skipped" in `Combined 3 files, skipped 2`.
- **Under any parallel scheme:** it deletes the data of every process that
  finished earlier. The gate then fails closed: coverage goes under 80 % and
  verify turns red, so a pass is never false. But the result depends on
  scheduling.
- This must be fixed in the test before or with the parallel change (§4).

## 4. Options

| Option | CI saving (est.) | Verdict |
|---|---|---|
| (a) One process per top-level unit module, in a pool of k = min(nproc, 4), started largest file first, in `test.sh` | unit 542–793 s → about 310–450 s (× 0.57, run D), so **about 4–6 min off a 15–19 min job** | **Recommended** |
| (a′) Split `test_offline_bundle.py` into 3 modules (bundle side, `InstallPs1Test`, `install.sh` side); classes move unchanged | about 0.5–1 min more on CI (the critical path drops from 237 s toward total/2 ≈ 213 s on 2 CPUs); locally about 340 s → about 100 s | Recommended as step 2, tests only |
| (b) Make the slowest tests cheaper without weakening them. Example: the 10 real `lint.sh` runs in `test_lint_runs_no_code_from_a_powershell_filename` lint only `lint.sh`, the planted file and one clean `.ps1` (at least 2 list entries, so the "closing" payload still parses in a list), not every repo script. Example: build the install fixture bundle once per class and copy it per subTest | Under the pool, CI gains about half of the CPU saved (k = 2). Locally it helps only on the critical path | Optional, tester-owned, one test at a time, each with a mutant to show it still bites |
| (c) Build cache through buildx in `verify.sh` | ≤ about 30–35 s for the build (plus about 40 s of store pulls, which a build cache does not cover) | **Not possible without a CI step.** The `type=gha` backend needs `ACTIONS_CACHE_URL`/`ACTIONS_RUNTIME_TOKEN` (v2: `ACTIONS_RESULTS_URL`), which the runner gives only to actions, not to a `run:` step. Exposing them needs an extra action step, which breaks the one-step rule (`test_harness_port`). `type=local` needs `actions/cache`, another step. `type=registry` needs `packages: write` and a `docker login` with the job token, which adds a credential and a push to the gate run (security-relevant) for under 1 min. Rejected |
| (d1) Overlap the unit suite (in `gates`, `network_mode: none`) with `launch.sh` | up to about 80 s, less on 2 contended CPUs | Deferred. Coverage would then span two containers with separate `/tmp` tmpfs, which needs a shared writable volume and goes against PS-3.5 least privilege |
| (d2) `healthcheck.start_interval` (Engine ≥ 25; the floor is 28) for neo4j and api | about 5–10 s per launch, × 2 launches | Small. Optional, compose-only. A JVM `cypher-shell` probe every few seconds competes for the 2 CPUs while neo4j boots, so measure it before adopting |
| (d3) A faster offline check | — | No. It is the PS-3.2 gate. Load and launch dominate, and the bundle is already uncompressed |
| (d4) A larger runner (public repos get 4 vCPU; private needs paid larger runners) | about 2× on CPU-bound stages | Out of scope, a human/cost decision. It also changes `runs-on`, which a test pins |
| Rejected: `pytest-xdist` or `unittest-parallel` | — | New dependency, and a different output format that the sentinel and `Ran N` checks depend on |
| Rejected: fixed shards (B, C) | — | B is unbalanced. C needs a maintained weights table. In both, which modules share a process depends on N, so it differs between machines |
| Rejected: an in-process multiprocessing runner | — | A custom runner, plus coverage `concurrency` config: more code to review for the same result as (a) |

Projected CI job with (a): 340–390 s fixed + 310–450 s unit, about
**11–14 min**. PS-3.4's rule (timeout = measured + 50 %) then applies to the
first two green runs after the change.

## 5. How the existing guarantees survive (a)

- **Sentinel.** `tests.test_sentinel` runs in its own process. Each module's
  output is buffered to `/tmp/ke-unit/<module>.log` and printed whole after
  the pool, in module order. The line
  `test_top_level_unit_suite_ran (…) ... ok` is never interleaved, so the
  regex in `verify.sh` matches as today.
- **"Ran N tests".** Every module prints its own `Ran N` line, so the
  `verify.sh` check passes on real output. `test.sh` adds a stricter check: it
  fails unless every module exited 0 **and** every module log has a
  `Ran N > 0` line. A dropped or silent module therefore turns the run red,
  which one process gave implicitly before.
- **Coverage.** Each process already uses `coverage run -p`, so each writes
  its own `/tmp/.coverage.<host>.<pid>.<rand>` file, and `coverage combine`
  reads them all, as today. This holds only after the test fix in §3. The
  threshold, `erase` before the first run, and mypy are unchanged.
- **CI and verify.sh** are unchanged. k comes from `nproc` inside the
  container, not from the caller, so the two-key rule (PS-2.21) stands.
