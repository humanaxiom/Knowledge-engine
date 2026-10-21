# Security re-audit, rework 3: harness-claude-code (2026-10-18)

Scope: `git diff 886de45` plus untracked in-scope files (excluded: docs/knowledge-engine-claude-code-prompt.md, .venv/).
Only production change since rework 2: scripts/hooks/block-main-commit.sh (plus tests and evidence).
Judged against requirements.md criterion 4 (round-3 ruling: 4a precise off main, 4c broad on main, 4d accepted bypasses
off main: `"$(...)"`, bash -c, sh -c, xargs, aliases, eval, variable indirection, gh, update-ref, checkout main && commit).

## Verdict: FAIL (1 high)

## Method
Payloads only, piped to the hook in scratch repos (branch set with `git symbolic-ref`), never a real commit/push.
Compact Claude Code payload (session_id, transcript_path, cwd, permission_mode, hook_event_name, tool_name,
tool_input{command, description, timeout}), built by a JSON generator. Three modes: host Git Bash no jq (GNU Awk 5.4.0,
the environment 4e targets), gates image with jq 1.6 + mawk 1.3.4, gates image with jq replaced by a stub that exits 127.
187-row table = rework 1 + rework 2 tables + 86 new rows. Backslash cases built from character codes (a JSON generator
with chr(92)/chr(10)) so no shell layer can alter the backslash count.

## Fixed / confirmed since rework 2
- M1 (nested forms) fixed in all three modes: `( )`, `{ ;}`, if/while/until, `&`, leading redirection, `$( )`, backticks,
  `!`, time/command/env/exec, VAR= prefixes, case/function/for bodies. On main every Table-2 shape is denied (broad rule).
- L10 `$((1<<2))` then newline then a push/commit: DENY on and off main.
- On main the broad 4c rule denies bash -c, sh -c, xargs, `"$(...)"`, heredoc bodies, nohup/timeout prefixes.
- Never `allow`: 561 probe rows + 15 malformed-payload rows: output is the fixed deny JSON or nothing, rc=0 everywhere.
  Malformed but clearly-a-commit payloads (truncated, missing brace, raw text, top-level array, toolInput) are DENY.
- 4c on main is fast at any size (5 MB: 1.58 s host, 0.34 s image).

## Findings

### High (merge-blocking)
- H2 (new, regression) On the Windows host (gawk, no jq) the no-jq extractor doubles every backslash in the command.
  The step that restores an escaped backslash uses gsub() with a backslash replacement string; gawk 5.4 and mawk read that
  replacement differently (gawk emits two backslashes, mawk one). Measured on the host: a JSON-escaped single backslash
  is extracted as two backslashes; JSON backslash + newline-escape becomes two backslashes + newline. The judge lexer then
  sees an escaped backslash instead of an escape, so off main (Table B):
    - line continuation: `git push`, backslash, newline, `origin main`: silent (image: DENY)
    - `git push`, backslash, newline, `-f`: silent (image: DENY)
    - an escaped double quote inside a quoted message, then a push (`git commit -m "a<bs>"b"; git push origin main`,
      `<bs>` = one backslash): silent (image: DENY). The lexer ends the string at the escaped quote and swallows the push
      into a new string.
    - `git push origin ma<bs>in`: silent (rework 2 host: DENY; image: DENY)
  These are 4a/4b denials that fail open on exactly the host 4e names, in forms Claude writes by accident (multi-line
  commands with backslash continuations, quoted messages with escaped quotes). No accepted 4d class covers them. On main
  the broad rule still denies. The gates cannot see it: the image has only mawk, so
  test_escaped_quote_does_not_hide_following_push passes there.
  Fix (developer): restore the backslash without a gsub replacement string (split on the placeholder byte and join with a
  one-backslash string by concatenation), or unescape in one left-to-right pass. Add gawk to the gates image and run the
  hook tests under both awks, so the host's awk is covered.

### Medium (non-blocking)
- M3 (L9 residual; criterion 4f not met) Linear only for short tokens. mawk (gates image) still builds tokens one
  character at a time (add(), and the heredoc line buffer in skip_heredocs). 1 MB as a single word, single-quoted string,
  double-quoted string or one heredoc line: 7.7-8.1 s in the image, jq or not (4f: under 3 s). 5 MB single word: killed
  at 300 s. Host gawk is fine for long tokens (under 0.9 s) but a heredoc of many short lines is quadratic: 1 MB 5.1 s,
  2 MB 19.5 s, 4 MB 74.3 s. Past the 10 s hook timeout Claude Code falls back to the normal permission flow, never
  allow, and only off main (on main the broad regex returns first). The unit test covers only `echo x && ` segments.
  Fix: take a token as a substr() span (start, length) instead of per-character concatenation; same for the heredoc
  line (index() for the next newline). Add 1 MB single-token and 1 MB many-line-heredoc cases to the timing test.
