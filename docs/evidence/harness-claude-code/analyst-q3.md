# 2026-10-18 — analyst: Q3 resolved, Q2 updated

- Asked to: mark Q3 (no Docker daemon in cloud session) resolved in
  `docs/open-questions.md`, keeping the original text; update Q2 where no longer true.
  Written here, not in the handoff doc, because the architect was appending to it concurrently.
- Verified before editing:
  - `docker version` server reports 29.5.2 on the local Windows clone.
  - `green-full.txt` ends `== verify full: PASS ==`.
  - `git branch -a`: remote has only `origin/ccr-19465ed4-j1u0m5`; local work on `agent/harness-claude-code`.
- Changed (only `docs/open-questions.md`):
  - Q3: heading now "Resolved 2026-10-18" with the resolution (local clone, Docker 29.5.2,
    gates via `scripts/verify.sh`, evidence path); original question and A3 kept verbatim after
    "Original question, kept for the record:".
  - Q2: dropped "this cloud session ... is reclaimed when idle, so unpushed work is lost" and
    "so they survive"; now says the session branch is still the only remote branch, work runs
    locally since 2026-10-18, plan items on local `agent/<slug>`, no push of any branch and no PR
    without explicit go-ahead.
- Not changed: Q1, Q4–Q17; no new requirements.
- Note for orchestrator: A3's original text ("gates are proven in GitHub Actions ... and on your
  machine") is kept as history; it is superseded by the resolution line, not edited.
