# Security re-audit, rework 1: harness-claude-code (2026-10-18)

Scope: `git diff 886de45` plus untracked in-scope files (CLAUDE.md, .claude/, .dockerignore, docker/, tests/*, handoff doc,
docs/evidence/harness-claude-code/*). Excluded: docs/knowledge-engine-claude-code-prompt.md, .venv/.
Prior audit: docs/evidence/harness-claude-code/security.md.

## Verdict: FAIL (1 high)

## Findings

### High (merge-blocking)
- H1 Rewritten hook denies (almost) nothing on the host it actually runs on: a regression from the base hook.
  scripts/hooks/block-main-commit.sh runs on the developer host (Git Bash), where jq is ABSENT (`command -v jq` fails), so it
  takes the raw-stdin fallback. Claude Code sends compact JSON (`"command":"git commit -m x","description":"..."`). After the
  `tr -d` of double quotes, single quotes and braces, the segment reads `...command:git commit -m x,description:...`, so:
  1. the `(^|[[:space:]])git[[:space:]]` test never matches when git is the first word (preceded by `:`), so nothing is judged;
  2. the last argument is followed by `,` not space/EOL, so `push` / `main` / `-f` at the end of a command never match;
  3. quoted args become `\main\` in the JSON text, so they never match either.
  The base hook (886de45) denied `git commit -m x` on main in this configuration; the new hook does not (side-by-side, table 1).
  Confirmed LIVE in this session through the real Claude Code payload (branch agent/harness-claude-code, harmless read-only
  `git rev-parse` probes):
    - `git -C <repo> rev-parse --quiet push origin main && echo done` -> NOT denied (git is the first word)
    - `echo start && git rev-parse --quiet push origin main` -> NOT denied (main is the last word)
    - `echo start && git rev-parse --quiet push origin main && echo end` -> denied (control)
  So on this host: on main, `git commit -m "x"`, `git push`, `git merge x` are not denied; from a plan-item branch,
  `git push origin main`, `HEAD:main` and `--force` pushes are not denied. The documented branch-policy control (AGENTS.md Branch
  Policy, CLAUDE.md) is silently inactive. Inside the gates image (jq present) the hook works (table 3), which is why the tests
  are green: they run only in the gates image, with a minimal payload lacking `description`, so the raw fallback that the host
  uses has no realistic coverage. Severity High: OWASP A01, regression of an access-control guard rail the docs rely on,
  masked by the tests. Remaining mitigations: Claude Code permission prompts (no allow rules configured); remote branch
  protection (unverified).
  Fix (developer): make the no-jq path extract the `command` field properly (a JSON-string regex plus unescape, or
  `python3 -c json` when present), or fail CLOSED when jq is absent and the payload looks like a git commit/push/merge/rebase,
  or require jq on the host and deny with a clear "install jq" reason. Add tests that feed the REAL compact payload shape
  (session_id, cwd, tool_input.command + description) with git as the first word and the target as the last word, and that
  force the raw path (PATH without jq) so the image having jq cannot hide it.

### Medium (non-blocking)
- M1 (residual, jq path) Remaining bypasses even with jq, expected for a regex guard rail: `git push --all` / `--mirror`
  (push local main), `git checkout main && git commit`, `git switch main; git commit`, `git -C <other main checkout> commit`,
  `git update-ref refs/heads/main`, aliases (`git ci`, `-c alias.x=commit`), `gh pr merge`, `gh api .../refs/heads/main`,
  command substitution / backslash-split names / eval / variable indirection, `git pull` on main (merge commit).
  Fixed vs the prior table (with jq): push to main via HEAD:main, src:main, refs/heads/main, :main, --delete, quoted names;
  --force / -f / --force-with-lease / +refspec from any branch; merge/cherry-pick/am/rebase/revert on main.
  Accept as a guard rail; recommend adding --all/--mirror and enabling branch protection on main.

### Low (non-blocking)
- L8 (new) Hook cost is one subshell pipeline per segment: a 400-segment command took 12.3 s on the host, over the 10 s hook
  timeout. A timed-out hook is a non-blocking error, so Claude Code falls back to the normal permission flow (not auto-allow).
- Still open from the prior audit, unchanged: L2 (gates container runs as root, repo bind-mounted rw), L5 (KE_IN_GATES=1 on the
  host skips the container), L7 (analyst/marketer web tools plus Bash). L6 is superseded by H1.

## Fixes confirmed
- M2 FIXED. Both FROMs pinned by digest. `docker buildx imagetools inspect` against the registries today:
  python:3.12-slim-bookworm -> sha256:34386ef0...a07258 (OCI index, multi-arch); ghcr.io/astral-sh/uv:0.11.21 ->
  sha256:ff07b86a...369946 (OCI index). Both equal the pins and the digests the earlier tag-only builds resolved
  (green-fast.txt, green-full.txt, gate-offline-stale-cache.txt); green-rework1.txt shows the pinned refs resolving. Pinning the
  index digest (not a per-platform manifest) is correct. apt packages (git, jq) stay unpinned: acceptable (Debian-signed).
- L1 FIXED. `gh api repos/actions/checkout/git/ref/tags/v4` and `.../tags/v4.4.0` both point at commit
  11d5960a326750d5838078e36cf38b85af677262 ("backport fixes to releases-v4 (#2524)", 2026-07-16), the SHA in ci.yml.
  Workflow keeps `permissions: contents: read`.
- L3 FIXED. `safe.directory /work` instead of `*`.
- L4 FIXED. .dockerignore excludes .git, .venv, __pycache__, docs/evidence, .env*, .claude; the Dockerfile COPYs only
  pyproject.toml, uv.lock and harness_telemetry.
- UV_OFFLINE=1 effective. Image ENV set after `uv sync --locked`; nothing overrides it (grep for UV_OFFLINE, --refresh,
  index-url over scripts, docker, compose, pyproject, .github: only the Dockerfile). In the image, `uv run --with six` fails with
  "network was disabled". uv applies UV_OFFLINE to all subcommands; only an explicit UV_OFFLINE=0 re-enables it, and then
  `network_mode: none` still stops it (dns error, verified). UV_PYTHON_DOWNLOADS=never also set. UV_OFFLINE is the
  reliability fix; the no-network guarantee is still network_mode: none.

## New-risk checks on the rewritten hook
- Command injection: none. Payload flows only through `printf %s`, jq, tr, sed, `read -r` and `[[ =~ ]]` as data; never
  evaluated, sourced, or expanded unquoted as a command. `git branch --show-current` output is only compared.
- printf of the reason: the format string is constant and `$reason` is one of three fixed literals (no payload data, no
  double quote or backslash), so the emitted JSON cannot be injected or malformed.
- Silent default kept (no "allow"), so the hook never auto-approves.
- Fail-open modes: hook error/timeout -> normal permission flow (L8); jq absent -> H1.

## Secrets and local paths
Grep of `git diff 886de45` plus all untracked in-scope files (3557 lines, including the new evidence files red-rework1.txt,
green-rework1*.txt, offline-*.txt, gate-offline-stale-cache.txt, mutation-*.txt) for AWS/GitHub/Slack/OpenAI/Anthropic/Google
key shapes, private keys, connection strings, user:pass@, key/secret/password/token assignments, Bearer tokens, emails,
Windows user-profile / home paths, usernames, hostnames: no hits (only the prior security.md describing its own search).
Long hex strings are public image digests and the public checkout SHA. .claude/settings.json: hook only, no
permissions/allow/defaultMode; no settings.local.json.

## Raw output
Probe: scratch repo, payload shaped like the Claude Code one {session_id, transcript_path, cwd, permission_mode,
hook_event_name, tool_name, tool_input{command, description, timeout}}. "allow-or-ask" = no output, exit 0 (normal
permission flow). The git_AUTHOR_NAME row is a probe artifact (placeholder substitution); ignore it.

### Table 1: host (Git Bash, no jq), compact JSON as Claude Code sends; right column = base 886de45 hook
```
main     allow-or-ask  | git commit -m x   || base: DENY         
main     allow-or-ask  | git commit   || base: DENY         
main     allow-or-ask  | git push   || base: DENY         
main     allow-or-ask  | git commit -m "x"   || base: DENY         
main     DENY          | git_AUTHOR_NAME=a git commit -m x   || base: DENY         
main     allow-or-ask  | bash -c "git commit -m x"   || base: DENY         
main     allow-or-ask  | git ci -m x   || base: allow-or-ask 
main     allow-or-ask  | git -c alias.c=commit c -m x   || base: DENY         
main     allow-or-ask  | gh pr merge 1 --merge   || base: allow-or-ask 
main     allow-or-ask  | gh api repos/o/r/git/refs/heads/main -X PATCH   || base: allow-or-ask 
main     allow-or-ask  | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"   || base: allow-or-ask 
main     allow-or-ask  | g=git; $g commit -m x   || base: allow-or-ask 
main     allow-or-ask  | git merge feature   || base: allow-or-ask 
main     allow-or-ask  | git merge   || base: allow-or-ask 
main     allow-or-ask  | git cherry-pick abc   || base: allow-or-ask 
main     allow-or-ask  | git am p.patch   || base: allow-or-ask 
main     allow-or-ask  | git rebase x   || base: allow-or-ask 
main     allow-or-ask  | git revert abc   || base: allow-or-ask 
main     allow-or-ask  | git pull   || base: allow-or-ask 
main     allow-or-ask  | git pull origin main   || base: allow-or-ask 
main     allow-or-ask  | git reset --hard x   || base: allow-or-ask 
main     allow-or-ask  | git commit-tree HEAD^{tree} | xargs git update-ref refs/heads/main   || base: DENY         
main     allow-or-ask  | echo digital push-ups   || base: DENY         
main     allow-or-ask  | git log --grep=push   || base: DENY         
main     allow-or-ask  | git status   || base: allow-or-ask 
main     allow-or-ask  | ls -la   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin HEAD:main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin agent/x:main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin "HEAD:main"   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin "main"   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin 'main'   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin HEAD:refs/heads/main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin :main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push --delete origin main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push --force origin main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push --force origin agent/x   || base: allow-or-ask 
agent/x  allow-or-ask  | git push -f   || base: allow-or-ask 
agent/x  allow-or-ask  | git push --force-with-lease   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin +agent/x   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin +HEAD:main   || base: allow-or-ask 
agent/x  allow-or-ask  | git push --mirror   || base: allow-or-ask 
agent/x  allow-or-ask  | git push --all origin   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin ma\in   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin $(echo main)   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin refs/heads/*:refs/heads/*   || base: allow-or-ask 
agent/x  allow-or-ask  | git checkout main && git commit -m x   || base: allow-or-ask 
agent/x  allow-or-ask  | git switch main; git commit -m x   || base: allow-or-ask 
agent/x  allow-or-ask  | git -C ../other-main-checkout commit -m x   || base: allow-or-ask 
agent/x  allow-or-ask  | git update-ref refs/heads/main HEAD   || base: allow-or-ask 
agent/x  allow-or-ask  | git push origin agent/x   || base: allow-or-ask 
agent/x  allow-or-ask  | git push -u origin agent/x   || base: allow-or-ask 
agent/x  allow-or-ask  | git push   || base: allow-or-ask 
```

### Table 2: host (no jq), JSON with spaced separators
```
main     DENY          | git commit -m x
main     allow-or-ask  | git commit
main     allow-or-ask  | git push
main     DENY          | git commit -m "x"
main     DENY          | git_AUTHOR_NAME=a git commit -m x
main     allow-or-ask  | bash -c "git commit -m x"
main     allow-or-ask  | git ci -m x
main     allow-or-ask  | git -c alias.c=commit c -m x
main     allow-or-ask  | gh pr merge 1 --merge
main     allow-or-ask  | gh api repos/o/r/git/refs/heads/main -X PATCH
main     allow-or-ask  | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"
main     allow-or-ask  | g=git; $g commit -m x
main     DENY          | git merge feature
main     allow-or-ask  | git merge
main     DENY          | git cherry-pick abc
main     DENY          | git am p.patch
main     DENY          | git rebase x
main     DENY          | git revert abc
main     allow-or-ask  | git pull
main     allow-or-ask  | git pull origin main
main     allow-or-ask  | git reset --hard x
main     allow-or-ask  | git commit-tree HEAD^{tree} | xargs git update-ref refs/heads/main
main     allow-or-ask  | echo digital push-ups
main     allow-or-ask  | git log --grep=push
main     allow-or-ask  | git status
main     allow-or-ask  | ls -la
agent/x  allow-or-ask  | git push origin HEAD:main
agent/x  allow-or-ask  | git push origin agent/x:main
agent/x  allow-or-ask  | git push origin "HEAD:main"
agent/x  allow-or-ask  | git push origin "main"
agent/x  allow-or-ask  | git push origin 'main'
agent/x  allow-or-ask  | git push origin main
agent/x  allow-or-ask  | git push origin HEAD:refs/heads/main
agent/x  allow-or-ask  | git push origin :main
agent/x  allow-or-ask  | git push --delete origin main
agent/x  DENY          | git push --force origin main
agent/x  DENY          | git push --force origin agent/x
agent/x  allow-or-ask  | git push -f
agent/x  DENY          | git push --force-with-lease
agent/x  DENY          | git push origin +agent/x
agent/x  DENY          | git push origin +HEAD:main
agent/x  allow-or-ask  | git push --mirror
agent/x  allow-or-ask  | git push --all origin
agent/x  allow-or-ask  | git push origin ma\in
agent/x  allow-or-ask  | git push origin $(echo main)
agent/x  allow-or-ask  | git push origin refs/heads/*:refs/heads/*
agent/x  allow-or-ask  | git checkout main && git commit -m x
agent/x  allow-or-ask  | git switch main; git commit -m x
agent/x  allow-or-ask  | git -C ../other-main-checkout commit -m x
agent/x  allow-or-ask  | git update-ref refs/heads/main HEAD
agent/x  allow-or-ask  | git push origin agent/x
agent/x  allow-or-ask  | git push -u origin agent/x
agent/x  allow-or-ask  | git push
```

### Table 3: gates image (jq present), compact JSON
```
main     DENY          | git commit -m x
main     DENY          | git commit
main     DENY          | git push
main     DENY          | git commit -m "x"
main     DENY          | git_AUTHOR_NAME=a git commit -m x
main     DENY          | bash -c "git commit -m x"
main     allow-or-ask  | git ci -m x
main     allow-or-ask  | git -c alias.c=commit c -m x
main     allow-or-ask  | gh pr merge 1 --merge
main     allow-or-ask  | gh api repos/o/r/git/refs/heads/main -X PATCH
main     allow-or-ask  | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"
main     allow-or-ask  | g=git; $g commit -m x
main     DENY          | git merge feature
main     DENY          | git merge
main     DENY          | git cherry-pick abc
main     DENY          | git am p.patch
main     DENY          | git rebase x
main     DENY          | git revert abc
main     allow-or-ask  | git pull
main     allow-or-ask  | git pull origin main
main     allow-or-ask  | git reset --hard x
main     allow-or-ask  | git commit-tree HEAD^{tree} | xargs git update-ref refs/heads/main
main     allow-or-ask  | echo digital push-ups
main     allow-or-ask  | git log --grep=push
main     allow-or-ask  | git status
main     allow-or-ask  | ls -la
agent/x  DENY          | git push origin HEAD:main
agent/x  DENY          | git push origin agent/x:main
agent/x  DENY          | git push origin "HEAD:main"
agent/x  DENY          | git push origin "main"
agent/x  DENY          | git push origin 'main'
agent/x  DENY          | git push origin main
agent/x  DENY          | git push origin HEAD:refs/heads/main
agent/x  DENY          | git push origin :main
agent/x  DENY          | git push --delete origin main
agent/x  DENY          | git push --force origin main
agent/x  DENY          | git push --force origin agent/x
agent/x  DENY          | git push -f
agent/x  DENY          | git push --force-with-lease
agent/x  DENY          | git push origin +agent/x
agent/x  DENY          | git push origin +HEAD:main
agent/x  allow-or-ask  | git push --mirror
agent/x  allow-or-ask  | git push --all origin
agent/x  allow-or-ask  | git push origin ma\in
agent/x  allow-or-ask  | git push origin $(echo main)
agent/x  allow-or-ask  | git push origin refs/heads/*:refs/heads/*
agent/x  allow-or-ask  | git checkout main && git commit -m x
agent/x  allow-or-ask  | git switch main; git commit -m x
agent/x  allow-or-ask  | git -C ../other-main-checkout commit -m x
agent/x  allow-or-ask  | git update-ref refs/heads/main HEAD
agent/x  allow-or-ask  | git push origin agent/x
agent/x  allow-or-ask  | git push -u origin agent/x
agent/x  allow-or-ask  | git push
```

### Hook timing (host, no jq): 400 true-segments then a commit, on main
```
deny emitted; real 0m12.345s user 0m5.523s sys 0m6.476s (hook timeout in .claude/settings.json: 10 s)
```

### UV_OFFLINE probe (gates image, --network none)
```
env: UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv KE_IN_GATES=1 HARNESS_TRACING=off; uv 0.11.21
uv run --no-sync --with six python ...              -> hint: Packages were unavailable because the network was disabled.
UV_OFFLINE=0 uv run --no-sync --with six python ... -> Caused by: dns error / failed to lookup address information
```
