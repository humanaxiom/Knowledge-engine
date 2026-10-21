# 2026-10-18 - reviewer: harness-claude-code

Verdict: **CHANGES REQUESTED**

Scope reviewed: `git diff 886de45` plus every untracked file (CLAUDE.md,
.claude/, docker/, tests/test_harness_port.py, tests/test_block_main_commit_hook.py,
the handoff doc, docs/evidence/harness-claude-code/). Excluded:
docs/knowledge-engine-claude-code-prompt.md, .venv/.

## Requirement-by-requirement

| # | Status | Notes |
|---|---|---|
| 1 | met | test_claude_md_imports_agents |
| 2 | partly | Constraints and duty step guarded. **File ownership is not**: it lives in `## Approach` (e.g. analyst.md:25, architect.md:24), which no test compares. See B2 |
| 3 | met | test_agent_model_tiers; reviewer/security are opus |
| 4 | met, with nit | hook prints nothing unless denying; 5 tests. jq path never runs in gates (N1) |
| 5 | met | verify.sh only calls test.sh / smoke.sh; test greps it |
| 6 | met as written, defeated in practice | CLAUDE.md line 1 `@AGENTS.md` imports AGENTS.md:15,40,53,54 (tester runs `scripts/smoke.sh`; `scripts/test.sh` is the tester/developer entry point) into every session. See B1 |
| 7 | met | marked blocks identical in CLAUDE.md, developer, tester, documenter |
| 8 | met | evidence-contract block identical; orchestrator re-run sentence asserted |
| 9 | **not met as written** | no `ci/generated-artifacts-drift` gate exists. See B3 |
| 10 | met | tester `## Contradictions` section + regex test |
| 11 | met | duty step identical across roles (test) |
| 12 | met | no diff under .github/agents/; ADR-KE-001 "As built" added |
| 13 | **half** | dispatch-ROLE.md x8 present. verify runs were on a dirty tree: green-fast.txt:68 and green-full.txt:66 print `886de45+dirty`. See B4 |
| 14 | met | delivery rules in CLAUDE.md, Done check in handoffs/README.md, test_handoff_line_cap |

## Agent file port (bodies diffed with frontmatter stripped, CR removed)

- analyst, architect, reviewer, security, marketer: bodies **byte-identical** to
  the Copilot source.
- developer: only steps 3, 6, 7 changed (verification), plus added
  `## Verification depth` and `## Evidence contract` sections.
- tester: only steps 3-5 changed, plus depth, evidence and `## Contradictions` sections.
- documenter: only step 4 extended, plus depth and evidence sections.
- Depth table and evidence contract match CLAUDE.md exactly (marked blocks, test-enforced).

## Blocking

**B1. AGENTS.md, imported into every session, still names direct gate commands.**
CLAUDE.md:1 is `@AGENTS.md`. AGENTS.md:15 ("Writes/runs unit tests and
`scripts/smoke.sh`"), :40 ("`tester` runs `scripts/smoke.sh`"), :53-54 (test.sh and
smoke.sh as tester/developer entry points) load into the orchestrator and
every subagent next to the CLAUDE.md rule that verify.sh is the only verification command.
test_no_stray_verification_commands scans CLAUDE.md but not the file it imports,
so requirement 6 passes while the session context contradicts it.
Fix: reword those AGENTS.md lines to point at `scripts/verify.sh` (item 12
freezes `.github/agents/` only, not AGENTS.md; CI already runs verify.sh, so the
change is accurate for Copilot too) and add AGENTS.md to the scanned files; or
record an explicit decision (analyst/architect) for why AGENTS.md is exempt.

**B2. The port test does not guard what requirement 2 lists.**
test_agent_port_preserves_constraints compares only `## Constraints` and the
duty step. File ownership (Approach steps naming docs/requirements.md,
docs/architecture.md, CHANGELOG.md, README.md), the rest of Approach, and Output
Format can drift silently. Today they match (verified by the diff above), but
nothing keeps it that way. Cheap fix: for the five non-producer roles, assert the
whole body after frontmatter equals the Copilot body (CR-normalised). For
producers, assert equality after removing the marked blocks, the added sections
and the named verification steps, or at least compare every `##` section except
Approach plus the ownership lines.

