# Requirements & Acceptance Criteria

Maintained by the `analyst` agent. One section per plan item.

Status: **draft plan, awaiting human approval** (plan item `engine-plan`,
2026-10-18). Nothing below is implemented yet. Open questions and the
assumptions taken in their absence are in
[docs/open-questions.md](open-questions.md); where an assumption is load-bearing
the criterion cites it as `(A<n>)`.

Conventions:

- **Given/When/Then** for behaviour; every criterion maps to at least one test
  or gate named in brackets, e.g. `[unit: test_ledger_one_row_per_file]`,
  `[integration]`, `[gate: ci/deployable-offline]`.
- Test names are the intended names. The tester may rename them, but the
  traceability table in §R-DR must be kept in sync in the same commit.
- "Integration" means real PostgreSQL / Neo4j / Valkey via testcontainers inside
  the `gates` compose service, with mocked model calls (design rule 31).
- **Outcome metrics** for the whole project (shipping rule): *drafts a human
  reviewer has acted on* and *ratified rules*. Every plan item states which of
  the two it moves, or that it moves neither and why it is still next.

---

## Item: engine-plan (this document)

- Given the build prompt (v2, 2026-10-18), when the plan is delivered, then
  `docs/requirements.md`, `docs/architecture.md` and `docs/open-questions.md`
  exist, the architecture contains the port verdict table and the Mermaid
  diagrams named in §5.2 of the prompt, and no production code has been written.
- Outcome metric moved: neither. It is the precondition for every item that does.

---

## Item: harness-claude-code

Outcome metric moved: neither directly; it is the gate machinery every later item
relies on. Done when the proof below exists, not when the files exist.

1. Given `CLAUDE.md`, when a Claude Code session starts, then it imports
   `@AGENTS.md` and states the session is the **orchestrator**, which delegates
   and never skips a gate. `[unit: test_claude_md_imports_agents]`
