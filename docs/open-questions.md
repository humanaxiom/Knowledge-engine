# Open questions and working assumptions

The consolidated pre-code message asked for in §5.1 of the build prompt
(2026-10-18). Each question names the assumption the plan uses until you
answer it. Answer by number; anything left unanswered stands as assumed.

## Repository and process

- **Q1. The repo was empty.** `humanaxiom/Knowledge-engine` had no commits; it was
  not created from the template. **A1:** the `monitored-harness` template (commit
  `9abb753`) was imported verbatim as the first commit (`119aca7`).
- **Q2. Branches and pushing.** The prompt says pushing and PRs need your
  approval, and plan items go on `agent/<slug>`. The cloud session that started
  this work was assigned the branch `ccr-19465ed4-j1u0m5`, which is still the
  only branch on the remote. Since 2026-10-18 the work runs in your local clone,
  so idle reclamation no longer applies. **A2:** the planning documents are on
  `ccr-19465ed4-j1u0m5`. Each plan item is built on a local `agent/<slug>`
  branch, and nothing is pushed (to `agent/*` or any other branch), and no PR
  is opened, without your explicit go-ahead.
- **Q3. Resolved 2026-10-18.** The work moved to your local clone on Windows,
  where Docker 29.5.2 runs, and every gate now runs locally through
  `scripts/verify.sh` (evidence:
  `docs/evidence/harness-claude-code/green-full.txt`). Original question, kept
  for the record: *No Docker daemon in this cloud session.* The Docker CLI is installed
  but `/var/run/docker.sock` is absent. Every gate must run inside Docker, and
  item 0 is not done until `scripts/verify.sh` has run in every mode on a clean
  checkout. **A3:** gates are proven in GitHub Actions (which has Docker) and on
  your machine, and the evidence files say which. Nothing is reported green here
  that ran outside Docker. If you can enable Docker for this environment, say so.
- **Q4. Iteration cap.** **A4:** 5 per fix-and-retest loop, as in `AGENTS.md`.
- **Q18. Branch protection on `main`.** Is branch protection enabled on `main` in
  `humanaxiom/Knowledge-engine`? The local hook (`block-main-commit.sh`,
  harness-claude-code criterion 4) is only a guard rail against agent mistakes
  and can be bypassed; branch protection is the real control (security M1).
  **A18:** not verified from here. Recommend enabling it: require a PR to merge
  into `main` and block force pushes.

## Deployment

- **Q5. SSO.** Which identity provider goes first: CAS (as in the JD repo's
  ADR-008), SAML or OIDC? **A5:** CAS first, behind the pluggable interface,
  with a dev provider for CI.
- **Q6. Port range.** The box runs other stacks. **A6:** all host ports default to
  the `47100–47199` range, set in `.env`, never in code.
- **Q7. Model host.** What is the model host's address, and is it reachable from
  where the gates run? **A7:** it is an OpenAI-compatible endpoint set by
  `MODEL_BASE_URL`. CI never calls it, and live golden tests skip when it is
  absent. Defaults are `qwen2.5:14b-instruct` (fallback `llama3.1:8b`) and
  `nomic-embed-text` (768-dim).
- **Q8. Target hardware.** CPU and GPU, RAM, and disk on the on-premises box,
  which decide the OCR and layout models. **A8:** a CPU-only path (Tesseract,
  Docling or unstructured layout) is the default, and GPU models are opt-in per
  stage.

## Data and metrics

- **Q9. Manual baseline for "time per JD".** Who measured it, how, and when?
  **A9:** none exists yet. The metric is shown as *not yet measured*, with a
  placeholder that names the owner to be decided. It is never estimated.
- **Q10. Source identity for corpus revisions.** When a file is uploaded again,
  how do we know it is a new version of an existing document rather than a new
  document? **A10:** `source_key` is, in order of preference: an external ID from
  the institution profile (for example a position number), else a
  corpus-relative path, else the original filename plus the uploader's choice in
  the upload dialog ("new document" or "new version of …"). This choice is never
  inferred from similarity (DR12).
- **Q11. Retention and erasure.** Revisions are append-only. Does any corpus
  carry personal data that may need erasing, which conflicts with append-only
  storage? **A11:** revision content is stored in an encrypted blob keyed per
  source, so erasure deletes the key ("crypto-shredding"). Metadata, hashes and
  the audit chain remain, and the audit chain records the erasure itself. All
  revisions are retained indefinitely by default.
- **Q12. Policy effective dates.** Do rules need `effective_from` (applying from a
  future date, or back-dated) as well as the ratification date? **A12:** yes, both
  clocks are stored. Evaluation uses the version in effect at the evaluation
  time, and every output records that time.
- **Q13. Human corrections to records.** May reviewers correct extracted fields,
  as opposed to drafts? **A13:** yes, as `entered` revisions through the review
  queue. They survive re-parse, and any conflict goes to review (§R-REV-C.5).
- **Q14. Ratification owners.** DR22 needs named people and dates per owner tier
  (institutional policy, policy-informed, technical). **A14:** they appear as
  marked placeholders (`OWNER-TBD`) in the plan. The milestone "Done" check
  reports them as an external blocker until you name them.

## Corpus

- **Q15. JD fixtures.** The prompt permits the JD repo's `fixtures/golden/` as the
  `jd` test corpus because it is published on public job boards. **A15:** it is
  copied as-is into `fixtures/jd/`, with the source commit and that provenance
  statement in `fixtures/README.md`. No other JD-repo data is copied.
- **Q16. The second corpus.** Which corpus follows JD? It shapes how generic the
  pack schema must be. **A16:** none is named yet. A toy pack under
  `tests/packs/toy/` proves "a new corpus is a new pack, not code".

## Frontend

- **Q17. Stack.** **A17 (proposed in ADR-KE-006):** server-rendered FastAPI +
  Jinja + htmx for every view, with one Cytoscape.js island for the graph
  explorer, all assets vendored. React + TypeScript stays the fallback if the
  graph explorer outgrows the island.
