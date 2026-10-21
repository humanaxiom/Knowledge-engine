# Audit: audit-l2 follow-ups (M-L2a, L-L2a to L-L2e), review and security, scoped

Date 2026-10-19. Auditor: security, also covering review as the orchestrator scoped it.
Scope: `git diff HEAD -- engine/startup.py scripts/launch.sh scripts/launch.ps1 scripts/install.ps1
docs/quickstart.md docs/architecture.md docs/requirements.md`, plus the new tests in
`tests/test_stack_scripts.py`, `tests/test_engine_startup.py` and `tests/test_offline_bundle.py`.
The worktree hashes, the runner, the mutant diffs, all probe scripts and their output are in
`audit-fu-probes.txt` (redacted: `<sid>`, `<machine-sid>`, `<host>`, `<user>`, `<scratch>`).
All work ran in the scratch directory only (`<scratch>/final/fu`). HEAD, the index and tracked
files were not touched. Producer evidence read: `green-fu-verify-full.txt` (verify full PASS, 342 s)
and `green-fu-windows-host.txt` (9 OK).

## Verdict

**PASS / APPROVED.** All six audit-l2 findings are fixed. There are no critical, high or medium
findings. One new low finding (L-FUa, hygiene) and five info notes do not block.

## Confirmations

| Item | Result |
|---|---|
| **M-L2a** | **Fixed.** `check()` l.77-82: an `elif` after the auth-off branch, so it only *logs* and never raises. Matrix probe (gates image): with auth=true, dev and ci both log `auth.enabled (KE_AUTH__ENABLED) is true: it has no effect until auth-audit, so the API is not authenticated (env=...)`, and dev+0.0.0.0 logs both warnings and STARTS. The only ci refusals in the matrix come from the existing bind and auth-off rules. prod gets no warning and is still refused (refusal 7, last), and the shipped defaults are refused. The message is accurate (auth is not built) and names only `env`; the canary secrets in the probe never appear. The env enum is closed (`staging` is a ConfigError), so "outside prod" means exactly dev and ci. |
| **L-L2a** | **Fixed.** The guard is `! -e && ! -L`, and the create is `(umask 077; set -C; cat .env.example > .env)`. Probes (bash 5.2, real script): a dangling `.env` is left alone, its target is not created, the link is unchanged, and no "created" message appears. **Race**: a racer injected through `BASH_ENV` + `bash -T` DEBUG trap writes `.env` just after `umask 077`; the create fails `cannot overwrite existing file`, rc=1, and the racer's content is kept. A racer that plants a dangling symlink in the same window gets the same refusal, and its target is not created. Controls: umask 022/000 give 0600 and the same content; an existing 0640 `.env` is kept. |
| **L-L2b** | **Fixed.** `FileStreamOptions{Mode=CreateNew, Access=Write, UnixCreateMode=UserRead|UserWrite}`, then a write on the same stream. Probe (pwsh 7.4, gates image): the mode is 600 at size 0 *right after the open, before the write*, under umask 022 and 000, so there is no wide window and nothing for a held fd to exploit. The real script gives 600 under umask 022/002/000. CreateNew refuses a dangling link even with Test-Path bypassed ("already exists"; the target is not created) and refuses a file a racer created (the racer's content is kept). |
| **L-L2c** | **Fixed.** (ii) The grant is `*<SID>` from `WindowsIdentity::GetCurrent().User.Value`. On this host, under 5.1 and pwsh 7, the ACL is exactly one ACE for the user with inheritance removed. (i) Warn-only: with a failing icacls stand-in, and with icacls absent from PATH, both Windows PowerShell 5.1 and pwsh 7 print `WARNING: could not restrict .env to the current user; restrict .env before adding secrets to it: ...`, show no NativeCommandError, carry on, and leave the inherited ACL (SYSTEM, Administrators, user), so there is no lockout. When icacls is absent, `$LASTEXITCODE` is unset in a fresh process, so `restricted` stays false and the warning prints rather than passing silently. The local `Continue` is scoped to the `& { }` block, so the outer `Stop` still governs the rest of launch. (iii) The message says to restrict before adding secrets. **Quickstart one-liner**: run verbatim under 5.1 and pwsh 7, it gives exit 0 and a DACL `PAI(A;;0x12019f;;;<sid>)`, and the user can still read and append. |
| **No secret in the icacls warning** | **Confirmed.** icacls reads and writes only the security descriptor, never file data. The warning interpolates icacls stdout and stderr (via `"$_"`) or, in the catch, only `$_.Exception.Message`. Nothing in the Windows branch reads `.env` content except `Copy-Item`. A canary secret (`KE_CANARY_SECRET=...`) in `.env.example` appeared 0 times in all 12 runs (2 copies, 2 shells, ok/fail/absent). At creation `.env` holds only the public placeholders anyway. launch.ps1 has no tracing or logging sink, so the warning goes only to the operator's console. |
| **L-L2d** | **Fixed.** Architecture §2.3 lists refusal 7 and the M-L2a warning, and its stated order "1, 2, 3, 4, 6, 5, 7" matches `check()` line by line. ADR-KE-010 points to it. Requirements PS-1.5 lists both, with test names. |
| **L-L2e** | **Fixed.** The install.ps1 `next:` line reads `Copy-Item .env.example .env; restrict .env to your account before adding secrets (see docs/quickstart.md, Offline bundle step 5); set real secrets in it; scripts/launch.ps1`. The order is right, and step 5 covers icacls on Windows and `chmod 600` elsewhere. The line prints only the install path. |

## Mutants (scratch copies)

| Mutant | Result |
|---|---|
| **ma** (L-L2a): drop `set -C` | **killed**: `LaunchEnvCreationStaticTest.test_launch_sh_creates_env_with_noclobber`. Probe: the mutant clobbers a racer's `.env` (and leaves it 0644 with placeholders), and it creates the target of a dangling link planted in the window (0600). |
| **mc** (L-L2c): grant `$($env:USERNAME):(F)` | **killed**: `LaunchEnvCreationStaticTest.test_launch_ps1_icacls_grants_current_user_sid`, both in the gates image and on the Windows host. |
| mg (extra): guard back to `! -f`, `set -C` kept | survives; equivalent in safety. `set -C` alone makes launch refuse a dangling link (rc=1, target not created), which the behavioural test accepts ("refuses or leaves alone"). |
| Control (unmutated) | gates image 29 OK; Windows host 8 OK (no skips) |

The secret-pattern grep over the added lines of the scoped diff and the three test files (AWS/GH/OpenAI/Slack tokens, private keys, credentialed URLs, secret assignments, S-1-5-21 SIDs, profile paths) found no matches.

## Findings

- **L-FUa (low, sensitive-data hygiene; route: developer/documenter before the next commit, human for history).** The local account and host name appear in this round's untracked `red-fu-windows-host.txt` (profile paths in tracebacks) and in the documenter's handoff line ("ACL shows only `<host>\<user>:(R,W)`", unredacted there). The same appears in already committed evidence: `audit-l2.md`/`audit-l2-probes.txt` (mine), `security-u2-r4*`/`-r5*`, `recorded-amd64.txt`, platform-stack(-ready) Windows proofs and several archived handoffs. No SID appears anywhere. These are not secrets, but they break the redaction rule. Redact the untracked and working files; the committed history is a human call before any push.
- I-FU1 (info): the race is proven only by this probe and the static `set -C` test. A behavioural race test (the `BASH_ENV` + `bash -T` DEBUG-trap racer in `audit-fu-probes.txt`) would pin it without a static regex (tester, optional).
- I-FU2 (info): on a non-shadowed host the Windows-host test cannot tell grant-by-name from grant-by-SID, so the static test is the only guard against mc. That is acceptable.
- I-FU3 (info): `KE_ENV_FILE` set to a dangling symlink now passes the guard (before: "KE_ENV_FILE does not exist") and fails later at compose `--env-file`. It still fails closed, with a less direct message.
- I-FU4 (info): the launch.ps1 off-Windows path needs pwsh >= 7.3 (.NET 7 `UnixCreateMode`). On older pwsh, setting the property should throw under `Stop` before the stream opens, so it should fail closed with no file (not run here). There is no `#Requires`.
- I-FU5 (info, pre-existing): the Windows branch is still check-then-create (`Test-Path`, then `Copy-Item` overwrites a file created in between). Exploiting this needs write access to the install directory, which the profile ACL limits to the user, SYSTEM and Administrators.