2. Given `.github/agents/<role>.agent.md` for each of analyst, architect,
   developer, tester, reviewer, security, documenter, marketer, when the port runs,
   then `.claude/agents/<role>.md` exists for each, and the *Constraints*, file
   ownership and handoff/log duties are byte-identical to the Copilot source
   (modulo frontmatter and the removed verification commands of #5).
   `[unit: test_agent_port_preserves_constraints]`
3. Model tiers: analyst, architect, tester, reviewer, security → `opus`;
   developer, documenter, marketer → `sonnet` or `haiku`. Reviewer and security
   are never below `opus`. `[unit: test_agent_model_tiers]`
4. `.claude/settings.json` wires `scripts/hooks/block-main-commit.sh` as a
   `PreToolUse` hook on `Bash`. The hook is a **guard rail against agent
   mistakes, not a security boundary**: it is a simple, fail-safe text rule,
   not a shell parser, and any string-matching hook on a shell command can be
   bypassed. The real control is branch protection on the remote (Q18).
   Decision record: ADR-KE-001 "Decision: commit hook is a simple fail-safe
   text rule (2026-10-18)" in `docs/architecture.md`; round-4 ruling on
   security H2/L13/M3 (`docs/evidence/harness-claude-code/security-rework3.md`)
   and review B10/B11 (`docs/evidence/harness-claude-code/review-rework3.md`).
   The round-4 ruling replaces the round-3 segment/command-position parsing
   (earlier history: security M1/L9/L10, review B5-B9, in `security.md`,
   `security-rework2.md`, `review-rework1.md`, `review-rework2.md`).
   a. **Extraction.** The hook takes the command text from the payload with
      `jq` if `jq` is present and succeeds; otherwise the first
      `"command":"…"` value in the payload; otherwise the raw input. A JSON
      payload with no `command` field prints nothing.
   b. **Normalisation.** Before any rule is applied the extracted text is
      normalised: line continuations (backslash-newline) are joined, JSON `\n`
      escapes become newlines, all quote characters and backslashes are
      deleted, and the text is lower-cased.
   c. **On `main`/`master`** the hook denies when the normalised text contains
      the word `git` and any of the words `commit`, `push`, `merge`,
      `cherry-pick`, `am`, `rebase` or `revert`, anywhere in the text.
   d. **Off `main`/`master`** the hook denies any normalised line that contains
      `git`, later `push`, and later on that same line any of:
      - `main` or `master` as a word;
      - `--force` or `--force-with-lease`;
      - `--mirror` or `--all`;
      - a single-dash short-flag cluster containing `f` (e.g. `-f`, `-fu`);
      - a `+` refspec.
   e. **Otherwise** it prints nothing, so the normal permission flow decides. It
      never emits `allow` (which would auto-approve every Bash call).
      - **Accepted false positives (fail safe):** one-line commands that mention
        git, push and main (e.g. `git commit -m "fix push to main docs"` on a
        plan-item branch, or `echo "git push origin main"`).
      - **Accepted bypasses off `main`/`master`** (silent by design; Q18 branch
        protection is the real control): words hidden from the text (variables,
        `eval`, aliases, encodings), `gh`, `git update-ref`, and a push split
        across lines without a line continuation.
   f. **Performance.** The hook's cost is linear in the command's length and it
      uses no `awk`. Given a 1 MB command, when the hook runs in the gates image
      with `jq` present and with it absent, then it completes in under 3 s,
      whatever the command's shape: many short tokens, one long token, or one
      long heredoc line.
   `[unit: tests/test_block_main_commit_hook.py]` feeds Claude Code's real
   compact payload (`{"tool_input":{"command":"…"}}`, no spaces after `:`) and
   tests every rule in a-f both with `jq` on `PATH` and with it absent,
   including: a line continuation; an escaped quote; `ma\in`; `g''it` and
   uppercase `GIT` on `main`; `sh -c` and a bash heredoc on `main`;
   `>/dev/null git push origin main` and the backtick form off `main`; and the
   three 1 MB timing shapes of f.
5. `scripts/verify.sh` is the single verification entry point. It runs inside the
   `gates` compose service and only *calls* `scripts/test.sh`, `scripts/smoke.sh`
   and the CI step scripts; it never re-lists their commands.
   `[unit: test_verify_sh_has_no_inlined_commands]` greps it for `pytest`,
   `mypy`, `ruff`, `unittest`. Modes: `fast` (pure functions, docs) and `full`
   (integration + smoke).
6. No agent file and no `CLAUDE.md` contains a verification command other than
   `scripts/verify.sh [fast|full]`. `[unit: test_no_stray_verification_commands]`
7. `CLAUDE.md` and every producer agent (developer, tester, documenter) contain
   the same **path → required depth** table (schema, SQL, graph/vector stores,
   embeddings, workers, API routes → `full`; pure functions and docs → `fast`).
   `[unit: test_depth_table_identical_everywhere]`
8. Every producer agent's *Output Format* requires: the exact command, the last
   ~15 lines of real output, and what is now green that was red. The tester shows
   RED the same way. The orchestrator re-runs `scripts/verify.sh` and reads the
   diff before approving a commit. `[unit: test_evidence_contract_present]`
9. `CLAUDE.md` lists everything CI runs that `verify.sh` does not, and every
   committed generated artifact with its regenerate command. Today CI runs
   nothing beyond `scripts/verify.sh full`, and the only generated artifact is
   `uv.lock`; its drift check is that every gate script and the gates image run
   uv with `--locked`, so a stale lock turns verify red.
   `[unit: test_gate_scripts_use_locked]` The generic regenerate-and-diff gate
   (`ci/generated-artifacts-drift`) belongs to policy-book criterion 2.
10. The tester agent owns contradiction resolution: a change that contradicts an
    existing test resolves it in the same commit, citing the decision record.
11. Every role logs with `harness_telemetry.log_event` and appends to
    `docs/handoffs/<slug>.md`; evidence in `docs/evidence/<slug>/`.
12. `.github/agents/` is unchanged. An ADR records the port.
13. **Proof:** each of the eight subagents is dispatched once on a trivial task and
    the transcript is saved to `docs/evidence/harness-claude-code/dispatch-<role>.md`;
    every mode of `scripts/verify.sh` is run on a clean checkout and saved.
    The item is not done without these files.
14. `CLAUDE.md` carries the delivery and shipping rules of the prompt (outcome
    metric per item, ship only after live end-to-end smoke, deployable without
    the assistant, docs never restate live counts, handoffs ≤ ~200 lines).
    `docs/handoffs/README.md` gains the milestone "Done" check (metric now vs
    last milestone, why it did not move, external blocker with person and date).
    `[unit: test_handoff_line_cap]` fails if an active handoff exceeds 200 lines.

---

## Item: platform-skeleton

Outcome metric moved: neither; makes the product deployable, which is a
precondition for any human using it.

1. `docker compose up` brings up api, worker, postgres, neo4j, valkey, phoenix
   and the `gates` one-shot service. Every host port comes from `.env` and the
   defaults sit in a non-default range (A6). `[unit: test_no_hardcoded_ports]`
   scans source and compose for literal ports outside config.
2. Configuration is typed (pydantic-settings); every key has a default in
   `config/defaults.yaml`, an env override, and a register entry (DR16).
3. **Egress guard:** given an inference host not on `EGRESS_ALLOWLIST`, when the
   app starts, then startup fails; when a runtime call targets it, then the call
   raises before any socket opens. `[unit: test_egress_guard_startup]`,
   `[unit: test_egress_guard_runtime]` (DR30).
4. `/healthz` (process) and `/readyz` (postgres, neo4j, valkey, model host,
   embedding-dimension check DR13) return per-dependency status.
5. **Offline:** `[gate: ci/offline]` runs the integration suite with container
   networking disabled (`network_mode: none` for app containers, internal-only
   compose network). `[gate: ci/deployable-offline]` builds the offline bundle
   (`scripts/bundle.sh`: saved images, wheels, vendored JS/CSS, checksums) and
   installs it into a clean, network-less runner, then runs the smoke test.
6. Build/launch/teardown scripts and a fresh-machine quickstart exist for
   PowerShell, macOS and Linux; CI lints them (`shellcheck`, `PSScriptAnalyzer`).
7. Startup refuses unsafe settings: auth off outside `ENV=dev`, tracing to a
   non-local collector, `OPENINFERENCE_HIDE_*` not `true`. `[unit: test_startup_refuses_unsafe]` (DR39).
8. Coverage ≥ 80% and `mypy --strict` are enforced by `scripts/test.sh`.

---

## Item: ingest-ledger

Outcome metric moved: neither directly; without a complete ledger every later
count is wrong (DR1, DR2).

1. Given N input files, when ingest runs, then the ledger has exactly N rows, one
   per source file, even if several files are byte-identical; duplicates become
   `duplicate_of` edges, never dropped rows. `[integration: test_ledger_one_row_per_file]` (DR1)
2. Parsed + skipped = input, always. Each skip has a named reason from a closed
   enum (`unsupported_type`, `corrupt`, `encrypted`, `empty`, `too_large`, …).
   `[integration: test_ingest_accounting_adds_up]` (DR2)
3. File type is detected from content (magic bytes), not the extension; a `.doc`
   that is RTF is parsed as RTF. `[unit: test_type_detection_by_content]` (DR2)
4. Ingest is idempotent (same file twice → no new rows, no new revision),
   incremental (only new or changed checksums are processed) and resumable (a
   killed run resumes from its manifest). `[integration: test_ingest_idempotent]`,
   `[integration: test_ingest_resume_after_kill]` (DR41)
5. Workers scale horizontally: two workers on one queue never process the same
   file twice. `[integration: test_two_workers_no_double_process]`
6. **Source revisions (corpus history).** See §R-REV-C.

---

## Item: data-plane

Outcome metric moved: neither directly; feeds drafts.

1. Every normalized record carries lineage: source file, page/region, extraction
   method, parser version, model + version, checksum, timestamp.
   `[unit: test_record_lineage_complete]`
2. Extraction profiles are per template and read headers, footers, tables and
   content controls as well as the body. `[unit: test_profile_reads_docx_header_table]`
   using a fixture whose identifying table sits in the header (DR3).
3. "Unknown" is a typed state (`FieldValue.unknown(reason)`), never a string.
   `[unit: test_no_sentinel_strings]` fails if any writer emits a value from the
   sentinel list (`Untitled`, `N/A`, `TBD`, `Unknown`, …); coverage checks count
   typed unknowns as not covered. (DR4)
4. Truncated values are refused and become unknown(`fragment`).
   `[unit: test_refuse_fragments]` (DR5)
5. Every field records `how`: `parsed | routed | entered | imported`.
   `[unit: test_field_provenance_required]` (DR6)
6. Every facet/filter returns matched / not matched / could-not-evaluate, and a
   signal's coverage is published before it may define membership.
   `[unit: test_facet_three_numbers]`, `[unit: test_low_coverage_signal_cannot_define_membership]` (DR7)
7. Version stamps propagate to every derived object; the freshness check lists
   stale objects after any parser, schema or rule version change.
   `[integration: test_freshness_flags_stale_after_parser_bump]` (DR8)
8. Supported inputs: PDF (text + OCR), DOCX/DOC/RTF, XLSX/CSV, HTML, Markdown,
   images, tables, each with a golden fixture. Model per stage is configured
   separately (DR29).

---

## Item: knowledge-plane

Outcome metric moved: neither directly; feeds drafts.

1. Exact-hash tier runs first and its groups are kept as a signal.
   `[integration: test_exact_tier_first_and_kept]` (DR9)
2. Edges are idempotent and canonically oriented; re-running the build produces
   no new edges; invariants (no self edge, star vs clique as pinned) are tested.
   `[integration: test_edges_idempotent_canonical]` (DR10)
3. Singletons reach the graph. `[integration: test_singletons_in_graph]` (DR11)
4. Vectors only rank. No code path compares a similarity to a threshold for a
   decision, and no template renders a similarity number.
   `[unit: test_no_similarity_threshold_in_decisions]` (AST scan),
   `[unit: test_templates_render_no_similarity]` (DR12)
5. Embedding windows are sized in tokens, per section, with `truncated` stamped
   on every vector node and back-off on rejection; dimension matches across model,
   index and config or `/readyz` fails. `[unit: test_token_windows]`,
   `[integration: test_embedding_dimension_mismatch_fails]` (DR13)
6. Title/keyword passes run in PostgreSQL and rank above semantic passes; vectors
   exclude the title. `[integration: test_title_pass_ranks_first]` (DR14)
7. Config knobs that select an algorithm are closed enums the code dispatches on.
   `[unit: test_algorithm_knobs_are_dispatched_enums]` (DR15)
8. Graph schema comes from the domain pack YAML; adding a corpus is adding a pack.
   `[integration: test_second_pack_without_code_change]` with a toy pack.

---

## Item: policy-book

Outcome metric moved: **ratified rules** (directly).

1. Every non-trivial default lives in versioned YAML with a register entry; the
   policy book fails to load if a knob has no entry; a `ratified` entry must carry
   `decided_by`, `decided_on`, `decision_note`. `[unit: test_registry_enforced]` (DR16)
2. A generated human-readable register (`docs/register.md`) has a CI drift check.
   This item introduces the generic drift gate, called by `scripts/verify.sh`: it
   regenerates every non-lockfile generated artifact listed in `CLAUDE.md` and
   fails on `git diff --exit-code`. `[gate: ci/generated-artifacts-drift]` (DR16)
3. Every rule has an owner tier: `institutional_policy | policy_informed | technical`;
   the review queue routes by tier. `[unit: test_rule_requires_owner_tier]` (DR17)
4. Every policy-book version is baselined over the full corpus snapshot before it
   can be offered for ratification; a rule that fires on 100% or 0% is flagged as
   a probable defect. `[integration: test_baseline_required_before_ratification]`,
   `[unit: test_always_fires_rule_flagged]` (DR18)
5. The review packet shows each rule's measured effect (what it blocks, how
   often, on which snapshot). `[integration: test_review_packet_has_effect]` (DR19)
