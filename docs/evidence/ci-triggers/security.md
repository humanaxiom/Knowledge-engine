# ci-triggers: security audit (2026-10-21)

Verdict: **PASS**. 0 critical, 0 high, 0 medium, 3 low, 4 info. Nothing blocks the merge.

Scope: `git diff` of the working tree on `agent/ci-triggers` (ci.yml, AGENTS.md, README.md,
CHANGELOG.md, docs/architecture.md ADR-KE-015, docs/requirements.md CT-1..CT-7 + PS-3.4
pointer, docs/log.md, tests/test_stack_ready_docs.py), plus untracked
`docs/handoffs/ci-triggers.md`, `docs/handoffs/archive/ci-triggers-part1.md` and
`docs/evidence/ci-triggers/*`.

## 1. Trigger change: GitHub Actions threat model

The diff only adds `branches: [ccr-19465ed4-j1u0m5]` under `push:` and a 4-line comment.
The set of triggers gets smaller: `pull_request` was already there and unfiltered.
`permissions: contents: read`, `concurrency`, `runs-on: ubuntu-24.04` (GitHub-hosted),
the checkout SHA, `persist-credentials: false` and the single `./scripts/verify.sh full`
step are all unchanged. The workflow has no `secrets.*`, `env:`, `pull_request_target`,
`workflow_dispatch`, `schedule`, `workflow_run` or self-hosted runner.

Repo settings, read-only `gh api` on 2026-10-21:
- `private: true`, `visibility: private`, `allow_forking: false`, default branch
  `ccr-19465ed4-j1u0m5` (matches the ci.yml list and `DEFAULT_BRANCH`).
- `actions/permissions/workflow`: `default_workflow_permissions: read`,
  `can_approve_pull_request_reviews: false`.
- `actions/permissions/fork-pr-workflows-private-repos`:
  `run_workflows_from_fork_pull_requests: false`, `send_write_tokens_to_workflows: false`,
  `send_secrets_and_variables: false`.
- `actions/permissions/access`: `access_level: none`.

Result: only collaborators with write access can open a PR that runs. Every run gets a
read-only GITHUB_TOKEN (the `contents: read` cap applies on top of the repo default)
that is not persisted to `.git/config`, and no secrets. A collaborator's PR code could
already run on the runner through `pull_request` before this change, so no privilege
is added. CiTriggersTest CT-1 now fails if `pull_request_target`, `workflow_dispatch`,
`schedule`, a `types:` filter or a `paths` filter is added (mutants b, g, d, e in
`red-mutants.txt`).

## 2. Denial of service and cost

- Concurrency `ci-${{ github.ref }}` with `cancel-in-progress: true`: a PR run uses
  `refs/pull/<n>/merge` and a default-branch push uses `refs/heads/ccr-19465ed4-j1u0m5`,
  so the two groups never overlap. When one PR is pushed many times, the older runs are
  cancelled. Each cancelled job is still billed for the time it ran, rounded up to a
  whole minute.
- Worst case for a hung job (timeout 37): before, 2 runs per PR push = 74 billed min.
  After, 1 run = 37 billed min. A merge still gets one push run on the merge commit,
  37 min worst case, the same as before. A green run is about 22 billed min per PR
  push, down from 44 (`ct7-cost.md` before half: 23 + 21).
- Spam: N open PRs give N groups that run in parallel, up to 37 min each. The account
  concurrency limit caps this, and only collaborators can open PRs (forking is
  disabled). The new triggers add no amplification. `pull_request` keeps its default
  types (opened, synchronize, reopened), so editing, labelling or commenting starts no run.

## 3. Coverage gaps

- **L-1 (low, accepted and documented).** A branch with no open PR gets no CI, and a
  PR with a merge conflict gets none until the conflict is resolved. AGENTS.md Branch
  Policy and README both say so, and CT-6 pins the wording. Nothing reaches the default
  branch through this gap without a run: a conflicted PR cannot merge, and resolving
  the conflict pushes a commit, which triggers a run.
