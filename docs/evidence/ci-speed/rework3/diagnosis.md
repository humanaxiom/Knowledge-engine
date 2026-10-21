# ci-speed rework 3: why the unit pool is slower on CI (architect, 2026-10-21)

Diagnosis only: no production code, test, CI or script was changed. The
commit under test is `a375a4e`.

| Input | File (under `docs/evidence/ci-speed/`) |
|---|---|
| Pooled CI runs (red) | `ci/ci-39530356210.log`, `ci/ci-39530367383.log` |
| One-process CI baselines | `ci-39499437202.log` (542 s), `docs/evidence/platform-offline/ci-39370927416.log` (597 s) and `ci-39465361808.log` (793 s); stage parse `ci-stage-and-test-times.txt` |
| k replay | `rework3/infer_k.py`, `rework3/sizes-a375a4e.txt`, `rework3/infer-k.txt` |
| Per-test, pooled CI vs serial CI vs local | `rework3/compare_ci.py`, `rework3/per-test-compare-ci.txt` |
| Local CI-like box (7 runs) | `rework3/box/` (driver `drive.sh`, sampler `sample.sh`, `summ.sh`; `run-*`, `samples-*`, `stats-*`) |
| Local per-test, pool vs one process | `rework3/compare_local.py`, `local-pool-vs-onep-stack.txt`, `local-q1-pool-vs-onep-stack.txt` |
| Hook CPU vs wall | `rework3/hook_cpu_vs_wall.py`, `rework3/hook-cpu-vs-wall.txt` |

## 1. What the CI logs show

- **Runner spec is not in the log.** "Set up job" names only the hosted
  image (`ubuntu-24.04`, version 20261018.339.1), Azure `westus`, and runner
  "GitHub Actions 1000004269". The jobs API gives the labels `ubuntu-24.04`
  and nothing more. No line prints vCPU or RAM, and `test.sh` does not print
  k. The 7 GB figure below is GitHub's published spec for private-repo
  standard runners, not a measurement.
- **k was 2 (inferred, exact).** Replaying `test.sh`'s schedule (largest file
  first, at most k at once) with each module's `unit: <s>s` time gives
  847 s and 806 s for k = 2. The measured pool stage was 847.6 s and 806.4 s.
  k = 3 or 4 would give 753 s and 715 s (`infer-k.txt`). So `nproc` was 2
  inside gates-it, and the pool was saturated from start to end.
- **The runner was not generally slower.** Build took 44.6 and 42.4 s
  (baseline 48.4 s) and launch took 79.7 and 76.3 s (baseline 78.5 s). Only
  the unit stage regressed.
