# ci-triggers - part 1 history (analyst, architect, tester RED, developer GREEN)

Moved from docs/handoffs/ci-triggers.md on 2026-10-21 to keep it under 200 lines.

## 2026-10-22 — analyst
- Asked to: write `## Item: ci-triggers` (CT-1..n) in `docs/requirements.md`
  before `## Item: test-diet`; restate PS-3.4 two-run sourcing; flag questions.
- Did: added the section (`docs/requirements.md` lines 2606-2686): CT-1
  trigger shape, CT-2 one run per event, CT-3 concurrency, CT-4 pins
  unchanged, CT-5 PS-3.4 restated, CT-6 docs, CT-7 cost measured on CI;
  one follow-up (test-diet TD-5); open questions Q-CT1..Q-CT5.
- Decided/found:
  - `github.ref` is `refs/pull/<n>/merge` (pull_request) vs
    `refs/heads/<default>` (push): groups are already disjoint, so the
    concurrency group needs no change (CT-3).
  - CT-5 recommends a manual re-run (attempt 2) of the PR's pull_request run
    for PS-3.4, not PR run + post-merge push run (different commit, after
    merge, would push the timeout commit into another PR).
  - New edge: a PR with a merge conflict gets no pull_request run (today
    the push run still covers it); written into CT-6.
  - Bend: `yaml.safe_load` reads key `on` as `True`; CT-1's test must read
    `workflow.get("on", workflow.get(True))`. Existing pins
    (`test_ci_calls_verify_only` raw `run:` regex, no `-latest` anywhere in
    ci.yml text, checkout SHA/persist-credentials, timeout 37) are
    untouched by an `on:`-only diff.
  - Conflict: test-diet TD-5 Arm B "scratch branch never merged" gets no CI
    under CT-1 (Q-CT4: draft PR recommended).
- Evidence: none (requirements only); diff `git diff docs/requirements.md`.
- Next role needs to know: orchestrator rules Q-CT1..Q-CT5 (recommendations
  in the section); architect confirms the YAML shape; CT-2/CT-7 evidence
  needs a push and PR, which need the human's approval.

## 2026-10-22 — architect
- Asked to: design note for CT-1..CT-7 under the Q-CT1..Q-CT5 rulings.
- Did: new ADR-KE-015 in `docs/architecture.md` (lines 6476-6531; no
  earlier ADR covers triggers) and added it to the §9 index sentence.