6. A proposed rule's precision is measured over the corpus before it can be added.
   `[integration: test_precision_measured_before_add]` (DR20)
7. One knob answers one question: the register schema has a single `question`
   field and lint rejects a knob referenced by two unrelated rules.
   `[unit: test_one_knob_one_question]` (DR21)
8. Ratification sessions are planned objects with named owner and date; the
   funnel shows ratified / proposed per tier. (DR22)
9. The LLM may only propose; only ratified rules execute; evaluation is
   deterministic with no model client importable from the evaluator package.
   `[unit: test_evaluator_imports_no_llm]` (import-graph check)
10. **Policy history and revision UX.** See §R-REV-P.

---

## Item: verifier-validator

Outcome metric moved: drafts reviewed (raises trust so reviewers act).

1. The LLM edits field by field; it never receives replace-rights over a whole
   section or list. `[unit: test_llm_patch_is_field_scoped]` (DR23)
2. A carry-through verifier runs per section before and after every pass; >100%
   = fabrication, <100% = loss; deletions and new requirements are shown to the
   reviewer. `[unit: test_carry_through_flags_fabrication]`,
   `[unit: test_carry_through_flags_loss]` (DR24)
3. Advisory findings must quote verbatim evidence or are dropped.
   `[unit: test_advisory_without_quote_dropped]` (DR25)
