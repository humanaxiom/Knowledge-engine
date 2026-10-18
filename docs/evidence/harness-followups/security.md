# Security audit: harness-followups (2026-10-18)

Scope: `git diff a11842d` for .github/workflows/ci.yml, scripts/test.sh, scripts/hooks/block-main-commit.sh,
tests/test_block_main_commit_hook.py, plus untracked tests/test_harness_followups.py and the new evidence files.
Platform-skeleton plan docs excluded. Audited snapshot (sha256):
- scripts/hooks/block-main-commit.sh 129feb4776656ae6908ad1afaa32b02e7954c31875d04f26d8a9d800eb83b7f0
- scripts/test.sh 057e4682c7ae3df52b5dec0133331d680105c38365141282eed77929f96b1420 (rework 2 state)
- .github/workflows/ci.yml e6e2059370a5f3ea70bf7ab8a6ea0dfc47dfc7770c51bb4999fb74b1a0633bf2
- tests/test_harness_followups.py c8d95425e5bf9c80481e88fa083d12767c23605d88f2a89094fda1b8aac12274
- tests/test_block_main_commit_hook.py 21d0c3696e1acdd018262ffdfbd8f98101a224fa2d14fe806220dd34bbc993fc
Notation: <bs> = one backslash, <NL> = newline, <CR> = carriage return. Command examples use probe tokens so the
live hook does not deny the write:
- %G% = the version-control command word,
- %P% = the upload verb,
- %M% = the default branch name.

## Verdict: PASS (0 critical, 0 high; 1 medium, 1 low new, rest info or carried, all non-blocking)

M5 below is a fail-open regression introduced by this change (the old hook denied those rows). It is rated medium,
the same class as M4, so it does not block; I recommend fixing it in this item rather than deferring it.

## Method
Payloads only, piped to the hook in throwaway repos (branch set with `symbolic-ref`); never a commit to this repo.
Same generators as rework 4 (mk4.py, mkbad.py, mkbig.py; CR, backslash, NUL, SOH built from character codes).
Modes: Windows host (Git Bash 5.3.9 Cygwin, no jq), gates image knowledge-engine-gates with jq 1.6 (bash 5.2.15,
grep 3.8), gates image with jq shadowed by a stub that exits 127. Old hook (a11842d) run on the host for comparison.
- Table A: 331 rows = the 288 rework-4 rows + 43 new rows (CR in every position, backslash-CR, backslash-newline
  in comments, after an even run of backslashes, inside single quotes, splitting words).
- Table B: 66 malformed or unusual payloads x 2 branches (rework-4's 52 + 14 CR forms: raw CR inside a JSON string,
  JSON CR escape inside the %G% word, backslash + CR, backslash + CR LF continuation, a literal backslash-r).
