# analyst: requirements criterion 4, round-4 amendment (2026-10-18)

- Asked: rewrite `docs/requirements.md` harness-claude-code criterion 4 (4a-4f
  and the unit line) to the orchestrator's round-4 ruling. Touched only
  `docs/requirements.md` (architect is concurrently writing the ADR-KE-001
  decision; tester is concurrently rewriting the hook tests), so this section
  lives here instead of the handoff doc.
- Cites: ADR-KE-001 "Decision: commit hook is a simple fail-safe text rule
  (2026-10-18)" (not yet present in `docs/architecture.md` when written; the
  architect is adding it); security H2/L13/M3 (`security-rework3.md`); review
  B10/B11 (`review-rework3.md`).
- Before (round 3): 4a off-main shell-aware segmenting (segment breaks,
  skipped leading words/redirections, command-position git subcommand, global
  options, quoted/heredoc text never counts, `$((` arithmetic); 4b push target
  /force/--all/--mirror from any branch; 4c broad word rule on main over the
  extracted text; 4d silent otherwise + bypass list incl. `"$(...)"`, `bash -c`,
  `sh -c`, `xargs`, `checkout main && commit`; 4e no-jq compact payload; 4f
  linear, 1 MB under 3 s; unit line listing b/c cases and a's segment cases.
- After (round 4):
  - 4a extraction: jq if it works, else first `"command":"..."` value, else raw
    input; JSON with no command field is silent.
  - 4b normalisation: join line continuations, JSON `\n` -> newline, delete
    quotes and backslashes, lower-case (addresses H2 backslash doubling and
    L13 split words such as `g''it`, `ma\in`).
  - 4c on main/master: word `git` + any of commit/push/merge/cherry-pick/am/
    rebase/revert anywhere in the normalised text.
  - 4d off main: deny a normalised line with `git ... push` followed on that
    line by main/master word, --force/--force-with-lease, --mirror/--all, a
    short-flag cluster containing `f`, or a `+` refspec.
  - 4e silent otherwise, never `allow`; accepted false positives (one-line
    commands mentioning git, push and main) and accepted bypasses off main
    (hidden words via variables/eval/aliases/encodings, gh, update-ref, push
    split across lines without a continuation). Q18 is the real control.
  - 4f linear, no awk; 1 MB in under 3 s in the gates image in both jq modes
    for many short tokens, one long token, one long heredoc line (B10/M3).
  - Unit line (B11): every rule in both modes with the compact payload,
    naming line continuation, escaped quote, `ma\in`, `g''it` and `GIT` on
    main, `sh -c` and bash heredoc on main, `>/dev/null git push origin main`
    and backtick form off main, and the three timing shapes.
- Dropped as no longer required: round-3 segment/skip-word parsing and its
  silent cases (e.g. commit message mentioning push to main off main is now an
  accepted false positive, not a must-be-silent case).
- Open questions: none blocking. Note for tester: the round-3 must-be-silent
  cases (`git commit -m "fix push to main docs"`, `echo "git push origin main"`
  off main) now invert to deny; tests asserting silence there contradict 4e.