- M1 (residual, narrowed) Off main, leading command words outside the 4a list still hide a push to main:
  `timeout 60 git push origin main`, nohup, nice, sudo, `env -i`, `command -p`, `time -p`, and
  `git --config-env x=Y push origin main` (an option with a separate argument). Uppercase `GIT push origin main` runs
  git on the Windows host (case-insensitive file system; `GIT --version` verified) and is silent. Not in 4d; 4a's word
  list is explicit, so this is a spec gap rather than a violation. Branch protection (Q18) remains the control.

### Low (non-blocking)
- L10 (residual) Off main only; all denied on main by the broad rule. Following lines are hidden after
  `((x=1<<2))` (arithmetic command, not `$((`), `$[1<<2]`, partly quoted delimiters `<<"E"OF` and `<<E"OF"`,
  `<<` + backslash + `EOF` (a common form), here-strings `<<< word` / `<<<word` (the 2nd and 3rd `<` are read as a
  heredoc); on the same line after `${#x}` (the `{` breaks the segment, then `#` reads as a comment). Also skipped as
  arithmetic: `$(( 1 + $(git push origin main) ))` and `$((git push origin main) )`; bash runs the latter as a command
  substitution (verified: `echo $((echo hi) )` prints hi). Fix: delimiter = whole word with quotes/backslashes removed;
  `<<<` is a here-string; treat `((` like `$((`; recurse into `$(` inside arithmetic; `#` starts a comment only at a word
  start after whitespace or a separator.
- L13 (new, partial regression) The 4c broad rule matches raw text, so splitting the word defeats it on main:
  `g''it commit -m x` (rework 2: DENY), `"g"it`, `gi<bs>t`, `git co''mmit`, `git c<bs>ommit`, `$'<bs>x67'it`, and
  uppercase `GIT commit` / `Git commit` (runs on the Windows host). Deliberate obfuscation except uppercase. Fix: before
  the broad match, delete quotes and backslashes and lower-case the text.
- L14 (new) jq mode: the judge uses RS = byte 0x01 and jq decodes the JSON escape for 0x01 to that byte, so only the text
  after the last 0x01 is judged. `git commit -m x; echo <0x01>x` on main and `git push origin main; echo <0x01>x` off
  main are silent with jq (DENY without jq). Crafted only; the Windows host has no jq. Fix: strip 0x01 before judging.
- L15 (new, info) No-jq mode: pretty-printed JSON (newline between `"command":` and the value) is silent; jq mode denies.
  Unreachable from Claude Code (compact JSON).
- L12 (updated) Hook tests run only in the gates image (mawk); on the Windows host the test harness gets bash exit 127.
  H2 shows host-awk coverage is needed.
- Unchanged: L11 (unicode-escape divergence, unreachable), L2 (gates container root, rw bind mount), L5 (KE_IN_GATES=1
  skips the container), L7 (analyst/marketer web tools plus Bash). Not in spec: `git pull` on main (merge commit),
  `HEAD:MAIN`, wildcard refspecs, `$'main'`, `main~0`.

## Secrets and local paths
Grep (key shapes for AWS/GitHub/Slack/OpenAI/Anthropic/Google, private keys, user:pass@ URLs, key/secret/password/token
assignments, Bearer, emails, Windows profile/AppData/home paths, host username, repo absolute path) over `git diff 886de45`
plus untracked in-scope files (7004 lines) and the evidence files new since rework 2 (analyst-req4-r3.md,
green-fast-r3.txt, green-rework3.txt, hook-live-host-r3.txt, hook-timing-host-r3.txt, mutation-hook-r3.txt,
red-rework3.txt, review-rework2.md, security-rework2.md): no secrets, no user-profile paths, no username.
Hits: the public noreply co-author trailer inside a test string; security-rework2.md describing its own search; and
hook-probe-review-r3.txt (reviewer, written in parallel) records the repo path `/c/repos/Knowledge-engine` four times
(info: not a profile path, no username; consider redacting). .claude/settings.json unchanged (hook only, timeout 10).

## Raw output
"allow-or-ask" = no output, exit 0 (normal permission flow). Every row rc=0. In rows, `\n` = newline in the command,
`<0x01>` = that byte.

