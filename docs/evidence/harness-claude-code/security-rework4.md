# Security re-audit, rework 4: harness-claude-code (2026-10-18)

Scope: `git diff 886de45` plus untracked in-scope files (excluded: docs/knowledge-engine-claude-code-prompt.md, .venv/).
Production change since rework 3: scripts/hooks/block-main-commit.sh only (rewritten per ADR-KE-001 "simple fail-safe
text rule"), plus tests, docs and evidence. .claude/settings.json unchanged (hook only, timeout 10).
Judged against requirements.md criterion 4 (4a-4f, round-4 text) and the ADR's accepted false positives and bypasses.
Notation: <bs> = one backslash.

## Verdict: PASS (0 critical, 0 high; 1 medium, 4 low, rest info, all non-blocking)

## Method
Payloads only, piped to the hook in scratch repos (branch set with `git symbolic-ref`), never a real commit to this repo.
Same compact Claude Code payload generator as rework 3; control bytes, backslashes and CR built from character codes.
Three modes: Windows host (Git Bash: bash 5.3.9 Cygwin, GNU grep 3.0, GNU sed 4.9, no jq; gawk present, the hook no longer
uses awk), gates image with jq 1.6 (grep 3.8, bash 5.2.15), gates image with jq replaced by a stub that exits 127.
- Table A: 288 rows = the 187 rework-3 rows + 101 new rows (M1 leading words, H2 backslash forms, L13 split/cased words,
  CR, NUL, 0x01, tab, Windows paths, push option spellings, accepted false positives and bypasses).
- Table B: 52 malformed or unusual payloads x 2 branches.
- Table C: 5 MB commands (8.7 MB payloads for the backslash shapes), 7 shapes, on and off main.

## Fixed / confirmed since rework 3
- H2 fixed: host no-jq output is identical to image no-jq output on all 288 rows (no awk, so no dialect split).
  Line continuation, continuation + `-f`, escaped quote then a push, `ma<bs>in`, `m<bs>ain`, `a<bs><bs>b`: DENY in all modes.
- L13 fixed: `g''it`, `"g"it`, `gi<bs>t`, `co''mmit`, `c<bs>ommit`, uppercase `GIT` / `Git` commit on main: DENY in all modes.
- M1 fixed: `timeout 60`, nohup, nice, sudo, `env -i`, `command -p`, `time -p`, `--config-env x=Y`, uppercase: DENY off main.
- L10 fixed: `((x=1<<2))`, `$[..]`, quoted / backslash heredoc delimiters, here-strings, `${#x}`, `$(( $(..) ))`: DENY.
- L14 fixed: 0x01 before or after the command no longer hides it (DENY in all modes, raw byte or JSON escape).
- M3 / 4f met: 5 MB, all shapes, every row DENY. Host no-jq 2.0-4.6 s; image jq 0.33-0.58 s; image no-jq 1.4-2.1 s
  (10 s hook timeout; 4f's 3 s budget is for 1 MB in the image).
- Never `allow`: 0 allow outputs in 864 Table-A rows, 312 Table-B rows and 63 Table-C rows; every exit code 0.
- Accepted false positives confirmed (fail safe): one-line mentions such as a commit message naming push to main, `echo`
  of a push command, `bash -c` / `sh -c` / `"$(..)"` wrappers: DENY off main. Accepted bypasses confirmed silent off main:
  ANSI-C hex quoting, brace tricks, `${B:-main}`, a push split across lines, update-ref, gh, aliases.

## Findings

### Critical / High
None.

### Medium (non-blocking)
- M4 (new) A carriage return in the command fails open on the Windows host, on and off main. The host bash (Cygwin) drops
  unquoted CR while parsing (verified with `bash file` and with `eval`; `igncr` is off). Demonstrated in a scratch repo:
  a script whose only line is the git push-to-main command followed by CR LF created `main` on a bare local remote;
  `git<CR> --version` runs git. The no-jq extractor leaves the JSON `<bs>r` escape in place and normalisation then
  deletes only its backslash, so the word becomes `mainr` / `commitr` / `gitr`. Silent rows (host and image no-jq; jq
  mode DENY, since a raw CR is a separator):
    - off main: the push-to-main command + CR; `git status` CR LF, then the push-to-main command + CR LF
    - on main: `git commit` + CR LF; `git` + CR + ` commit -m x`
  Still denied: `git commit -m x` + CR LF, and the `-f` push + CR LF (the CR lands after a word that does not matter).
  No 4e bypass class covers it (the words are not hidden). Medium, not high: Claude does not normally put CR in a Bash
  command, and the CR must sit right after `git`, the verb or `main`. The gates image cannot show it (Linux bash keeps
  the CR, so the command there would fail), the same host-only blind spot as H2.
  Fix (developer): in the sed extractor drop the `<bs>r` escape (after the double-backslash placeholder step); in
  normalisation also delete raw CR (tr -d with the CR byte), so jq mode matches host bash for a CR inside a word too.
  Add the four rows above to the hook tests (both modes) and to the host live check.

### Low (non-blocking)
- L16 (new) Windows backslash path: `"C:<bs>Program Files<bs>Git<bs>cmd<bs>git.exe" commit -m x` on main, and the same
  path with a push to main off main, are silent in all three modes. Deleting backslashes joins `cmd` and `git` into one
  word, so the word `git` is gone. Host bash runs that path (verified with `--version`). The forward-slash and
  `/c/Program<bs> Files/` forms are denied. Conforms to 4b (backslashes deleted) but fails open with visible words on
  main. Uncommon. Fix: also run the rules on a second normalisation with backslashes replaced by a space; deny if
  either matches.
- L17 (new, spec gap) Off main, push options that push every branch without naming it: `--branches` (an alias of
  `--all` in host git 2.54, per its `-h` help) and the unambiguous abbreviations `--mirr` and `--al` (the option parser
  accepts them; verified on host). Silent. Fix (analyst/developer): add `--branches` and the prefixes (`--mi..`, `--al`,
  `--br..`) to 4d.
- L18 (info, changed by design) On main, `git commit-tree .. | xargs git update-ref refs/heads/main` and
  `git pull --no-rebase origin main` are now silent (rework 3: DENY). Neither is in 4c's verb list (`commit-tree` is one
  word, since `-` counts as a word character). 4e accepts update-ref only off main. Suggest the analyst decide whether
  4c should add `pull` and `update-ref` (cheap and fail safe).
- L19 (new, info, unreachable) Payloads where no-jq is silent and jq denies: a duplicate `command` key or an earlier
  `command` key in another object (no-jq takes the first match), the JSON escape `<bs>u0067it`, invalid UTF-8 or
  Latin-1 bytes in the image (grep 3.8 will not match across them; host grep 3.0 denies). Silent in every mode:
  truncated JSON (rework 3: DENY) and a raw newline inside the JSON string. Raw or escaped NUL: jq DENY, no-jq silent.
  None is reachable: Claude Code sends Node JSON.stringify output (valid UTF-8, one `command` key, newlines escaped, no
  unicode escape for printable ASCII), and Node refuses NUL in spawn arguments.
- L15 (unchanged) No-jq: a newline between `"command":` and its value is silent; jq denies. Unreachable.
- L12 (narrowed) The hook tests run only in the gates image. awk is gone, but M4 shows host bash still differs from
  Linux bash. hook-live-host-r4.txt covers 20 host cases; add the CR rows there.
- Unchanged: L11 (unicode escapes, unreachable), L2 (gates container root, rw bind mount), L5 (KE_IN_GATES=1 skips the
  container), L7 (analyst/marketer web tools plus Bash). Not in spec: wildcard refspecs; `git checkout main && git commit`
  off main; `git -C ../other commit`.

## Secrets and local paths
Grep (AWS/GitHub/Slack/OpenAI/Anthropic/Google key shapes, private keys, user:pass@ URLs, key/secret/password/token
assignments, Bearer, emails, Windows profile / AppData / home paths, host username, repo absolute path) over the
evidence files new since rework 3 (analyst-req4-r4.md, architect-hook-adr.md, green-rework4.txt, hook-live-host-r4.txt,
hook-timing-host-r4.txt, mutation-hook-r4.txt, red-rework4.txt) plus review-rework3.md and every file changed since
rework 3 (hook, hook tests, architecture.md, requirements.md, handoff): 2698 lines. One hit, a false positive: a test
dict key named "unquoted token". No secrets, no profile paths, no username, no absolute repo path.

## Raw output
"allow-or-ask" / "silent" = no output, exit 0 (normal permission flow). Every row rc=0. Rows use the probe tokens:
%G% = the git word, %U% = it in upper case, %Gc% = it capitalised, %P% = the push verb, %M% = the main branch name,
%BS% = one backslash, %NL% = newline, %CR% = carriage return, %TAB% = tab, %SOH% = byte 0x01, %NUL% = byte 0x00,
%DQ% / %SQ% = double / single quote. In the 187 rework-3 rows a literal <bs>n is a newline and a literal backslash is
one backslash.

### Table A: host, no jq (288 rows)
Image no-jq output is identical to this table. Image jq differs only in the CR and NUL rows (jq DENY), listed after it.
```
main     DENY          | %G% commit -m x
main     DENY          | %G% commit
main     DENY          | %G% push
main     DENY          | %G% commit -m "x"
main     DENY          | %G%_AUTHOR_NAME=a %G% commit -m x
main     DENY          | bash -c "%G% commit -m x"
main     allow-or-ask  | %G% ci -m x
main     DENY          | %G% -c alias.c=commit c -m x
main     allow-or-ask  | gh pr merge 1 --merge
main     allow-or-ask  | gh api repos/o/r/%G%/refs/heads/main -X PATCH
main     allow-or-ask  | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"
main     DENY          | g=%G%; $g commit -m x
main     DENY          | %G% merge feature
main     DENY          | %G% merge
main     DENY          | %G% cherry-pick abc
main     DENY          | %G% am p.patch
main     DENY          | %G% rebase x
main     DENY          | %G% revert abc
main     allow-or-ask  | %G% pull
main     allow-or-ask  | %G% pull origin main
main     allow-or-ask  | %G% reset --hard x
main     allow-or-ask  | %G% commit-tree HEAD^{tree} | xargs %G% update-ref refs/heads/main
main     allow-or-ask  | echo digital push-ups
main     DENY          | %G% log --grep=push
main     allow-or-ask  | %G% status
main     allow-or-ask  | ls -la
agent/x  DENY          | %G% push origin HEAD:main
agent/x  DENY          | %G% push origin agent/x:main
agent/x  DENY          | %G% push origin "HEAD:main"
agent/x  DENY          | %G% push origin "main"
agent/x  DENY          | %G% push origin 'main'
agent/x  DENY          | %G% push origin main
agent/x  DENY          | %G% push origin HEAD:refs/heads/main
agent/x  DENY          | %G% push origin :main
agent/x  DENY          | %G% push --delete origin main
agent/x  DENY          | %G% push --force origin main
agent/x  DENY          | %G% push --force origin agent/x
agent/x  DENY          | %G% push -f
agent/x  DENY          | %G% push --force-with-lease
agent/x  DENY          | %G% push origin +agent/x
agent/x  DENY          | %G% push origin +HEAD:main
agent/x  DENY          | %G% push --mirror
agent/x  DENY          | %G% push --all origin
agent/x  DENY          | %G% push origin ma\in
agent/x  DENY          | %G% push origin $(echo main)
agent/x  allow-or-ask  | %G% push origin refs/heads/*:refs/heads/*
agent/x  allow-or-ask  | %G% checkout main && %G% commit -m x
agent/x  allow-or-ask  | %G% switch main; %G% commit -m x
agent/x  allow-or-ask  | %G% -C ../other-main-checkout commit -m x
agent/x  allow-or-ask  | %G% update-ref refs/heads/main HEAD
agent/x  allow-or-ask  | %G% push origin agent/x
agent/x  allow-or-ask  | %G% push -u origin agent/x
agent/x  allow-or-ask  | %G% push
main     DENY          | (%G% commit -m x)
main     DENY          | { %G% commit -m x; }
main     DENY          | if true; then %G% commit -m x; fi
main     DENY          | time %G% commit -m x
main     DENY          | command %G% commit -m x
main     DENY          | env %G% commit -m x
main     DENY          | ! %G% commit -m x
main     DENY          | exec %G% commit -m x
main     DENY          | true & %G% commit -m x
main     DENY          | >/dev/null %G% commit -m x
main     DENY          | echo $(%G% commit -m x)
main     DENY          | echo `%G% commit -m x`
main     DENY          | xargs %G% commit -m x < /dev/null
main     DENY          | cd . && %G% commit -m x
main     DENY          | %G% --no-pager commit -m x
main     DENY          | %G% -P commit -m x
main     DENY          | %G% --git-dir=.git commit -m x
main     DENY          | %G% -C . -c user.name=a commit -m x
main     DENY          | %G% commit -m "$(cat <<'EOF'\nmsg\nEOF\n)"
main     DENY          | "%G%" commit -m x
main     DENY          | g''it commit -m x
main     DENY          | /usr/bin/%G% commit -m x
main     DENY          | %G%.exe commit -m x
main     DENY          | %G% -c core.hooksPath=/dev/null commit -m x
main     DENY          | echo $((1<<2))\n%G% commit -m x
main     DENY          | cat <<EOF\nhi\nEOF\n%G% commit -m x
main     DENY          | cat <<'EOF' > f\ngit push origin main\nEOF
agent/x  DENY          | %G% push origin $'main'
agent/x  DENY          | %G% push origin m"a"in
agent/x  DENY          | %G% push origin HEAD:MAIN
agent/x  DENY          | %G% push origin main:main
agent/x  DENY          | %G% push --force-if-includes origin agent/x
agent/x  DENY          | %G% push origin --force
agent/x  DENY          | %G% push -v -f
agent/x  DENY          | %G% push --repo=origin main
agent/x  DENY          | %G% push origin HEAD:refs/heads/master
agent/x  DENY          | %G% push origin refs/heads/agent/x:refs/heads/main
agent/x  DENY          | %G% push upstream main~0
agent/x  DENY          | %G% push origin @:main
agent/x  DENY          | echo $((1<<2))\n%G% push origin main
agent/x  DENY          | %G% commit -m "push to main"
agent/x  DENY          | %G% commit -m "x" -m 'git push -f'
agent/x  DENY          | echo "git push origin main"
agent/x  allow-or-ask  | %G% log --oneline main
main     DENY          | bash -c "%G% commit -m x"
main     DENY          | sh -c '%G% commit -m x'
main     DENY          | xargs %G% commit -m x < /dev/null
main     DENY          | echo "$(%G% commit -m x)"
main     DENY          | cat <<'EOF' > f\n%G% commit -m x\nEOF
main     DENY          | %G% commit -m x; echo %SOH%x
main     DENY          | %G% push; echo a%SOH%b
main     DENY          | "g"it commit -m x
main     DENY          | gi\t commit -m x
main     DENY          | %G% co''mmit -m x
main     DENY          | %G% c\ommit -m x
main     DENY          | %G% "commit" -m x
main     DENY          | %U% commit -m x
main     DENY          | Git commit -m x
main     DENY          | %G%.EXE commit -m x
main     allow-or-ask  | $'\x67'it commit -m x
main     allow-or-ask  | %G% pull
main     allow-or-ask  | %G% pull --no-rebase origin main
main     DENY          | nohup %G% commit -m x
main     DENY          | timeout 60 %G% commit -m x
main     DENY          | ((x=1<<2))\n%G% commit -m x
main     DENY          | echo $((%G% commit -m x) )
master   DENY          | %G% commit -m x
master   DENY          | %G% push
agent/x  DENY          | (%G% push origin main)
agent/x  DENY          | { %G% push origin main; }
agent/x  DENY          | if %G% push origin main; then :; fi
agent/x  DENY          | true & %G% push origin main
agent/x  DENY          | >/dev/null %G% push origin main
agent/x  DENY          | 2>&1 %G% push origin main
agent/x  DENY          | echo $(%G% push origin main)
agent/x  DENY          | echo `%G% push origin main`
agent/x  DENY          | echo $((1<<2))\n%G% push origin main
agent/x  DENY          | echo $((1<<2)) && %G% push origin main
agent/x  DENY          | while %G% push origin main; do :; done
agent/x  DENY          | until %G% push -f; do :; done
agent/x  DENY          | ! %G% push origin main
agent/x  DENY          | time %G% push origin main
agent/x  DENY          | command %G% push origin main
agent/x  DENY          | env %G% push origin main
agent/x  DENY          | exec %G% push origin main
agent/x  DENY          | X=1 Y=2 %G% push origin main
agent/x  DENY          | %G% push -fu origin agent/x
agent/x  DENY          | %G% push -uf origin agent/x
agent/x  DENY          | %G% -c x=y push origin main
agent/x  DENY          | %G% -C . push origin main
agent/x  DENY          | %G% push origin HEAD:refs/heads/main
agent/x  DENY          | %G% push origin :main
agent/x  DENY          | %G% push --force-with-lease=agent/x origin agent/x
agent/x  DENY          | %G% push origin HEAD:master
agent/x  DENY          | %G% commit -m "fix push to main docs"
agent/x  DENY          | %G% commit -m "note push -f is denied"
agent/x  DENY          | %G% commit -m "$(cat <<'EOF'\nsee git push to main\nEOF\n)"
agent/x  DENY          | echo "git push origin main"
agent/x  allow-or-ask  | %G% log --grep push
agent/x  DENY          | echo "$(%G% push origin main)"
agent/x  DENY          | bash -c "%G% push origin main"
agent/x  DENY          | sh -c '%G% push origin main'
agent/x  DENY          | xargs %G% push origin main < /dev/null
agent/x  DENY          | ((x=1<<2))\n%G% push origin main
agent/x  DENY          | echo $[1<<2]\n%G% push origin main
agent/x  DENY          | cat <<"E"OF\nbody\nEOF\n%G% push origin main
agent/x  DENY          | cat <<E"OF"\nbody\nEOF\n%G% push origin main
agent/x  DENY          | cat <<\EOF\nbody\nEOF\n%G% push origin main
agent/x  DENY          | cat <<< word\n%G% push origin main
agent/x  DENY          | cat <<<word\n%G% push origin main
agent/x  DENY          | x=1; echo ${#x}; %G% push origin main
agent/x  DENY          | echo ${#x}\n%G% push origin main
agent/x  DENY          | echo $(( 1 + $(%G% push origin main) ))
agent/x  DENY          | echo $((%G% push origin main) )
agent/x  DENY          | %G% push origin main; echo %SOH%x
agent/x  DENY          | nohup %G% push origin main
agent/x  DENY          | timeout 60 %G% push origin main
agent/x  DENY          | nice %G% push origin main
agent/x  DENY          | sudo %G% push origin main
agent/x  DENY          | env -i %G% push origin main
agent/x  DENY          | command -p %G% push origin main
agent/x  DENY          | time -p %G% push origin main
agent/x  DENY          | %G% --config-env x=Y push origin main
agent/x  DENY          | %U% push origin main
agent/x  DENY          | %G% push origin "ma"in
agent/x  DENY          | %G% push origin m\ain
agent/x  DENY          | %G% push origin 'HEAD:main'
agent/x  DENY          | %G% push origin HEAD:refs/heads/main --dry-run
agent/x  DENY          | case x in x) %G% push origin main;; esac
agent/x  DENY          | f() { %G% push origin main; }; f
agent/x  DENY          | for b in a; do %G% push origin main; done
agent/x  DENY          | %G% push origin main # c
agent/x  DENY          | echo hi # %G% push origin main
agent/x  DENY          | echo a#b; %G% push origin main
agent/x  DENY          | timeout 60 %G% %P% origin %M%
agent/x  DENY          | nohup %G% %P% origin %M%
agent/x  DENY          | sudo %G% %P% origin %M%
agent/x  DENY          | nice %G% %P% origin %M%
agent/x  DENY          | env -i %G% %P% origin %M%
agent/x  DENY          | command -p %G% %P% origin %M%
agent/x  DENY          | time -p %G% %P% origin %M%
agent/x  DENY          | %G% --config-env x=Y %P% origin %M%
agent/x  DENY          | %U% %P% origin %M%
agent/x  DENY          | %Gc% %P% origin %M%
agent/x  DENY          | %G% %P% origin ma%BS%in
agent/x  DENY          | %G% %P% origin m%BS%ain
agent/x  DENY          | %G% %P% %BS%%NL%  origin %M%
agent/x  DENY          | %G% %P% %BS%%NL%  -f
agent/x  DENY          | %G% %P% --force %BS%%NL%  origin agent/x
agent/x  DENY          | %G% commit -m %DQ%a%BS%%DQ%b%DQ%; %G% %P% origin %M%
agent/x  DENY          | echo a%BS%%BS%b; %G% %P% origin %M%
agent/x  allow-or-ask  | %DQ%C:%BS%Program Files%BS%Git%BS%cmd%BS%%G%.exe%DQ% %P% origin %M%
agent/x  allow-or-ask  | C:%BS%%BS%Program%BS% Files%BS%%BS%Git%BS%%BS%cmd%BS%%BS%%G%.exe %P% origin %M%
agent/x  DENY          | %DQ%C:/Program Files/Git/cmd/%G%.exe%DQ% %P% origin %M%
agent/x  DENY          | /c/Program%BS% Files/Git/cmd/%G%.exe %P% origin %M%
agent/x  allow-or-ask  | %G% %P% origin ${B:-%M%}
agent/x  allow-or-ask  | %G% %P% origin ${B-%M%}
agent/x  allow-or-ask  | %G% %P% --branches origin
agent/x  allow-or-ask  | %G% %P% --mirr origin
agent/x  allow-or-ask  | %G% %P% --al origin
agent/x  allow-or-ask  | %G% %P% origin %M%%CR%
agent/x  allow-or-ask  | %G% status%CR%%NL%%G% %P% origin %M%%CR%%NL%
agent/x  DENY          | %G% %P% -f%CR%%NL%
agent/x  DENY          | %G% %P% origin agent/x%SOH%; %G% %P% origin %M%
agent/x  DENY          | %G% %P% origin %M%; echo %SOH%x
agent/x  allow-or-ask  | %G% %P% origin %SQ%refs/heads/*:refs/heads/*%SQ%
agent/x  DENY          | %G% %P% origin HEAD:refs/heads/%M%
agent/x  DENY          | %G% %P% origin HEAD --force-if-includes
agent/x  DENY          | %G% %P% origin agent/x%TAB%-f
agent/x  DENY          | %G% %P% origin agent/x%TAB%--force
agent/x  DENY          | %G%%TAB%%P%%TAB%origin%TAB%%M%
agent/x  allow-or-ask  | %G% %P% origin agent/x
agent/x  allow-or-ask  | %G% %P% -u origin agent/x
agent/x  allow-or-ask  | %G% %P% origin agent/fix-foo
agent/x  allow-or-ask  | %G% %P% origin agent/x:agent/main-notes
agent/x  DENY          | %G% commit -m %DQ%fix %P% to %M% docs%DQ%
agent/x  allow-or-ask  | cat <<%SQ%EOF%SQ%%NL%note %P% to %M%%NL%EOF
agent/x  allow-or-ask  | %G% %P% origin%NL%%M%
agent/x  DENY          | ((x=1<<2))%NL%%G% %P% origin %M%
agent/x  DENY          | $((1<<2))%NL%%G% %P% origin %M%
agent/x  DENY          | x=$[1<<2]%NL%%G% %P% origin %M%
agent/x  DENY          | cat <<<word%NL%%G% %P% origin %M%
agent/x  DENY          | echo ${#x} %G% %P% origin %M%
agent/x  allow-or-ask  | %G% %P% origin ma{i,}n
agent/x  allow-or-ask  | $%SQ%%BS%x67%SQ%it %P% origin %M%
agent/x  allow-or-ask  | %G% %P% origin ma%NUL%in
agent/x  allow-or-ask  | %G% %P% origin %M%%NUL%
agent/x  DENY          | %G% -c alias.p=%P% p origin %M%
agent/x  DENY          | %G% %P% origin @:%M%
agent/x  DENY          | %G% %P% origin %M%~0
agent/x  DENY          | %G% %P% origin +agent/x
agent/x  DENY          | %G% %P% origin %SQ%+agent/x%SQ%
agent/x  DENY          | %G% %P% -fu origin agent/x
agent/x  DENY          | %G% %P% -uf origin agent/x
agent/x  DENY          | %G% %P% --force-with-lease=agent/x origin agent/x
agent/x  DENY          | %G% %P% origin --delete %M%
agent/x  DENY          | %G% %P% origin :%M%
agent/x  allow-or-ask  | %G% log --oneline %M%
agent/x  allow-or-ask  | %G% %P% origin %M%-old
main     DENY          | g%SQ%%SQ%it commit -m x
main     DENY          | %DQ%g%DQ%it commit -m x
main     DENY          | gi%BS%t commit -m x
main     DENY          | %G% co%SQ%%SQ%mmit -m x
main     DENY          | %G% c%BS%ommit -m x
main     DENY          | %U% commit -m x
main     DENY          | %Gc% commit -m x
main     DENY          | timeout 60 %G% commit -m x
main     DENY          | sudo %G% commit -m x
main     DENY          | nohup %G% commit -m x
main     DENY          | nice %G% commit -m x
main     DENY          | %G% --config-env x=Y commit -m x
main     allow-or-ask  | %DQ%C:%BS%Program Files%BS%Git%BS%cmd%BS%%G%.exe%DQ% commit -m x
main     allow-or-ask  | C:%BS%%BS%Program%BS% Files%BS%%BS%Git%BS%%BS%cmd%BS%%BS%%G%.exe commit -m x
main     DENY          | %DQ%C:/Program Files/Git/cmd/%G%.exe%DQ% commit -m x
main     DENY          | /c/Program%BS% Files/Git/cmd/%G%.exe commit -m x
main     DENY          | %G% commit -m x; echo %SOH%x
main     allow-or-ask  | %G% commit%CR%%NL%
main     allow-or-ask  | %G%%CR% commit -m x
main     DENY          | %G% commit -m x%CR%%NL%
main     DENY          | %G%%TAB%commit%TAB%-m%TAB%x
main     allow-or-ask  | %G%%NUL% commit -m x
main     allow-or-ask  | %G% commit-tree HEAD^{tree} | xargs %G% update-ref refs/heads/%M%
main     allow-or-ask  | %G% pull
main     DENY          | %G% merge x
main     DENY          | %G% rebase x
main     DENY          | %G% am x.patch
main     DENY          | %G% cherry-pick x
main     DENY          | %G% revert x
main     DENY          | %G% -c alias.c=commit c -m x
main     allow-or-ask  | %G% ci -m x
main     DENY          | sh -c %DQ%%G% commit -m x%DQ%
main     DENY          | bash <<EOF%NL%%G% commit -m x%NL%EOF
main     DENY          | %G% status%NL%%NL%%NL%echo commit
main     allow-or-ask  | %G% status
main     allow-or-ask  | ls -la
```

Image jq vs image no-jq (diff, < = jq, > = no-jq):
```
214,215c214,215
< agent/x  DENY          | %G% %P% origin %M%%CR%
< agent/x  DENY          | %G% status%CR%%NL%%G% %P% origin %M%%CR%%NL%
---
> agent/x  allow-or-ask  | %G% %P% origin %M%%CR%
> agent/x  allow-or-ask  | %G% status%CR%%NL%%G% %P% origin %M%%CR%%NL%
239,240c239,240
< agent/x  DENY          | %G% %P% origin ma%NUL%in
< agent/x  DENY          | %G% %P% origin %M%%NUL%
---
> agent/x  allow-or-ask  | %G% %P% origin ma%NUL%in
> agent/x  allow-or-ask  | %G% %P% origin %M%%NUL%
270,271c270,271
< main     DENY          | %G% commit%CR%%NL%
< main     DENY          | %G%%CR% commit -m x
---
> main     allow-or-ask  | %G% commit%CR%%NL%
> main     allow-or-ask  | %G%%CR% commit -m x
274c274
< main     DENY          | %G%%NUL% commit -m x
---
> main     allow-or-ask  | %G%%NUL% commit -m x
```

### Table B: malformed and unusual payloads (columns: branch, host no-jq verdict, case, rc | image jq | image no-jq)
```
main     DENY    commit-array                       rc=0| DENY   | DENY   
main     DENY    commit-crlf-payload                rc=0| DENY   | DENY   
main     DENY    commit-crlf-whole                  rc=0| DENY   | DENY   
main     silent  commit-dup-key                     rc=0| DENY   | silent 
main     silent  commit-earlier-command-key         rc=0| DENY   | silent 
main     DENY    commit-esc-nul-after               rc=0| DENY   | DENY   
main     DENY    commit-invalid-utf8-before         rc=0| DENY   | silent 
main     DENY    commit-invalid-utf8-inside         rc=0| DENY   | silent 
main     DENY    commit-json-string                 rc=0| DENY   | DENY   
main     silent  commit-key-nl-value                rc=0| DENY   | silent 
main     DENY    commit-latin1-cmd                  rc=0| DENY   | silent 
main     DENY    commit-leading-space               rc=0| DENY   | DENY   
main     DENY    commit-missing-brace               rc=0| DENY   | DENY   
main     DENY    commit-ok                          rc=0| DENY   | DENY   
main     DENY    commit-pretty                      rc=0| DENY   | DENY   
main     silent  commit-raw-newline-in-string       rc=0| silent | silent 
main     DENY    commit-raw-nul-after               rc=0| DENY   | DENY   
main     DENY    commit-raw-nul-mid                 rc=0| DENY   | DENY   
main     DENY    commit-raw-soh-after               rc=0| DENY   | DENY   
main     DENY    commit-raw-soh-mid                 rc=0| DENY   | DENY   
main     DENY    commit-raw-text                    rc=0| DENY   | DENY   
main     DENY    commit-toolInput                   rc=0| DENY   | DENY   
main     silent  commit-truncated                   rc=0| silent | silent 
main     silent  commit-uescape                     rc=0| DENY   | silent 
main     silent  empty-command                      rc=0| silent | silent 
main     silent  empty-stdin                        rc=0| silent | silent 
main     silent  no-command                         rc=0| silent | silent 
main     silent  only-brace                         rc=0| silent | silent 
main     DENY    push-array                         rc=0| DENY   | DENY   
main     DENY    push-crlf-payload                  rc=0| DENY   | DENY   
main     DENY    push-crlf-whole                    rc=0| DENY   | DENY   
main     silent  push-dup-key                       rc=0| DENY   | silent 
main     silent  push-earlier-command-key           rc=0| DENY   | silent 
main     DENY    push-esc-nul-after                 rc=0| DENY   | DENY   
main     DENY    push-invalid-utf8-before           rc=0| DENY   | silent 
main     DENY    push-invalid-utf8-inside           rc=0| DENY   | silent 
main     DENY    push-json-string                   rc=0| DENY   | DENY   
main     silent  push-key-nl-value                  rc=0| DENY   | silent 
main     DENY    push-latin1-cmd                    rc=0| DENY   | silent 
main     DENY    push-leading-space                 rc=0| DENY   | DENY   
main     DENY    push-missing-brace                 rc=0| DENY   | DENY   
main     DENY    push-ok                            rc=0| DENY   | DENY   
main     DENY    push-pretty                        rc=0| DENY   | DENY   
main     silent  push-raw-newline-in-string         rc=0| silent | silent 
main     DENY    push-raw-nul-after                 rc=0| DENY   | DENY   
main     DENY    push-raw-nul-mid                   rc=0| DENY   | DENY   
main     DENY    push-raw-soh-after                 rc=0| DENY   | DENY   
main     DENY    push-raw-soh-mid                   rc=0| DENY   | DENY   
main     DENY    push-raw-text                      rc=0| DENY   | DENY   
main     DENY    push-toolInput                     rc=0| DENY   | DENY   
main     silent  push-truncated                     rc=0| silent | silent 
main     silent  push-uescape                       rc=0| DENY   | silent 
agent/x  silent  commit-array                       rc=0| silent | silent 
agent/x  silent  commit-crlf-payload                rc=0| silent | silent 
agent/x  silent  commit-crlf-whole                  rc=0| silent | silent 
agent/x  silent  commit-dup-key                     rc=0| silent | silent 
agent/x  silent  commit-earlier-command-key         rc=0| silent | silent 
agent/x  silent  commit-esc-nul-after               rc=0| silent | silent 
agent/x  silent  commit-invalid-utf8-before         rc=0| silent | silent 
agent/x  silent  commit-invalid-utf8-inside         rc=0| silent | silent 
agent/x  silent  commit-json-string                 rc=0| silent | silent 
agent/x  silent  commit-key-nl-value                rc=0| silent | silent 
agent/x  silent  commit-latin1-cmd                  rc=0| silent | silent 
agent/x  silent  commit-leading-space               rc=0| silent | silent 
agent/x  silent  commit-missing-brace               rc=0| silent | silent 
agent/x  silent  commit-ok                          rc=0| silent | silent 
agent/x  silent  commit-pretty                      rc=0| silent | silent 
agent/x  silent  commit-raw-newline-in-string       rc=0| silent | silent 
agent/x  silent  commit-raw-nul-after               rc=0| silent | silent 
agent/x  silent  commit-raw-nul-mid                 rc=0| silent | silent 
agent/x  silent  commit-raw-soh-after               rc=0| silent | silent 
agent/x  silent  commit-raw-soh-mid                 rc=0| silent | silent 
agent/x  silent  commit-raw-text                    rc=0| silent | silent 
agent/x  silent  commit-toolInput                   rc=0| silent | silent 
agent/x  silent  commit-truncated                   rc=0| silent | silent 
agent/x  silent  commit-uescape                     rc=0| silent | silent 
agent/x  silent  empty-command                      rc=0| silent | silent 
agent/x  silent  empty-stdin                        rc=0| silent | silent 
agent/x  silent  no-command                         rc=0| silent | silent 
agent/x  silent  only-brace                         rc=0| silent | silent 
agent/x  DENY    push-array                         rc=0| DENY   | DENY   
agent/x  DENY    push-crlf-payload                  rc=0| DENY   | DENY   
agent/x  DENY    push-crlf-whole                    rc=0| DENY   | DENY   
agent/x  silent  push-dup-key                       rc=0| DENY   | silent 
agent/x  silent  push-earlier-command-key           rc=0| DENY   | silent 
agent/x  DENY    push-esc-nul-after                 rc=0| DENY   | DENY   
agent/x  DENY    push-invalid-utf8-before           rc=0| DENY   | silent 
agent/x  DENY    push-invalid-utf8-inside           rc=0| DENY   | silent 
agent/x  DENY    push-json-string                   rc=0| DENY   | DENY   
agent/x  silent  push-key-nl-value                  rc=0| DENY   | silent 
agent/x  DENY    push-latin1-cmd                    rc=0| DENY   | silent 
agent/x  DENY    push-leading-space                 rc=0| DENY   | DENY   
agent/x  DENY    push-missing-brace                 rc=0| DENY   | DENY   
agent/x  DENY    push-ok                            rc=0| DENY   | DENY   
agent/x  DENY    push-pretty                        rc=0| DENY   | DENY   
agent/x  silent  push-raw-newline-in-string         rc=0| silent | silent 
agent/x  DENY    push-raw-nul-after                 rc=0| DENY   | DENY   
agent/x  DENY    push-raw-nul-mid                   rc=0| DENY   | DENY   
agent/x  DENY    push-raw-soh-after                 rc=0| DENY   | DENY   
agent/x  DENY    push-raw-soh-mid                   rc=0| DENY   | DENY   
agent/x  DENY    push-raw-text                      rc=0| DENY   | DENY   
agent/x  DENY    push-toolInput                     rc=0| DENY   | DENY   
agent/x  silent  push-truncated                     rc=0| silent | silent 
agent/x  silent  push-uescape                       rc=0| DENY   | silent 
```

### Table C: 5 MB commands (branch, verdict, shape, wall time, rc)

big-host-nojq:
```
main     DENY    commit-bsl-end           4024 ms rc=0
main     DENY    commit-escq-end          3491 ms rc=0
main     DENY    commit-heredoc-end       4649 ms rc=0
main     DENY    commit-lines-end         4040 ms rc=0
main     DENY    commit-short-end         2086 ms rc=0
main     DENY    commit-start-token       2058 ms rc=0
main     DENY    commit-token-end         2148 ms rc=0
main     DENY    push-bsl-end             3922 ms rc=0
main     DENY    push-escq-end            3410 ms rc=0
main     DENY    push-heredoc-end         4600 ms rc=0
main     DENY    push-lines-end           3899 ms rc=0
main     DENY    push-short-end           2101 ms rc=0
main     DENY    push-start-token         2169 ms rc=0
main     DENY    push-token-end           2155 ms rc=0
agent/x  DENY    push-bsl-end             3890 ms rc=0
agent/x  DENY    push-escq-end            3423 ms rc=0
agent/x  DENY    push-heredoc-end         4636 ms rc=0
agent/x  DENY    push-lines-end           3891 ms rc=0
agent/x  DENY    push-short-end           2036 ms rc=0
agent/x  DENY    push-start-token         2078 ms rc=0
agent/x  DENY    push-token-end           1978 ms rc=0
```

big-img-jq:
```
main     DENY    commit-bsl-end            432 ms rc=0
main     DENY    commit-escq-end           396 ms rc=0
main     DENY    commit-heredoc-end        429 ms rc=0
main     DENY    commit-lines-end          359 ms rc=0
main     DENY    commit-short-end          582 ms rc=0
main     DENY    commit-start-token        371 ms rc=0
main     DENY    commit-token-end          539 ms rc=0
main     DENY    push-bsl-end              469 ms rc=0
main     DENY    push-escq-end             424 ms rc=0
main     DENY    push-heredoc-end          392 ms rc=0
main     DENY    push-lines-end            367 ms rc=0
main     DENY    push-short-end            581 ms rc=0
main     DENY    push-start-token          388 ms rc=0
main     DENY    push-token-end            549 ms rc=0
agent/x  DENY    push-bsl-end              325 ms rc=0
agent/x  DENY    push-escq-end             325 ms rc=0
agent/x  DENY    push-heredoc-end          346 ms rc=0
agent/x  DENY    push-lines-end            349 ms rc=0
agent/x  DENY    push-short-end            500 ms rc=0
agent/x  DENY    push-start-token          471 ms rc=0
agent/x  DENY    push-token-end            360 ms rc=0
```

big-img-nojq:
```
main     DENY    commit-bsl-end           2059 ms rc=0
main     DENY    commit-escq-end          2001 ms rc=0
main     DENY    commit-heredoc-end       1732 ms rc=0
main     DENY    commit-lines-end         1690 ms rc=0
main     DENY    commit-short-end         1769 ms rc=0
main     DENY    commit-start-token       1568 ms rc=0
main     DENY    commit-token-end         1688 ms rc=0
main     DENY    push-bsl-end             2087 ms rc=0
main     DENY    push-escq-end            2098 ms rc=0
main     DENY    push-heredoc-end         1767 ms rc=0
main     DENY    push-lines-end           1632 ms rc=0
main     DENY    push-short-end           1672 ms rc=0
main     DENY    push-start-token         1460 ms rc=0
main     DENY    push-token-end           1570 ms rc=0
agent/x  DENY    push-bsl-end             1977 ms rc=0
agent/x  DENY    push-escq-end            2024 ms rc=0
agent/x  DENY    push-heredoc-end         1602 ms rc=0
agent/x  DENY    push-lines-end           1529 ms rc=0
agent/x  DENY    push-short-end           1608 ms rc=0
agent/x  DENY    push-start-token         1538 ms rc=0
agent/x  DENY    push-token-end           1430 ms rc=0
```