- Table C: 5 MB commands, 10 shapes (rework 4's 7 + CR LF lines, backslash-newline lines, 5 M raw CRs).
- Live run: the M5 shapes written to script files and executed with host bash in a scratch repo with a bare remote.

## 1. M4: fixed
- The four M4 rows are now DENY on the host (no jq), in the image with jq and in the image without jq:
  off main `%G% %P% origin %M%<CR>` and `%G% status<CR><NL>%G% %P% origin %M%<CR><NL>`;
  on main `%G% commit<CR><NL>` and `%G%<CR> commit -m x`.
- New CR rows, all DENY in all three modes: CR inside the %G% word, inside `commit`, inside the branch name,
  inside `--mirror`, before the %G% word, before the branch name, before `-f`, before `+x`, double CR, backslash +
  CR after the branch name, JSON CR escape, raw CR in the JSON string, backslash + CR LF used as a continuation.
- Stripping CR matches host bash: Cygwin bash drops an unquoted CR (verified: `echo a<CR>b` prints `ab`), so
  deleting it cannot hide a word bash would see. Correctly silent: `x<CR>%G% commit` (bash runs `x%G%`),
  `%M%<bs>r` (bash reads it with a trailing r).
- Extractor: `\r` is dropped after the `\` placeholder step, so an escaped backslash followed by `r` is kept as a
  backslash and r, as bash reads it. Every remaining backslash starts an escape pair, so removing `\r` cannot
  create a new `\n` or `\t` escape. No new fail-open from CR stripping found.
- Host no-jq output is identical to image no-jq output on all 331 Table-A rows and on Table B except the
  rework-4 L19 rows (invalid UTF-8 / Latin-1, grep 3.8 vs 3.0). Image jq differs from no-jq only on the known
  NUL rows (Table A) and the known L19/L15 rows (Table B). Never `allow`: 0 allow outputs, every exit code 0.
- Timing (Table C, 5 MB, all 30 rows DENY): host no-jq max 4.6 s, image jq max 0.65 s, image no-jq max 2.2 s
  (10 s hook timeout). Unchanged from rework 4.

## 2. Regressions from joining backslash-newline to nothing
Rows that changed from DENY (old hook) to silent (new hook), all three modes:
```
main     #x<bs><NL>%G% commit -m x
main     # copy to C:<bs>out<bs><NL>%G% commit -m x
main     ls #a<bs><NL>%G% commit -m x
main     #x<bs><NL>%G% %P%
main     echo a<bs><bs><NL>%G% commit -m x
main     echo a<bs><bs><bs><bs><NL>%G% commit -m x
agent/x  #x<bs><NL>%G% %P% origin %M%
agent/x  #x<bs><NL>%G% %P% -f
agent/x  echo a<bs><bs><NL>%G% %P% origin %M%
```
Also DENY to silent, but correct (bash does not run %G% there either): `echo a<bs><bs><bs><NL>%G% commit`,
`echo <SQ>a<bs><NL><SQ>%G% commit` (inside single quotes), `%G% %P% origin x<bs><NL>%M%` (bash joins it to
x%M%), `%G% %P%<bs><NL>origin %M%` (bash joins the verb to `origin`).

### M5 (medium, new, introduced by this change) backslash-newline that bash does not treat as a continuation
The normaliser deletes every backslash-newline pair. Bash does not join lines there when the backslash ends a
comment, or when it is the second of an even run (an escaped backslash followed by a real newline). The next line
is then a separate command in bash, but the hook glues its first word to the previous line (`#x%G%`, `a%G%`), so
the %G% word is gone and the rule stays silent on main and off main. Before this change the pair became a space
and these rows were denied.
Live proof (host bash, scratch repo with a bare remote, script files built from character codes; the hook judged
the same text as a compact payload first):
```
main    c1  #x<bs><NL>%G% commit ..                    new hook silent, old hook deny, commit c1 created
main    c2  echo a<bs><bs><NL>%G% commit ..            new hook silent, old hook deny, commit c2 created
main    c3  # copy to C:<bs>out<bs><NL>%G% commit ..   new hook silent, old hook deny, commit c3 created
agent/x p1  #x<bs><NL>%G% %P% origin HEAD:%M%          new hook silent, old hook deny, remote branch moved to c3
```
Medium, not high: the hook is a guard rail, not the security boundary (branch protection on the remote is, Q18),
and the trigger needs an alphanumeric character right before the backslash with the %G% word at the start of the
next line. It is plausible on this Windows project, though: a comment that ends in a Windows path (c3). No 4e
bypass class covers it (the words are visible).
Fix (developer): judge two normalisations and deny if either matches: the current one (join to nothing, which
PS-0.5 requires) and one where backslash-newline becomes a newline (or a space). Union is fail safe and keeps every
PS-0.5 row denied. The same two-pass shape also fixes L16 (backslash replaced by a space). Tests (tester): add the
nine rows above in both jq modes, and c1-c3/p1 to the host live check.

## 3. CI
- `gh api repos/actions/checkout/git/ref/tags/v5.1.0` and `.../tags/v5`: both object type commit,
  sha fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 (lightweight tags, no annotated-tag dereference).
- `gh api repos/actions/checkout/commits/fbc6f399...`: "backport fixes to releases-v5 (#2523)", 2026-07-16,
  verification.verified = true. Release v5.1.0: target releases/v5, published 2026-07-20.
  The pinned SHA in ci.yml is the v5.1.0 commit. Confirmed.
- `runs-on: ubuntu-24.04` (no `-latest` left) and top-level `permissions: contents: read` are present. The only
  other step is `./scripts/verify.sh full`. No secrets referenced, no pull_request_target, no
  github.event expressions interpolated into `run:`.
- L20 (low, pre-existing, not introduced): checkout runs with the default `persist-credentials: true`, so the
  read-only GITHUB_TOKEN stays in the checkout's config for the verify step, and the gates container bind-mounts
  the work tree (L2). Scope is contents:read, so impact is small. Suggest `with: persist-credentials: false`.

## 4. scripts/test.sh
Module names come from `tests/test*.py`: the path with `.py` cut and `/` mapped to `.`, held in a bash array and
passed quoted to `python -m unittest`. No eval, no word splitting, no shell re-parse, so a hostile file name cannot
inject shell. Every argument starts with `tests.`, so none can be read as a unittest option. A file name with `;`,
spaces or a newline becomes an unimportable module name and the run fails (fail closed). Directory loops quote
the loop variable; `find` does not follow symlinks; a symlinked `tests/*/` dir would be passed to `discover -s`,
which runs code from it, but that is code already committed to the repo, so no new trust boundary. The
`find | sed | sort` dir check splits on newlines, so a dir name containing a newline gives a false
"no __init__.py" error (fail closed). No path or injection finding. Info: it runs repo-controlled code, as before.

tests/test_harness_followups.py: copies scripts/test.sh into a mkdtemp project, puts a fake `uv` first on PATH that
execs the test interpreter, cleans up with addCleanup. Paths come from tempfile, no shell=True, no network. No
finding.

## 5. Secrets and local paths
Grep (AWS/GitHub/Slack/OpenAI/Anthropic/Google key shapes, private keys, user:pass@ URLs, key/secret/password/
token/bearer assignments, emails, Windows profile paths, AppData, `/home/`, host username, repo absolute path)
over every file in docs/evidence/harness-followups/ (14 files before this one), docs/handoffs/harness-followups.md,
both test files, the hook, test.sh and ci.yml: 3007 lines. Hits: the compose image/container name
`knowledge-engine-gates` (project name, not a local path) and the test dict key "unquoted token" (false positive).
No secrets, no profile paths, no username, no absolute repo path. This file adds none (re-checked after writing).

## Carried findings (unchanged, non-blocking)
L16 (Windows backslash path; M5's fix would close it), L17 (`--branches`, `--mirr`, `--al`), L18 (pull and
update-ref on main), L19 (unreachable malformed payloads), L15, L12 (narrowed: the CR rows are now in the image
tests and in the developer's host check), L11, L2, L5, L7.

## Raw output
Probe tokens as above, plus %BS% = one backslash, %NL% = newline, %CR% = carriage return, %NUL% = byte 0x00,
%SOH% = byte 0x01, %SQ% / %DQ% = quotes, %U% / %Gc% = the %G% word upper-cased / capitalised.
"allow-or-ask" / "silent" = no output, exit 0.

### Table A diff: old hook (a11842d) vs new hook, host no jq (< old, > new)
```
214,215c214,215
< agent/x  allow-or-ask  | %G% %P% origin %M%%CR%   [rc=0]
< agent/x  allow-or-ask  | %G% status%CR%%NL%%G% %P% origin %M%%CR%%NL%   [rc=0]
---
> agent/x  DENY          | %G% %P% origin %M%%CR%   [rc=0]
> agent/x  DENY          | %G% status%CR%%NL%%G% %P% origin %M%%CR%%NL%   [rc=0]
270,271c270,271
< main     allow-or-ask  | %G% commit%CR%%NL%   [rc=0]
< main     allow-or-ask  | %G%%CR% commit -m x   [rc=0]
---
> main     DENY          | %G% commit%CR%%NL%   [rc=0]
> main     DENY          | %G%%CR% commit -m x   [rc=0]
289,296c289,296
< main     DENY          | #x%BS%%NL%%G% commit -m x   [rc=0]
< main     DENY          | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
< main     DENY          | ls #a%BS%%NL%%G% commit -m x   [rc=0]
< main     DENY          | #x%BS%%NL%%G% push   [rc=0]
< main     DENY          | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     DENY          | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     DENY          | echo a%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     DENY          | echo %SQ%a%BS%%NL%%SQ%%G% commit -m x   [rc=0]
---
> main     allow-or-ask  | #x%BS%%NL%%G% commit -m x   [rc=0]
> main     allow-or-ask  | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
> main     allow-or-ask  | ls #a%BS%%NL%%G% commit -m x   [rc=0]
> main     allow-or-ask  | #x%BS%%NL%%G% push   [rc=0]
> main     allow-or-ask  | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     allow-or-ask  | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     allow-or-ask  | echo a%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     allow-or-ask  | echo %SQ%a%BS%%NL%%SQ%%G% commit -m x   [rc=0]
298,299c298,299
< main     allow-or-ask  | gi%BS%%NL%t commit -m x   [rc=0]
< main     allow-or-ask  | %G% com%BS%%NL%mit -m x   [rc=0]
---
> main     DENY          | gi%BS%%NL%t commit -m x   [rc=0]
> main     DENY          | %G% com%BS%%NL%mit -m x   [rc=0]
301,303c301,303
< main     allow-or-ask  | %G% commit%CR%%NL%   [rc=0]
< main     allow-or-ask  | %G%%CR% commit -m x   [rc=0]
< main     allow-or-ask  | %CR%%G% commit -m x   [rc=0]
---
> main     DENY          | %G% commit%CR%%NL%   [rc=0]
> main     DENY          | %G%%CR% commit -m x   [rc=0]
> main     DENY          | %CR%%G% commit -m x   [rc=0]
305,307c305,307
< main     allow-or-ask  | %G% com%CR%mit -m x   [rc=0]
< main     allow-or-ask  | gi%CR%t commit -m x   [rc=0]
< main     allow-or-ask  | %G%%CR%%CR% commit   [rc=0]
---
> main     DENY          | %G% com%CR%mit -m x   [rc=0]
> main     DENY          | gi%CR%t commit -m x   [rc=0]
> main     DENY          | %G%%CR%%CR% commit   [rc=0]
310,314c310,314
< agent/x  DENY          | #x%BS%%NL%%G% push origin %M%   [rc=0]
< agent/x  DENY          | #x%BS%%NL%%G% push -f   [rc=0]
< agent/x  DENY          | echo a%BS%%BS%%NL%%G% push origin %M%   [rc=0]
< agent/x  allow-or-ask  | %G% push origin %M%%CR%   [rc=0]
< agent/x  allow-or-ask  | %G% push origin ma%CR%in   [rc=0]
---
> agent/x  allow-or-ask  | #x%BS%%NL%%G% push origin %M%   [rc=0]
> agent/x  allow-or-ask  | #x%BS%%NL%%G% push -f   [rc=0]
> agent/x  allow-or-ask  | echo a%BS%%BS%%NL%%G% push origin %M%   [rc=0]
> agent/x  DENY          | %G% push origin %M%%CR%   [rc=0]
> agent/x  DENY          | %G% push origin ma%CR%in   [rc=0]
316c316
< agent/x  DENY          | %G% push origin x%BS%%NL%%M%   [rc=0]
---
> agent/x  allow-or-ask  | %G% push origin x%BS%%NL%%M%   [rc=0]
319,321c319,321
< agent/x  DENY          | %G% push%BS%%NL%origin %M%   [rc=0]
< agent/x  allow-or-ask  | %G% push origin %M%%CR%%NL%   [rc=0]
< agent/x  allow-or-ask  | %G% status%CR%%NL%%G% push origin %M%%CR%%NL%   [rc=0]
---
> agent/x  allow-or-ask  | %G% push%BS%%NL%origin %M%   [rc=0]
> agent/x  DENY          | %G% push origin %M%%CR%%NL%   [rc=0]
> agent/x  DENY          | %G% status%CR%%NL%%G% push origin %M%%CR%%NL%   [rc=0]
323,324c323,324
< agent/x  allow-or-ask  | %G% push %CR%-f origin x   [rc=0]
< agent/x  allow-or-ask  | %G% push origin %CR%+x   [rc=0]
---
> agent/x  DENY          | %G% push %CR%-f origin x   [rc=0]
> agent/x  DENY          | %G% push origin %CR%+x   [rc=0]
326c326
< agent/x  allow-or-ask  | %G% push origin %M%%BS%%CR%   [rc=0]
---
> agent/x  DENY          | %G% push origin %M%%BS%%CR%   [rc=0]
328,329c328,329
< agent/x  allow-or-ask  | %G% push origin %CR%%M%   [rc=0]
< agent/x  allow-or-ask  | %G% push --mir%CR%ror   [rc=0]
---
> agent/x  DENY          | %G% push origin %CR%%M%   [rc=0]
> agent/x  DENY          | %G% push --mir%CR%ror   [rc=0]
```

### Table A diff: image no-jq vs image jq (host no-jq output is identical to image no-jq)
```
239,240c239,240
< agent/x  allow-or-ask  | %G% %P% origin ma%NUL%in   [rc=0]
< agent/x  allow-or-ask  | %G% %P% origin %M%%NUL%   [rc=0]
---
> agent/x  DENY          | %G% %P% origin ma%NUL%in   [rc=0]
> agent/x  DENY          | %G% %P% origin %M%%NUL%   [rc=0]
274c274
< main     allow-or-ask  | %G%%NUL% commit -m x   [rc=0]
---
> main     DENY          | %G%%NUL% commit -m x   [rc=0]
```

### Table A: host, no jq, new hook (331 rows)
```
main     DENY          | %G% commit -m x   [rc=0]
main     DENY          | %G% commit   [rc=0]
main     DENY          | %G% push   [rc=0]
main     DENY          | %G% commit -m "x"   [rc=0]
main     DENY          | %G%_AUTHOR_NAME=a %G% commit -m x   [rc=0]
main     DENY          | bash -c "%G% commit -m x"   [rc=0]
main     allow-or-ask  | %G% ci -m x   [rc=0]
main     DENY          | %G% -c alias.c=commit c -m x   [rc=0]
main     allow-or-ask  | gh pr merge 1 --merge   [rc=0]
main     allow-or-ask  | gh api repos/o/r/%G%/refs/heads/main -X PATCH   [rc=0]
main     allow-or-ask  | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"   [rc=0]
main     DENY          | g=%G%; $g commit -m x   [rc=0]
main     DENY          | %G% merge feature   [rc=0]
main     DENY          | %G% merge   [rc=0]
main     DENY          | %G% cherry-pick abc   [rc=0]
main     DENY          | %G% am p.patch   [rc=0]
main     DENY          | %G% rebase x   [rc=0]
main     DENY          | %G% revert abc   [rc=0]
main     allow-or-ask  | %G% pull   [rc=0]
main     allow-or-ask  | %G% pull origin main   [rc=0]
main     allow-or-ask  | %G% reset --hard x   [rc=0]
main     allow-or-ask  | %G% commit-tree HEAD^{tree} | xargs %G% update-ref refs/heads/main   [rc=0]
main     allow-or-ask  | echo digital push-ups   [rc=0]
main     DENY          | %G% log --grep=push   [rc=0]
main     allow-or-ask  | %G% status   [rc=0]
main     allow-or-ask  | ls -la   [rc=0]
agent/x  DENY          | %G% push origin HEAD:main   [rc=0]
agent/x  DENY          | %G% push origin agent/x:main   [rc=0]
agent/x  DENY          | %G% push origin "HEAD:main"   [rc=0]
agent/x  DENY          | %G% push origin "main"   [rc=0]
agent/x  DENY          | %G% push origin 'main'   [rc=0]
agent/x  DENY          | %G% push origin main   [rc=0]
agent/x  DENY          | %G% push origin HEAD:refs/heads/main   [rc=0]
agent/x  DENY          | %G% push origin :main   [rc=0]
agent/x  DENY          | %G% push --delete origin main   [rc=0]
agent/x  DENY          | %G% push --force origin main   [rc=0]
agent/x  DENY          | %G% push --force origin agent/x   [rc=0]
agent/x  DENY          | %G% push -f   [rc=0]
agent/x  DENY          | %G% push --force-with-lease   [rc=0]
agent/x  DENY          | %G% push origin +agent/x   [rc=0]
agent/x  DENY          | %G% push origin +HEAD:main   [rc=0]
agent/x  DENY          | %G% push --mirror   [rc=0]
agent/x  DENY          | %G% push --all origin   [rc=0]
agent/x  DENY          | %G% push origin ma\in   [rc=0]
agent/x  DENY          | %G% push origin $(echo main)   [rc=0]
agent/x  allow-or-ask  | %G% push origin refs/heads/*:refs/heads/*   [rc=0]
agent/x  allow-or-ask  | %G% checkout main && %G% commit -m x   [rc=0]
agent/x  allow-or-ask  | %G% switch main; %G% commit -m x   [rc=0]
agent/x  allow-or-ask  | %G% -C ../other-main-checkout commit -m x   [rc=0]
agent/x  allow-or-ask  | %G% update-ref refs/heads/main HEAD   [rc=0]
agent/x  allow-or-ask  | %G% push origin agent/x   [rc=0]
agent/x  allow-or-ask  | %G% push -u origin agent/x   [rc=0]
agent/x  allow-or-ask  | %G% push   [rc=0]
main     DENY          | (%G% commit -m x)   [rc=0]
main     DENY          | { %G% commit -m x; }   [rc=0]
main     DENY          | if true; then %G% commit -m x; fi   [rc=0]
main     DENY          | time %G% commit -m x   [rc=0]
main     DENY          | command %G% commit -m x   [rc=0]
main     DENY          | env %G% commit -m x   [rc=0]
main     DENY          | ! %G% commit -m x   [rc=0]
main     DENY          | exec %G% commit -m x   [rc=0]
main     DENY          | true & %G% commit -m x   [rc=0]
main     DENY          | >/dev/null %G% commit -m x   [rc=0]
main     DENY          | echo $(%G% commit -m x)   [rc=0]
main     DENY          | echo `%G% commit -m x`   [rc=0]
main     DENY          | xargs %G% commit -m x < /dev/null   [rc=0]
main     DENY          | cd . && %G% commit -m x   [rc=0]
main     DENY          | %G% --no-pager commit -m x   [rc=0]
main     DENY          | %G% -P commit -m x   [rc=0]
main     DENY          | %G% --git-dir=.git commit -m x   [rc=0]
main     DENY          | %G% -C . -c user.name=a commit -m x   [rc=0]
main     DENY          | %G% commit -m "$(cat <<'EOF'\nmsg\nEOF\n)"   [rc=0]
main     DENY          | "%G%" commit -m x   [rc=0]
main     DENY          | g''it commit -m x   [rc=0]
main     DENY          | /usr/bin/%G% commit -m x   [rc=0]
main     DENY          | %G%.exe commit -m x   [rc=0]
main     DENY          | %G% -c core.hooksPath=/dev/null commit -m x   [rc=0]
main     DENY          | echo $((1<<2))\n%G% commit -m x   [rc=0]
main     DENY          | cat <<EOF\nhi\nEOF\n%G% commit -m x   [rc=0]
main     DENY          | cat <<'EOF' > f\ngit push origin main\nEOF   [rc=0]
agent/x  DENY          | %G% push origin $'main'   [rc=0]
agent/x  DENY          | %G% push origin m"a"in   [rc=0]
agent/x  DENY          | %G% push origin HEAD:MAIN   [rc=0]
agent/x  DENY          | %G% push origin main:main   [rc=0]
agent/x  DENY          | %G% push --force-if-includes origin agent/x   [rc=0]
agent/x  DENY          | %G% push origin --force   [rc=0]
agent/x  DENY          | %G% push -v -f   [rc=0]
agent/x  DENY          | %G% push --repo=origin main   [rc=0]
agent/x  DENY          | %G% push origin HEAD:refs/heads/master   [rc=0]
agent/x  DENY          | %G% push origin refs/heads/agent/x:refs/heads/main   [rc=0]
agent/x  DENY          | %G% push upstream main~0   [rc=0]
agent/x  DENY          | %G% push origin @:main   [rc=0]
agent/x  DENY          | echo $((1<<2))\n%G% push origin main   [rc=0]
agent/x  DENY          | %G% commit -m "push to main"   [rc=0]
agent/x  DENY          | %G% commit -m "x" -m 'git push -f'   [rc=0]
agent/x  DENY          | echo "git push origin main"   [rc=0]
agent/x  allow-or-ask  | %G% log --oneline main   [rc=0]
main     DENY          | bash -c "%G% commit -m x"   [rc=0]
main     DENY          | sh -c '%G% commit -m x'   [rc=0]
main     DENY          | xargs %G% commit -m x < /dev/null   [rc=0]
main     DENY          | echo "$(%G% commit -m x)"   [rc=0]
main     DENY          | cat <<'EOF' > f\n%G% commit -m x\nEOF   [rc=0]
main     DENY          | %G% commit -m x; echo %SOH%x   [rc=0]
main     DENY          | %G% push; echo a%SOH%b   [rc=0]
main     DENY          | "g"it commit -m x   [rc=0]
main     DENY          | gi\t commit -m x   [rc=0]
main     DENY          | %G% co''mmit -m x   [rc=0]
main     DENY          | %G% c\ommit -m x   [rc=0]
main     DENY          | %G% "commit" -m x   [rc=0]
main     DENY          | %U% commit -m x   [rc=0]
main     DENY          | Git commit -m x   [rc=0]
main     DENY          | %G%.EXE commit -m x   [rc=0]
main     allow-or-ask  | $'\x67'it commit -m x   [rc=0]
main     allow-or-ask  | %G% pull   [rc=0]
main     allow-or-ask  | %G% pull --no-rebase origin main   [rc=0]
main     DENY          | nohup %G% commit -m x   [rc=0]
main     DENY          | timeout 60 %G% commit -m x   [rc=0]
main     DENY          | ((x=1<<2))\n%G% commit -m x   [rc=0]
main     DENY          | echo $((%G% commit -m x) )   [rc=0]
master   DENY          | %G% commit -m x   [rc=0]
master   DENY          | %G% push   [rc=0]
agent/x  DENY          | (%G% push origin main)   [rc=0]
agent/x  DENY          | { %G% push origin main; }   [rc=0]
agent/x  DENY          | if %G% push origin main; then :; fi   [rc=0]
agent/x  DENY          | true & %G% push origin main   [rc=0]
agent/x  DENY          | >/dev/null %G% push origin main   [rc=0]
agent/x  DENY          | 2>&1 %G% push origin main   [rc=0]
agent/x  DENY          | echo $(%G% push origin main)   [rc=0]
agent/x  DENY          | echo `%G% push origin main`   [rc=0]
agent/x  DENY          | echo $((1<<2))\n%G% push origin main   [rc=0]
agent/x  DENY          | echo $((1<<2)) && %G% push origin main   [rc=0]
agent/x  DENY          | while %G% push origin main; do :; done   [rc=0]
agent/x  DENY          | until %G% push -f; do :; done   [rc=0]
agent/x  DENY          | ! %G% push origin main   [rc=0]
agent/x  DENY          | time %G% push origin main   [rc=0]
agent/x  DENY          | command %G% push origin main   [rc=0]
agent/x  DENY          | env %G% push origin main   [rc=0]
agent/x  DENY          | exec %G% push origin main   [rc=0]
agent/x  DENY          | X=1 Y=2 %G% push origin main   [rc=0]
agent/x  DENY          | %G% push -fu origin agent/x   [rc=0]
agent/x  DENY          | %G% push -uf origin agent/x   [rc=0]
agent/x  DENY          | %G% -c x=y push origin main   [rc=0]
agent/x  DENY          | %G% -C . push origin main   [rc=0]
agent/x  DENY          | %G% push origin HEAD:refs/heads/main   [rc=0]
agent/x  DENY          | %G% push origin :main   [rc=0]
agent/x  DENY          | %G% push --force-with-lease=agent/x origin agent/x   [rc=0]
agent/x  DENY          | %G% push origin HEAD:master   [rc=0]
agent/x  DENY          | %G% commit -m "fix push to main docs"   [rc=0]
agent/x  DENY          | %G% commit -m "note push -f is denied"   [rc=0]
agent/x  DENY          | %G% commit -m "$(cat <<'EOF'\nsee git push to main\nEOF\n)"   [rc=0]
agent/x  DENY          | echo "git push origin main"   [rc=0]
agent/x  allow-or-ask  | %G% log --grep push   [rc=0]
agent/x  DENY          | echo "$(%G% push origin main)"   [rc=0]
agent/x  DENY          | bash -c "%G% push origin main"   [rc=0]
agent/x  DENY          | sh -c '%G% push origin main'   [rc=0]
agent/x  DENY          | xargs %G% push origin main < /dev/null   [rc=0]
agent/x  DENY          | ((x=1<<2))\n%G% push origin main   [rc=0]
agent/x  DENY          | echo $[1<<2]\n%G% push origin main   [rc=0]
agent/x  DENY          | cat <<"E"OF\nbody\nEOF\n%G% push origin main   [rc=0]
agent/x  DENY          | cat <<E"OF"\nbody\nEOF\n%G% push origin main   [rc=0]
agent/x  DENY          | cat <<\EOF\nbody\nEOF\n%G% push origin main   [rc=0]
agent/x  DENY          | cat <<< word\n%G% push origin main   [rc=0]
agent/x  DENY          | cat <<<word\n%G% push origin main   [rc=0]
agent/x  DENY          | x=1; echo ${#x}; %G% push origin main   [rc=0]
agent/x  DENY          | echo ${#x}\n%G% push origin main   [rc=0]
agent/x  DENY          | echo $(( 1 + $(%G% push origin main) ))   [rc=0]
agent/x  DENY          | echo $((%G% push origin main) )   [rc=0]
agent/x  DENY          | %G% push origin main; echo %SOH%x   [rc=0]
agent/x  DENY          | nohup %G% push origin main   [rc=0]
agent/x  DENY          | timeout 60 %G% push origin main   [rc=0]
agent/x  DENY          | nice %G% push origin main   [rc=0]
agent/x  DENY          | sudo %G% push origin main   [rc=0]
agent/x  DENY          | env -i %G% push origin main   [rc=0]
agent/x  DENY          | command -p %G% push origin main   [rc=0]
agent/x  DENY          | time -p %G% push origin main   [rc=0]
agent/x  DENY          | %G% --config-env x=Y push origin main   [rc=0]
agent/x  DENY          | %U% push origin main   [rc=0]
agent/x  DENY          | %G% push origin "ma"in   [rc=0]
agent/x  DENY          | %G% push origin m\ain   [rc=0]
agent/x  DENY          | %G% push origin 'HEAD:main'   [rc=0]
agent/x  DENY          | %G% push origin HEAD:refs/heads/main --dry-run   [rc=0]
agent/x  DENY          | case x in x) %G% push origin main;; esac   [rc=0]
agent/x  DENY          | f() { %G% push origin main; }; f   [rc=0]
agent/x  DENY          | for b in a; do %G% push origin main; done   [rc=0]
agent/x  DENY          | %G% push origin main # c   [rc=0]
agent/x  DENY          | echo hi # %G% push origin main   [rc=0]
agent/x  DENY          | echo a#b; %G% push origin main   [rc=0]
agent/x  DENY          | timeout 60 %G% %P% origin %M%   [rc=0]
agent/x  DENY          | nohup %G% %P% origin %M%   [rc=0]
agent/x  DENY          | sudo %G% %P% origin %M%   [rc=0]
agent/x  DENY          | nice %G% %P% origin %M%   [rc=0]
agent/x  DENY          | env -i %G% %P% origin %M%   [rc=0]
agent/x  DENY          | command -p %G% %P% origin %M%   [rc=0]
agent/x  DENY          | time -p %G% %P% origin %M%   [rc=0]
agent/x  DENY          | %G% --config-env x=Y %P% origin %M%   [rc=0]
agent/x  DENY          | %U% %P% origin %M%   [rc=0]
agent/x  DENY          | %Gc% %P% origin %M%   [rc=0]
agent/x  DENY          | %G% %P% origin ma%BS%in   [rc=0]
agent/x  DENY          | %G% %P% origin m%BS%ain   [rc=0]
agent/x  DENY          | %G% %P% %BS%%NL%  origin %M%   [rc=0]
agent/x  DENY          | %G% %P% %BS%%NL%  -f   [rc=0]
agent/x  DENY          | %G% %P% --force %BS%%NL%  origin agent/x   [rc=0]
agent/x  DENY          | %G% commit -m %DQ%a%BS%%DQ%b%DQ%; %G% %P% origin %M%   [rc=0]
agent/x  DENY          | echo a%BS%%BS%b; %G% %P% origin %M%   [rc=0]
agent/x  allow-or-ask  | %DQ%C:%BS%Program Files%BS%Git%BS%cmd%BS%%G%.exe%DQ% %P% origin %M%   [rc=0]
agent/x  allow-or-ask  | C:%BS%%BS%Program%BS% Files%BS%%BS%Git%BS%%BS%cmd%BS%%BS%%G%.exe %P% origin %M%   [rc=0]
agent/x  DENY          | %DQ%C:/Program Files/Git/cmd/%G%.exe%DQ% %P% origin %M%   [rc=0]
agent/x  DENY          | /c/Program%BS% Files/Git/cmd/%G%.exe %P% origin %M%   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin ${B:-%M%}   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin ${B-%M%}   [rc=0]
agent/x  allow-or-ask  | %G% %P% --branches origin   [rc=0]
agent/x  allow-or-ask  | %G% %P% --mirr origin   [rc=0]
agent/x  allow-or-ask  | %G% %P% --al origin   [rc=0]
agent/x  DENY          | %G% %P% origin %M%%CR%   [rc=0]
agent/x  DENY          | %G% status%CR%%NL%%G% %P% origin %M%%CR%%NL%   [rc=0]
agent/x  DENY          | %G% %P% -f%CR%%NL%   [rc=0]
agent/x  DENY          | %G% %P% origin agent/x%SOH%; %G% %P% origin %M%   [rc=0]
agent/x  DENY          | %G% %P% origin %M%; echo %SOH%x   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin %SQ%refs/heads/*:refs/heads/*%SQ%   [rc=0]
agent/x  DENY          | %G% %P% origin HEAD:refs/heads/%M%   [rc=0]
agent/x  DENY          | %G% %P% origin HEAD --force-if-includes   [rc=0]
agent/x  DENY          | %G% %P% origin agent/x%TAB%-f   [rc=0]
agent/x  DENY          | %G% %P% origin agent/x%TAB%--force   [rc=0]
agent/x  DENY          | %G%%TAB%%P%%TAB%origin%TAB%%M%   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin agent/x   [rc=0]
agent/x  allow-or-ask  | %G% %P% -u origin agent/x   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin agent/fix-foo   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin agent/x:agent/main-notes   [rc=0]
agent/x  DENY          | %G% commit -m %DQ%fix %P% to %M% docs%DQ%   [rc=0]
agent/x  allow-or-ask  | cat <<%SQ%EOF%SQ%%NL%note %P% to %M%%NL%EOF   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin%NL%%M%   [rc=0]
agent/x  DENY          | ((x=1<<2))%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY          | $((1<<2))%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY          | x=$[1<<2]%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY          | cat <<<word%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY          | echo ${#x} %G% %P% origin %M%   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin ma{i,}n   [rc=0]
agent/x  allow-or-ask  | $%SQ%%BS%x67%SQ%it %P% origin %M%   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin ma%NUL%in   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin %M%%NUL%   [rc=0]
agent/x  DENY          | %G% -c alias.p=%P% p origin %M%   [rc=0]
agent/x  DENY          | %G% %P% origin @:%M%   [rc=0]
agent/x  DENY          | %G% %P% origin %M%~0   [rc=0]
agent/x  DENY          | %G% %P% origin +agent/x   [rc=0]
agent/x  DENY          | %G% %P% origin %SQ%+agent/x%SQ%   [rc=0]
agent/x  DENY          | %G% %P% -fu origin agent/x   [rc=0]
agent/x  DENY          | %G% %P% -uf origin agent/x   [rc=0]
agent/x  DENY          | %G% %P% --force-with-lease=agent/x origin agent/x   [rc=0]
agent/x  DENY          | %G% %P% origin --delete %M%   [rc=0]
agent/x  DENY          | %G% %P% origin :%M%   [rc=0]
agent/x  allow-or-ask  | %G% log --oneline %M%   [rc=0]
agent/x  allow-or-ask  | %G% %P% origin %M%-old   [rc=0]
main     DENY          | g%SQ%%SQ%it commit -m x   [rc=0]
main     DENY          | %DQ%g%DQ%it commit -m x   [rc=0]
main     DENY          | gi%BS%t commit -m x   [rc=0]
main     DENY          | %G% co%SQ%%SQ%mmit -m x   [rc=0]
main     DENY          | %G% c%BS%ommit -m x   [rc=0]
main     DENY          | %U% commit -m x   [rc=0]
main     DENY          | %Gc% commit -m x   [rc=0]
main     DENY          | timeout 60 %G% commit -m x   [rc=0]
main     DENY          | sudo %G% commit -m x   [rc=0]
main     DENY          | nohup %G% commit -m x   [rc=0]
main     DENY          | nice %G% commit -m x   [rc=0]
main     DENY          | %G% --config-env x=Y commit -m x   [rc=0]
main     allow-or-ask  | %DQ%C:%BS%Program Files%BS%Git%BS%cmd%BS%%G%.exe%DQ% commit -m x   [rc=0]
main     allow-or-ask  | C:%BS%%BS%Program%BS% Files%BS%%BS%Git%BS%%BS%cmd%BS%%BS%%G%.exe commit -m x   [rc=0]
main     DENY          | %DQ%C:/Program Files/Git/cmd/%G%.exe%DQ% commit -m x   [rc=0]
main     DENY          | /c/Program%BS% Files/Git/cmd/%G%.exe commit -m x   [rc=0]
main     DENY          | %G% commit -m x; echo %SOH%x   [rc=0]
main     DENY          | %G% commit%CR%%NL%   [rc=0]
main     DENY          | %G%%CR% commit -m x   [rc=0]
main     DENY          | %G% commit -m x%CR%%NL%   [rc=0]
main     DENY          | %G%%TAB%commit%TAB%-m%TAB%x   [rc=0]
main     allow-or-ask  | %G%%NUL% commit -m x   [rc=0]
main     allow-or-ask  | %G% commit-tree HEAD^{tree} | xargs %G% update-ref refs/heads/%M%   [rc=0]
main     allow-or-ask  | %G% pull   [rc=0]
main     DENY          | %G% merge x   [rc=0]
main     DENY          | %G% rebase x   [rc=0]
main     DENY          | %G% am x.patch   [rc=0]
main     DENY          | %G% cherry-pick x   [rc=0]
main     DENY          | %G% revert x   [rc=0]
main     DENY          | %G% -c alias.c=commit c -m x   [rc=0]
main     allow-or-ask  | %G% ci -m x   [rc=0]
main     DENY          | sh -c %DQ%%G% commit -m x%DQ%   [rc=0]
main     DENY          | bash <<EOF%NL%%G% commit -m x%NL%EOF   [rc=0]
main     DENY          | %G% status%NL%%NL%%NL%echo commit   [rc=0]
main     allow-or-ask  | %G% status   [rc=0]
main     allow-or-ask  | ls -la   [rc=0]
main     allow-or-ask  | #x%BS%%NL%%G% commit -m x   [rc=0]
main     allow-or-ask  | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
main     allow-or-ask  | ls #a%BS%%NL%%G% commit -m x   [rc=0]
main     allow-or-ask  | #x%BS%%NL%%G% push   [rc=0]
main     allow-or-ask  | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     allow-or-ask  | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     allow-or-ask  | echo a%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     allow-or-ask  | echo %SQ%a%BS%%NL%%SQ%%G% commit -m x   [rc=0]
main     DENY          | %G%%BS%%NL% commit -m x   [rc=0]
main     DENY          | gi%BS%%NL%t commit -m x   [rc=0]
main     DENY          | %G% com%BS%%NL%mit -m x   [rc=0]
main     allow-or-ask  | %G% commit%BS%%CR%%NL%-m x   [rc=0]
main     DENY          | %G% commit%CR%%NL%   [rc=0]
main     DENY          | %G%%CR% commit -m x   [rc=0]
main     DENY          | %CR%%G% commit -m x   [rc=0]
main     allow-or-ask  | x%CR%%G% commit -m x   [rc=0]
main     DENY          | %G% com%CR%mit -m x   [rc=0]
main     DENY          | gi%CR%t commit -m x   [rc=0]
main     DENY          | %G%%CR%%CR% commit   [rc=0]
main     DENY          | %G% commit -m x%BS%r   [rc=0]
main     allow-or-ask  | echo %G%%BS%r commit   [rc=0]
agent/x  allow-or-ask  | #x%BS%%NL%%G% push origin %M%   [rc=0]
agent/x  allow-or-ask  | #x%BS%%NL%%G% push -f   [rc=0]
agent/x  allow-or-ask  | echo a%BS%%BS%%NL%%G% push origin %M%   [rc=0]
agent/x  DENY          | %G% push origin %M%%CR%   [rc=0]
agent/x  DENY          | %G% push origin ma%CR%in   [rc=0]
agent/x  DENY          | %G% push origin %M%%BS%%NL%   [rc=0]
agent/x  allow-or-ask  | %G% push origin x%BS%%NL%%M%   [rc=0]
agent/x  DENY          | %G% push origin x %BS%%NL%%M%   [rc=0]
agent/x  DENY          | %G% %P%%BS%%NL% origin %M%   [rc=0]
agent/x  allow-or-ask  | %G% push%BS%%NL%origin %M%   [rc=0]
agent/x  DENY          | %G% push origin %M%%CR%%NL%   [rc=0]
agent/x  DENY          | %G% status%CR%%NL%%G% push origin %M%%CR%%NL%   [rc=0]
agent/x  DENY          | %G% push origin +x%CR%   [rc=0]
agent/x  DENY          | %G% push %CR%-f origin x   [rc=0]
agent/x  DENY          | %G% push origin %CR%+x   [rc=0]
agent/x  allow-or-ask  | %G% push origin %M%%BS%r   [rc=0]
agent/x  DENY          | %G% push origin %M%%BS%%CR%   [rc=0]
agent/x  allow-or-ask  | %G% push origin %M%%BS%%BS%r   [rc=0]
agent/x  DENY          | %G% push origin %CR%%M%   [rc=0]
agent/x  DENY          | %G% push --mir%CR%ror   [rc=0]
agent/x  allow-or-ask  | %G% push origin agent/x%CR%%NL%   [rc=0]
agent/x  allow-or-ask  | ls -la%CR%%NL%   [rc=0]
```

### Table B: host, no jq, new hook (132 rows)
```
main     DENY    commit-array                       rc=0
main     DENY    commit-crlf-payload                rc=0
main     DENY    commit-crlf-whole                  rc=0
main     silent  commit-dup-key                     rc=0
main     silent  commit-earlier-command-key         rc=0
main     DENY    commit-esc-bs-cr-lf-cont           rc=0
main     DENY    commit-esc-bs-cr                   rc=0
main     DENY    commit-esc-cr-in-git               rc=0
main     DENY    commit-esc-nul-after               rc=0
main     DENY    commit-invalid-utf8-before         rc=0
main     DENY    commit-invalid-utf8-inside         rc=0
main     DENY    commit-json-string                 rc=0
main     silent  commit-key-nl-value                rc=0
main     DENY    commit-latin1-cmd                  rc=0
main     DENY    commit-leading-space               rc=0
main     silent  commit-literal-bs-r                rc=0
main     DENY    commit-missing-brace               rc=0
main     DENY    commit-ok                          rc=0
main     DENY    commit-pretty                      rc=0
main     DENY    commit-raw-cr-after-verb           rc=0
main     DENY    commit-raw-cr-end                  rc=0
main     DENY    commit-raw-cr-in-git               rc=0
main     silent  commit-raw-newline-in-string       rc=0
main     DENY    commit-raw-nul-after               rc=0
main     DENY    commit-raw-nul-mid                 rc=0
main     DENY    commit-raw-soh-after               rc=0
main     DENY    commit-raw-soh-mid                 rc=0
main     DENY    commit-raw-text                    rc=0
main     DENY    commit-toolInput                   rc=0
main     silent  commit-truncated                   rc=0
main     silent  commit-uescape                     rc=0
main     silent  empty-command                      rc=0
main     silent  empty-stdin                        rc=0
main     silent  no-command                         rc=0
main     silent  only-brace                         rc=0
main     DENY    push-array                         rc=0
main     DENY    push-crlf-payload                  rc=0
main     DENY    push-crlf-whole                    rc=0
main     silent  push-dup-key                       rc=0
main     silent  push-earlier-command-key           rc=0
main     DENY    push-esc-bs-cr-lf-cont             rc=0
main     DENY    push-esc-bs-cr                     rc=0
main     DENY    push-esc-cr-in-git                 rc=0
main     DENY    push-esc-nul-after                 rc=0
main     DENY    push-invalid-utf8-before           rc=0
main     DENY    push-invalid-utf8-inside           rc=0
main     DENY    push-json-string                   rc=0
main     silent  push-key-nl-value                  rc=0
main     DENY    push-latin1-cmd                    rc=0
main     DENY    push-leading-space                 rc=0
main     silent  push-literal-bs-r                  rc=0
main     DENY    push-missing-brace                 rc=0
main     DENY    push-ok                            rc=0
main     DENY    push-pretty                        rc=0
main     DENY    push-raw-cr-after-verb             rc=0
main     DENY    push-raw-cr-end                    rc=0
main     DENY    push-raw-cr-in-git                 rc=0
main     silent  push-raw-newline-in-string         rc=0
main     DENY    push-raw-nul-after                 rc=0
main     DENY    push-raw-nul-mid                   rc=0
main     DENY    push-raw-soh-after                 rc=0
main     DENY    push-raw-soh-mid                   rc=0
main     DENY    push-raw-text                      rc=0
main     DENY    push-toolInput                     rc=0
main     silent  push-truncated                     rc=0
main     silent  push-uescape                       rc=0
agent/x  silent  commit-array                       rc=0
agent/x  silent  commit-crlf-payload                rc=0
agent/x  silent  commit-crlf-whole                  rc=0
agent/x  silent  commit-dup-key                     rc=0
agent/x  silent  commit-earlier-command-key         rc=0
agent/x  silent  commit-esc-bs-cr-lf-cont           rc=0
agent/x  silent  commit-esc-bs-cr                   rc=0
agent/x  silent  commit-esc-cr-in-git               rc=0
agent/x  silent  commit-esc-nul-after               rc=0
agent/x  silent  commit-invalid-utf8-before         rc=0
agent/x  silent  commit-invalid-utf8-inside         rc=0
agent/x  silent  commit-json-string                 rc=0
agent/x  silent  commit-key-nl-value                rc=0
agent/x  silent  commit-latin1-cmd                  rc=0
agent/x  silent  commit-leading-space               rc=0
agent/x  silent  commit-literal-bs-r                rc=0
agent/x  silent  commit-missing-brace               rc=0
agent/x  silent  commit-ok                          rc=0
agent/x  silent  commit-pretty                      rc=0
agent/x  silent  commit-raw-cr-after-verb           rc=0
agent/x  silent  commit-raw-cr-end                  rc=0
agent/x  silent  commit-raw-cr-in-git               rc=0
agent/x  silent  commit-raw-newline-in-string       rc=0
agent/x  silent  commit-raw-nul-after               rc=0
agent/x  silent  commit-raw-nul-mid                 rc=0
agent/x  silent  commit-raw-soh-after               rc=0
agent/x  silent  commit-raw-soh-mid                 rc=0
agent/x  silent  commit-raw-text                    rc=0
agent/x  silent  commit-toolInput                   rc=0
agent/x  silent  commit-truncated                   rc=0
agent/x  silent  commit-uescape                     rc=0
agent/x  silent  empty-command                      rc=0
agent/x  silent  empty-stdin                        rc=0
agent/x  silent  no-command                         rc=0
agent/x  silent  only-brace                         rc=0
agent/x  DENY    push-array                         rc=0
agent/x  DENY    push-crlf-payload                  rc=0
agent/x  DENY    push-crlf-whole                    rc=0
agent/x  silent  push-dup-key                       rc=0
agent/x  silent  push-earlier-command-key           rc=0
agent/x  DENY    push-esc-bs-cr-lf-cont             rc=0
agent/x  DENY    push-esc-bs-cr                     rc=0
agent/x  DENY    push-esc-cr-in-git                 rc=0
agent/x  DENY    push-esc-nul-after                 rc=0
agent/x  DENY    push-invalid-utf8-before           rc=0
agent/x  DENY    push-invalid-utf8-inside           rc=0
agent/x  DENY    push-json-string                   rc=0
agent/x  silent  push-key-nl-value                  rc=0
agent/x  DENY    push-latin1-cmd                    rc=0
agent/x  DENY    push-leading-space                 rc=0
agent/x  silent  push-literal-bs-r                  rc=0
agent/x  DENY    push-missing-brace                 rc=0
agent/x  DENY    push-ok                            rc=0
agent/x  DENY    push-pretty                        rc=0
agent/x  DENY    push-raw-cr-after-verb             rc=0
agent/x  DENY    push-raw-cr-end                    rc=0
agent/x  DENY    push-raw-cr-in-git                 rc=0
agent/x  silent  push-raw-newline-in-string         rc=0
agent/x  DENY    push-raw-nul-after                 rc=0
agent/x  DENY    push-raw-nul-mid                   rc=0
agent/x  DENY    push-raw-soh-after                 rc=0
agent/x  DENY    push-raw-soh-mid                   rc=0
agent/x  DENY    push-raw-text                      rc=0
agent/x  DENY    push-toolInput                     rc=0
agent/x  silent  push-truncated                     rc=0
agent/x  silent  push-uescape                       rc=0
```

### Table B diffs
```
# old hook vs new hook (host)
6c6
< main     silent  commit-esc-bs-cr-lf-cont           rc=0
---
> main     DENY    commit-esc-bs-cr-lf-cont           rc=0
8c8
< main     silent  commit-esc-cr-in-git               rc=0
---
> main     DENY    commit-esc-cr-in-git               rc=0
22c22
< main     silent  commit-raw-cr-in-git               rc=0
---
> main     DENY    commit-raw-cr-in-git               rc=0
41c41
< main     silent  push-esc-bs-cr-lf-cont             rc=0
---
> main     DENY    push-esc-bs-cr-lf-cont             rc=0
43c43
< main     silent  push-esc-cr-in-git                 rc=0
---
> main     DENY    push-esc-cr-in-git                 rc=0
57c57
< main     silent  push-raw-cr-in-git                 rc=0
---
> main     DENY    push-raw-cr-in-git                 rc=0
107,109c107,109
< agent/x  silent  push-esc-bs-cr-lf-cont             rc=0
< agent/x  silent  push-esc-bs-cr                     rc=0
< agent/x  silent  push-esc-cr-in-git                 rc=0
---
> agent/x  DENY    push-esc-bs-cr-lf-cont             rc=0
> agent/x  DENY    push-esc-bs-cr                     rc=0
> agent/x  DENY    push-esc-cr-in-git                 rc=0
123c123
< agent/x  silent  push-raw-cr-in-git                 rc=0
---
> agent/x  DENY    push-raw-cr-in-git                 rc=0
# host no-jq vs image no-jq
10,11c10,11
< main     DENY    commit-invalid-utf8-before         rc=0
< main     DENY    commit-invalid-utf8-inside         rc=0
---
> main     silent  commit-invalid-utf8-before         rc=0
> main     silent  commit-invalid-utf8-inside         rc=0
14c14
< main     DENY    commit-latin1-cmd                  rc=0
---
> main     silent  commit-latin1-cmd                  rc=0
45,46c45,46
< main     DENY    push-invalid-utf8-before           rc=0
< main     DENY    push-invalid-utf8-inside           rc=0
---
> main     silent  push-invalid-utf8-before           rc=0
> main     silent  push-invalid-utf8-inside           rc=0
49c49
< main     DENY    push-latin1-cmd                    rc=0
---
> main     silent  push-latin1-cmd                    rc=0
111,112c111,112
< agent/x  DENY    push-invalid-utf8-before           rc=0
< agent/x  DENY    push-invalid-utf8-inside           rc=0
---
> agent/x  silent  push-invalid-utf8-before           rc=0
> agent/x  silent  push-invalid-utf8-inside           rc=0
115c115
< agent/x  DENY    push-latin1-cmd                    rc=0
---
> agent/x  silent  push-latin1-cmd                    rc=0
# image no-jq vs image jq
4,5c4,5
< main     silent  commit-dup-key                     rc=0
< main     silent  commit-earlier-command-key         rc=0
---
> main     DENY    commit-dup-key                     rc=0
> main     DENY    commit-earlier-command-key         rc=0
10,11c10,11
< main     silent  commit-invalid-utf8-before         rc=0
< main     silent  commit-invalid-utf8-inside         rc=0
---
> main     DENY    commit-invalid-utf8-before         rc=0
> main     DENY    commit-invalid-utf8-inside         rc=0
13,14c13,14
< main     silent  commit-key-nl-value                rc=0
< main     silent  commit-latin1-cmd                  rc=0
---
> main     DENY    commit-key-nl-value                rc=0
> main     DENY    commit-latin1-cmd                  rc=0
31c31
< main     silent  commit-uescape                     rc=0
---
> main     DENY    commit-uescape                     rc=0
39,40c39,40
< main     silent  push-dup-key                       rc=0
< main     silent  push-earlier-command-key           rc=0
---
> main     DENY    push-dup-key                       rc=0
> main     DENY    push-earlier-command-key           rc=0
45,46c45,46
< main     silent  push-invalid-utf8-before           rc=0
< main     silent  push-invalid-utf8-inside           rc=0
---
> main     DENY    push-invalid-utf8-before           rc=0
> main     DENY    push-invalid-utf8-inside           rc=0
48,49c48,49
< main     silent  push-key-nl-value                  rc=0
< main     silent  push-latin1-cmd                    rc=0
---
> main     DENY    push-key-nl-value                  rc=0
> main     DENY    push-latin1-cmd                    rc=0
66c66
< main     silent  push-uescape                       rc=0
---
> main     DENY    push-uescape                       rc=0
105,106c105,106
< agent/x  silent  push-dup-key                       rc=0
< agent/x  silent  push-earlier-command-key           rc=0
---
> agent/x  DENY    push-dup-key                       rc=0
> agent/x  DENY    push-earlier-command-key           rc=0
111,112c111,112
< agent/x  silent  push-invalid-utf8-before           rc=0
< agent/x  silent  push-invalid-utf8-inside           rc=0
---
> agent/x  DENY    push-invalid-utf8-before           rc=0
> agent/x  DENY    push-invalid-utf8-inside           rc=0
114,115c114,115
< agent/x  silent  push-key-nl-value                  rc=0
< agent/x  silent  push-latin1-cmd                    rc=0
---
> agent/x  DENY    push-key-nl-value                  rc=0
> agent/x  DENY    push-latin1-cmd                    rc=0
132c132
< agent/x  silent  push-uescape                       rc=0
---
> agent/x  DENY    push-uescape                       rc=0
```

### Table C: 5 MB payloads (host no-jq row | image jq | image no-jq)
```
main     DENY    commit-bsl-end           3938 ms| DENY 404 ms| DENY 2167 ms
main     DENY    commit-bsnl-end          3940 ms| DENY 490 ms| DENY 1795 ms
main     DENY    commit-crlines-end       3732 ms| DENY 358 ms| DENY 1645 ms
main     DENY    commit-crs-end           3552 ms| DENY 436 ms| DENY 1898 ms
main     DENY    commit-escq-end          3566 ms| DENY 440 ms| DENY 1965 ms
main     DENY    commit-heredoc-end       4554 ms| DENY 408 ms| DENY 1652 ms
main     DENY    commit-lines-end         3911 ms| DENY 418 ms| DENY 1631 ms
main     DENY    commit-short-end         2135 ms| DENY 647 ms| DENY 1726 ms
main     DENY    commit-start-token       2052 ms| DENY 402 ms| DENY 1444 ms
main     DENY    commit-token-end         2033 ms| DENY 535 ms| DENY 1587 ms
main     DENY    push-bsl-end             3846 ms| DENY 385 ms| DENY 2060 ms
main     DENY    push-bsnl-end            3897 ms| DENY 488 ms| DENY 1797 ms
main     DENY    push-crlines-end         3715 ms| DENY 371 ms| DENY 1701 ms
main     DENY    push-crs-end             3537 ms| DENY 445 ms| DENY 2219 ms
main     DENY    push-escq-end            3593 ms| DENY 394 ms| DENY 2053 ms
main     DENY    push-heredoc-end         4516 ms| DENY 364 ms| DENY 1689 ms
main     DENY    push-lines-end           4306 ms| DENY 387 ms| DENY 1609 ms
main     DENY    push-short-end           2131 ms| DENY 578 ms| DENY 1679 ms
main     DENY    push-start-token         2141 ms| DENY 376 ms| DENY 1521 ms
main     DENY    push-token-end           2073 ms| DENY 530 ms| DENY 1716 ms
agent/x  DENY    push-bsl-end             4053 ms| DENY 341 ms| DENY 2029 ms
agent/x  DENY    push-bsnl-end            3785 ms| DENY 411 ms| DENY 1696 ms
agent/x  DENY    push-crlines-end         3679 ms| DENY 336 ms| DENY 1601 ms
agent/x  DENY    push-crs-end             3532 ms| DENY 430 ms| DENY 1871 ms
agent/x  DENY    push-escq-end            3473 ms| DENY 328 ms| DENY 1965 ms
agent/x  DENY    push-heredoc-end         4506 ms| DENY 323 ms| DENY 1653 ms
agent/x  DENY    push-lines-end           3973 ms| DENY 318 ms| DENY 1608 ms
agent/x  DENY    push-short-end           1978 ms| DENY 424 ms| DENY 1549 ms
agent/x  DENY    push-start-token         1993 ms| DENY 425 ms| DENY 1523 ms
agent/x  DENY    push-token-end           2059 ms| DENY 336 ms| DENY 1398 ms
```