4. Temperature 0; schema-constrained decoding where supported, else JSON mode
   with a repair loop that feeds back the real validation error; error class and
   message logged per item. `[unit: test_repair_loop_feeds_error]` (DR26)
5. Every required prompt instruction maps to a schema field.
   `[unit: test_prompt_schema_alignment]` (DR27)
6. Provenance alignment is one-to-one (Hungarian / linear assignment), never argmax.
   `[unit: test_alignment_one_to_one]` (DR28)
7. Model configuration is per pass (embed, rewrite, audit, compose).
   `[unit: test_per_pass_model_config]` (DR29)
8. The deterministic validator re-judges every AI output and fails closed.
9. Each guard is proven able to fail: a mutation test breaks it once and the
   suite goes red. `[gate: ci/guard-mutation]` (DR38)

---

## Item: agent-workflow

Outcome metric moved: drafts produced → drafts reviewed.

1. Steps Plan → Locate → Evaluate → Compose → Verify → Validate → Review queue →
   Publish run in order; each is a `harness_telemetry` span of the right kind and
   a test asserts the tree. `[unit: test_workflow_span_tree]`
2. Authorization filters are inside the Cypher/SQL query, never post-filtering.
   `[integration: test_authz_in_query_not_post]` seeds a forbidden record and
   asserts it is never fetched (span document count).
