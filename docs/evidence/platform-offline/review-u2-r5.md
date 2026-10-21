# Review: platform-offline unit 2, scoped confirmation of round 5/5 (2026-10-19)

Reviewer. Base 1fe81dd; working tree on agent/platform-offline (uncommitted). Scope (human-approved):
RB7, RB8, M-7, N10, N11, N13, N14/N15 docs, I-14. No new design questions opened.
Read: install.sh (cleanup, refuse_unsafe_parent, publish_into_claim), install.ps1 (Assert-SafeParent,
Close-Claim, finally), the round-5 tests in tests/test_offline_bundle.py, tests/fake_docker.py `rename` hook,
quickstart.md step 4, architecture.md §2.5/ADR-KE-012 round-5 text, the round-5 handoff sections,
green-u2r5-verify-full.txt (PASS), green-u2r5-windows.txt (12 OK), security-u2-r5 handoff entry.
Raw probes and mutant output: `review-u2-r5-probes.txt`. Verify: `review-u2-r5-verify-fast.txt`.

Verdict: **APPROVED**. No blocking findings.

## Verify
- `COMPOSE_PROJECT_NAME=ke-review-r5 scripts/verify.sh fast`: `== verify fast: PASS ==`, Ran 562, OK (skipped=6),
  lint PASS (shellcheck 14, PSScriptAnalyzer 4).

## Scoped items
| Item | Status | Evidence |
|---|---|---|
| RB7 ps1 sticky o+w parent | fixed | install.ps1:327-331 no `-not $sticky`. Probe re-run: ps1 parents 0o1757 and 0o1703 now rc 1, no docker, no target (r4: rc 0, installed); 1777/0757 refused; 0755 installs. sh identical. Test: `test_install_flags_target_parent_others_can_write` += 0o1757, 0o1703 (both runners), docstring corrected |
| RB8 quickstart "warns" | fixed | quickstart.md:115-120 says refuses, owned by you (root/SYSTEM/Administrators), sticky /tmp and `C:\` refused, unreadable parent refused; no "warns". `test_quickstart_parent_rule_round5` |
| I-14 | fixed | quickstart.md:123-126 ancestor advice + not on synced/shared media; same test |
| M-7 | fixed | install.sh:101-107 `rmdir -- "$staging"` (still gated on `*/.ke-install.*`); install.ps1:845-848 `Directory.Delete($script:Staging, $false)` in try; link branch unchanged. Tests: behavioural `test_install_never_removes_dir_renamed_into_staging_name` (sh+ps1, fake-docker `rename` hook) + static `test_install_{sh,ps1}_never_removes_staging_recursively_by_name` |
| N10 | fixed | install.sh:161-166 comment says sticky is refused; `test_install_sh_comments_never_allow_a_sticky_parent` |
| N11 | fixed | one `[ "$target" -ef . ]` left (install.sh:233); `test_install_sh_refuses_real_dir_swapped_in_at_publish` pins it (tester's no-`-ef` mutant killed: red-u2r5-n11-mutant.txt) |
| N13 | fixed | `Assert-SafeParent` (def :283, call :435); no `Write-SharedParentWarning` left in code, tests or live docs |
| N14/N15 | fixed (docs) | architecture.md §2.5 / ADR-KE-012 round-5 text matches the code (rmdir / Delete($false), owner check in Initialize-Staging, OWNER RIGHTS / CREATOR OWNER recorded) |

## M-7 mutant (scratch copy only)
- sh: cleanup back to `rm -rf -- "$staging" || true`; ps1: `Directory.Delete($script:Staging, $true)`.
- Result: **killed**. Behavioural test fails for both runners ("deleted the operator directory renamed into the
  staging name"), and both static tests flag the line (install.sh:105, install.ps1:847). Ran 297, failures=13:
  4 distinct M-7 failures (duplicated by the scratch module's imports) + ExecBitTest (no .git, by design).

## Test-weakening check
- `test_install_empties_swapped_staging` amendment is **legitimate**. Before, it also required the lookalike
  planted at the staging name to be emptied; that can only be satisfied by recursive removal by name, which
  the round-5 M-7 ruling forbids (whatever sits at the name is not this run's). The I-7 property it exists for
  (the renamed original, the pinned dir holding the image tars, is emptied from inside) is still asserted
  unchanged, and the dropped half is replaced by the stronger opposite assertion in
  `test_install_never_removes_dir_renamed_into_staging_name`. The docstring cites the ruling.
- No other test was removed, skipped or loosened in the round-5 delta; 562 tests (r4 555 + 7 new).

## Regression
- None found: verify fast PASS (562), developer's verify full PASS and Windows host 12 OK, all prior r4 probes
  that matter (RB6, publish swap) remain covered by tests that still pass.

## Non-blocking observations (not findings; no action required this round)
- O1 install.sh:165 the N10 edit left a 147-char comment line (cosmetic reflow).
- O2 After a staging swap, rmdir leaves the swapped-in directory (and any empty renamed original) in the
  parent with no message; this is the intended M-7 behaviour (matches security O-2), noted for the quickstart
  troubleshooting section in a later item if operators report leftovers.
- N8 (carried) untracked docs/knowledge-engine-claude-code-prompt.md: keep it out of the commit.

## Conformance
- No eval / Invoke-Expression, argv arrays, no secrets. Operator scripts: no agent loop, model call, retrieval
  or tool call, so no span required.
