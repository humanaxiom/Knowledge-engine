# Handoff: harness-claude-code

Outcome metric moved: neither directly. This item is the gate machinery every
later item relies on. Done only with the proof in requirements item 13.

## 2026-10-18 — orchestrator (bootstrap; role subagents did not exist yet)
- Asked to: port the Copilot harness to Claude Code (build prompt §0).
- Did:
  - `.gitattributes` forces LF for shell scripts; the Windows checkout had CRLF, which breaks bash in containers.
  - `gates` compose service and `docker/gates.Dockerfile` (no network).
  - `scripts/verify.sh [fast|full]`; CI calls only that.
  - `CLAUDE.md`; `.claude/agents/<role>.md` x8, built from the Copilot bodies; `.claude/settings.json` hook.
  - Done check in `docs/handoffs/README.md`.
- Decided/found:
  - The hook printed `permissionDecision: allow` for every non-blocked Bash call. In Claude Code that auto-approves every shell command, so it now prints nothing and defers to the normal permission flow.
- Evidence (all in `docs/evidence/harness-claude-code/`):
  - `red.txt` — 25 failing before the change.
  - `green-fast.txt` and `green-full.txt` — 33 tests OK, smoke pass.
  - `mutation-constraints.txt` — one changed word turns the suite red.
- Next role needs to know: each subagent is dispatched once on a trivial task, and the transcripts go to `dispatch-<role>.md`.

## Trivial dispatch task (for the proof)
Each role: read this file; append a 3-line section headed `<date> — <role>: dispatch check`, listing (1) your model tier as you understand it, (2) the one verification command you are allowed to run, or "none" if your role runs none, and (3) one file you own. Then log with `log_event --gate "dispatch: ok"`. Change nothing else.

## 2026-10-18 — orchestrator: dispatch proof
- Did: after a session restart (Claude Code loads `.claude/agents/` only at session start), dispatched all eight roles in parallel on the trivial task. Each wrote its section to its own file to avoid racing on this doc.
- Found:
  - All eight dispatched by name and wrote `docs/evidence/harness-claude-code/dispatch-<role>.md`.
  - `docs/log.md` has eight intact `dispatch: ok` lines; concurrent appends did not interleave.
  - Self-reported tiers match the frontmatter.
  - Nit: the marketer named `scripts/verify.sh fast` as its verification command, but its agent file gives it none, so it inferred one. The roles that write no code should say "none" explicitly.
- Next: architect (ADR-KE-001 as-built) and analyst (Q3) in parallel; then reviewer + security on the full diff; then the orchestrator runs `scripts/verify.sh full` and commits.

## 2026-10-18 — architect: ADR-KE-001 as built
- Asked to: align `docs/architecture.md` with what this branch built.
- Did: updated the "Current state" paragraph to name the port; added an "As built" group to ADR-KE-001; the sync-test consequence now names `tests/test_harness_port.py` (Constraints + duty step). No other ADR text changed.
- Checked against files: `scripts/verify.sh`, `docker-compose.yml` (`network_mode: none`), `.github/workflows/ci.yml`, `.gitattributes`, `scripts/hooks/block-main-commit.sh`, `.github/agents/developer.agent.md` hook wiring, `core.autocrlf=true`.
- Next: docs-only change; `scripts/verify.sh fast` suffices for it (full still runs before commit).

## 2026-10-18 — tester: rework 1 RED (B1, B2, B3, M1, N1)
- Asked to: write failing tests for review B1–B3 and security M1/N1. Production files left unchanged.
- Did (tests only):
  - `tests/test_harness_port.py`:
    - `test_no_stray_verification_commands` now scans AGENTS.md too (B1).
    - `test_non_producer_body_identical_to_copilot`, plus `test_producer_sections_identical_except_verification_steps` (B2). Helpers: `body`, `sections`, `numbered_steps`.
    - `test_gate_scripts_use_locked` (B3, the name requirement 9 uses).
  - `tests/test_block_main_commit_hook.py`:
    - `test_denies_push_to_main_or_force_push_from_any_branch`, `test_silent_for_plain_push_of_plan_item_branch` and `test_denies_commit_creating_commands_on_main` (M1).
    - `test_jq_reads_only_the_command_field`, skipped without jq; plus `GatesImageJqTest.test_gates_image_installs_jq`, so jq stays installed in the image (N1).