3. No user input is interpolated into Cypher/SQL; templates and parameters are
   recorded separately. `[unit: test_no_query_interpolation]` (AST + runtime).
4. `OPENINFERENCE_HIDE_INPUTS=true` / `_OUTPUTS=true` are defaults; Phoenix local.
5. Nothing publishes without a human approval action in the audit log.
   `[integration: test_publish_requires_human]`
6. Every output records the policy-book version and rule revision ids and the
   corpus revisions it cited (§R-REV-P.6, §R-REV-C.7).
7. CI never calls a model; live golden tests are opt-in and skip without an
   endpoint. `[unit: test_no_model_calls_in_ci]` (network guard) (DR31)

---

## Item: auth-audit

Outcome metric moved: neither; it is a ship blocker (an unauthenticated approve
once published, DR39).

1. Authorization matrix test walks the live routing table; a route without an
   access decision fails the build. `[unit: test_authz_matrix_covers_all_routes]`
2. The actor always comes from the session, never the request body.
   `[unit: test_actor_from_session_only]`
3. CSRF protection on every cookie-authenticated state change.
   `[integration: test_csrf_required]`
4. Audit log is append-only and hash-chained; `ke audit verify` detects a
   modified, deleted or reordered row. `[integration: test_audit_chain_detects_tamper]` (DR40)
5. SSO is pluggable (CAS, SAML, OIDC behind one interface) with a dev provider that
   never contacts a live IdP in CI. (DR42, A5)
6. Runbooks: "healthy silence vs hung" with its one query; a tested restore
   runbook whose test fails if a restore empties the store and exits 0. (DR41)

---

## Item: frontend

Outcome metric moved: **drafts reviewed** and **ratified rules** (the review
queue and policy editor are where humans act). Funnel ships first.

1. Funnel page: ingested → parsed → in graph → drafted → reviewed → published,
   computed from the database at request time; no count is cached or written to
   docs. `[integration: test_funnel_counts_match_store]`
2. Corpus manager: upload, ingest status, skip ledger, per-record lineage,
   **file and record history** (§R-REV-C.8).
3. Graph explorer: entities, relationships, the evidence behind each edge.
4. Policy-book editor: proposed vs ratified, clause citations, version diff,
   measured effect, owner tier, **rule and book history** (§R-REV-P.7).
5. Review queue: approve / edit / reject with audit; reviewer throughput view.
6. Ask/compose workspace: answer, rules applied (with revision), cited records
   (with revision) side by side.
7. No view renders a similarity percentage (DR12).
8. All JS/CSS assets vendored for offline use.

---

## §R-REV-C — Corpus revision history and UX

Added at the user's request (2026-10-18): "revision UX and history for both
corpus and policy". Owning plan items: `ingest-ledger` (source revisions),
`data-plane` (record revisions), `knowledge-plane` (stamps), `frontend` (UX).
Outcome metric: drafts reviewed — reviewers can only trust a draft whose source
history they can see.

Terms: a **source** is a logical document identified by `(corpus, source_key)`
(A10). A **source revision** is one byte-level version of it (checksum). A
**record revision** is one normalized extraction of a source revision under one
parser/profile/schema version, or one human correction.