### Table A: host, no jq, gawk (187 rows)
Versus image no-jq: rows 44 and 179 (`ma\in`, `m\ain`) are DENY in the image (H2).
Versus image jq: the same two rows, and rows 103, 104, 168 (the 0x01 rows) are allow-or-ask with jq (L14).
```
main     DENY          | git commit -m x
main     DENY          | git commit
main     DENY          | git push
main     DENY          | git commit -m "x"
main     DENY          | git_AUTHOR_NAME=a git commit -m x
main     DENY          | bash -c "git commit -m x"
main     allow-or-ask  | git ci -m x
main     DENY          | git -c alias.c=commit c -m x
main     allow-or-ask  | gh pr merge 1 --merge
main     allow-or-ask  | gh api repos/o/r/git/refs/heads/main -X PATCH
main     allow-or-ask  | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"
main     DENY          | g=git; $g commit -m x
main     DENY          | git merge feature
main     DENY          | git merge
main     DENY          | git cherry-pick abc
main     DENY          | git am p.patch
main     DENY          | git rebase x
main     DENY          | git revert abc
main     allow-or-ask  | git pull
main     allow-or-ask  | git pull origin main
main     allow-or-ask  | git reset --hard x
main     DENY          | git commit-tree HEAD^{tree} | xargs git update-ref refs/heads/main
main     allow-or-ask  | echo digital push-ups
main     DENY          | git log --grep=push
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
main     DENY          | (git commit -m x)
main     DENY          | { git commit -m x; }
main     DENY          | if true; then git commit -m x; fi
main     DENY          | time git commit -m x
main     DENY          | command git commit -m x
main     DENY          | env git commit -m x
main     DENY          | ! git commit -m x
main     DENY          | exec git commit -m x
main     DENY          | true & git commit -m x
main     DENY          | >/dev/null git commit -m x
main     DENY          | echo $(git commit -m x)
main     DENY          | echo `git commit -m x`
main     DENY          | xargs git commit -m x < /dev/null
main     DENY          | cd . && git commit -m x
main     DENY          | git --no-pager commit -m x
main     DENY          | git -P commit -m x
main     DENY          | git --git-dir=.git commit -m x
main     DENY          | git -C . -c user.name=a commit -m x
main     DENY          | git commit -m "$(cat <<'EOF'\nmsg\nEOF\n)"
main     DENY          | "git" commit -m x
main     allow-or-ask  | g''it commit -m x
main     DENY          | /usr/bin/git commit -m x
main     DENY          | git.exe commit -m x
main     DENY          | git -c core.hooksPath=/dev/null commit -m x
main     DENY          | echo $((1<<2))\ngit commit -m x
main     DENY          | cat <<EOF\nhi\nEOF\ngit commit -m x
main     DENY          | cat <<'EOF' > f\ngit push origin main\nEOF
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
agent/x  DENY          | echo $((1<<2))\ngit push origin main
agent/x  allow-or-ask  | git commit -m "push to main"
agent/x  allow-or-ask  | git commit -m "x" -m 'git push -f'
agent/x  allow-or-ask  | echo "git push origin main"
agent/x  allow-or-ask  | git log --oneline main
main     DENY          | bash -c "git commit -m x"
main     DENY          | sh -c 'git commit -m x'
main     DENY          | xargs git commit -m x < /dev/null
main     DENY          | echo "$(git commit -m x)"
main     DENY          | cat <<'EOF' > f\ngit commit -m x\nEOF
main     DENY          | git commit -m x; echo <0x01>x
main     DENY          | git push; echo a<0x01>b
main     allow-or-ask  | "g"it commit -m x
main     allow-or-ask  | gi\t commit -m x
main     allow-or-ask  | git co''mmit -m x
main     allow-or-ask  | git c\ommit -m x
main     DENY          | git "commit" -m x
main     allow-or-ask  | GIT commit -m x
main     allow-or-ask  | Git commit -m x
main     DENY          | git.EXE commit -m x
main     allow-or-ask  | $'\x67'it commit -m x
main     allow-or-ask  | git pull
main     DENY          | git pull --no-rebase origin main
main     DENY          | nohup git commit -m x
main     DENY          | timeout 60 git commit -m x
main     DENY          | ((x=1<<2))\ngit commit -m x
main     DENY          | echo $((git commit -m x) )
master   DENY          | git commit -m x
master   DENY          | git push
agent/x  DENY          | (git push origin main)
agent/x  DENY          | { git push origin main; }
agent/x  DENY          | if git push origin main; then :; fi
agent/x  DENY          | true & git push origin main
agent/x  DENY          | >/dev/null git push origin main
agent/x  DENY          | 2>&1 git push origin main
agent/x  DENY          | echo $(git push origin main)
agent/x  DENY          | echo `git push origin main`
agent/x  DENY          | echo $((1<<2))\ngit push origin main
agent/x  DENY          | echo $((1<<2)) && git push origin main
agent/x  DENY          | while git push origin main; do :; done
agent/x  DENY          | until git push -f; do :; done
agent/x  DENY          | ! git push origin main
agent/x  DENY          | time git push origin main
agent/x  DENY          | command git push origin main
agent/x  DENY          | env git push origin main
agent/x  DENY          | exec git push origin main
agent/x  DENY          | X=1 Y=2 git push origin main
agent/x  DENY          | git push -fu origin agent/x
agent/x  DENY          | git push -uf origin agent/x
agent/x  DENY          | git -c x=y push origin main
agent/x  DENY          | git -C . push origin main
agent/x  DENY          | git push origin HEAD:refs/heads/main
agent/x  DENY          | git push origin :main
agent/x  DENY          | git push --force-with-lease=agent/x origin agent/x
agent/x  DENY          | git push origin HEAD:master
agent/x  allow-or-ask  | git commit -m "fix push to main docs"
agent/x  allow-or-ask  | git commit -m "note push -f is denied"
agent/x  allow-or-ask  | git commit -m "$(cat <<'EOF'\nsee git push to main\nEOF\n)"
agent/x  allow-or-ask  | echo "git push origin main"
agent/x  allow-or-ask  | git log --grep push
agent/x  allow-or-ask  | echo "$(git push origin main)"
agent/x  allow-or-ask  | bash -c "git push origin main"
agent/x  allow-or-ask  | sh -c 'git push origin main'
agent/x  allow-or-ask  | xargs git push origin main < /dev/null
agent/x  allow-or-ask  | ((x=1<<2))\ngit push origin main
agent/x  allow-or-ask  | echo $[1<<2]\ngit push origin main
agent/x  allow-or-ask  | cat <<"E"OF\nbody\nEOF\ngit push origin main
agent/x  allow-or-ask  | cat <<E"OF"\nbody\nEOF\ngit push origin main
agent/x  allow-or-ask  | cat <<\EOF\nbody\nEOF\ngit push origin main
agent/x  allow-or-ask  | cat <<< word\ngit push origin main
agent/x  allow-or-ask  | cat <<<word\ngit push origin main
agent/x  allow-or-ask  | x=1; echo ${#x}; git push origin main
agent/x  DENY          | echo ${#x}\ngit push origin main
agent/x  allow-or-ask  | echo $(( 1 + $(git push origin main) ))
agent/x  allow-or-ask  | echo $((git push origin main) )
agent/x  DENY          | git push origin main; echo <0x01>x
agent/x  allow-or-ask  | nohup git push origin main
agent/x  allow-or-ask  | timeout 60 git push origin main
agent/x  allow-or-ask  | nice git push origin main
agent/x  allow-or-ask  | sudo git push origin main
agent/x  allow-or-ask  | env -i git push origin main
agent/x  allow-or-ask  | command -p git push origin main
agent/x  allow-or-ask  | time -p git push origin main
agent/x  allow-or-ask  | git --config-env x=Y push origin main
agent/x  allow-or-ask  | GIT push origin main
agent/x  DENY          | git push origin "ma"in
agent/x  allow-or-ask  | git push origin m\ain
agent/x  DENY          | git push origin 'HEAD:main'
agent/x  DENY          | git push origin HEAD:refs/heads/main --dry-run
agent/x  DENY          | case x in x) git push origin main;; esac
agent/x  DENY          | f() { git push origin main; }; f
agent/x  DENY          | for b in a; do git push origin main; done
agent/x  DENY          | git push origin main # c
agent/x  allow-or-ask  | echo hi # git push origin main
agent/x  DENY          | echo a#b; git push origin main
```

