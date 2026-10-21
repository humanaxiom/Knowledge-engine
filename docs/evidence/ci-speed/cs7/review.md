# Reviewer: ci-speed CS-7 close-out (2026-10-21)

Verdict: **APPROVED** (no blocking findings; 6 nits).

Scope reviewed: `git diff HEAD` on `agent/ci-speed` @ 24b6839 (ci.yml,
tests/test_stack_ready_docs.py, docs/requirements.md, docs/handoffs/ci-speed.md,
docs/log.md) plus untracked docs/evidence/ci-speed/cs7/ and ci/ files.

## Timeout recomputed (PS-3.4: slower run + 50 %, rounded up)

`gh run view <id> --json startedAt,updatedAt,jobs` (both success, headSha 24b6839):

| Run | Event | Run start-end | Run s | Job start-end | Job s |
|---|---|---|---|---|---|
| 39559700392 | push | 07:06:26-07:27:32 | 1266 (21.10 min) | 07:06:29-07:27:31 | 1262 (21.03 min) |
| 39559708963 | pull_request | 07:06:31-07:26:47 | 1216 (20.27 min) | 07:06:34-07:26:47 | 1213 (20.22 min) |

Slower run 21.1 x 1.5 = 31.65 -> **32** (job basis 31.55 -> 32). The value 32 is correct.
CI logs confirm `verify full: PASS (1254s)` / `(1206s)` and `Ran 724 tests in 893.552s` / `860.530s`;
resource-probe arithmetic in ci-timeout.md (819.4 s / 896.3 s, PSI 289.6 s) re-derived from the log lines and matches.

## Agreement across artifacts

ci.yml comment, CI_TIMEOUT_MINUTES comment, module docstring, assertion message,
requirements CS-7 MET, cs7/ci-timeout.md: all name 39559700392 (21.1 min),
39559708963 (20.3 min), 31.65 -> 32. Consistent. Per-module file confirms
test_harness_followups 16 s/24 tests -> 106 s/41 tests (+90), totals 544 -> 902.

## ci.yml invariants

Single step `./scripts/verify.sh full`; `runs-on: ubuntu-24.04`; checkout pinned
`fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09`, `persist-credentials: false`;
`permissions: contents: read`. Only line 17 changed. test_ci_calls_verify_only ok.

## Tests / gates

- Test not weakened: assertEqual on the exact pin kept; only constant/message/comments change (same pattern as platform-offline R5). CS-7 text was amended to say so.
- RED: cs7/red-verify-fast.txt, single FAIL test_ci_job_has_timeout `29 != 32` (expected reason), 724 run.
- GREEN: green-verify-fast.txt PASS (cov 90%), green-verify-full.txt PASS (552 s), test_ci_job_has_timeout ok, sentinel ok, test_handoff_line_cap ok.
- Handoff: 125 lines (< 200).
- Observability: no agent loop/model/retrieval/tool code touched; no span required.

## Done check (docs/handoffs/ci-speed.md)

Follows the README template's five fields and heading. Claims checked: metric
"neither" matches requirements' ci-speed header; "no data store, no query"
matches every prior Done check precedent; External blocker "none" is correct
(Q18 skipped, Q14 resolved 2026-10-20, open-questions.md:99).

## Nits (optional)

- N1. Handoff orchestrator bullet (line 113) calls 21.1 min the "job" duration ("job 21.1 min", "slower job 21.1 min"); the job was 21.0 min (1262 s), 21.1 is the run duration. Result unchanged.
- N2. Done check: headed "orchestrator" but drafted by the documenter; the later tester/developer/security bullets now sit under the Done check heading. Orchestrator should own/confirm it at close. "Value at the last milestone" cites platform-offline; the last milestone was model-roles (also 29 min), so accurate but imprecise.
- N3. TD note (requirements test-diet): "this item's own ~110 s" reads as test-diet's own under that heading; say "ci-speed's". It is nested as a 4th bullet of "Candidate cuts". The +90 s is a raw delta against one baseline run, not normalised for the ~1.5x runner variance the same evidence cites (16 s x 1.5 ~ 24 s, so ~80 s net), and part of it is 17 added tests; "fixture cost" is an inference. Directionally right; test-diet should re-profile before cutting.
- N4. ci.yml comment points at `docs/evidence/ci-speed` (directory) rather than `cs7/ci-timeout.md`. Meets CS-7 as written.
- N5. cs7/doc-verify-fast.txt is a FAIL (the same expected RED failure, from the tester's change in the shared tree) and the documenter's log gate says only "see evidence". Superseded by green-verify-fast.txt. cs7/orchestrator-verify-full.txt was incomplete at review time (no PASS line); do not cite it until the run finishes.
- N6. Commit hygiene: commit the untracked cs7/ and ci/ evidence (referenced by path); keep docs/knowledge-engine-claude-code-prompt.md out, as before.
