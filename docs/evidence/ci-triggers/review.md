# ci-triggers: reviewer, 2026-10-21

Verdict: **APPROVED** (no blocking findings; nits N1-N7 optional).

Scope: `git diff` of the working tree on `agent/ci-triggers` (base b3ea4f6) plus
untracked `docs/evidence/ci-triggers/`, `docs/handoffs/ci-triggers.md`,
`docs/handoffs/archive/ci-triggers-part1.md`. Files changed: ci.yml, AGENTS.md,
README.md, CHANGELOG.md, docs/architecture.md, docs/requirements.md,
docs/log.md, tests/test_stack_ready_docs.py. `.github/agents/`, `.claude/`,
CLAUDE.md untouched (git status clean for them).

## Checks

- ci.yml: the `on:` block is byte-for-byte the ADR-KE-015 block (4-line
  comment, `push: branches: [ccr-19465ed4-j1u0m5]`, bare `pull_request:`).
  Diff is +5 lines inside `on:` only; timeout 37, ubuntu-24.04, checkout SHA
  fbc6f39..., persist-credentials false, permissions contents: read,
  concurrency `ci-${{ github.ref }}`/cancel true, single verify step all
  unchanged. Only one workflow file exists (`.github/workflows/ci.yml`).
- CiTriggersTest: three tests, exactly CT-1 / CT-3 / CT-6 per the ADR.
  `workflow.get("on", workflow.get(True))` handles PyYAML's `on` -> True.
  CT-1 uses dict equality, so extra keys anywhere fail.
- Mutants: `red-mutants.txt` 11 variants, 0 unexpected; failure reasons are
  consistent with the code. Reviewer re-ran 7 extra variants
  (scratchpad `rv_mutants.py`, driving `assert_triggers` on temp copies):
  | variant | result |
  |---|---|
  | pull_request `types: [opened]` | fail (`{'types': [...]} not found in (None, {})`) |
  | pull_request `[]` | fail |
  | push branches + `tags` | fail (dict inequality) |
  | push `branches:` as a bare string | fail |
  | push `branches: ['ccr-*']` glob | fail |
  | `on: [push, pull_request]` list form | fail (not a mapping) |
  | quoted `"on":` (bad) + bare `on:` (good) | fail (quoted wins) |
  Questions from the brief: `pull_request` with a `types:` filter fails;
  `push` with an extra key fails. Only gap found: N1.
- Docs: AGENTS.md bullet and README sentence match the architect's text
  (archive part1, architect section) word for word; both contain P1/P2
  (lowercased, whitespace-normalised); AGENTS.md also contains "merge
  conflict". No other doc says CI runs on every push.
- requirements.md: PS-3.4 pointer present (line 1214). CT status table is
  accurate: CT-1/3/4/5/6 MET match the evidence and diff; CT-2 and CT-7
  correctly PENDING (they need the human's push, PR and merge).
- CHANGELOG: accurate apart from N3.
- Evidence contract:
  - `red-verify-fast.txt`: 770 tests, `FAILED (failures=6, skipped=8)`; all
    6 FAIL lines are the two expected tests (CT-1 + 5 CT-6 subtests); no
    ERROR lines; `test_ci_concurrency_per_ref` ok (pin).
  - `green-verify-fast.txt`: 770 tests `OK (skipped=8)`, ends
    `== verify fast: PASS ==`. `green-verify-full.txt`: 770 tests OK, ends
    `== offline_check: PASS (99s) ==` / `== verify full: PASS (652s) ==`.
    Same test count red and green; no tests removed or skipped extra.
  - `ct7-cost.md` before half re-checked with `gh run view <id> --json jobs`
    and `gh run list --commit b3ea4f65...`: 2 runs on b3ea4f6;
    39723927881 push, job 04:43:09Z-05:05:52Z (22m43s); 39724208839
    pull_request, job 04:46:07Z-05:06:48Z (20m41s); total 43m24s, 44 billed.
    All match.
- Handoff 66 lines (< 200). Log has analyst, orchestrator (rulings),
  architect, tester, developer, documenter, marketer entries for ci-triggers.
- Observability: no agent loop, model call, retrieval or tool call; no spans
  needed.
- Reviewer host sanity run (not a gate): `uv run --locked python -m unittest
  tests.test_stack_ready_docs tests.test_harness_port` -> 25 tests OK on the
  final tree.

## Findings

Blocking: none.

- **N1 (test, contrived).** If ci.yml ever had both a quoted `"on":` and a
  bare `on:` key, PyYAML keeps both (`"on"` and `True`) and the test checks
  only `"on"`; GitHub treats them as one duplicate key. A good quoted block
  plus a bad bare block would pass. Optional: assert not both
  `"on" in workflow and True in workflow`.
- **N2 (evidence freshness).** The green verify runs (05:29Z) predate the
  documenter's README re-wrap, PS-3.4 pointer and status table, and the
  CHANGELOG entry. Only the CiTriggers subset was re-run after. The
  orchestrator's pre-commit `scripts/verify.sh full` covers this; say so in
  the commit gate rather than citing the developer's run for the final tree.
- **N3 (CHANGELOG wording).** "CI runs once per pull request push and once
  per push to the default branch, not twice." suggests a default-branch push
  used to run twice; only PR pushes did. Suggest: "A push to a PR branch now
  runs CI once, not twice; a push to the default branch still runs it once."
- **N4 (ADR number).** ADR-KE-015 Context (architecture.md line 6483) and
  the orchestrator handoff say "about 48 billed minutes per push"; the
  measured figure is 44 (43.4 job min, `ct7-cost.md`). CT-7 says the claim
  is taken from the numbers; update when the after half is filled.
- **N5 (requirements).** "Open questions for this item" still reads as open
  ("Recommend ..."); the rulings live only in the handoff, ADR status and
  log. Other items record rulings in requirements.md; add one line
  ("Ruled 2026-10-22: Q-CT1..Q-CT5 as recommended").
- **N6 (mutant reproducibility).** `red-mutants.txt` cites
  `<scratchpad>/ct_mutants.py`, which is not saved; the run cannot be
  repeated from evidence. Optional: copy the script into the evidence dir.
- **N7 (dates).** Handoff sections run 10-22 (orchestrator..tester) then
  10-21 (developer..marketer), while the log is all 10-22Z: local vs UTC
  dates mixed. Cosmetic.

## Open before close-out (not findings)

CT-2 (`ct2-pr-head.txt`, `ct2-merge-commit.txt`) and the CT-7 after half
need the human's push, PR and merge; the item cannot be Done until they are
filled.

Mutant scripts saved beside this file: `ct_mutants.py` (tester), `rv_mutants.py` (reviewer).