### Table B: backslash cases (H2), payloads built from character codes
cont-origin-main / cont-f = git push, backslash, newline, then origin main / -f; cont-force has --force before the backslash.
dq-bs-quote = escaped quote inside a quoted -m message, then ; git push origin main. dbl-bs = echo a, two backslashes, b; git push origin main.
```
agent/x  cont-origin-main   silent
agent/x  cont-force         DENY
agent/x  cont-f             silent
agent/x  ma-bs-in           silent
agent/x  dbl-bs             DENY
agent/x  dq-bs-quote        silent
main     cont-origin-main   DENY
main     cont-force         DENY
main     cont-f             DENY
main     ma-bs-in           DENY
main     dbl-bs             DENY
main     dq-bs-quote        DENY
# image jq (mawk)
agent/x  cont-origin-main   DENY
agent/x  cont-force         DENY
agent/x  cont-f             DENY
agent/x  ma-bs-in           DENY
agent/x  dbl-bs             DENY
agent/x  dq-bs-quote        DENY
main     cont-origin-main   DENY
main     cont-force         DENY
main     cont-f             DENY
main     ma-bs-in           DENY
main     dbl-bs             DENY
main     dq-bs-quote        DENY
# image no jq (mawk)
agent/x  cont-origin-main   DENY
agent/x  cont-force         DENY
agent/x  cont-f             DENY
agent/x  ma-bs-in           DENY
agent/x  dbl-bs             DENY
agent/x  dq-bs-quote        DENY
main     cont-origin-main   DENY
main     cont-force         DENY
main     cont-f             DENY
main     ma-bs-in           DENY
main     dbl-bs             DENY
main     dq-bs-quote        DENY
```

