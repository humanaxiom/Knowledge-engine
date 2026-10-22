# PSC-9: CI cost of the image scan, and the CI timeout re-measure (PS-3.4)

Commit under test: `34fc0c1` (PR #10, branch `agent/platform-supply-chain`).
Times are UTC, 2026-10-22, from `gh run view <id> --json
event,headSha,createdAt,startedAt,updatedAt,conclusion,jobs`. Saved logs:
`docs/evidence/platform-supply-chain/ci/ci-39713504156.log` and
`ci-39713519072.log`. Both runs conclude `success`.

## The two green runs

| Run | Event | Run start | Run end | Run duration | Job `verify` start-end | Job duration | verify stage | Unit stage |
|---|---|---|---|---|---|---|---|---|
| 39713504156 | push | 02:49:44 | 03:14:13 | 24 min 29 s = 24.5 min | 02:49:47 - 03:14:13 | 24 min 26 s = 24.4 min | 1461 s (`verify full: PASS (1461s)`) | 1001.955 s (Ran 767 tests) |
| 39713519072 | pull_request | 02:49:55 | 03:12:55 | 23 min 00 s = 23.0 min | 02:49:57 - 03:12:54 | 22 min 57 s = 22.9 min | 1372 s | 934.776 s (Ran 767 tests) |

The slower run is 39713504156. Its run duration (24.5 min, including queue and
setup) is the figure used, the larger of the two readings, as at CS-7. Note
for the pull_request run: `gh` reports head SHA `34fc0c1`, and the log's
`== verify full: f5ff2de ==` line is the PR merge commit that GitHub checks out
for that event; the branch content is the same.

## Scan stage timings (marker line to the next marker line; ADR-KE-013 amendment 1, D8)

From the `scan: <stage> took Ns` lines in the two logs.

| Run | save | scan-db | scan | Total added |
|---|---|---|---|---|
| 39713504156 (push) | 2 s | 90 s | 6 s | 98 s |
| 39713519072 (pull_request) | 2 s | 81 s | 5 s | 88 s |

## Q60 check

The three stages add 88-98 s to the run. The Q60 trigger is more than 3 min
(180 s). 98 s is under 180 s, so the orchestrator needs no decision, and the
scan stays in every `verify.sh full`.

## Arithmetic (PS-3.4, same rule as platform-offline and CS-7)

slower run 24.5 min x 1.5 = 36.75 min, rounded up to a whole minute = **37
min**. `timeout-minutes` goes 32 -> 37. (Using the job duration, 24.4 min,
gives 36.6 -> 37; the result does not depend on the choice.)
`test_ci_job_has_timeout` pins the value (`CI_TIMEOUT_MINUTES` 37).

## Honest note: what grew, and what is variance

The job is 3.4 min (about 204 s) longer than at ci-speed (21.1 min, run
39559700392, `docs/evidence/ci-speed/cs7/ci-timeout.md`). The verify stage went
1254 s -> 1461 s (+207 s). Of that:

- The scan adds 98 s (this item, measured above).
- The unit stage also grew on CI: 1002 s vs 893.6 s at ci-speed (+108 s, +12%),
  with 767 tests vs 724 (+43 tests from this item). Part of that is the new
  tests and part is runner variance; this evidence does not separate them. The
  earlier one-process baselines spanned 542-793 s for the same suite, and
  ci-speed saw modules this item did not touch run about 1.5x slower than the
  baseline.
- 98 + 108 = 206 s accounts for the +207 s; the remainder is within rounding.

No speed claim is made. The timeout rises because the suite, the scan and the
runner together are slower than at the CS-7 measure (32 min), not because a
single stage regressed. Local scan timings (about +76 s at unit 4) were
informational only, as PSC-9 requires; CI is the measure.

## Resource-probe readings (`scripts/resource_probe.sh`, around the unit stage)

`resources: phase=start` and `phase=end` lines are in the two CI logs. Derived
over the unit stage (start line to end line):

| Run | nproc | RAM | Swap used | cgroup CPU used / wall | PSI cpu "some" / wall | Throttled | Steal ticks | Peak cgroup memory |
|---|---|---|---|---|---|---|---|---|
| 39713504156 | 2 | 8122984 KiB (about 8 GB) | none (swap_free 3145704 -> 3145704 KiB) | 899.9 s / 1005.4 s = 0.89 cores | 352.7 s / 1005.4 s = 35% | 0 | 0 | 418754560 B |
| 39713519072 | 2 | 8128876 KiB (about 8 GB) | none (swap_free 3145724 -> 3145724 KiB) | 834.8 s / 937.3 s = 0.89 cores | 311.7 s / 937.3 s = 33% | 0 | 0 | 426790912 B |

Memory PSI is negligible (about 0.08 s "some" and 0.05 s "full" growth in the
push run; about 0.12 s and 0.05 s in the pull_request run). Reading: the same
runner as at ci-speed (2 vCPU, 8 GB, 0.9 cores used, CPU pressure about a third
of the time, no throttling, no swap, no steal), so the unit-stage growth is not
a different machine; CPU contention on a shared runner remains the diagnosis.