- RED (`scripts/verify.sh fast`, `red-rework1.txt`): 41 tests, 11 failures, 1 skipped, all expected:
  - AGENTS.md matches `scripts/smoke.sh`.
  - 4 push subtests and 5 on-main subtests are not denied.
  - The Dockerfile has no jq.
  - The jq test is skipped (no jq in the image).
- Green already, no production change needed:
  - The B2 port tests: the bodies match today.
  - `test_gate_scripts_use_locked`: every uv call already has `--locked`.
  - Both silent-push tests.
- Mutation (`mutation-approach.txt`): analyst.md step 5 `docs/requirements.md` -> `docs/architecture.md`. Exactly one new failure, `test_non_producer_body_identical_to_copilot (role='analyst')`.
  - Restored: sha256 and `cmp` match the backup. `.claude/` is untracked, so `git diff` cannot show it.
- New blocker found, for the developer (`gate-offline-stale-cache.txt`): the first `verify.sh fast` died before any test ran. `uv run` rebuilds the editable project, which needs `hatchling` from the build-time uv cache. Once that cache's index entries go stale, uv tries PyPI and fails, because the gates container has no network.
  - `docker compose --profile gates build --no-cache gates` cleared it, so the stale cache is the likely cause.
  - Any run made more than a few minutes after the image build will fail. Likely fix: set `UV_OFFLINE=1` (or pass `--offline`) at gate runtime, or avoid rebuilding the project.
- Next (developer): reword AGENTS.md; extend the hook (push refspec main/+/--force from any branch; merge, cherry-pick, am, rebase and revert on main); install jq in gates.Dockerfile; fix the offline rebuild; then run `scripts/verify.sh full`.

## 2026-10-18 — developer: rework 1 GREEN (B1, M1, M2, L1, L4, N1, offline blocker)
- Did (production files only, no tests edited):
  - `AGENTS.md`: roles row, gate 4 and File Conventions name only `scripts/verify.sh` (B1).
  - `scripts/hooks/block-main-commit.sh`: per-segment (`&& || ; |` newline) checks. Any branch: deny push naming main/master (incl. `HEAD:main`, `refs/heads/main`) and `--force`/`-f`/`--force-with-lease`/`+refspec`. On main: also merge, cherry-pick, am, rebase, revert. jq/raw fallback and silent default kept; comment says guard rail (M1).
  - `docker/gates.Dockerfile`: jq installed, `safe.directory /work`, `core.autocrlf true`, both FROM digest-pinned (from green-full.txt), `ENV UV_OFFLINE=1` after `uv sync --locked`.
  - `.github/workflows/ci.yml`: `actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0` (SHA from `gh api`; v4 tag points at it) (L1).
  - `.dockerignore` added (L4).
- Evidence (`docs/evidence/harness-claude-code/`):
  - `green-rework1.txt`: `scripts/verify.sh full` PASS, 41 tests OK, 0 skipped (jq test now runs).
  - Offline proof: `offline-after.txt` shows the old behaviour (`UV_OFFLINE=0` + `--refresh`, emulating stale cache) dies fetching hatchling from PyPI. `green-rework1-later.txt` is a rerun 11 min after the image build, PASS. The pre-rebuild image was only 2 min old, so it was not stale (`offline-before.txt`).
- Note: uv refuses `--refresh` together with UV_OFFLINE, so the stale case cannot be emulated under offline; the 11-minute rerun is the proof.
- Not staged or committed.

