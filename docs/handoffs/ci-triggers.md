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
  (about 48 billed minutes on a private repo; roughly 40 green pushes a month
  on 2,000 min). PR #11 shows it: runs 39723927881 (push) and 39724208839
  (pull_request) on the same commit.
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