- Decided:
  - ci.yml: only the `on:` block changes, to the block in ADR-KE-015
    (`push: branches: [ccr-19465ed4-j1u0m5]`, bare `pull_request:`, a
    4-line comment with no `-latest`, `run:` or `uses:`). Checked:
    `yaml.safe_load` gives `{True: {'push': {'branches': [...]},
    'pull_request': None}}`; the raw `run:`/`uses:`/`-latest` regexes in
    the existing pins find nothing in it.
  - Tests: new class `CiTriggersTest` in `tests/test_stack_ready_docs.py`
    after `CiTimeoutTest`; constant `DEFAULT_BRANCH = "ccr-19465ed4-j1u0m5"`
    with a comment that a rename updates ci.yml and this constant (Q-CT5);
    add a ci-triggers bullet to the module docstring. PyYAML is a runtime
    dependency (pyproject, uv.lock 6.0.3), already used by
    `test_ci_job_has_timeout`: no regex fallback, no new dependency.
    1. `test_ci_triggers_push_default_branch_and_pull_request` (CT-1):
       `on = workflow.get("on", workflow.get(True))`, not None; keys ==
       {push, pull_request}; `on["push"] == {"branches": [DEFAULT_BRANCH]}`;
       `on["pull_request"] in (None, {})`. RED today (push is None).
    2. `test_ci_concurrency_per_ref` (CT-3): group == `ci-${{ github.ref }}`,
       `cancel-in-progress is True`. Green on arrival (pin, not RED).
    3. `test_docs_say_ci_needs_a_pull_request` (CT-6): lowercase and
       whitespace-normalise; AGENTS.md `## Branch Policy` section (same
       regex as `AgentsHookWordingTest`) contains P1, P2 and "merge
       conflict"; README.md contains P1 and P2. RED today.
       P1 = "ci runs only on pushes to the default branch and on pull requests"
       P2 = "a branch pushed with no open pr gets no ci"
  - AGENTS.md Branch Policy, new last bullet (documenter):
    "- CI runs only on pushes to the default branch and on pull requests. A
    branch pushed with no open PR gets no CI, so the developer (with the
    human's approval) or the human opens a PR for it; a draft PR is fine. A
    PR with a merge conflict gets no `pull_request` run until the conflict
    is resolved."
  - README CI bullet (line 211), sentence appended (documenter):
    "CI runs only on pushes to the default branch and on pull requests: a
    branch pushed with no open PR gets no CI, and a PR with a merge conflict
    gets none until the conflict is resolved."
  - PS-3.4 pointer (CT-5, documenter): append to the PS-3.4 bullet in
    `docs/requirements.md` (ends line 1214, before `[unit: ...]`):
    "From `ci-triggers` on, the two green runs are a PR's `pull_request` run
    and its manual re-run (attempt 2) on the same head commit (CT-5)."
  - Docs say "the default branch", never its literal, so a rename touches
    only ci.yml and `DEFAULT_BRANCH`. CLAUDE.md is not edited (CT-4).
- Evidence expected under `docs/evidence/ci-triggers/`:
  - `ct7-cost.md` "before" half: `gh run list --commit <PR #11 head>` and
    `gh run view <id> --json jobs` for 39723927881 / 39724208839. Read-only;
    can be produced now.
  - `ct2-pr-head.txt` + `ct7-cost.md` "after" half: `gh run list --commit
    <head sha>` showing one run, event `pull_request`, and its job minutes.
    Needs the human to approve the push of `agent/ci-triggers` and the PR.
  - `ct2-merge-commit.txt`: one run, event `push`, on the merge commit.
    Needs the human's merge; it lands in a close-out commit, as
    platform-supply-chain's did.
  - No CT-5 re-run now: the 37 pin is not re-measured in this item.
- Next role needs to know: the tester writes tests 1 and 3 RED first (test 2
  is a pin and is green on arrival; say so in the RED report); the ci.yml
  diff means `scripts/verify.sh full`. No spans (no agent/model/tool code).

## 2026-10-22 — tester (RED)
- Asked to: add `CiTriggersTest` per ADR-KE-015; run verify fast; mutants.
- Did: `tests/test_stack_ready_docs.py`: `DEFAULT_BRANCH` + rename note
  (Q-CT5), CT-6 phrase constants, docstring bullet, `_flat()`, class
  `CiTriggersTest` after `CiTimeoutTest`. CT-1 logic sits in
  `assert_triggers(path=CI)` so mutants drive the same code. README check
  uses `assertTrue(phrase in readme)` so a failure does not dump README.
- Command: `COMPOSE_PROJECT_NAME=ke-tester-ct scripts/verify.sh fast`
  (throwaway `.env` from `.env.example` + marker, removed after). Result:
  `Ran 770 tests`, `FAILED (failures=6, skipped=8)`, sentinel ok, lint PASS.
  All 6 failures are the new tests; nothing else red:
  - `test_ci_triggers_push_default_branch_and_pull_request` (CT-1): `None !=
    {'branches': ['ccr-19465ed4-j1u0m5']}`: `push:` is bare today.
  - `test_docs_say_ci_needs_a_pull_request` (CT-6), 5 subtests: AGENTS.md
    Branch Policy lacks P1, P2, "merge conflict"; README lacks P1, P2.
  - `test_ci_concurrency_per_ref` (CT-3): ok on arrival (a pin, not a RED).
- Mutants (scratch copies; repo ci.yml untouched), 0 unexpected: pass for
  target block, `pull_request: {}`, quoted `"on":`; fail for current
  ci.yml, +`workflow_dispatch`, push `[main]`, push +`paths-ignore`,
  pull_request `branches:` filter (e), push `[default, main]`,
  +`pull_request_target`, no `on:`. (e) already fails as specified; no
  tightening needed.
- Evidence: `docs/evidence/ci-triggers/red-verify-fast.txt` (FAIL lines
  1242-1290, summary 1305-1307), `docs/evidence/ci-triggers/red-mutants.txt`.
- Next (developer + documenter): ci.yml `on:` block from ADR-KE-015 only;
  AGENTS.md Branch Policy bullet and README sentence with the exact P1/P2
  wording (matched lowercased, whitespace-normalised); then `verify.sh full`.

## 2026-10-21 — developer (GREEN)
- Changed: `.github/workflows/ci.yml` (`on:` block per ADR-KE-015, nothing else), `AGENTS.md` (new last Branch Policy bullet), `README.md` (CI bullet sentence). Tests untouched; no commit.
- `scripts/verify.sh fast` -> `== verify fast: PASS ==`; `scripts/verify.sh full` -> `== verify full: PASS (652s) ==` (no KE_MODEL_*; throwaway `.env` deleted).
- Green: `CiTriggersTest.test_ci_triggers_push_default_branch_and_pull_request`, `test_docs_say_ci_needs_a_pull_request`.
- Evidence: `docs/evidence/ci-triggers/green-verify-fast.txt`, `green-verify-full.txt`.
