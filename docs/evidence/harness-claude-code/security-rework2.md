# Security re-audit, rework 2: harness-claude-code (2026-10-18)

Scope: `git diff 886de45` plus untracked in-scope files (CLAUDE.md, .claude/, .dockerignore, docker/, tests/*, handoff doc,
docs/evidence/harness-claude-code/*). Excluded: docs/knowledge-engine-claude-code-prompt.md, .venv/.
Prior: security.md, security-rework1.md. Orchestrator-accepted bypasses (not findings): aliases, eval, variable indirection,
gh, update-ref, `checkout main && commit` (switch main; commit is the same class). Branch protection = Q18.

## Verdict: PASS (0 critical, 0 high)

## Fixes confirmed
- H1 FIXED. Same 55-case table as rework 1, fed Claude Code's real compact payload (session_id, transcript_path, cwd,
  permission_mode, hook_event_name, tool_name, tool_input{command, description, timeout}), piped in. Host (Git Bash, no jq,
  gawk 5.4.0) and gates image (jq 1.6, mawk) give IDENTICAL results (Table 1). Every case the rework 1 host run let through
  that is in spec 4b/4c is now denied: git as first word, target as last word, quoted args, HEAD:main, refs/heads/main, :main,
  --delete, --force/-f/--force-with-lease/+refspec, --all/--mirror, merge/cherry-pick/am/rebase/revert on main.
  Still not denied (accepted classes or out of spec): aliases, eval, `$g`, gh, update-ref, commit-tree|update-ref,
  `$(echo main)`, the `refs/heads/*:refs/heads/*` wildcard, checkout/switch main then commit, `git -C <other checkout>`, pull.
- L8 FIXED. Host, no jq, on main, 400 `true &&` segments then `git commit`: DENY in 0.19 s (was 12.3 s). Image: 0.02 s.
- Payload confusion: none reachable. The no-jq extractor takes the FIRST `"command"\s*:\s*"` in the raw JSON. Any field value
  (description, cwd, transcript_path) is JSON-escaped by Claude Code, so every double quote inside it is backslash-escaped and
  a `"command":` key cannot be forged; a description placed before command containing `"command":"ls"`, and a cwd containing
  an escaped key, both still yield the real command (DENY). The scan stops at the first unescaped double quote and unescapes
  quote, backslash, n, t, r correctly; CRLF, non-UTF-8 bytes and spaced JSON are handled.
- Fail-open paths: the hook never prints `allow` on any path (only the fixed deny JSON or nothing). The printf format is
  constant and the reason is one of three literals, so the output cannot be injected.
    - malformed JSON (truncated, missing brace): jq fails, awk fallback still extracts the command: DENY.
      Garbage, empty stdin, command missing / null / non-string: silent (normal permission flow).
    - awk fatal error: `set -e` propagates awk's exit 2; Claude Code treats exit 2 as a BLOCKING error (fails closed).
      awk missing: exit 127, non-blocking error, normal permission flow (not allow).
    - jq broken or absent: falls through to awk (pipefail plus `if !`), as designed.
    - timeout (10 s): non-blocking, normal permission flow. Reachable only with MB-scale commands (L9).

## Findings

### Critical / High
None.

### Medium (non-blocking)
- M1 (residual, narrowed) Shell forms the lexer does not see as a git command, beyond the accepted classes. Some are
  plausible by accident, not only by evasion (Table 2, all on main, all silent): `(git commit -m x)`, `{ git commit -m x; }`,
  `if ...; then git commit ...; fi`, `time git commit`, `command git`, `env git`, `! git`, `exec git`, `true & git commit`
  (single `&` is not a separator), `>/dev/null git commit` (leading redirection), `echo $(git commit)` and backticks,
  `xargs git commit`, and `bash -c "git commit -m x"` (the base hook denied this one; the new hook deliberately ignores quoted
  text, so it is a regression of the same class as eval).
  Recommend (developer, optional): treat `&`, `(`, `)`, `{`, `}` as separators; skip a leading `!`, redirections and the words
  then/do/else/elif/time/command/env/exec/nohup/xargs/sudo before judging; recurse into `$(...)`, backticks and
  `bash -c`/`sh -c` string arguments. Branch protection (Q18) remains the real control.

### Low (non-blocking)
- L9 (new) Hook cost is quadratic in command length (per-character string concatenation in both awk programs). Host, no jq:
  100 KB 0.25 s, 1 MB 3.2 s, 5 MB 109 s. Image (jq, mawk): 1 MB 4.3 s, 5 MB 138 s; image no-jq 1 MB 11.6 s. Past the 10 s
  timeout Claude Code proceeds with the normal permission flow, so a multi-MB command (for example a large heredoc file write)
  ending in `git commit` on main is prompted, not denied. Never an allow. Fix if cheap: accumulate tokens with substr() spans
  instead of per-char concatenation, or apply a size cap.
- L10 (new) Heredoc lexer confusion: `<<` inside arithmetic (`echo $((1<<2))`) or a partly quoted delimiter (`<<"E"OF`) is taken
  as a heredoc whose delimiter never appears, so every later line is skipped. `echo $((1<<2))` then newline `git commit -m x`
  on main, and the same before `git push origin main` on a branch, are silent. Crafted input only. Fix: ignore `<<` inside
  `$((`/`((`, and build the delimiter from the whole word with quotes removed.
- L11 (new, info) jq/no-jq divergence on JSON unicode escapes: awk turns backslash-u0067 + `it` into `u0067it` (silent); jq
  decodes it to `git` (DENY). Unreachable from Claude Code (JSON.stringify only unicode-escapes control characters).
- L12 (new, info) Unit tests run only in the gates image (mawk); the host's gawk path is covered by this probe and the
  developer's hook-live-host.txt. Results match.
- Still open, unchanged: L2 (gates container runs as root, repo bind-mounted rw), L5 (KE_IN_GATES=1 on the host skips the
  container), L7 (analyst/marketer web tools plus Bash).

## Secrets and local paths
Grep of `git diff 886de45` plus untracked in-scope files (1658 lines) and every file in docs/evidence/harness-claude-code/
(new since rework 1: green-rework1-later.txt, hook-probe-rework1.txt, review-rework1.md, analyst-req4.md, red-rework2.txt,
green-rework2.txt, hook-timing-host.txt, hook-live-host.txt, hook-probe-rework2.txt, review-rework2.md) for AWS/GitHub/Slack/
OpenAI/Anthropic/Google key shapes, private keys, user:pass@ URLs, key/secret/password/token assignments, Bearer tokens,
emails, Windows profile / AppData / home paths, the host username and the repo's absolute path: no secrets, no local paths.
Only hits: the public noreply co-author trailer inside a test-case string (hook-probe-rework2.txt:260) and security.md
describing its own search. Long hex strings are public image digests and local build manifest digests.
.claude/settings.json: hook only (timeout 10), no permissions/allow/defaultMode; no settings.local.json.

## Raw output
"allow-or-ask" = no output, exit 0 (normal permission flow). Payloads built with a compact-JSON generator and piped to the hook
in a scratch repo; no real commit or push was run. The git_AUTHOR_NAME row is a probe artifact.

### Table 1: host (no jq, gawk); identical to gates image (jq, mawk), diff empty
```
main     DENY          | git commit -m x
main     DENY          | git commit
main     DENY          | git push
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
agent/x  DENY          | git push --mirror
agent/x  DENY          | git push --all origin
agent/x  DENY          | git push origin ma\in
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

### Table 2: lexer edge cases, host (no jq). `~` = newline.
```
main     allow-or-ask  | (git commit -m x)
main     allow-or-ask  | { git commit -m x; }
main     allow-or-ask  | if true; then git commit -m x; fi
main     allow-or-ask  | time git commit -m x
main     allow-or-ask  | command git commit -m x
main     allow-or-ask  | env git commit -m x
main     allow-or-ask  | ! git commit -m x
main     allow-or-ask  | exec git commit -m x
main     allow-or-ask  | true & git commit -m x
main     allow-or-ask  | >/dev/null git commit -m x
main     allow-or-ask  | echo $(git commit -m x)
main     allow-or-ask  | echo `git commit -m x`
main     allow-or-ask  | xargs git commit -m x < /dev/null
main     DENY          | cd . && git commit -m x
main     DENY          | git --no-pager commit -m x
main     DENY          | git -P commit -m x
main     DENY          | git --git-dir=.git commit -m x
main     DENY          | git -C . -c user.name=a commit -m x
main     DENY          | git commit -m "$(cat <<'EOF'~msg~EOF~)"
main     DENY          | "git" commit -m x
main     DENY          | git.exe commit -m x
main     DENY          | git -c core.hooksPath=/dev/null commit -m x
main     allow-or-ask  | echo $((1<<2))~git commit -m x
main     DENY          | cat <<EOF~hi~EOF~git commit -m x
main     allow-or-ask  | cat <<'EOF' > f~git push origin main~EOF
agent/x  allow-or-ask  | git push origin $'main'
agent/x  DENY          | git push origin m"a"in
agent/x  allow-or-ask  | git push origin HEAD:MAIN
agent/x  DENY          | git push origin main:main
agent/x  allow-or-ask  | git push --force-if-includes origin agent/x
agent/x  DENY          | git push origin --force
agent/x  DENY          | git push -v -f
agent/x  DENY          | git push --repo=origin main
agent/x  DENY          | git push origin HEAD:refs/heads/master
agent/x  DENY          | git push origin refs/heads/agent/x:refs/heads/main
agent/x  allow-or-ask  | git push upstream main~0
agent/x  DENY          | git push origin @:main
agent/x  allow-or-ask  | echo $((1<<2))~git push origin main
agent/x  allow-or-ask  | git commit -m "push to main"
agent/x  allow-or-ask  | git commit -m "x" -m 'git push -f'
agent/x  allow-or-ask  | echo "git push origin main"
agent/x  allow-or-ask  | git log --oneline main
```

### Fail-open / payload confusion (host, no jq, branch main)
```
abs path git (/usr/bin/git commit)       -> DENY   rc=0
g''it commit -m x                        -> DENY   rc=0
malformed: truncated                     -> DENY   rc=0
malformed: no closing brace              -> DENY   rc=0
malformed: garbage                       -> silent rc=0
empty stdin                              -> silent rc=0
json without command                     -> silent rc=0
command not string / null                -> silent rc=0
spaced json                              -> DENY   rc=0
description before command, spoofed      -> DENY   rc=0
cwd with escaped command key             -> DENY   rc=0
non-utf8 bytes / CRLF                    -> DENY   rc=0
unicode-escaped g in git (no-jq)         -> silent rc=0   (with jq: DENY)
fake awk exiting 2                       -> rc=2   (Claude Code: blocking)
fake awk exiting 127                     -> rc=127 (non-blocking, permission flow)
```

### Timing (deny emitted in every case)
```
host, no jq, gawk:   400 segments 0.188s | 100KB 0.247s | 1MB 3.153s | 5MB 1m48.952s
image, jq, mawk:     400 segments 0.022s | 100KB 0.034s | 1MB 4.259s | 5MB 2m18.469s
image, no jq, mawk:  1MB 11.601s
hook timeout (.claude/settings.json): 10 s
```