- **Unit stage:** pooled 847.6 and 806.4 s; one-process baselines 542, 597
  and 793 s (the earlier commit, without this item's pool tests).

Per-module wall time on CI for the modules this item did not change:

| Module | serial 542 / 597 / 793 | pooled 847 / 806 | pooled ÷ serial |
|---|---:|---:|---:|
| `test_offline_bundle` | 280 / 297 / 410 | 753 / 715 | 1.7–2.7 |
| `test_stack_scripts` | 160 / 180 / 225 | 375 / 359 | 1.6–2.3 |
| `test_offline_netprobe` | 19 / 21 / 29 | 48 / 45 | 1.6–2.5 |
| `test_stack_readiness` (real sleeps) | 17 / 18 / 21 | 37 / 38 | 1.8–2.2 |
| 6 unchanged heavy modules, summed | 490 / 535 / 710 | 1260 / 1207 | **1.70–2.57** |
| `test_harness_followups` (pool tests added by this item) | 16 / 19 / 25 | 257 / 241 | new work |
| `test_block_main_commit_hook` (pure CPU, no I/O) | 22 / 27 / 36 | 75 / 70 | 2.0–3.4 |

- **Per test:** unchanged-module tests that appear in the pooled
  `--durations 10` lists take 2.44× their serial-CI time in total
  (`per-test-compare-ci.txt`). The pwsh-heavy ones run 2.2–3.3× slower.
- **Throughput:** two modules at once delivered 2 ÷ (1.70–2.57) =
  **0.78–1.18×** the throughput of one process. So on this runner the second
  vCPU added close to nothing for this workload.

## 2. Local reproduction (CI-like box)

The box is a privileged `docker:29.9.1-dind` (the pinned offline-check image)
named `ke-arch-r3-box`, labelled `ke.arch-r3=1`, with the daemon on a unix
socket only.

- It ran with `--cpuset-cpus 0,1 --memory 7g --memory-swap 11g`, which gives
  a 7 GiB memory cap plus 4 GiB swap, as on the runner.
- The stack was the verify project brought up by `scripts/launch.sh`, with
  the same compose files and env as `verify.sh full`.
- Tests ran in `gates-it` (stack up) or `gates` (stack down) at `a375a4e`.
- Its images were loaded from this checkout. A nested build cannot reach
  PyPI, and `a375a4e` changes no Dockerfile, pyproject or lock file.
- The sampler reads the box's cgroup (the whole emulated machine) every
  5 s: CPU, PSI for cpu/memory/io, anon/file/shmem, swap, major faults and
  io bytes.
- The box and its volumes are removed. The orphaned anonymous volume of a
  first, aborted box was identified (created 02:21:39Z, a fresh dind tree)
  and removed. Nothing else was touched.

| Run | CPU | Stack | Shape | Wall | CPU avg | cpu PSI | mem PSI | io PSI | peak anon | swap |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| pool-stack | 2 cores | up | k=2, `test.sh full` | 295 s (pool 286) | 1.66 | 41.7 % | 0.00 % | 0.10 % | 1.37 GiB | 0 |
| onep-stack | 2 cores | up | one process (unit) | 462 s | 1.11 | 19.4 % | 0.01 % | 0.05 % | 1.43 GiB | 0 |
| pool-nostack | 2 cores | down | k=2, `test.sh fast` | 252 s (pool 249) | 1.58 | 25.9 % | 0.00 % | 0.01 % | 0.34 GiB | 0 |
| onep-nostack | 2 cores | down | one process (unit) | 420 s | 0.88 | 6.6 % | 0.00 % | 0.00 % | 0.29 GiB | 0 |
| q1-pool-stack | quota 1.0, nproc 2 | up | k=2, `test.sh full` | 576 s (pool 567) | 0.99 | 70.1 % | 0.03 % | 0.05 % | 1.36 GiB | 0 |
| q1-onep-stack | quota 1.0 | up | one process (unit) | 602 s | 0.90 | 38.3 % | 0.01 % | 0.05 % | 1.36 GiB | 0 |
| q1-k1-stack | quota 1.0 | up | k=1 (`OMP_NUM_THREADS=1`), `test.sh full` | 658 s (modules 649) | 0.90 | 39.1 % | 0.02 % | 0.06 % | 1.42 GiB | 0 |

PSI is the "some" share of the run. Peak total memory was 5.3–5.65 GiB, but
about 4 GiB of that is reclaimable page cache from the loaded images. Anon is
the working set. Every run was green, with coverage at 90 %.

- **Pool ÷ one process, pool stage only:**
  - 2 dedicated cores: **0.62×**, with tests 1.13× slower each
    (`local-pool-vs-onep-stack.txt`).
  - 1-core quota with nproc still 2: **0.94×**, with tests 1.74× slower each
    (`local-q1-pool-vs-onep-stack.txt`).
  - CI: **1.02–1.56×**, with tests 2.44× slower each.
- **The same pool gives anything from a 38 % gain to a 56 % loss, depending
  only on how much parallel CPU is behind `nproc = 2`.** `nproc` cannot tell
  these machines apart.
- **The 1-core model reproduces "no gain" and about 2× per-module inflation,
  but not CI's extra loss.** On CI two concurrent trees get less than one
  process's throughput. That points to SMT siblings, host contention/steal or
  a quota. The logs cannot tell these apart, and local hardware cannot
  reproduce them. **So this is not a faithful reproduction of CI's CPU.** It
  is faithful for memory, swap, the stack and I/O.
- **k = 1 per module** costs 1.08× a single process (+47 s at quota 1),
  because 32 more `uv run`/python/coverage start-ups run in series.
- **The stack** costs about 0.23 CPU on average (1.11 vs 0.88 for one
  process), which is 42–43 s (9–15 %) in both shapes. It was up in the serial
  CI baselines too, so it does not explain the regression.

## 3. Root cause

1. **CPU capacity, not memory and not I/O.** The pool assumes that the
   2 vCPUs `nproc` reports give about 2× the throughput of one process. The
   hosted runner gives 0.78–1.18×, so every module runs about 2.4× slower and
   the pool stage takes as long as, or longer than, one process.
   - Strongest single sign: the hook tests (bash/jq on in-memory input, no
     file I/O) run 2.0–3.4× slower when pooled.
2. **Memory and swap are ruled out at 7 GiB.** Anon peaked at 1.43 GiB with
   the stack up, swap stayed at 0, and memory PSI was ≤ 0.03 % in all 7 runs.
   - Caveat: CI's memory was never observed. The workload is the same, so
     only a runner far below 7 GB would change this.
3. **Disk I/O is ruled out locally.** io PSI was ≤ 0.1 %, each run read at
   most 23 MB, and `/tmp` is tmpfs. The pure-CPU hook tests inflate as much
   as the pwsh tests do.
4. **Contributing: this item's own tests.** `test_harness_followups` grew
   from 16 s to 241–257 s on CI (77–91 s locally). That is about 15 % of the
   pool's module-seconds, or about 2 min of wall time at k = 2.
5. **Bound:** `test_offline_bundle` alone takes 280–410 s serially on CI, so
   no pool shape gets the unit stage under that on this runner.

## 4. Options, with expected CI effect

| Option | Expected CI unit stage | Evidence | Verdict |
|---|---|---|---|
| (a) size k from memory as well as CPU | unchanged (806–847 s) | memory is not binding: anon ≤ 1.43 of 7 GiB, swap 0, mem PSI ≈ 0 | **Reject**: it fixes a bottleneck that does not exist |
| (b) unit stage before `launch.sh` | about −1 to −1.5 min in any shape (the stack's 0.23 CPU) | −42/−43 s locally on 2 cores (pool-nostack vs pool-stack, onep-nostack vs onep-stack) | **Not in this rework.** It changes `verify.sh` (CS-6 forbids that here; ADR-KE-009 ordering). Unit coverage (`gates`) and integration coverage (`gates-it`) would then sit in two tmpfs `/tmp`s, needing a shared writable volume (against PS-3.5) or a split `fail_under`. It needs its own ADR and a security review |
| (c) k = 1 below a threshold | about one process +8 % + pool tests (about +1.5 min) ≈ **670–960 s** (estimate, overlaps today's) | q1-k1 is 1.08× one process and 1.14× k=2. No CI run of k=1 exists. The threshold cannot be set on `nproc` (local cores and CI both report 2) | Possible only as `k = 1 when nproc < 4`, and only if local verify speed is worth about 1.5–2.5 min per CI run; needs the corrected CS-9 (§6) |
| (d) revert the pool | **542–793 s** (measured, 3 baseline runs), the pool tests' cost gone | the only option with a measured CI figure better than today | **Recommended** (§5) |
| (e1) cut the work in the heaviest classes (`InstallPs1Test`, `LintScriptTest`: 51 % of the suite; profile.md option (b)) | saves exactly the CPU it removes, on any runner | it is the only lever that helps a runner with about 1 core of parallel capacity | **Recommended as a new plan item** (tests only, one test at a time, each with a mutant) |
| (e2) a larger runner | unknown until measured; a 4-vCPU runner might let k ≥ 2 pay | n/a | Human/cost decision; it also changes the pinned `runs-on` |
| (e3) a resource line in `test.sh`: `nproc`, k, `MemTotal`, cgroup `cpu.max`, `/proc/pressure/{cpu,memory,io}` totals and `/proc/stat` steal, at the start and end of the unit stage | none | this diagnosis had to infer k and could not observe CI's CPU, memory or steal | **Recommended** with whichever option ships: about 5 lines, with a static test that the line is printed |

## 5. Recommendation

**(d): revert the pool shape. Keep what does not depend on it. Move the
speed goal to (e1). Put (e2) to the human.** (d) is the simplest option and
the only one whose CI figure is measured and better than today. The item's
outcome metric is CI time, which the pool cannot improve on this runner.

What changes under (d):

- **`test.sh`:** the top-level run goes back to one
  `coverage run -p -m unittest -v <all modules>` process.
- **Kept:**
  - the CS-5 fix and its test (nested `test.sh` never touches the gate's
    coverage data);
  - CS-8 (the hook header) and its test;
  - the coverage hardening that does not depend on the pool: `data_file`
    from the API, a `--data-file` label per run (`tests` for the top-level
    run), the explicit `combine` list and the leftover check;
  - optionally `--durations 20` on the single process, for CI timings.
- **Dropped:** k, ordering, per-module logs and `unit:` lines, the
  per-module `Ran` check, the INT/TERM pool trap, and the pool-only tests in
  `test_harness_followups`.

If the orchestrator rules that local verify speed justifies keeping the
pool, take (c) as `k = 1 when nproc < 4`. Before merging, it must pass the
CI-measured CS-9 in §6. Either way, add (e3). I amend §2.2.1 once the ruling
is made, with a recorded orchestration decision.

**Hook wall-clock budget tests.** Measure the hook's CPU time instead of wall
time: user + sys of the hook and its waited-for children, from the
`RUSAGE_CHILDREN` delta around the single `subprocess.run`.

- **The intent holds.** Linear cost, with no catastrophic backtracking, is a
  CPU property: a super-linear regression on 1–5 MB blows a CPU budget
  exactly as it blows a wall budget.
- **CPU time does not move under contention; wall time does.** On one CPU
  with 0/1/2 busy loops, 5 MB "windows paths" without jq took 2.26 / 5.03 /
  7.61 s of wall time but 2.25 / 2.51 / 2.53 s of CPU
  (`hook-cpu-vs-wall.txt`).
- **Headroom:** the worst CPU locally is 0.37 s against the 3 s budget
  (1 MB) and 2.53 s against 9 s (5 MB). CI cores are about 1.2–1.5× slower (one process: 540 vs 462 s; the 5 MB
  test serially: 10.4 vs 7.0 s).
- **Keep a hang guard.** `timeout=` on `subprocess.run` (for example 60 s)
  catches a hook that sleeps or blocks, which CPU time cannot see. It is a
  guard, not a budget.
- **Prior art.** The wall-clock 5 MB bound already flaked serially on CI once
  (platform-stack; the comment at `tests/test_block_main_commit_hook.py:536`).
- **Serialising is worse.** It needs a per-module exception list in
  `test.sh`, a second scheduling rule against §2.2.1 decision 1, and it would
  still be exposed to the stack's load.
- **Flag (analyst):** requirement 4f says "completes in under 3 s", which is
  wall-clock wording. It needs rewording to "uses under 3 s of CPU (user +
  sys, hook and children)" before the tests change.
- Under (d) this is hardening, not a blocker: serially the tests passed in
  all 3 baseline runs.

## 6. CS-9: is the method wrong for its purpose? Yes

CS-9 measured on 2 **dedicated physical cores** (this host has no SMT), with
**no stack and no memory cap**. It assumed one vCPU equals one core. Its
purpose is CI wall time on the hosted runner. §2 shows that the measurement
swings from 0.62× to 1.56× on the CPU model alone. Memory and the stack can be
modelled locally (no effect); the runner's CPU cannot. Corrected CS-9:

- **Measured on CI, same commit, A/B.**
  - Arm A is the candidate.
  - Arm B is the same commit with only the unit-stage shape changed (one
    process). It lives on a scratch branch, is never merged, and is pushed
    with the human's approval. No env key is added, so PS-2.21 stands.
  - Run each arm twice, interleaved in time, with the (e3) resource line in
    both.
- **Metric:** the unit stage from the runner's per-line timestamps
  (`lint: PASS` → the first line after the unit stage), parsed by
  `experiments/parse_ci.py`. Run ids, timestamps and the arithmetic are saved
  under `docs/evidence/ci-speed/`.
- **Pass:** A's slower run is faster than B's faster run (no overlap, given
  the ±25 % runner noise), **and** the A/B median ratio is ≤ 0.85.
  Otherwise the shape is not adopted for that runner. The target is not
  adjusted to pass.
- **The local box measurement** (2 CPUs, 7 GiB, stack up) stays as a
  regression check only. It is informational, not the acceptance figure.
- **Under (d), CS-9 is withdrawn**, since there is no speed claim, and the
  CHANGELOG states none.