### Table C: malformed payloads, host no jq
```
main     truncated mid-command            DENY
main     no closing brace                 DENY
main     garbage                          silent
main     empty stdin                      silent
main     no command key                   silent
main     command null / number         silent
main     spaced json                      DENY
main     newline after colon (pretty) silent (L15)
main     forged key in description        DENY
main     toolInput (camelCase)            DENY
main     raw text (not JSON)              DENY
main     top-level array                  DENY
agent/x  truncated push to main           DENY
agent/x  escaped quote then push         silent (H2)
```

### Table D: timing (seconds; hook timeout 10 s; command ends with ; git push origin main)
```
# host, Git Bash, no jq, GNU Awk 5.4.0
agent/x  segs1M          DENY      1.05s rc=0
agent/x  word1M          DENY      0.86s rc=0
agent/x  sq1M            DENY      0.59s rc=0
agent/x  dq1M            DENY      0.74s rc=0
agent/x  heredocline1M   DENY      0.48s rc=0
agent/x  heredoclines1M  DENY      4.56s rc=0
agent/x  utf8word1M      DENY      0.85s rc=0
agent/x  utf8dq1M        DENY      0.72s rc=0
agent/x  arith1M         DENY      0.34s rc=0
agent/x  segs5M          DENY      4.74s rc=0
agent/x  word5M          DENY      3.89s rc=0
main     segs1M          DENY      0.45s rc=0
main     word1M          DENY      0.30s rc=0
main     segs5M          DENY      1.58s rc=0
main     word5M          DENY      0.90s rc=0
# image, jq 1.6, mawk
agent/x  segs1M          DENY      0.27s rc=0
agent/x  word1M          DENY      8.08s rc=0
agent/x  sq1M            DENY      7.79s rc=0
agent/x  dq1M            DENY      7.96s rc=0
agent/x  heredocline1M   DENY      7.80s rc=0
agent/x  heredoclines1M  DENY      0.11s rc=0
agent/x  utf8word1M      DENY      7.97s rc=0
agent/x  utf8dq1M        DENY      7.96s rc=0
agent/x  arith1M         DENY      0.07s rc=0
agent/x  segs5M          DENY      1.28s rc=0
agent/x  word5M          silent  299.99s rc=124
main     segs1M          DENY      0.07s rc=0
main     word1M          DENY      0.05s rc=0
main     segs5M          DENY      0.34s rc=0
# image, no jq, mawk
agent/x  segs1M          DENY      0.27s rc=0
agent/x  word1M          DENY      7.98s rc=0
agent/x  sq1M            DENY      7.88s rc=0
agent/x  dq1M            DENY      7.69s rc=0
agent/x  heredocline1M   DENY      7.88s rc=0
agent/x  heredoclines1M  DENY      0.10s rc=0
agent/x  utf8word1M      DENY      8.05s rc=0
agent/x  utf8dq1M        DENY      7.85s rc=0
agent/x  arith1M         DENY      0.07s rc=0
agent/x  segs5M          DENY      1.38s rc=0
agent/x  word5M          silent  299.99s rc=124
# host gawk, heredoc of 100-byte lines then git push origin main (agent/x)
1 MB 5.07s DENY | 2 MB 19.49s DENY | 4 MB 74.27s DENY
```
