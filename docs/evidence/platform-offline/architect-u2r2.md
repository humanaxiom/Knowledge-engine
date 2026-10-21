# Architect: unit-2 rework round 2 design (2026-10-19)

Scope: docs only. `docs/architecture.md` §2.5 (Install, *`install.sh` portability*,
new *Entry hardening*, steps 1, 2, 6–9, trust anchor), ADR-KE-012 (status, decision
0–7, alternatives, consequences), §2.6 item 5c; `docs/requirements.md` PS-3.1
(Q53 bullet, new "unit-2 rework round 2" block) and PS-3.2 *Docs*;
`docs/open-questions.md` Q53 resolved (extended).

## Decisions
- **Publish (L-8).** Step 1 claims the target with `mkdir -m 0700` (exclusive, no
  final-symlink follow; an existing empty target is `rmdir`ed first and restored on
  failure). A random `.ke-claim.*` file marks the claim. Staging stays **beside** the
  target (keeps `test_install_stages_privately_in_target_parent` valid). Publish:
  check the target still holds exactly the marker, rename each top-level `app/` entry
  (from the verified manifest list + the override) into it, remove the marker,
  `chmod 0755` last. Windows pwsh holds the marker open (`FileShare.None`) until publish.
  Cleanup removes the target only if it is still the claim (dir, not link, marker).
- **H-1 pinning.** sh: `cd` into staging right after `mktemp -d`, relative paths only
  (`./<file>`, `./app`). pwsh: `Set-Location` + `[Environment]::CurrentDirectory`,
  relative paths; restore location in `finally`.
- **H-1 Windows ACL.** One helper: `DirectorySecurity` (owner = me, protected, one
  FullControl ACE) + `FileSystemAclExtensions.Create`, then verify owner/ACL from
  `Get-Acl` (SID form). Used for staging and the claimed target. No `Set-Acl`.
- **H-1 parent writable by others: WARN, not refuse.** Changed from my first draft to
  match the tester: `InstallPs1WindowsAclTest` must install (exit 0) under a parent
  granting Authenticated Users Modify, and `test_install_flags_target_parent_others_can_write`
  accepts either. Reason recorded: integrity no longer depends on the parent (pinning,
  ACL at creation, claim marker); the parent only affects the target after install.
  Warning text names the parent and "writable by others". POSIX: group/other write
  without sticky, or (bash) owner not me/root. Windows: non-inherit-only Allow ACEs with
  write/append/delete-child/delete/WDAC/WO/generic for SIDs other than me, SYSTEM,
  Administrators, TrustedInstaller.
- **M-4.** Whole body in functions; last line `main "$@"; exit`.
- **L-9.** First thing in `main`, builtins only: refuse empty or non-`/` PATH entries.
  ps1: refuse non-fully-qualified entries; on Windows drop empty ones.
- **L-10/RB1.** sh traps INT 130, TERM 143, HUP 129, QUIT 131. pwsh `KeInterrupt` adds
  SIGQUIT; `Install()` resets `Fired`; `Dispose()` in outer `finally`;
  `Assert-NotInterrupted` after each docker call, step boundary, loop iteration, before
  publish; exits via script `exit 1` (never `[Environment]::Exit` except the
  pwsh-stopped-pipeline SIGINT case) so in-process runs return to the session.
- **pwsh.** `#Requires -Version 7.3`; keep 5.1-parseable syntax; ConstrainedLanguage
  unsupported (fail-safe at Add-Type). Documented call `pwsh -NoProfile -File`.
- **Exec bits.** `git add --chmod=+x` for bundle.sh/install.sh; test covers
  bundle/install/launch/teardown.
- **Q53 extended.** launch.sh (`mapfile` -> read loops, `sort -V` -> pure-bash compare)
  and teardown.sh under the bash 3.2/BSD rule; forbid list (+P5 forms) over all three.
- **I-3/P2.** `cp -R -P` (no `-n`) into fresh staging after a lowercase `uniq -d`
  name pre-check that refuses by the case rule. **P7** one awk pass per membership
  check. **I-5** `} || exit 1` on piped groups. **P3** platform separator in next-step line.
- **Quickstart (a–e, RB2, P6)** listed in §2.5 trust anchor and PS-3.2 *Docs*.

## Test names (aligned to the tester's file; tester's names won)
`test_install_survives_staging_swap_after_verification`,
`test_install_stops_on_signal_to_its_own_pid`, `test_install_ps1_session_recovers_after_signal`,
`test_install_claims_target_before_docker`, `test_install_refuses_target_replaced_during_load`,
`test_install_flags_target_parent_others_can_write`, `test_install_ignores_script_changed_during_run`,
`test_install_sh_refuses_relative_or_empty_path_entries`, `test_install_sh_piped_checks_exit_explicitly`,
`test_install_sh_names_case_rule_for_present_case_variant`, `test_install_ps1_requires_pwsh_7_3`,
`test_install_ps1_creates_windows_staging_with_its_acl`, `InstallPs1WindowsAclTest.test_staging_never_inherits_an_ace`,
`test_operator_scripts_are_executable_in_git`, `test_operator_scripts_use_no_gnu_or_bash4_constructs`,
`test_launch_and_teardown_run_with_bsd_tool_shims`, `test_quickstart_offline_commands_run_as_written`,
`test_quickstart_offline_safety_notes`, `test_quickstart_target_not_directly_under_c_or_opt`.
No test yet (flagged): static "no absolute staging path after `cd`"; ps1 PATH rule;
final 0755 and marker removal; quickstart absolute-PATH / pwsh 7.3 / .DS_Store / no-smoke-on-Mac.

## Verify
`COMPOSE_PROJECT_NAME=ke-arch-r2 scripts/verify.sh fast` -> lint PASS; Ran 526, FAILED
(failures=37, skipped=1). All 37 in `tests.test_offline_bundle` (tester's in-flight RED);
0 failures elsewhere. Full output: `architect-u2r2-verify-fast.txt`. (A first run before
the tester's tests landed: 501 OK, PASS.)
