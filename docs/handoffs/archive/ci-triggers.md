# Handoff: ci-triggers

Plan item: `ci-triggers`. Outcome metric: none directly (CI infrastructure; moves
neither *drafts a human reviewer has acted on* nor *ratified rules*; say so in
the Done check). Branch: `agent/ci-triggers`, cut from
`agent/platform-supply-chain-closeout` (PR #11) so it carries the 37 min
timeout; rebase onto main once #11 merges.

## 2026-10-22 — orchestrator
- Asked to: open `ci-triggers` (human agreed 2026-10-22; see
  `docs/handoffs/NEXT-SESSION.md` §1.2 and the platform-supply-chain close-out
  security note in `docs/handoffs/archive/platform-supply-chain.md`).
- Problem: `.github/workflows/ci.yml` triggers on every `push` and every
  `pull_request`, so each push to a PR branch runs `verify.sh full` twice
  (measured 44 billed / 43.4 job minutes per PR push on a private repo, 17 /
  16.7 after, PR #12; roughly 40 green pushes a month on 2,000 min). PR #11
  shows it: runs 39723927881 (push) and 39724208839 (pull_request) on the same
  commit.
- Direction: run `push` only for the default branch (`ccr-19465ed4-j1u0m5`)
  and `pull_request` for branches. Keep `concurrency` sensible for both.
- Constraints to respect:
  - tests that pin ci.yml: `tests/test_harness_port.py`
    (`test_ci_calls_verify_only`), `tests/test_harness_followups.py` (runner
    label, pinned `uses`, checkout SHA, persist-credentials),
    `tests/test_stack_ready_docs.py` (`test_ci_job_has_timeout`, 37 min);
  - PS-3.4 (CI timeout = slower of two green runs + 50%): today the two runs
    come from push + pull_request on one commit. The analyst must restate how
    two green runs are obtained after this change (two pushes, or a re-run)
    and record it in the criteria, without changing the 37 min pin.
  - CLAUDE.md "What CI runs that verify.sh does not: Nothing": unchanged.
  - A branch pushed with no PR open gets no CI; that is accepted and must be
    written down (the developer opens a PR, or the human does).
- Next role (analyst): write `## Item: ci-triggers` in `docs/requirements.md`
  (criteria CT-1..n, each testable; name the outcome metric honestly), check
  prior art in `docs/handoffs/archive/ci-speed.md` and
  `docs/handoffs/archive/platform-supply-chain.md`, append here, log the event.

## 2026-10-22 — analyst
- Wrote CT-1..CT-7 and Q-CT1..Q-CT5 in `docs/requirements.md`. Evidence: none (requirements only). detail: docs/handoffs/archive/ci-triggers-part1.md

## 2026-10-22 — orchestrator (rulings on Q-CT1..Q-CT5)
- Q-CT1: no `pull_request` filter (stacked PRs still get CI).
- Q-CT2: keep `cancel-in-progress: true` for both events, group unchanged.
- Q-CT3: the human approves the CT-5 re-run, as for a push.
- Q-CT4: TD-5 Arm B becomes a draft PR, never merged; recorded as a test-diet
  follow-up, not done here.
- Q-CT5: pin the literal default-branch name in the test with a rename note.
- CT-5's one-line pointer in PS-3.4 is in scope for this item.
- Next role (architect): design note / ADR amendment; then tester RED.

## 2026-10-22 — architect
- ADR-KE-015 in `docs/architecture.md`: only the ci.yml `on:` block changes; `CiTriggersTest` designed. Evidence: expected under `docs/evidence/ci-triggers/`. detail: docs/handoffs/archive/ci-triggers-part1.md

## 2026-10-22 — tester (RED)
- `CiTriggersTest` added; verify fast RED with 6 failures, all new tests; mutants 0 unexpected. Evidence: `docs/evidence/ci-triggers/red-verify-fast.txt`, `red-mutants.txt`. detail: docs/handoffs/archive/ci-triggers-part1.md

## 2026-10-21 — developer (GREEN)
- ci.yml `on:` block, AGENTS.md bullet, README sentence; verify fast and full PASS. Evidence: `docs/evidence/ci-triggers/green-verify-fast.txt`, `green-verify-full.txt`. detail: docs/handoffs/archive/ci-triggers-part1.md

## 2026-10-21 — documenter
- Did: PS-3.4 pointer (CT-5) and CT status table in `docs/requirements.md`; README CI bullet re-wrapped (no word changes); history split to the archive file.
- Wrote `docs/evidence/ci-triggers/ct7-cost.md` before half: 2 runs on b3ea4f6, 22.7 + 20.7 = 43.4 job min (44 billed rounded up).
- Quick check: `uv run python -m unittest tests.test_stack_ready_docs -k CiTriggers -v` -> 3 tests OK. No verify run (docs only; orchestrator runs full before commit).
- Pending: CT-2 and CT-7 after halves need the human's push, PR and merge.

## 2026-10-21 — marketer
- CHANGELOG.md: `### 2026-10-21 (ci-triggers)` added under Unreleased (Changed, 2 bullets, 5 lines). README and AGENTS.md not touched by me; no code or tests.

## 2026-10-21 — reviewer
- Verdict: APPROVED. Diff matches ADR-KE-015 (ci.yml `on:` only); CiTriggersTest covers CT-1/3/6; 7 extra mutants all caught; ct7 before-half re-checked with `gh`, matches.
- No blocking findings; nits N1-N7 (dual `on` keys, green run predates docs edits, CHANGELOG "not twice" wording, ADR 48 vs measured 44, Q-CT rulings not in requirements, mutant script not saved, dates). Detail: `docs/evidence/ci-triggers/review.md`.
- Next: orchestrator verify full before commit (N2); CT-2/CT-7 after halves need the human's push, PR, merge.

## 2026-10-21 — security
- PASS, 0 critical/high/medium. The trigger set only gets smaller. Private repo with forking disabled, fork-PR workflows off, read-only token and no secrets. A hung job now bills 37 min per PR push, down from 74.
- Low, none blocking: L-1 no-PR/conflict gap (documented); L-2 no branch protection (Q18), so the merge-commit push run checks only after merge; L-3 cancel-in-progress on the default branch can cancel an earlier merge commit's run. Info: I-1 rename, I-2 tags, I-3 stacked base, I-4 `permissions` not pinned.
- Evidence sweep clean (no profile paths, SIDs, tokens or keys). No pin weakened (tests +76/-0). Detail: `docs/evidence/ci-triggers/security.md`, `security-sweep.txt`.

## 2026-10-21 — documenter (review nits)
- N3 CHANGELOG reworded; N5 Q-CT1..5 marked ruled in requirements; N6 mutant scripts saved in evidence (no profile paths found).
- Follow-ups recorded in requirements: N1, security L-3, I-4, N4.

## 2026-10-22 — orchestrator (commit gate)
- Review APPROVED (7 nits; N3/N5/N6 fixed, N1/N4 and security L-3/I-4 recorded as follow-ups); security PASS (3 low, 4 info, none blocking).
- Orchestrator verify full PASS 629 s (770 unit + 15 integration; `docs/evidence/ci-triggers/orchestrator-verify-full.txt`); diff read.
- Commit APPROVED: ci.yml `on:` block, AGENTS.md/README CT-6, CiTriggersTest, ADR-KE-015, requirements (item + PS-3.4 pointer + rulings), CHANGELOG, evidence, handoffs, log. Not the untracked NEXT-SESSION.md or the build prompt.
- Still pending after commit: CT-2/CT-7 after-halves need the human's push, PR and merge.

## 2026-10-22 — orchestrator: milestone Done check (drafted by the documenter, orchestrator to confirm)
- Outcome metric(s) this item names: neither *drafts a human reviewer has acted on* nor *ratified rules*; this is CI infrastructure (workflow triggers).
- Value now: none moved; query: n/a (no data store or live page exists yet). The item's own figure, from `gh` (`docs/evidence/ci-triggers/ct7-cost.md`): runs per PR push 2 -> 1, job minutes 43.4 -> 16.7 (billed 44 -> 17; PR #11 before, PR #12 after).
- Value at the last milestone: none moved; query: n/a (platform-supply-chain, same reason).
- If it did not move, why: by design; nothing a reviewer or ratifier can act on exists until the later product items. This item only cuts duplicate CI runs.
- External blocker, if any: none

## 2026-10-22 — documenter (close-out)
- ct7-cost.md after-half and comparison filled from `gh` (PR #12 run 39832485123, 16m40s; merge run 39837794999 push, in progress at 19:10Z).
- requirements: CT-2 MET (PR half; merge half in `ct2-merge-commit.txt`, tester), CT-7 MET, N4 dropped; ADR-KE-015 and orchestrator section use measured figures.
- platform-skeleton closing line added; Done check drafted above. No verify run (docs only).

## 2026-10-22 — tester (CT-2 evidence)
- PR head `3c3382a`: one run, 39832485123, pull_request, success, 16.7 job min (`docs/evidence/ci-triggers/ct2-pr-head.txt`); merge `d6b7035`: one run, 39837794999, push, success, 23.6 job min (`ct2-merge-commit.txt`).
- CT-2 now plain MET in requirements; ct7-cost.md "After merge" filled. Read-only `gh` only; no verify run (evidence/docs only), nothing unexpected.

## 2026-10-22 — security (close-out)
- PASS: docs/evidence only (6 `docs/**/*.md` + 2 ct2 txt); no code/test/workflow/compose/Dockerfile/script change. No tokens, keys, profile paths, SIDs, emails or internal hosts; no gh `actor`/avatar/node_id blocks (all queries `--jq`/`--json` projected).
- Info only: I-1 public job URL (org/repo already committed); I-2 untracked `orchestrator-closeout-verify-full.txt` out of scope, quick check clean. Detail: `docs/evidence/ci-triggers/security-closeout.md`.

## 2026-10-22 — reviewer (close-out)
- APPROVED, 0 blocking. Docs-only diff; all ct7/ct2 figures re-derived with own `gh` (4 runs, head_sha counts 2/1/1, PR #12 base = default); CT-2/CT-7 MET evidence exists; N4 consistent in ADR + handoff; Done check per template. Nits N1-N5 (62% partly run variance; platform-skeleton line lacks "+ part1"/"Next:"; re-wrap line 16; stale documenter line; blank line/table date). Detail: `docs/evidence/ci-triggers/review-closeout.md`.

## 2026-10-22 — documenter (close-out nits)
- Review close-out nits N1 (ct7 cost sentence), N2 (platform-skeleton line), N3 (re-wrap), N5 (blank line, table date) fixed; N4 left (append-only). Docs only, no verify.

## 2026-10-22 — orchestrator: close-out confirmation
- Done check CONFIRMED (drafted by the documenter; figures checked against ct7-cost.md and the reviewer's own gh queries). Metrics unmoved by design: CI infrastructure.
- Close-out review APPROVED (5 nits; N1/N2/N3/N5 fixed, N4 left: append-only), security PASS (2 info). Orchestrator verify full PASS 667 s on the final tree (`docs/evidence/ci-triggers/orchestrator-closeout-verify-full.txt`; 770 unit + 15 integration).
- Commit APPROVED: this handoff moves to `docs/handoffs/archive/ci-triggers.md` in the same commit. ci-triggers CLOSED pending push. Next item: platform-sbom.
