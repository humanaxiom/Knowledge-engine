# analyst: requirements criterion 4, round-3 amendment (2026-10-18)

- Asked: amend `docs/requirements.md` harness-claude-code criterion 4 to the
  orchestrator's round-3 ruling on review B8/B9 (`review-rework2.md`) and
  security M1/L9/L10 (`security-rework2.md`). Not touching `tests/` or
  `docs/handoffs/` (tester runs concurrently), so this section lives here.
- Changed (criterion 4 only):
  - Decision record now cites review-rework2 B8/B9 and security-rework2
    M1/L9/L10, and states the round-3 ruling replaces the earlier ruling that
    4a's precise judging also applies on main (analyst-req4.md, N8 question).
  - 4a is now explicitly the **off main/master** rule. Added segment breaks
    (unquoted `&`, `(`, `)`, `{`, `}`, `$(`, backtick, plus newline), skipped
    leading words (`!`, if/then/elif/else/do/while/until/time/command/env/exec)
    and leading redirections, and `$((` is arithmetic, not a heredoc (L10).
    Added denied examples from B8/M1 (subshell, brace group, if, `&`, leading
    redirect, unquoted `$( )`, backticks, arithmetic-then-push).
  - 4c is now **broad and fail-safe on main/master**: word `git` plus any of
    commit/push/merge/cherry-pick/am/rebase/revert anywhere in the extracted
    text, including quotes, `$( )`, backticks, `bash -c`/`sh -c`, heredocs.
    False positives accepted.
  - 4d lists the **accepted bypasses off main** (Q18 is the real control):
    `"$(…)"`, `bash -c`, `sh -c`, `xargs`, aliases, eval, variable
    indirection, gh, update-ref, `checkout main && commit`.
  - New 4f **performance** (L9): linear cost; 1 MB command under 3 s in the
    gates image.
  - Unit line (B9): every case in 4b and 4c tested in both jq and no-jq modes,
    naming `git -c`, `refs/heads/main`, `:main`, `--force-with-lease`, plain
    `-f`, push to master from a plan-item branch, push on master.
- Before text: 4a judged on every branch; 4c listed subcommands on main without
  saying how they are matched; unit line said "covers each denial in b and c".
- Open questions for the orchestrator:
  1. 4f: does the 3 s bound apply to both jq and no-jq modes in the image?
     Security L9 measured image no-jq at 11.6 s for 1 MB. I wrote "in the gates
     image" without a mode, per the ruling; a test needs to pick.
  2. 4f has no named unit test. Should the timing case be a unit test in
     `tests/test_block_main_commit_hook.py` (risk: flaky timing on CI) or an
     evidence-file probe?
  3. Review N13 items not ruled on: `git pull` on main (the broad 4c word list
     does not include `pull`), `nohup`/`sudo` as skipped words (security M1
     recommended them; ruling omits them), redirect glued to a token
     (`main&>/dev/null`), `--branches` as an `--all` alias. Left out of 4.
- Next role: tester pins the new 4a/4c/4f cases and the B9 list in both modes;
  developer implements the broad on-main match and linear lexer.
