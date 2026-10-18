# analyst: amend requirement 4 (2026-10-18)

Written here instead of the handoff doc because the tester was appending to
`docs/handoffs/harness-claude-code.md` concurrently (orchestrator instruction).
The orchestrator should link or fold this into the handoff.

- Asked: resolve review B7 by amending `docs/requirements.md`, item
  harness-claude-code, criterion 4, to the orchestrator's ruling on
  `scripts/hooks/block-main-commit.sh`; add Q18 (branch protection) to
  `docs/open-questions.md`.
- Inputs read: `review-rework1.md` (B5, B6, B7, N7, N8), `security.md` (M1),
  `security-rework1.md` (M1 residual), current criterion 4.
- Done:
  - Criterion 4 rewritten as 4 + sub-items a-e: guard rail not boundary (Q18 is
    the real control); judge the actual git subcommand per segment, skipping
    global options `-C`/`-c`, never words in arguments/messages/heredocs;
    any-branch push denials (main/master target, `--force`, `-f` incl. combined
    short flags, `--force-with-lease`, `+refspec`, `--all`, `--mirror`); on-main
    denials (commit, push, merge, cherry-pick, am, rebase, revert); otherwise
    silent, never `allow`; works without jq on compact JSON. Test clause now
    requires the real compact payload and every case run with and without jq.
  - Decision record cited: security M1, review B5/B6/B7.
  - Q18 added under "Repository and process" in `docs/open-questions.md`.
- Decisions / notes for next roles:
  - The silent cases in 4a (three commit-message forms incl. heredoc, and the
    `echo` case) are taken from review B6 and are now testable requirements.
  - Review N8 (word-anywhere match on main denies e.g. `git log --grep revert`)
    is NOT required to be fixed: 4a says only the subcommand is judged, which
    would make that case silent; if the developer keeps a broad on-main match,
    that contradicts 4a. Orchestrator to confirm 4a applies on main too (my
    reading of the ruling: yes, it applies to "each shell segment").
  - Global options: ruling names `-C` and `-c`; review B6 also lists
    `--git-dir=`, `--work-tree=`, `--no-pager`. Criterion says "at least `-C`
    and `-c`"; the others are allowed but not required.
  - Out of scope by ruling (accepted bypasses): aliases, `eval`, variable
    indirection, `gh pr merge`, `update-ref`, `checkout main && commit`.
- Next: tester pins 4a-4e in `tests/test_block_main_commit_hook.py` (criterion
  10: resolve contradictions in the same commit, citing M1/B7); developer
  rewrites the hook.
