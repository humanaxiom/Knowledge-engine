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

## After (ci-triggers PR, one push)

Fill in once the human approves the push of `agent/ci-triggers` and the PR.
- Query C: `gh run list --commit <head sha> --json databaseId,event,headSha,conclusion,createdAt,updatedAt`
  - run count (expect 1), run id: PENDING, event (expect pull_request): PENDING
- Query D: `gh run view <run id> --json jobs`
  - job start/finish and minutes: PENDING
- Pass: one run per PR push, against two before.

## After merge

Fill in once the human merges (CT-2, see `ct2-merge-commit.txt`).
- Query E: `gh run list --commit <merge sha> --json databaseId,event,headSha,conclusion,createdAt,updatedAt`
  - run count (expect 1), run id: PENDING, event (expect push): PENDING, job minutes (Query D form): PENDING
