# Security audit: harness-claude-code (2026-10-18)

Scope: `git diff 886de45` plus untracked CLAUDE.md, .claude/, docker/, tests/test_block_main_commit_hook.py,
tests/test_harness_port.py, docs/handoffs/harness-claude-code.md, docs/evidence/harness-claude-code/*.
Excluded: docs/knowledge-engine-claude-code-prompt.md, .venv/.

## Verdict: PASS (no critical/high findings)

## Findings

### Medium (non-blocking)
- M1 Hook bypasses (scripts/hooks/block-main-commit.sh). The check is "current branch is main/master AND command matches
  `git[^&|;]*(commit|push)`". Not denied (probe table below):
  - From a plan-item branch: `git push origin HEAD:main`, `git push --force origin main`, `git checkout main && git commit`,
    `git update-ref refs/heads/main HEAD`, `git -C <other main checkout> commit`.
  - On main: `git merge|cherry-pick|am` (create commits), user git aliases (`git ci`), `gh pr merge`, `gh api ... refs/heads/main`,
    indirection (`g=git; $g commit`, `eval "$(... | base64 -d)"`).
  The hook is a guard rail against agent mistakes, NOT a security boundary; any string-match hook on a shell command is
  bypassable by construction. The realistic gap is the push-refspec case (an agent on agent/* pushing to main), which matches
  the doc claim "denies any commit/push attempted while on main" literally but not its intent. Real controls: GitHub branch
  protection on main (not verified from here; recommend enabling it) and Claude Code's normal permission prompt (no allow
  rules are configured). Fix suggestion: also deny any `push` whose args name main/master (or `--force`/`+` refspec) regardless
  of current branch, and add merge/cherry-pick/am/rebase/revert to the on-main pattern; add tests for each.
- M2 Gate image base images pinned by tag, not digest (docker/gates.Dockerfile): `python:3.12-slim-bookworm` is a floating tag,
  `ghcr.io/astral-sh/uv:0.11.21` is a mutable version tag; `apt-get install git` unpinned. The image runs every gate locally and
  in CI. Pin both FROMs by `@sha256:` (digests already appear in green-full.txt build output). Python deps are fine: `uv sync --locked`
  is hash-verified from uv.lock.

### Low (non-blocking)
- L1 CI: `actions/checkout@v4` pinned by tag, not commit SHA (first-party action; acceptable, SHA pinning preferred).
  Positive: `permissions: contents: read` at workflow level; the third-party `astral-sh/setup-uv` action was removed.
- L2 Gate container runs as root with the repo bind-mounted read-write (`.:/work`). On Linux hosts/CI any file written by the
  gates is root-owned, and test code can modify the working tree. Consider `user:` in compose or a non-root USER.
- L3 `git config --system --add safe.directory '*'`: acceptable in a single-repo, network-less container; narrowing to `/work` is tidier.
- L4 No `.dockerignore`: build context `.` sends .git, .venv and any future .env to the daemon. Not copied into image layers
  (only explicit COPY), but add a .dockerignore before secrets files ever exist in the tree.
- L5 `KE_IN_GATES=1` set on the host makes verify.sh skip the container (and the no-network guarantee). Gate-integrity, not
  exploitable; CI never sets it. Worth a comment or a check (e.g. test for /.dockerenv).
- L6 Raw-stdin fallback: jq is absent in Git Bash on this machine (confirmed), so the hook scans the whole JSON payload
  (cwd, transcript_path, description). Produces false-positive denies on main (e.g. `echo digital push-ups` denied). Fails in the
  safe direction. If the hook itself errors (exit not 0/2), Claude Code fails open; acceptable for a guard rail.
- L7 analyst and marketer have WebFetch/WebSearch together with Bash/Write/Edit: prompt-injection exposure from untrusted web
  content. Same as the Copilot definitions (`web` + `execute`), mitigated by permission prompts. Informational.

## Checks that passed
- Silent default is safe: no output + exit 0 defers to the normal permission flow (the old `"allow"` would have auto-approved
  every Bash call). Covered by tests/test_block_main_commit_hook.py (test_silent_*).
- No command injection: payload only flows through `printf '%s'`, jq and `grep -Eq`; never eval'd or expanded as code.
  `$CLAUDE_PROJECT_DIR` is double-quoted in .claude/settings.json and comes from the user's own project path.
- .claude/settings.json contains only the PreToolUse hook: no `permissions.allow`, no `defaultMode`, no `additionalDirectories`;
  no settings.local.json present.
- verify.sh: `$mode` validated by a case allow-list before use; no other user input.
- `network_mode: none` IS applied by `docker compose run` (resolved config shows it; runtime probe below). Only the image BUILD
  has network (needed for apt/uv sync).
- Secrets: grep of the diff + all untracked in-scope files for API keys, tokens, AWS/GitHub/Slack/OpenAI key shapes, private keys,
  connection strings (postgres/mongodb/redis/neo4j/bolt/amqp/user:pass@), local usernames, C:\Users / AppData paths, emails:
  no hits. Only long hex strings are public image digests in build logs.
- Tracing: HARNESS_TRACING=off in the gate image; no new span attributes or retriever queries in this change.

## Raw output

### Runtime network probe (`docker compose --profile gates run --rm gates sh -c ...`)
interfaces: lo only
uid: 0
python socket.create_connection(("1.1.1.1",53)): OSError: [Errno 101] Network is unreachable

### Resolved compose config (gates service)
    network_mode: none
    volumes: bind <repo> -> /work
    working_dir: /work

### Hook probe (scratch repo, realistic PreToolUse JSON payload, jq absent => raw fallback)
```
jq present: no
main     DENY         | git commit -m x
main     DENY         | GIT_AUTHOR_NAME=a git commit -m x
main     DENY         | bash -c "git commit -m x"
main     DENY         | git status~git commit -m x
main     allow-or-ask | git ci -m x
main     DENY         | git -c alias.c=commit c -m x
main     allow-or-ask | gh pr merge 1 --merge
main     allow-or-ask | gh api repos/o/r/git/refs/heads/main -X PATCH
main     allow-or-ask | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"
main     allow-or-ask | g=git; $g commit -m x
main     DENY         | git log --grep=push
main     DENY         | git commit-tree HEAD^{tree} | xargs git update-ref refs/heads/main
main     allow-or-ask | git merge feature
main     allow-or-ask | git cherry-pick abc
main     allow-or-ask | git am p.patch
main     DENY         | python -c "import subprocess;subprocess.run([\"git\",\"commit\"])"
main     DENY         | echo digital push-ups
agent/x  allow-or-ask | git push origin HEAD:main
agent/x  allow-or-ask | git push origin agent/x:main
agent/x  allow-or-ask | git checkout main && git commit -m x
agent/x  allow-or-ask | git switch main; git commit -m x
agent/x  allow-or-ask | git -C ../other-main-checkout commit -m x
agent/x  allow-or-ask | git update-ref refs/heads/main HEAD
agent/x  allow-or-ask | git push --force origin main
```
