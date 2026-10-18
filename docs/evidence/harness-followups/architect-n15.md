# harness-followups: architect, docs gate N15a / N15b / sentinel as-built (2026-10-18)

- **Asked:** update ADR-KE-001's hook decision to match the code (review N15a, N15b),
  add security L23, do not record N16, and add the sentinel contract to "As built".
  Only `docs/architecture.md` was touched.
- **Done (docs/architecture.md, ADR-KE-001):**
  - As built: new bullet. verify.sh needs `Ran N tests` with N > 0 and the exact whole-line
    sentinel line (quoted on one line in a code block) from `tests/test_sentinel.py`. The module
    must stay top-level, with its module, class and method names unchanged; renaming any of them
    turns verify red.
  - Decision: "Normalise: join line continuations" replaced. Now: CR deleted (PS-0.4); text (a)
    joins backslash-newline to nothing (PS-0.5, M5); text (b) is built only when a
    backslash-newline is present (L21) and turns it into a space (M6); deny if either matches.
  - Consequences: added fail-safe false positives (backslash-newline in single quotes, glued
    continuation, comment and even-backslash shapes). Added accepted bypasses: the off-main
    word-split after a comment or even run (L23, the off-main form of Table M rows 14 and 15),
    `git<CR>push`, and on main Table M rows 14 and 15. Added the cost line: 4.9 s / 6.8 s host,
    under the 10 s timeout, low headroom with a backslash-newline
    (`hook-timing-host-r4.txt`).
  - N16: the ADR never mentioned it, so there was nothing to remove. It is not recorded.
- **Verify:** `scripts/verify.sh fast`: rc=1, full output in `architect-n15-verify-fast.txt`.
  All 10 failures are the subtests of
  `tests.test_harness_followups.VerifyRequiresTestsRunTest.test_sentinel_followed_by_large_output_passes`.
  That is the tester's concurrent N19 RED test (SIGPIPE in the verify.sh `tr | grep -q` pipeline).
  It is unrelated to this docs diff. The gate cannot be called passed until the developer fixes N19.
- **Next:** developer fixes N19 in verify.sh. If the fix changes how the sentinel is matched,
  the As-built wording ("contains, as a whole line, the exact sentinel line") still holds.
  Documenter covers N15c in CLAUDE.md, AGENTS.md and the verify.sh header.