## 2026-10-18 — tester: rework 2 RED (B5, B6, N7, H1, L8)
- Asked to: pin review B5/B6/N7 and security H1/L8. Only `tests/test_block_main_commit_hook.py` edited.
- Did:
  - `claude_code_payload`: compact JSON with session_id, transcript_path, cwd, hook_event_name, tool_name, tool_input{command, description}. Every JSON case uses it.
  - Every case runs in modes `jq` and `no-jq` (subTest). no-jq puts a fake `jq` that exits 127 first on PATH. The hook has no test switch.
  - New tests: `test_payload_helper_is_compact_claude_code_shape`, `test_denies_git_first_word_on_main` (B5), `test_silent_for_text_that_only_mentions_push_on_plan_item_branch` (B6, incl. heredoc and `git log --oneline main`), `test_long_command_finishes_quickly` (L8, 400 segments < 5 s).
  - Extended push denials: quoted `"main"`, `-C .`, `--all`, `--mirror`, `-fu` (N7).
  - Renamed `test_jq_reads_only_the_command_field` to `test_judges_only_the_command_field`; it now runs in both modes. The raw-stdin test is kept and runs in both modes.
- RED (`scripts/verify.sh fast`, `red-rework2.txt`): 45 tests, 31 subtest failures, 0 skipped. All of them are in the hook file, and all are expected:
  - no-jq: every on-main deny and every push-from-branch deny is silent (B5/H1). The heredoc is denied (B6). The description field is judged (H1).
  - jq: `--all`, `--mirror` and `-fu` are not denied (N7). Both commit messages, the echo and the heredoc are denied (B6).
- Green already: plain plan-item pushes, `git log --oneline main`, raw stdin, and L8 in the image (Linux). L8 was only slow on the host (12.3 s), so the image cannot show it RED.
- Next (developer): extract `tool_input.command` without jq; judge the git subcommand after global options; skip quoted and heredoc text; handle `--all`/`--mirror`/short-flag clusters; then run `scripts/verify.sh full`. Re-time the 400-segment case on the host.

