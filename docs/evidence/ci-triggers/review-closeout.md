# ci-triggers close-out review (reviewer, 2026-10-22)

Scope: `git diff` on `agent/ci-triggers-closeout` (base d6b7035) plus the untracked
`docs/evidence/ci-triggers/ct2-pr-head.txt` and `ct2-merge-commit.txt`.
Ignored, as asked: `docs/handoffs/NEXT-SESSION.md` and `docs/knowledge-engine-claude-code-prompt.md`.

Verdict: APPROVED (0 blocking, 5 nits).

## Docs only
- `git diff --stat d6b7035 -- . ':!docs'` is empty and `git status --short -- . ':!docs'` is empty.
  Changed: architecture.md (+2/-1), ct7-cost.md, handoffs/ci-triggers.md, handoffs/platform-skeleton.md (+1),
  log.md (+3), requirements.md (2 rows, N4 bullet removed). No code, test, ci.yml or script change.
- Handoff is 103 lines, under the 200 cap.

## gh re-check (reviewer's own queries, read-only)
`gh run view <id> --json event,headSha,headBranch,status,conclusion,attempt,jobs`:

| Run | Event | Branch | Head | Concl. | Attempt | verify start -> finish | Job min |
|---|---|---|---|---|---|---|---|
| 39723927881 | push | agent/platform-supply-chain-closeout | b3ea4f6 | success | 1 | 04:43:09Z -> 05:05:52Z | 22m43s = 22.7 |
| 39724208839 | pull_request | agent/platform-supply-chain-closeout | b3ea4f6 | success | 1 | 04:46:07Z -> 05:06:48Z | 20m41s = 20.7 |
| 39832485123 | pull_request | agent/ci-triggers | 3c3382a | success | 1 | 18:33:46Z -> 18:50:26Z | 16m40s = 16.7 |
| 39837794999 | push | ccr-19465ed4-j1u0m5 | d6b7035 | success | 1 | 19:10:41Z -> 19:34:15Z | 23m34s = 23.6 |

`gh api repos/humanaxiom/Knowledge-engine/actions/runs?head_sha=<sha>` total_count:
b3ea4f6 = 2 (push + pull_request), 3c3382a = 1 (pull_request), d6b7035 = 1 (push).
`gh pr view 12`: head 3c3382a, merge commit d6b7035, base `ccr-19465ed4-j1u0m5` (= repo default branch), 1 commit, MERGED 19:10:34Z.
`gh run list --branch agent/ci-triggers`: one run only (39832485123).

Arithmetic: 22.7 + 20.7 = 43.4 (43m24s); billed 23 + 21 = 44; after 17; merge 24;
43.4 - 16.7 = 26.7; 26.7 / 43.4 = 61.5% ("about 62%"). Every number in ct7-cost.md,
ct2-pr-head.txt and ct2-merge-commit.txt matches.

## Checks
- CT table: CT-2 MET cites ct2-pr-head.txt and ct2-merge-commit.txt (both exist, raw gh output, PASS
  verdicts match the criterion: PR targeting the default branch -> one pull_request run; merge -> one push run;
  run ids named in the handoff tester section). CT-7 MET cites ct7-cost.md (exists; before, after, comparison,
  after-merge filled; claim taken from measured numbers as CT-7 requires).
- N4: ADR-KE-015 context and the orchestrator handoff section both now say "44 billed (43.4 job) ... 17 billed
  (16.7 job) after (PR #12)"; ct7-cost.md records the replacement; the N4 follow-up bullet is removed. No
  remaining "about 48" in tracked live docs (only historical review.md and ignored NEXT-SESSION.md).
- Done check: all five template fields present; figures (2 -> 1, 43.4 -> 16.7, 44 -> 17, PR #11 / PR #12) match
  ct7-cost.md; "query: n/a" with reason matches the platform-supply-chain precedent. Heading carries
  "(drafted by the documenter, orchestrator to confirm)": the orchestrator still has to confirm it.
- Log: documenter close-out (2026-10-22T19:12:17Z) and tester CT-2 (19:36:31Z) entries present; also the
  developer commit line (05:49:34Z) that post-dated commit 3c3382a.

## Findings

Blocking: none.

- N1 (attribution of the 62%). ct7-cost.md "Job minutes fall by 26.7 (about 62%)" compares two runs before with
  one fast run after. A single verify run varied 16.7-23.6 min across these four runs (the merge run took 23.6),
  so part of the 26.7 is run-to-run variance, not the trigger change. The measured figures are correct and are
  what CT-7 asks for; suggest one sentence: "the change removes one of two runs per PR push; one run varied
  16.7-23.6 min here, so the saving per PR push is one run, roughly 17-24 job min."
- N2 (platform-skeleton line style). Other closing lines cite the part1 archive ("archive/platform-supply-chain.md
  + part1") and end with "Next: ..." and follow-ups. The ci-triggers line has neither: suggest
  "(archive/ci-triggers.md + part1)" and "Next: platform-sbom; test-diet queued (TD-5 draft PR, Q-CT4);
  follow-ups in requirements (N1, L-3, I-4)." archive/ci-triggers.md is created by the orchestrator's archive move.
- N3 (handoff rewrite). The orchestrator section (lines 15-17) was edited in place. N4 asked for exactly that, so
  acceptable, but the new line 16 runs past the wrap width; re-wrap. AGENTS.md's append-only rule otherwise holds.
- N4 (stale documenter line). The documenter close-out says merge run "in progress at 19:10Z" and "CT-2 MET
  (PR half ...)"; the tester section after it supersedes both. Append-only, so leave; the orchestrator should
  read the tester section as current.
- N5 (cosmetic). Double blank line before the Done check heading; requirements status table header still
  "Status (documenter, 2026-10-21)" though rows were updated 2026-10-22.