1. **Append-only.** Given a source whose content changes, when it is re-ingested,
   then a new source revision is added with `revision_no = previous + 1` and
   `parent_revision_id`; no prior revision row is updated or deleted.
   `[integration: test_source_revision_append_only]` (DB role has no UPDATE/DELETE
   on revision tables).
2. **No-op on unchanged.** Same checksum → no new revision, ledger row gets a
   `seen_at` touch only. `[integration: test_unchanged_reingest_no_revision]`
3. **Cause is typed.** Every record revision has `cause ∈ {source_changed,
   parser_changed, profile_changed, schema_changed, human_correction, restore,
   tombstone}` and `caused_by` (actor or version id).
   `[unit: test_revision_cause_closed_enum]`
4. **Removal is a tombstone.** A source deleted upstream gets a `tombstone`
   revision; history, lineage and every draft that cited it remain readable.
   `[integration: test_tombstone_keeps_history]`
5. **Human corrections survive re-parse.** Given a field whose current value is
   `entered`, when a re-parse yields a different parsed value, then the entered
   value stays current and a `conflict` is raised to the review queue showing
   both; nothing is silently overwritten. `[integration: test_entered_value_survives_reparse]`
6. **Field-level history (blame).** For any field of any record, the system
   returns every value it has had, with revision, `how` (DR6), actor/version and
   timestamp. `[integration: test_field_blame]`
7. **Downstream stamps.** Every entity, vector, edge, draft and answer stores the
   record revision ids it was built from. After a new revision, the freshness
   check lists exactly the derived objects built from the superseded revision.
   `[integration: test_freshness_after_new_source_revision]` (DR8, DR32 — query
   the store, not the run counter).
8. **Corpus snapshots.** A snapshot is an immutable, named set of
   `(record_id, record_revision_id)` taken at a timestamp. Baselines (DR18),
   metrics and findings files name the snapshot they ran on. Comparing two
   snapshots reports buckets: added, changed, removed (tombstoned), unchanged,
   **unaccounted for** (DR33). Buckets sum to the union.
   `[integration: test_snapshot_compare_buckets_sum]`
9. **As-of reads.** Any record, the funnel and search can be read *as of* a
   snapshot or timestamp, with authorization applied in the query (DR39).
   `[integration: test_as_of_read_respects_authz]`
10. **Restore is a new revision.** Restoring an old revision creates a
    `restore` revision that goes through the review queue; it never rewinds a
    pointer silently. `[integration: test_restore_creates_revision_and_review_item]`
11. **Audit.** Every revision write (ingest, correction, restore, tombstone) emits
    an audit-log entry in the hash chain (DR40).
12. **UX — corpus manager** (`frontend`):
    - Source page **History** tab: a timeline of source and record revisions with
      cause badges, actor, parser/profile version, and the skip-ledger outcome per
      revision.
    - **Compare** any two revisions: field-level diff for structured fields,
      section-level text diff (word-level within a section), table cell diff;
      unknown↔value transitions shown explicitly, never as blank.
    - **Blame** toggle on the record view: hover/expand a field to see who or what
      set it, when, and how (parsed/routed/entered/imported).
    - **Impact panel**: for a selected revision, counts of derived objects built
      from it and how many are stale — computed live from the store.
    - **Snapshot** list and snapshot-vs-snapshot comparison with the five buckets.
    - Restore and correction actions require a reason, show a preview diff, and
      land in the review queue.
    - Every view works without JavaScript for reading (server-rendered); diffs are
      keyboard navigable and do not rely on colour alone (WCAG 2.1 AA).
    `[integration: test_history_views_render]`, `[e2e smoke: history page]`

## §R-REV-P — Policy-book revision history and UX

Owning plan items: `policy-book` (model and lifecycle), `agent-workflow`
(provenance on outputs), `frontend` (UX). Outcome metric: **ratified rules** —
ratifiers must see exactly what changed and its effect before signing.

Terms: a **rule** has a stable `rule_key`. A **rule revision** is one immutable
typed definition of it (decision table, threshold, routing), with clause
citation, owner tier and status. A **policy-book version** is an immutable set of
rule revisions plus knob values, identified by a monotonically increasing
version number and a content hash. A **changeset** is a mutable working draft
of the next version.

1. **Immutability.** Ratified rule revisions and published book versions are
   never updated or deleted. `[integration: test_policy_versions_immutable]`