## developer - rework 2 GREEN (2026-10-18)
- Rewrote `scripts/hooks/block-main-commit.sh`: jq when it works, else awk extracts `tool_input.command` (unescapes `\"` `\` `\n` `\t`; non-JSON input = the command; JSON without command = silent). One awk program lexes quotes, heredocs, `&& || ; |` and newlines, skips `VAR=` prefixes and git global options (`-C`, `-c`, `--git-dir`, `--work-tree`, `--no-pager`, `-P`...), and judges only `git` command words by subcommand, on main too (supersedes N8). Push rules per spec 4b; reason strings unchanged.
- Evidence: `docs/evidence/harness-claude-code/green-rework2.txt` (`scripts/verify.sh full`: PASS, 45 tests, jq mode ran, none skipped), `hook-timing-host.txt` (400 segments, no jq, 0.23 s), `hook-live-host.txt` (main: commit/push denied; agent/x: quoted-message commit silent).
- Note: on this Windows host `python -m unittest` resolves `bash` to WSL's System32 bash (exit 127); the gates image is the authoritative run. Not committed.

## 2026-10-18 — tester: rework 3 RED (B8, B9, M1, L9, L10)
- Rework-2 findings: reviewer in `docs/evidence/harness-claude-code/review-rework2.md`, security in `security-rework2.md`.
- Asked to: pin the orchestrator ruling (broad on main, precise off main; `"$(…)"`, `bash -c`, `sh -c`, xargs, aliases, eval, indirection, gh, update-ref accepted off main and not tested as denied). Only `tests/test_block_main_commit_hook.py` edited; jq/no-jq modes and `claude_code_payload` used for every case.
- New tests: `test_denies_nested_git_on_main` (12 shapes), `test_denies_nested_push_to_main_or_force_from_plan_item_branch` (7), `test_denies_push_with_c_global_option_from_plan_item_branch`, `test_denies_push_refspec_forms_from_plan_item_branch`, `test_denies_push_on_master`, `test_escaped_quote_does_not_hide_following_push`, `test_silent_for_claude_code_heredoc_commit_on_plan_item_branch`, `test_description_with_forged_command_key_is_not_judged`, `test_one_megabyte_command_finishes_quickly` (L9, 1 MB < 3 s). Existing B6 silent cases kept unchanged.
- RED (`scripts/verify.sh fast`, `red-rework3.txt`): 54 tests, 37 subtest failures, 0 skipped, all expected:
  - 22 = nested-on-main, 11 shapes x 2 modes, silent instead of deny (B8/M1). `echo $((1<<2)) && git commit -m x` already denied.
  - 14 = nested-off-main, 7 shapes x 2 modes, silent instead of deny (B8/M1/L10).
  - 1 = L9 no-jq: 7.98 s (jq mode passed in the image).
- Already green (pins only, B9): `-c` push, refs/heads/main, `:main`, lease, `-f`, master target, push on master, escaped quote, Claude Code heredoc form, forged description key.
- Next (developer): broad on-main text rule; segment breaks/leading-word skips/`$((` per ruling; linear-time lexer; then `scripts/verify.sh full`.

## developer, rework 3 GREEN (2026-10-18)
- Asked: make tests/test_block_main_commit_hook.py pass (criterion 4a/4c/4f), no test edits.
- Changed scripts/hooks/block-main-commit.sh only: (1) 4c broad whole-text rule on main/master (word `git` + commit/push/merge/cherry-pick/am/rebase/revert) before the lexer; (2) 4a lexer breaks on unquoted & ( ) { } backtick, `$((` skipped as arithmetic, prefix skip of VAR=, redirections, ! if then elif else do while until time command env exec; (3) 4f linear: extractor splits on quotes and streams pieces (no per-char concat), RS slurp instead of per-line concat, heredoc skipping scans chars instead of substr(s,i) copies.
- Evidence: `scripts/verify.sh fast` green (green-fast-r3.txt); `scripts/verify.sh full` PASS, 54 tests (green-rework3.txt); host 1 MB no-jq ~1.1 s (hook-timing-host-r3.txt); mutations a-d each RED, hook restored byte-identical sha256 422f0aa0... (mutation-hook-r3.txt); live host check (hook-live-host-r3.txt).
- Note: mutation (b) first attempt was a no-op sed, redone; file records the re-run.
- Not staged, not committed. Next: reviewer/security.

## 2026-10-18 — tester: rework 4 RED (ADR-KE-001 simple text rule; B10, B11, H2, L13, M3)
- Round-3 findings: reviewer in `docs/evidence/harness-claude-code/review-rework3.md`, security in `security-rework3.md`.
- Asked to: pin ADR-KE-001 "Decision: commit hook is a simple fail-safe text rule (2026-10-18)" and resolve the contradiction it creates (criterion 10). Only `tests/test_block_main_commit_hook.py` edited; every case uses `claude_code_payload` in jq and no-jq modes.
- Contradiction resolved (ADR cited in comments):
  - B6 silent test narrowed to the heredoc whose body has no git+push+main line, `git push origin agent/x`, `git log --oneline main`.
  - Moved to new `test_one_line_mentions_are_accepted_false_positives_off_main` (deny): `fix push to main docs`, `note push -f is denied` (the `-f` follows `git ... push` on one line, so the rule denies it too), the echo, the original heredoc (body line `git push to main`), plus `bash -c "git push origin main"` and `echo "$(git push origin main)"`.
  - Claude Code heredoc commit test: body changed to `note: push to main and push --force are denied` (no git on that line); still silent.
  - Rework-3 comment block rewritten: `"$(...)"`/`bash -c`/`sh -c` are no longer bypasses when one line says git+push+main.
- New tests: `test_grep_for_a_verb_on_main_is_accepted_false_positive`, `test_silent_for_everyday_commands_on_plan_item_branch`, `test_backslash_forms_deny_push_off_main` (H2), `test_split_or_cased_git_word_denied_on_main` (L13), `test_prefixed_push_to_main_denied_off_main` and `test_shell_wrapped_commit_denied_on_main` (B11), `test_one_megabyte_token_shapes_finish_quickly` (B10/M3, 4 shapes, < 3 s).
- RED (`scripts/verify.sh fast`, `red-rework4.txt`): 62 tests, 28 subtest failures, 0 skipped, all expected:
  - 12 = one-line false positives off main, silent instead of deny (6 x 2 modes).
  - 10 = L13 split/cased git on main, silent (5 x 2 modes).
  - 6 = B10/M3 1 MB unquoted token, `-m` message, heredoc line: 7.7-8.1 s (3 x 2 modes).
- Already green in the image (pins): H2 backslash forms (the image has mawk; H2 is gawk-only, so the image cannot show it RED), B11 forms, `git log --grep revert` on main, the everyday silent set, the 1 MB many-line heredoc.
- Next (developer): rewrite the hook per ADR-KE-001 (no awk), then `scripts/verify.sh full`; run the hook tests or a probe on the Windows host (gawk) for H2.

## developer, rework 4 GREEN (2026-10-18)
- Asked: make tests/test_block_main_commit_hook.py pass per criterion 4a-4f and ADR-KE-001 "simple fail-safe text rule"; no test edits. Spec: `docs/evidence/harness-claude-code/analyst-req4-r4.md`, `architect-hook-adr.md`.
- Rewrote `scripts/hooks/block-main-commit.sh` (about 55 lines, no awk): extract (jq, else grep -o + sed on first `"command":"..."`, else raw), normalise (sed -z joins continuations, tr deletes quotes/backslashes, tr lower-cases), then one grep -E per rule. Reason strings and silent default unchanged; never prints allow.
- Evidence: `green-rework4.txt` (`scripts/verify.sh full` PASS, 62 tests OK); `hook-live-host-r4.txt` (Windows gawk host, natural no-jq and fake jq exit 127, 20 cases each, 0 failures); `hook-timing-host-r4.txt` (1 MB shapes, 0.5-0.6 s); `mutation-hook-r4.txt` (a-d each RED, sha256 746f090b... restored, match).
- Gotcha: backslash-heavy heredocs through the Bash tool get halved; the hook was fixed via Edit. Not staged, not committed. Next: reviewer/security.

## 2026-10-18 — orchestrator: gates after rework round 4 of 5
- Review: APPROVED (`review-rework4.md`). Security: PASS, 0 critical/high (`security-rework4.md`).
- Orchestrator re-ran `scripts/verify.sh full`: 62 tests OK, smoke pass (`orchestrator-verify-full.txt`); read the hook, settings, AGENTS.md and compose diffs.
- Round history:
  - r1 AGENTS.md stray commands, port drift guard, lockfile drift, refspec push (fixed);
  - r2 hook failed open without jq (fixed);
  - r3 nested shell syntax (fixed);
  - r4 lexer replaced by the simple text rule (ADR-KE-001 decision).
- Deferred follow-ups (non-blocking; next harness touch, or a fix/ item):
  - security M4: a CR in the command fails open on the host without jq. Fix: drop the `\r` escape in extraction and `tr -d '\r'`.
  - review N16: a backslash-newline should join to nothing, not a space.
  - review N17: test "JSON without command is silent" and "first command value".
  - review N18: ADR wording ("single sed").
  - review N19: AGENTS.md says the hook is wired in developer.agent.md; Claude Code wires it in `.claude/settings.json`.
  - security L16: a Windows backslash path to git.exe is silent.
  - security L17: `--branches` and abbreviated `--mirr`/`--al`.
  - security L18: `pull`/`update-ref` on main.
  - review N3: integration tests run twice once `tests/integration` exists.
  - review N5, N6: hook judges the session cwd; Copilot agents still run gate scripts on the host.
  - security L2, L5, L7: root in gates, `KE_IN_GATES` override, web tools on analyst/marketer.
- Item 13 still open after commit: clean-checkout `verify.sh fast|full` (use `-c core.autocrlf=false` clone), and CI green (needs a push, i.e. human approval).
- Human actions: Q18 branch protection on main; delete the stray empty `git init` skeleton at `C:\c` left by a security probe.
