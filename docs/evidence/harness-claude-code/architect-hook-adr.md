# 2026-10-18 - architect: harness-claude-code, hook decision record (round 4)

- **Asked:** record the orchestrator's round-4 hook ruling as a decision record
  inside ADR-KE-001, answer review N15, and correct the "As built" hook bullet.
  Touch only `docs/architecture.md` (analyst and tester run concurrently).
- **Read:** `review-rework3.md` (B10, B11, N15), `security-rework3.md` (H2, M1,
  M3, L13), ADR-KE-001 in `docs/architecture.md`.
- **Did (`docs/architecture.md` only):**
  - "As built" hook bullet: it now says the hook never prints `allow` (a
    fixed deny or nothing). A new bullet says the hook is a simple fail-safe
    text rule (broad on main/master, narrow off main, no awk) and points to
    the decision record, which supersedes the round-3 off-main lexer.
  - New sub-heading under ADR-KE-001: "Decision: commit hook is a simple
    fail-safe text rule (2026-10-18)". It covers context (B5, B8, H2 fail-open
    regressions; L9/B10 timing; security M1 medium; Q18 branch protection),
    the decision (extraction, normalisation, on-main rule, off-main rule, no
    awk, never `allow`), the consequences (accepted false positives, which
    reverses B6; accepted off-main bypasses) and the rejected alternatives.
- **Not decided here:** requirements item 4 (4a-4f) still describes the
  round-3 split. The analyst owns that amendment. It must agree with this
  record, especially the B6 reversal and the off-main bypass list.
- **Testability (first failing tests for the tester):**
  - Off main, deny: `git push origin main`, `git push -f`, `git push -uf`,
    `git push --mirror`, `git push origin +agent/x`, a continuation-joined
    push to main, `GIT push origin main`, `git push origin ma\in`.
  - Off main, silent: `git push -u origin agent/x`, a heredoc commit whose body
    has `git push origin main` on separate lines, `git log --oneline main`.
  - Off main, denied as accepted false positives (pins the B6 reversal):
    `echo "git push origin main"`, `git commit -m "fix git push to main docs"`.
  - On main, deny: `g''it commit -m x`, `Git commit -m x`, `git c\ommit -m x`
    (the L13 forms, closed by normalisation).
  - Static: the hook source contains no `awk`, and no output path prints
    `allow`.
  - Timing: 1 MB single token, 1 MB heredoc line and a 1 MB heredoc of many
    short lines, both jq modes, under 3 s in the gates image.
- **Observability:** no product agent loop, model call, retrieval or tool
  call. No spans required.
- **Next:** the analyst aligns requirements item 4; the tester writes RED
  tests from the list above; the developer rewrites the hook.
