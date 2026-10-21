# CS-7: CI timeout re-measure (PS-3.4)

Commit under test: `24b6839` (PR #8, branch `agent/ci-speed`). Times are UTC,
2026-10-21, from `gh run view <id> --json startedAt,updatedAt,jobs`.

## The two green runs

| Run | Event | Run start | Run end | Run duration | Job `verify` start-end | Job duration | verify stage | Unit stage |
|---|---|---|---|---|---|---|---|---|
| 39559700392 | push | 07:06:26 | 07:27:32 | 21 min 06 s = 21.1 min | 07:06:29 - 07:27:31 | 21 min 02 s = 21.0 min | 1254 s | 893.6 s (Ran 724 tests in 893.552s) |
| 39559708963 | pull_request | 07:06:31 | 07:26:47 | 20 min 16 s = 20.3 min | 07:06:34 - 07:26:47 | 20 min 13 s = 20.2 min | 1206 s | 860.5 s (Ran 724 tests in 860.530s) |

The verify and unit figures come from the saved logs `docs/evidence/ci-speed/ci/ci-39559700392.log`
and `ci-39559708963.log` ("Ran 724 tests in ..."). Both runs conclude `success`.
The slower run is 39559700392; its run duration (21.1 min, including job queue
and setup) is the figure used, the larger of the two readings.

## Arithmetic (same rule as platform-offline)

slower run 21.1 min x 1.5 = 31.65 min, rounded up to a whole minute = **32 min**.
`timeout-minutes` goes 29 -> 32. (Using the job duration, 21.0 min, gives 31.5
-> 32; the result does not depend on the choice.)

## Resource-probe readings (`scripts/resource_probe.sh`, around the unit stage)

Start and end lines are in the two CI logs (`resources: phase=start` /
`phase=end`). Derived over the unit stage:

| Run | nproc | RAM | Swap used | cgroup CPU used / wall | PSI cpu "some" / wall | Throttled | Peak cgroup memory |
|---|---|---|---|---|---|---|---|
| 39559700392 | 2 | 8128876 KiB (8 GB) | none (swap_free 3145724 -> 3145704 KiB) | 819.4 s / 896.3 s = 0.91 cores | 289.6 s / 896.3 s = 32% | 0 | 472035328 B |
| 39559708963 | 2 | 8128876 KiB (8 GB) | none (3145724 -> 3145704 KiB) | 793.2 s / 863.0 s = 0.92 cores | 271.7 s / 863.0 s = 31% | 0 | 465551360 B |

Reading: two vCPUs, but the single-process unit stage used about 0.9 core, with
CPU pressure around a third of the time and no throttling, no swap and no
memory pressure. That fits a shared runner (contention without a quota), which
is why the earlier parallel pool did not help and was withdrawn. CPU steal ticks are 0 at both start and end of both runs
(`cpu_steal_ticks=0`).

## Per-module comparison

`docs/evidence/ci-speed/ci/permodule-39499437202-vs-39559700392.txt`: baseline
run 39499437202 (one process, before this item) vs 39559700392. Sum of per-module
seconds: 544 s (baseline) -> 902 s (now). Largest deltas:
test_offline_bundle +139 s, test_harness_followups +90 s, test_stack_scripts
+76 s, test_block_main_commit_hook +19 s, test_resource_probe +2 s (new).

## Honest note: what this item adds, and what is runner variance

- This item's own tests add about **110 s** per CI run:
  `tests.test_harness_followups` +90 s (the main contributor, 24 -> 41 tests,
  fixture cost), the hook CPU-time tests +19 s, the resource-probe tests +2 s.
- The rest of the slowdown is runner variance, not this item. Modules this item
  does not touch (for example test_offline_bundle, test_stack_scripts) ran
  about 1.5x slower than in the baseline run, and the earlier one-process
  baselines themselves spanned 542-793 s for the same suite.
- The +90 s fixture cost in test_harness_followups is recorded as a scope note
  for `test-diet` (TD note in `docs/requirements.md`).
- No speed claim is made (CS-9 withdrawn). The timeout rises because the suite
  and runner are slower than at the platform-offline measure (29 min), not
  because of any gain.