2. **Lifecycle.** Rule revision status: `proposed → in_review → ratified |
   rejected`; later `superseded` or `retired` only by a newer version.
   Proposer is `llm` or a user; only a human with the rule's owner tier can
   ratify. `[unit: test_rule_lifecycle_transitions]`,
   `[integration: test_ratify_requires_owner_tier]`
3. **Two clocks.** Each version records `ratified_at` (when decided) and
   `effective_from` (when it applies); evaluation uses the version effective at
   the request's evaluation time, which is recorded. (A12)
   `[unit: test_effective_version_selection]`
4. **Diff between any two versions.** Output lists rules added / removed /
   changed / unchanged; for changed rules, a typed field diff (decision-table cell
   changes, threshold old→new, routing target), the citation change, the owner
   tier change, and the knob changes. `[unit: test_policy_diff_typed]`
5. **Effect diff.** For two versions baselined on the same corpus snapshot, the
   diff includes, per rule, how many records it blocks/routes under each version
   and the records that changed outcome (listed, not only counted).
   `[integration: test_effect_diff_same_snapshot]` (DR18, DR19, DR33)
6. **Answer provenance.** Every draft, answer and published artifact stores the
   book version, rule revision ids that fired, the corpus snapshot or record
   revisions cited, and the evaluation time. `[integration: test_output_records_rule_revision]`
7. **UX — policy-book editor** (`frontend`):
    - **Version timeline**: each version with status, ratified_at /
      effective_from, ratifiers, and the session it came from.
    - **Compare** picker (any two versions, default: current vs proposed
      changeset) showing the typed diff of P.4 and the effect diff of P.5 side by
      side.
    - **Rule history drawer**: every revision of a rule with who proposed it (LLM
      flagged as such), who ratified or rejected it and the `decision_note`.
    - **Clause view**: the cited clause text from the policy *document revision*
      it came from; when that document gets a new revision whose clause text
      changed, the rule is marked **citation stale** and queued for re-review.
      `[integration: test_citation_stale_on_policy_doc_revision]`
    - **Outputs by rule revision**: count and list of drafts/answers produced by a
      given rule revision, live from the store.
    - **Revert** = start a changeset that re-proposes an earlier revision; it goes
      through baseline and ratification like any change. No one-click rollback.
      `[integration: test_revert_is_a_new_changeset]`
    - Ratify/reject requires a `decision_note`; the packet cannot be submitted
      until the effect diff has loaded.
8. **Audit.** Every proposal, edit, ratification, rejection, publish and revert is
   an audit-chain entry with the actor from the session (DR39, DR40).

---

## §R-DR — Design-rule traceability (one test or gate per rule)

