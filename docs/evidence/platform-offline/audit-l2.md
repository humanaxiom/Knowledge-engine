# Audit: smoke-gate loop 2 (F9, F12a, F10, prod refusal until auth-audit), review and security, scoped

Date 2026-10-19. Auditor: security, covering review too as the orchestrator scoped it.
Scope: the working-tree `engine/startup.py` (sha256 `7efc37a7...8007c`), `scripts/launch.sh`
(`d0bee606...bfbe1`), `scripts/launch.ps1` (`f3d09a9a...6fb676`), the `next:` lines of
`scripts/install.sh` (staged; index == worktree, `04ab098e...e431e`) and `scripts/install.ps1`
(untracked, `5ad4b9d3...6f7cd`), `docs/quickstart.md` step 5 (`728168e9...05494`), and the six
engine tests the tester changed. Raw output (hashes, runner, mutant diffs, probes):
`audit-l2-probes.txt`. Scratch only: `...\scratchpad\final\l2\audit\`. HEAD, the index and tracked files were not touched.

## Verdict

**PASS / APPROVED.** There are no critical or high findings. One medium finding is pre-existing
and was not introduced by this diff; it needs a ruling. The low findings and info notes do not block.

## 1. engine/startup.py: prod refused until auth-audit

| Check | Result |
|---|---|
| Last in `check()` | **OK.** l.104-111, after the placeholder loop. Every other prod refusal still names its own setting (matrix probe: prod + auth off gives `authentication is disabled`; prod + 0.0.0.0 gives `KE_BIND_ADDRESS`). |
| Message | **Accurate.** `auth.enabled: KE_ENV=prod with auth.enabled=true (KE_AUTH__ENABLED): authentication is not implemented until auth-audit, so prod is refused until then`. It names no value and no secret. `startup()` records `ke.refused_setting=auth.enabled` on the span. |
| Shipped default refuses | **OK.** No `KE_ENV` means defaults.yaml `prod`, which is refused (probe). Matches ADR-KE-010, architecture l.3900. |
| Runtime paths do not need prod to start | **OK.** api/worker take `KE_ENV` from `.env`, and `.env.example` ships `dev`. `verify.sh full` runs on `KE_ENV_FILE=.env.example`, so dev, and green-l2 smoke PASS. CI runs only `verify.sh full`. gates-it sets no `KE_ENV`, but nothing in it runs `check()`: `test_stack_up` uses `ci`, `test_stack_ready` injects settings, and `integration/model.py` only builds `Settings()`. A grep of scripts/, docker/ and .github/ finds no `prod`. |
| Six changed tests aligned, not weakened | **OK.** `safe_defaults_pass` now asserts that prod's *only* refusal is the auth-audit one (`_check_passes`: setting + regex), and that `ci` starts. `real_secrets...accepted` and `prefix_only` (prod) use `_check_passes`: a real secret refused wrongly would name the secret and fail. In `bind_address...passes_everywhere` (prod), the refusal must not name `KE_BIND_ADDRESS` and must match auth...auth-audit. `accepts_local_collectors` and the egress accepted cases moved to `ci`: those rules do not depend on env (l.80-92), so nothing is lost. `is_traced`, `loads_settings_once` and telemetry `installs_exporter` need a passing startup, which prod can no longer give by design. The refusal tests per rule in prod are unchanged. M3 below proves they still test their own refusal. |

## 2. launch.sh / launch.ps1 private .env (F12a)

- **launch.sh `(umask 077; cat .env.example > .env)`.** open(O_CREAT) creates the file 0600 in one step, so it is never wider (probe: 0600 for umask 022/002/000/077 x example 0644/0777/0600, and contents identical). The umask applies only inside the subshell (the parent keeps 0022). An existing `.env` is kept, content and mode 0640 (probe; the `[ ! -f ]` guard). M4, which clobbers it, is killed by 17 tests. A `.env` that is a symlink to an existing file is not written. The construct is POSIX: it runs under dash, and it is bash-3.2 safe (no bashisms). Residues: L-L2a, I-1.
- **launch.ps1 off Windows.** It creates an empty file, then `SetUnixFileMode` 0600, then writes, so secrets are never written while the mode is wider (probe: 644/664 at size 0, then 600, then 600 at size 1574). Residue: L-L2b (an fd held open from the wide window still reads the content). An existing `.env` is kept. `Test-Path` is true on a dangling link, so nothing is written through it.
- **launch.ps1 on Windows (icacls best effort).** On this host (5.1 and 7.6) the result is `aria-alien1\adam:(F)` only, with inheritance removed. On failure (fake user) in pwsh 7.6: a warning, and the ACL is left inherited (SYSTEM, Administrators, user), so there is no lockout. **Judgement: a warning only is acceptable for this release.** The file holds only the public placeholders when it is created, an install under the profile already limits it to the user, SYSTEM and Administrators, and step 5 gives the manual command. Caveats: L-L2c.

## 3. Quickstart step 5 (F10/F12b) and install `next:` lines (F9)

Step 5 is accurate against the code. The `cp`, `chmod 600`, edit, launch order is right, and `cp` gives 0644 under umask 022. If skipped, launch.sh creates `.env` as dev with placeholders, now 0600. "Dev mode only" with loopback and real secrets is right. Prod: auth off is refused (`authentication is disabled`), auth on is refused (auth-audit), and the doc says the engine refuses prod. `.env.example` ships `KE_AUTH__ENABLED=false`. The icacls one-liner quoting is correct; the orchestrator verified it on this host. The install.sh `next:` line keeps `cd %q` and `bash scripts/launch.sh` (N6 is still enforced by the relaxed regex) and adds `cp` + `chmod 600` + secrets. install.ps1 adds `Copy-Item` + secrets, but no restriction (L-L2e).

## 4. Mutants (scratch copies, gates image, `--network none`, uid 10001, read-only)

| Mutant | Result |
|---|---|
| M1: remove the prod refusal | **killed**, 29 failures: `test_startup_refuses_prod_until_auth_audit` (3 subtests), `safe_defaults_pass`, `real_secrets...` (14), `prefix_only` (6), `bind_address...passes_everywhere` prod (5) |
| M2: launch.sh plain `cp .env.example .env` | **killed**: `LaunchShResolvedTest.test_launch_creates_env_private_whatever_the_umask` (umask 022 and 002) |
| M3 (extra): move the refusal to the top of `check()` | **killed**, 81 failures: the per-rule refusal tests in prod (hide flags, collectors, placeholders incl. invisible chars, bind, egress, span record) |
| M4 (extra): launch.sh rewrites an existing `.env` | **killed**, 17 failures |
| Control (unmutated) | engine 4 modules 59 OK; test_stack_scripts + QuickstartOfflineTest + next-line sh/ps1 103 OK |

The secret-pattern grep over the in-scope diff (AWS/GH/OpenAI keys, private keys, credentialed URLs, key=value secrets) found no matches beyond the `changeme-` placeholders and the named test fixtures.

## Findings

- **M-L2a (medium, non-blocking, PRE-EXISTING; route: architect/orchestrator ruling).** `auth.enabled=true` is accepted without comment in `dev` and `ci`. In dev it *removes* the only "authentication is disabled" warning, and dev allows a non-loopback bind with only a warning. So `KE_ENV=dev KE_AUTH__ENABLED=true KE_BIND_ADDRESS=0.0.0.0` publishes an unauthenticated API while the operator believes auth is on (matrix probe). The ruling's own reason for refusing prod ("`true` would claim a protection the API lacks") applies here as well. Suggested fix: when `auth.enabled=true` outside prod, log a warning that it has no effect until auth-audit. Refusing it in `ci` would break the ci path, which needs auth=true. Step 5's "leave it so for now" mitigates this.
- **L-L2a (low, security).** The launch.sh redirect follows a dangling `.env` symlink and creates the link target (0600, placeholders); GNU `cp` refused that case. The check-then-create also truncates a `.env` that a concurrent process created. Only someone who can already write the install dir can exploit either. Fix: add `set -C` inside the subshell (`umask 077; set -C; cat .env.example > .env`). noclobber opens with O_EXCL, which closes both.
- **L-L2b (low, security).** launch.ps1 off Windows: a local reader that opens `.env` while it is still the empty 0644/0664 file keeps an fd that reads everything written later (probe: 1574 bytes). That includes real secrets if an editor later writes in place. Fix: create with the mode at open: `FileStreamOptions` with Mode CreateNew, Access Write, UnixCreateMode UserRead|UserWrite (.NET 7+). CreateNew also refuses links and clobbering.
- **L-L2c (low, security).** launch.ps1 Windows branch: (i) under Windows PowerShell 5.1 (the code-first `scripts\launch.ps1` has no `#Requires`), an icacls failure with `2>&1` under `ErrorActionPreference=Stop` *terminates* with NativeCommandError instead of warning (probe). `.env` is left with the inherited ACL, and the next run skips creation without a message. (ii) `USERNAME` is resolved by name, and a same-named local account can shadow the domain user. Grant by SID instead: `*<sid>` with the sid from `[Security.Principal.WindowsIdentity]::GetCurrent().User.Value`. The same applies to the quickstart one-liner. (iii) The warning should say to restrict `.env` before adding secrets.
- **L-L2d (low, review/docs; route: architect/documenter).** Architecture §2.3 "Startup refusals (PS-1.5)" (l.773-787) and requirements PS-1.5 do not list the new seventh refusal (env=prod refused until auth-audit, checked last, `test_startup_refuses_prod_until_auth_audit`). Only the ADR-KE-010 consequence at l.3900 says it.
- **L-L2e (low, review).** The install.ps1 `next:` line names `Copy-Item` but no restriction step (icacls on Windows, `chmod 600` off Windows), unlike install.sh. Step 5 covers it.
- I-1 (info): if `.env.example` is missing, launch.sh now leaves an empty 0600 `.env` (`cp` left none). The next run fails closed on an empty KE_ENV.
- I-2 (info, nit): quickstart icacls grants `(R,W)`, launch.ps1 grants `(F)`.
- I-3 (info): prod with auth off says "authentication is disabled (env=prod)". An operator who then enables auth meets the auth-audit refusal. Step 5 explains this.
