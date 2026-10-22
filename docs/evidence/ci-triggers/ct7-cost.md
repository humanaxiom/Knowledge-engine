# CT-7 cost on CI: ci-triggers

Read-only `gh` queries. Job minutes = `completedAt - startedAt` of the single `verify` job.

## Before (PR #11, one push)

Query A: `gh run list --branch agent/platform-supply-chain-closeout --json databaseId,event,headSha,conclusion,createdAt,updatedAt`

| Run id | Event | Head sha | Conclusion | Created (UTC) |
|---|---|---|---|---|
| 39723927881 | push | b3ea4f65d9074a40a61b3497b707f75d5fa90ef6 | success | 2026-10-22T04:43:06Z |
| 39724208839 | pull_request | b3ea4f65d9074a40a61b3497b707f75d5fa90ef6 | success | 2026-10-22T04:46:04Z |

Result: 2 runs on one head commit (events push and pull_request).

Query B: `gh run view 39723927881 --json jobs` and `gh run view 39724208839 --json jobs` (job `verify`, `startedAt`/`completedAt`)

| Run id | Job start | Job finish | Minutes |
|---|---|---|---|
| 39723927881 (push) | 04:43:09Z | 05:05:52Z | 22m43s = 22.7 |
| 39724208839 (pull_request) | 04:46:07Z | 05:06:48Z | 20m41s = 20.7 |

Total for that one push: 43m24s = 43.4 job minutes (44 billed if each job rounds up to a whole minute: 23 + 21).
Computed from Query B by subtraction.

## After (PR #12, one push)

Query C: `gh run list --branch agent/ci-triggers --json databaseId,event,headSha,status,conclusion`

| Run id | Event | Head sha | Conclusion |
|---|---|---|---|
| 39832485123 | pull_request | 3c3382ac55783d8a901da8aa0f3429e95e2ef6f6 | success |

Result: 1 run on the head commit (event pull_request, no push run).

Query D: `gh run view 39832485123 --json jobs` (job `verify`)

| Run id | Job start | Job finish | Minutes |
|---|---|---|---|
| 39832485123 (pull_request) | 2026-10-22T18:33:46Z | 2026-10-22T18:50:26Z | 16m40s = 16.7 |

## Comparison (CT-7)

| Per PR push | Before (PR #11, b3ea4f6) | After (PR #12, 3c3382a) |
|---|---|---|
| Runs | 2 | 1 |
| Job minutes | 43.4 (22.7 + 20.7) | 16.7 |
| Billed minutes (each job rounded up) | 44 (23 + 21) | 17 |

Pass: one run per PR push, against two. The change removes one of the two runs per PR push, worth roughly 17 to 24 job minutes given the single-run spread seen (16.7 to 23.6 min across the four runs).
The "about 48 billed minutes" estimate in ADR-KE-015 is replaced by these
measured figures (review N4). Computed from Queries B and D by subtraction.

## After merge

Query E: `gh run list --commit d6b70355c452a0d209a88cc6b1791f32c2aef7ad --json databaseId,event,headSha,status,conclusion`
- Merge commit d6b7035 on the default branch: run 39837794999, event push.
- Final state: completed, conclusion success, attempt 1; the only run on
  that commit (API `total_count` 1).
- Job `verify`: 2026-10-22T19:10:41Z -> 19:34:15Z = 23m34s = 23.6 job
  minutes (billed 24). Source: `ct2-merge-commit.txt` (tester, 2026-10-22).
