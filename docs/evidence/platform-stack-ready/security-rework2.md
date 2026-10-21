# Security re-audit, rework round 2 (L-15): platform-stack-ready

- Date: 2026-10-19. Scope: `scripts/lint.sh` (rework 2), read with the developer's rework-2 handoff section and `green-rework2.txt` (verify full PASS, exit 0).
- Method: scratch copy of `scripts/` + `docker/` (tar) in `ke-gates:latest`, `docker run --rm --network none`, no compose project, nothing in `ke-verify-*`. Each case is a fresh copy, then one mutation, then `bash scripts/lint.sh`.
- Raw output: `docs/evidence/platform-stack-ready/security-rework2-scan.txt` (39 cases plus the quote-name re-run).

**Verdict: PASS.** L-15 is closed. L-12 stays closed. No critical, high or medium findings.

## Results
- **Directory symlinks** (scripts/ and docker/, targets inside and outside the repo, nested `scripts/hooks/deep`): all refused with `symlink refused: <path>`, before the tools run.
- **File links**: a link to a clean script (`alias.sh -> build.sh`), an outside `.ps1`, non-script names (`scripts/README`, `docker/gateway/entry`), dangling links (`z.ps1`, extensionless `docker/zz`), a self-loop, and a deep `scripts/a/b/c/x`: all refused.
- **Root links**: `scripts` -> outside dir, `docker` -> outside dir, `docker` -> in-repo dir. All refused. `find` with the default `-P` reports the starting point itself as type `l`.
- **Case**: `u.SH`, docker `u.Sh`, `x.PS1`, `m.psm1`, nested `a/b/m.PSM1`: all linted and FAIL on the planted finding.
- **Filename injection** (`;`, `$(...)`, backtick, `'); ...; ('`, `"; ...; "`, leading `-`, spaces): all linted, with no code executed and no marker files created. `[ ] * ?` and newline in .ps1 names are refused. A .sh name with a newline fails closed.
- **Tracked tree**: `git ls-files -s` shows no mode-120000 entries, so the current tree has no symlinks.
- **Secret grep** on the lint.sh diff: no matches.

## Findings
- **Info — I-1: hardlinks are not refused. This is not a bypass.** A hardlink is a regular file (`-type f`). It is linted under its own name, and its bytes are exactly what runs. Hardlinked outside `.ps1`/`.sh` files are flagged (FAIL). Git does not record hardlinks: a clone or CI checkout gets an independent regular file. So a hardlink can only exist in a local working tree, made by someone who already has write access to it. Severity: info, no action.
- **Low — L-16 (existing scope, not a rework-2 regression): lint selects scripts by extension only.** An extensionless shebang script under `scripts/`, the same thing as a hardlink (`hardlink-outside-noext`), or a `.ps1` under `docker/` passes lint without being analyzed. Nothing tracked today is affected: all executables are `*.sh`, and there are no `.ps1` files under docker/. Possible hardening for a later item: shellcheck any file with a `#!` shell shebang or mode 755, and add docker/ to the PSScriptAnalyzer selection. Non-blocking.

## Still deferred (orchestrator ruling, unchanged)
- M-2 (RQ callbacks/webhooks bypass the allowlist) and L-14 (a malformed job stops the worker) belong to the M-1 network unit (ingest-ledger, Q39).