- **L-2 (low, existing before this change).** No branch protection or ruleset exists
  (`protected: false`, 0 rulesets; human ruling Q18). A PR can therefore be merged
  before its `pull_request` run finishes, or while it is red. The push run on the merge
  commit catches this only after the merge. A direct push to the default branch also
  gets a push run, again only afterwards. Before this change the branch's own push run
  did not gate the merge either. Gating rests on the human reading the PR checks before
  merging. No new gap.
- **L-3 (low, existing before this change; the policy is unchanged under Q-CT2).**
  `cancel-in-progress: true` also applies to the default-branch push group. If two
  merges land within about 25 min, the first merge commit's push run is cancelled, so
  that intermediate commit is never verified on the default branch. The later run
  verifies the combined tree. Possible follow-up:
  `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`. That would need a
  new Q-CT2 ruling and an update to the CT-3 pin.
- **I-1 (info).** Renaming the default branch silently stops push CI. The ADR records
  this, and so do the ci.yml comment and the `DEFAULT_BRANCH` note. The test checks
  that the file matches the constant, not that it matches GitHub's setting.
- **I-2 (info).** Tag pushes no longer trigger CI. The unfiltered `push` used to cover
  them. The repo has 0 tags and no release workflow, so nothing is lost today.
- **I-3 (info).** In a stacked PR, the merge into a non-default base branch gets no
  push run. The final PR into the default branch and its merge-commit push run cover
  that code.

## 4. Evidence sweep (`docs/evidence/ci-triggers/*`, the handoff doc and the archive part1)

Full grep output: `docs/evidence/ci-triggers/security-sweep.txt`.
- Profile paths (`C:\Users`, `/c/Users`, `AppData`, `/home/<u>`): 0. SIDs `S-1-*`: 0.
  The files have no `<scratch>` or `<sid>` markers because there was nothing to redact.
  `red-mutants.txt` already writes `<scratchpad>`.
- Tokens and keys (ghp/gho/github_pat, AKIA, PEM private key, sk-, xox, JWT, AIza): 0.
  Keyword `password|secret|token|api_key = value`: 0. URLs with embedded credentials: 0.
- `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST`: these appear only in the skip messages
  ("is empty"). No values appear.
- IPs: 127.0.0.1, plus 192.168.160.2 and 172.19.0.2. The last two are Docker
  bridge-network targets of the smoke check's no-route probe, which is expected. No
  internal FQDNs and no email addresses.
- `ct7-cost.md` holds only run IDs, commit SHAs and timestamps.

## 5. Tests and docs: no pin weakened

- `git diff -- tests/` adds 76 lines and removes 0. `test_harness_port.py` and
  `test_harness_followups.py` are untouched. `CI_TIMEOUT_MINUTES` stays 37.
- In `green-verify-full.txt` (770 unit tests OK, 15 integration tests OK,
  `== verify full: PASS (652s) ==`), these all report ok: `test_ci_calls_verify_only`,
  `test_ci_runner_pinned`, `test_ci_actions_pinned_to_sha`,
  `test_ci_checkout_does_not_persist_credentials`, `test_ci_job_has_timeout` and the
  three CiTriggersTest tests.
- The test uses `yaml.safe_load`, not `yaml.load`, so no unsafe deserialisation.
  CLAUDE.md is not edited.
- The 2 lines removed in the docs are rewraps: the ADR index sentence and the PS-3.4
  sentence, each re-added with more text.
- **I-4 (info, existing before this change).** No test pins `permissions: contents: read`.
  A later regression to `write-all` would pass the gates. Possible follow-up: assert
  `workflow["permissions"] == {"contents": "read"}` next to CiTriggersTest.

## 6. Traces

No agent loop, model call, retrieval or tool span is touched.
`OPENINFERENCE_HIDE_*` does not apply. This audit's log event uses `HARNESS_TRACING=off`.