**B3. Requirement 9 drift gate does not exist.**
The requirement says `[gate: ci/generated-artifacts-drift]` regenerates each
artifact and fails on diff. The implementation relies on `uv ... --locked` in
the gate scripts and the image build (CLAUDE.md "Generated artifacts" row), with
no test showing that a stale uv.lock turns verify red, and no generic hook for
the next generated artifact (docs/register.md is already anticipated). `--locked`
is a reasonable mechanism for uv.lock, but the deviation is not recorded.
Fix: either add a small drift step called by verify.sh (regenerate, then
`git diff --exit-code` on the artifact list from CLAUDE.md) with a test, or have
the analyst amend item 9 to name `--locked` as the uv.lock check and add a test
that test.sh, smoke.sh and the Dockerfile all use `--locked`.

**B4. Requirement 13 "clean checkout" run has not happened.**
Both green runs report `886de45+dirty`, i.e. the uncommitted working tree. This
cannot be satisfied before commit, so it is a done-condition rather than a
commit blocker. But the handoff and ADR must not call the item done until it is:
after the commit, run `scripts/verify.sh fast` and `full` from a fresh clone and
save them as `verify-clean-fast.txt` / `verify-clean-full.txt`.
On this Windows host the banner will still say `+dirty` (see N2), so use a
clone made with `-c core.autocrlf=false`, or cite the Linux CI run, and say which.

## Nits

**N0. Roles that run no verification do not say so** (the known nit). Severity:
nit. The non-producer bodies are byte-identical to Copilot and contain no
verification instruction, so nothing tells them to run the wrong thing; the
marketer guessed `verify.sh fast` because the dispatch task asked for "the one
command you are allowed to run", and AGENTS.md (B1) primes that. Fixing B1
removes most of the pull. If wanted, add one non-Constraints line to the five
roles ("You run no verification; producers and the orchestrator run
`scripts/verify.sh`") and let the B2 equality test allow exactly that line.

**N1. The hook jq path is never tested.** jq is absent on the host (`which jq`
fails) and in the gates image (checked in-container: `no-jq`). Every hook test,
including the JSON ones, exercises the raw-stdin fallback, which greps the whole
payload (description, cwd, transcript path). On main that can false-deny (fail
safe), and the jq branch could break unnoticed. Install jq in gates.Dockerfile
and add one test that forces the fallback (PATH without jq) on a JSON payload.

**N2. The `+dirty` banner is always on for Windows checkouts.** Host
`core.autocrlf=true` comes from the system gitconfig, which the container does
not see. Inside the gates container `git status` lists 36 files modified (CRLF
working copies, incl. .github/agents/*, AGENTS.md, uv.lock). The banner cannot
tell a clean tree from a dirty one here. Consider passing autocrlf into the
container or a repo-wide `.gitattributes` text rule (separate item).

**N3. `fast` and `full` differ only by smoke today**, and once
`tests/integration` exists as a package, test.sh `unittest discover -s tests`
will recurse into it in both modes and `full` will run it twice. Fix when
platform-skeleton adds that directory.

**N4. `--build` on every verify run** resolves base-image metadata from the
registry (green-*.txt "load metadata" steps). Behaviour on an offline host is
untested; it matters for the later deployable-offline gate. No `.dockerignore`,
so the whole repo (incl. the Windows `.venv/`) is sent as build context each run.

**N5. The hook checks the session cwd branch,** so a commit aimed at another
repo (via `git -C other` or a preceding cd) is judged against the wrong repo.
Pre-existing; record it.

**N6. Copilot agents still tell developer/tester to run `scripts/test.sh` on the
host,** which no longer matches CI. Item 12 freezes them; log as an open question.

## Observability
No new agent loop, model call, retrieval or tool call in product code; no span
requirements apply.

## Next role needs to know
- developer: B1 (AGENTS.md lines + test scope), B2 (stronger port test),
  B3 (drift gate or analyst amendment of item 9). Rerun `scripts/verify.sh full`.
- orchestrator: B4 is a done-condition after the commit; do not archive the
  handoff before the clean-checkout evidence exists.