| DR | Rule (short) | Test / gate | Plan item |
|---|---|---|---|
| 1 | One ledger row per source file | `test_ledger_one_row_per_file` | ingest-ledger |
| 2 | Parsed + skipped = input; type by content | `test_ingest_accounting_adds_up`, `test_type_detection_by_content` | ingest-ledger |
| 3 | Per-template profiles read header/footer/tables | `test_profile_reads_docx_header_table` | data-plane |
| 4 | Unknown is typed; sentinel scan | `test_no_sentinel_strings` | data-plane |
| 5 | Refuse fragments | `test_refuse_fragments` | data-plane |
| 6 | Field provenance | `test_field_provenance_required` | data-plane |
| 7 | Facets report three numbers; coverage first | `test_facet_three_numbers`, `test_low_coverage_signal_cannot_define_membership` | data-plane |
| 8 | Version stamps + freshness | `test_freshness_flags_stale_after_parser_bump`, `test_freshness_after_new_source_revision` | data-plane |
| 9 | Exact-hash tier first, kept as signal | `test_exact_tier_first_and_kept` | knowledge-plane |
| 10 | Idempotent canonical edges | `test_edges_idempotent_canonical` | knowledge-plane |
| 11 | Singletons first-class | `test_singletons_in_graph` | knowledge-plane |
| 12 | Vectors rank, never threshold; no % in UI | `test_no_similarity_threshold_in_decisions`, `test_templates_render_no_similarity` | knowledge-plane, frontend |
| 13 | Token windows, truncated stamp, dim check | `test_token_windows`, `test_embedding_dimension_mismatch_fails` | knowledge-plane |
| 14 | Title/keyword in PG, ranked first | `test_title_pass_ranks_first` | knowledge-plane |
| 15 | Closed-enum knobs | `test_algorithm_knobs_are_dispatched_enums` | knowledge-plane |
| 16 | Registry enforced; ratified fields; drift | `test_registry_enforced`, `ci/generated-artifacts-drift` | policy-book |
| 17 | Owner tiers | `test_rule_requires_owner_tier` | policy-book |
| 18 | Baseline before ratification | `test_baseline_required_before_ratification`, `test_always_fires_rule_flagged` | policy-book |
| 19 | Review packet shows effect | `test_review_packet_has_effect` | policy-book |
| 20 | Precision before adding | `test_precision_measured_before_add` | policy-book |
| 21 | One knob, one question | `test_one_knob_one_question` | policy-book |
| 22 | Ratification is critical path | milestone Done check + funnel tier view | policy-book |
| 23 | Field-by-field LLM edits | `test_llm_patch_is_field_scoped` | verifier-validator |
| 24 | Carry-through verifier | `test_carry_through_flags_fabrication`, `test_carry_through_flags_loss` | verifier-validator |
| 25 | Advisory needs verbatim quote | `test_advisory_without_quote_dropped` | verifier-validator |
| 26 | Temp 0, constrained decoding, repair loop | `test_repair_loop_feeds_error` | verifier-validator |
| 27 | Prompts fit the schema | `test_prompt_schema_alignment` | verifier-validator |
| 28 | One-to-one alignment | `test_alignment_one_to_one` | verifier-validator |
| 29 | Per-pass model config | `test_per_pass_model_config` | verifier-validator |
| 30 | Egress allowlist fails closed | `test_egress_guard_startup`, `test_egress_guard_runtime` | platform-skeleton |
| 31 | CI never calls a model | `test_no_model_calls_in_ci` | agent-workflow |
| 32 | Check the store, not the counter | `test_funnel_counts_match_store`, `test_freshness_after_new_source_revision` | frontend, data-plane |
| 33 | Buckets + unaccounted | `test_snapshot_compare_buckets_sum` | data-plane |
| 34 | Population defined per metric | `test_metric_declares_population` (metric registry) | jd-metrics-and-demo |
| 35 | Probe reproduces a known number, then control | `test_probe_reproduces_known_count` | jd-metrics-and-demo |
| 36 | Full corpus before thresholds | `test_threshold_requires_full_corpus_run` | policy-book |
| 37 | Rising score suspicion | `test_score_increase_requires_carry_through_check` | verifier-validator |
| 38 | Each guard can fail | `ci/guard-mutation` | verifier-validator |
| 39 | Authz matrix, session actor, startup check, CSRF | `test_authz_matrix_covers_all_routes`, `test_actor_from_session_only`, `test_startup_refuses_unsafe`, `test_csrf_required` | auth-audit |
| 40 | Hash-chained audit + verify | `test_audit_chain_detects_tamper` | auth-audit |
| 41 | Manifests, resume, runbooks, tested restore | `test_ingest_resume_after_kill`, `test_restore_not_empty` | ingest-ledger, auth-audit |
| 42 | Pluggable SSO, dev hatch | `test_sso_dev_provider_offline` | auth-audit |

---

## Item: jd-pack-port

Outcome metric moved: drafts produced (the first real ones).

1. Port verdict table (architecture.md §Port) is followed module by module; the
   source commit `2e3e6dc` is recorded in every ported file's header comment and in
   `docs/port-log.md`.
2. Tests are ported with the code; a module is not "ported" until its tests pass
   under `mypy --strict` and coverage.
3. The `jd` pack deduplicates (exact, near, semantic), harmonizes to ratified
   rules, composes new JDs and routes everything to human review.
4. SFU values live in `profiles/sfu/` as pure data; `[unit: test_engine_has_no_sfu_literals]`
   greps engine and pack code for profile literals.
5. `fixtures/` holds the public JD corpus with provenance in `fixtures/README.md`.

## Item: jd-metrics-and-demo

Outcome metric moved: both are *reported*; this item makes them visible.

1. A dated findings file `docs/findings/<date>-jd-metrics.md` names the query and
   the corpus snapshot for each figure: corpus size, duplicate buckets, drafts
   produced, drafts reviewed, fabrication rate before/after the verifier, time per
   JD vs a recorded manual baseline (A9).
2. No figure is copied from the JD repo's docs. `[unit: test_findings_cite_query]`.
