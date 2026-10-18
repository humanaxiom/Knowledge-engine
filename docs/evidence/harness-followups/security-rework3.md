# Security re-audit: harness-followups rework 3 (2026-10-18)

Scope: `git diff a11842d` for scripts/hooks/block-main-commit.sh, .github/workflows/ci.yml, scripts/verify.sh
(first audit: rework 2 and 3 changes), scripts/test.sh, tests/test_block_main_commit_hook.py,
tests/test_harness_followups.py, tests/test_sentinel.py, and the evidence files. Platform-skeleton plan docs excluded.
Audited snapshot (sha256):
- scripts/hooks/block-main-commit.sh c7ec9af34725a980e9d342116d7ea660847a56e4ad4ffa559be32369958514a1
- scripts/verify.sh fd067da36d0da1627a304cec02542dd9f61f98f05f2658af6d4a32f28b8830d9
- scripts/test.sh 057e4682c7ae3df52b5dec0133331d680105c38365141282eed77929f96b1420 (unchanged since last audit)
- .github/workflows/ci.yml b1a3e54c8e457a1c66c4e7e707cbbf2838a7fc24cb070e960466161cc74e963d
- tests/test_harness_followups.py 979b8505f45e8695edc0f847e6c2b0b8d33c459a0eb1d0a0eb35b1685e4c9b4c
- tests/test_block_main_commit_hook.py a7a08edb9a2ab5c3c69811f8f80f3e2cca31316aa6bfe73336e28bbe49bfb0ca
- tests/test_sentinel.py 1fb16a814676af23ed54c2e18075651a656cea0f208b30bfebf47102178dd070
Notation as in security.md: <bs> backslash, <NL> newline, <CR> carriage return, %G% the version-control word,
%P% the upload verb, %M% the default branch name.

## Verdict: PASS (0 critical, 0 high; 1 medium new, 2 low new, 1 info; all non-blocking)

M5 and L20 are fixed. M6 below is what is left of M5. It is a fail-open regression against base a11842d, proven
live, in the same class as M4 and M5 (medium, not blocking). The fix is a one-character change with no extra
cost, so I recommend doing it in this item.

## Method
Payloads only, piped to the hook in throwaway repos (branch set with `symbolic-ref`); never a commit to this repo.
Payloads were built by the probe5 generators (mk4/mkbad/mkbig; CR, backslash, NUL and SOH from character codes), with
the rework-3 hook copied byte for byte (sha above). Modes: Windows host (Git Bash, no jq); gates image
knowledge-engine-gates (jq 1.6, bash 5.2.15, `--network none`); the same image with jq shadowed by a stub that
exits 127. The rework-2 hook and the base hook (a11842d) were run on the host for comparison.
- Table A: 373 rows = the 331 probe5 rows + 42 new (M5 rows, CR/tab/upper-case/double-continuation variants,
  quoted and heredoc shapes, continuations that bash really joins, benign controls).
- Table M: 16 rows that mix a non-continuation backslash-newline (comment or even run) with a real one.
- Table B: 66 malformed payloads x 2 branches. Table C: 5 MB payloads, 30 rows.
- Live run: two Table-M shapes as script files, run with host bash in a scratch repo with a bare remote.
- Scratch-only hook variants (never written to the repo) to test the suggested fix: "space" (pass b turns
  backslash-newline into a space instead of a newline) and "3pass" (nothing, newline and space).

## 1. M5: fixed
- All nine M5 rows and the live shapes c1-c3 and p1 are now DENY in all three modes. Another 25 variants are also
  DENY: CR before the newline, double continuation, blank or indented next line, tab, upper case, `merge`, heredoc
  body, Windows-path comment with `--all`, `+x`, `--mirror`, a four-backslash run with `--force`.
- No new fail-open from the dual normalisation. Text (a) is byte-identical to the single text of rework 2, and the
  loop only adds denies. r2 vs r3 on Table A: 0 DENY-to-silent rows, 34 silent-to-DENY rows. Table B: r2 = r3.
  The new silent-to-DENY rows that bash does not actually run (backslash-newline inside single quotes, an odd run
  joined by bash) are fail-safe false positives.
- The force-push regex changed from `<bs><bs>+` to `<bs>+` inside double quotes. Bash passes the same `<bs>+` to grep
  either way, and every `+refspec` row is still DENY.
- Mode parity: host no-jq = image no-jq on all 373 Table-A rows. Image jq differs only on the 3 known NUL rows.
  Table B differs only on the known L19/L15 rows, and image jq is identical to the probe5 round. Never `allow`:
  0 allow outputs and every exit code 0, across 373x3 + 132x4 + 30x3 runs.

## 2. M6 (medium, new: what is left of M5, a regression against a11842d)
A non-continuation backslash-newline (one that ends a comment, or the second backslash of an even run), followed
by a real continuation inside the `%G% %P%` line. Bash runs the next line as a separate command and joins its
continuation. Neither text the hook builds holds that command on one line:
- in (a), the comment glues onto `%G%` (`#x%G%`);
- in (b), the continuation breaks the push line in two.

The off-main rule is per line, so it stays silent. The base hook (pair -> space) denied all of these.
```
agent/x  #x<bs><NL>%G% %P% <bs><NL>origin %M%                  base DENY | r3 silent
agent/x  # push from C:<bs>repo<bs><NL>%G% %P% <bs><NL>  origin %M%   base DENY | r3 silent
agent/x  echo a<bs><bs><NL>%G% %P% <bs><NL>origin %M%            base DENY | r3 silent
(+7 more: --force, -f, --all, HEAD:%M%, continuation before %P% or before %M%; Table M)
```
- Live proof: q1 `#x<bs><NL>%G% %P% <bs><NL>origin HEAD:%M%` and q2 (the Windows-path comment form). The r3
  hook was silent, the base hook denied, and main on the bare remote moved to the q1 and then the q2 commit.
- On main, the rule needs no single line, so `#x<bs><NL>%G% <bs><NL>commit` is DENY. Only a continuation that
  splits the `%G%` word or the `commit` word after such a comment stays silent: 2 rows, also silent on base,
  contrived (info, not a regression).
- Medium, not high, for the same reasons as M4 and M5: the hook is a guard rail and branch protection is the
  control (Q18). The shape is plausible here, though: a comment ending in a Windows path, then a multi-line push.
- **Fix (developer):** in pass (b), replace backslash-newline with a space instead of a newline (the `text_b` sed
  replacement becomes a single space). The rules match only between non-word characters, and space and newline
  are both non-word, so the space text matches wherever the newline text does. Verified on the scratch variant:
  - on all 373 Table-A rows and 16 Table-M rows it gives exactly the 3pass result;
  - it denies all 10 M6 rows and keeps every r3 DENY;
  - it adds 3 fail-safe false positives (`%G% %P% origin x<bs><NL>%M%`, which bash reads as x%M%; the base hook
    denied these too);
  - it costs nothing extra (heredoc 9.38 s vs 9.30 s).

  Do not add a third pass instead: it costs 11.8 s on the host (L21).
- **Tests (tester):** add the Table-M rows listed in the raw section (both jq modes), and q1/q2 to the host check.
  Update the hook header and the ADR wording ("turned into a newline") to match.

## 3. L21 (low, new): host timing headroom halved
- Table C, all 30 rows DENY. Maximum time per mode:

  | Mode | This round | Last round |
  |---|---|---|
  | Host, no jq | 9.43 s | 4.6 s |
  | Image, jq | 0.83 s | 0.65 s |
  | Image, jq stub | 2.33 s | 2.2 s |

- The heredoc rows were re-timed 3x per branch: 9.24 to 9.43 s against the 10 s timeout (`.claude/settings.json`
  and developer.agent.md).
- Cost is per extra 5 MB command substitution under Cygwin (about 2.4 s each on the many-line shapes). A timed-out
  hook is a non-blocking error in Claude Code, so a slower host or a slightly bigger command fails open.
- Low: 5 MB commands are not a realistic agent-mistake shape, and the current numbers are under the limit.
- **Suggestion:** build and judge the second text only when the text contains a backslash-newline (a bash pattern
  test), or skip it when it equals text (a). That puts the heredoc and lines rows back on one pass. Check the result
  against Table C.

## 4. L20: fixed
ci.yml checkout now has `with: persist-credentials: false`. The SHA pin (v5.1.0, fbc6f399) and its comment are
unchanged, the job still has top-level `permissions: contents: read` and `runs-on: ubuntu-24.04`, and there are no
other steps, secrets or event expressions.

## 5. scripts/verify.sh (first audit of the rework 2/3 changes)
- No injection. The mode argument is checked against `fast|full` before any use. There is no eval, the log path is
  always quoted, and the greps are fixed patterns on a file.
- Temp file is safe:
  - `mktemp` (mode 0600, random name, in /tmp inside the gates container; on the host, verify.sh `exec`s docker
    before reaching it);
  - if `mktemp` fails, `set -e` aborts;
  - an EXIT trap removes the log on every exit path. Scratch run: 0 files left after PASS, after a failing test.sh
    and after a missing sentinel.
- Fails closed:
  - `pipefail` is set, so a test.sh failure fails verify even with forged lines (proven);
  - if tee fails, the run fails.
  - Nested verify.sh runs in tests/test_harness_followups.py use `capture_output`, so their fake `Ran` and
    sentinel lines never reach the real log (the real green-rework3 log has exactly one sentinel line and one
    `Ran` line).
- **I1 (info): the sentinel and `Ran` greps can be forged.** `test_top_level_unit_suite_ran .* ok` is unanchored,
  and `^Ran [1-9]` accepts any stdout. A scratch copy of verify.sh with a fake test.sh exiting 0 passed in three
  cases: a sub-package test with the same name, a skip whose reason contains " ok", and a test that prints both
  strings. In each case verify.sh reported PASS without the top-level suite.
  - Under the stated threat model (an agent mistake, not a hostile test) forging needs a second, unrelated
    mistake on top of dropping the top-level run, and it cannot hide a failing test (the exit code still gates).
    So it does not matter for security. It is a gate-integrity note only.
  - Optional hardening: anchor the sentinel grep to the whole line (start of line, the test name, the module
    `tests.test_sentinel.` in the parentheses, and `... ok` at end of line).

## 6. Secrets and local paths
- Grep for the same key, token and URL-credential patterns as last round, plus emails, profile/AppData/home paths,
  the host username, the scratch id and the repo absolute path. It covered all 25 files in
  docs/evidence/harness-followups/ (before this one), the handoff, the three test files, the hook, verify.sh,
  test.sh and ci.yml (5394 lines). No secrets.
- **L22 (low, new to this report; present since rework 1 and missed by my last scan because the path is
  JSON-escaped with doubled backslashes):** review-rework1-probes.txt line 18 contains a Windows profile path with
  the host username and the session scratch directory. This is personal data in a committed file, not a credential.
  **Fix (developer or orchestrator, before commit):** redact it to `<scratch>`.
- No other hits. green-rework3.txt, red-rework3.txt, mutation-rework3.txt and hook-live-host-r3.txt are clean.
  This file contains no local paths (re-checked after writing).

## Carried findings (unchanged, non-blocking)
- L16 is still open: the dual normalisation does not touch backslashes inside a path, and the M6 fix does not
  close it either.
- L17, L18, L19 (the Table-B mode differences above), L15, L12, L11, L2, L5 and L7 are unchanged.

## Raw output
"silent" = no output, exit 0. Table M columns: base a11842d | rework 2 | rework 3 | scratch "space" variant |
scratch "3pass" variant.

### Table M: mixed rows (host, no jq)
```
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %P% %BS%%NL%origin %M%   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %P% origin %BS%%NL%%M%   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %P% %BS%%NL%  origin %M%   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %P% %BS%%NL%-f origin x   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %P% %BS%%NL%--force   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %P% %BS%%NL%--all   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %P% origin %BS%%NL%HEAD:%M%   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     # push from C:%BS%repo%BS%%NL%%G% %P% %BS%%NL%  origin %M%   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     echo a%BS%%BS%%NL%%G% %P% %BS%%NL%origin %M%   [rc=0]
agent/x  DENY    silent  silent  DENY    DENY     #x%BS%%NL%%G% %BS%%NL%%P% origin %M%   [rc=0]
agent/x  DENY    DENY    DENY    DENY    DENY     %G% %P% %BS%%NL%origin %M% #x%BS%%NL%ls   [rc=0]
agent/x  silent  silent  silent  silent  silent   %G% %P% %BS%%NL%origin agent/x   [rc=0]
main     DENY    silent  DENY    DENY    DENY     #x%BS%%NL%%G% %BS%%NL%commit -m x   [rc=0]
main     silent  silent  silent  silent  silent   #x%BS%%NL%%G% commi%BS%%NL%t -m x   [rc=0]
main     silent  silent  silent  silent  silent   #x%BS%%NL%gi%BS%%NL%t commit -m x   [rc=0]
main     DENY    silent  DENY    DENY    DENY     # C:%BS%a%BS%%NL%%G% %BS%%NL%  commit -m x   [rc=0]
```

### Live run (host bash, scratch repo, bare remote)
```
agent/x q1  #x<bs><NL>%G% %P% <bs><NL>origin HEAD:%M%                  r3 hook silent | base hook DENY | remote main now: q1
agent/x q2  # push from C:<bs>repo<bs><NL>%G% %P% <bs><NL>  origin HEAD:%M%  r3 hook silent | base hook DENY | remote main now: q2
```

### Table A diff: rework 2 vs rework 3, host no jq (< r2, > r3)
```
289,296c289,296
< main     silent  | #x%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | ls #a%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | #x%BS%%NL%%G% push   [rc=0]
< main     silent  | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | echo a%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | echo %SQ%a%BS%%NL%%SQ%%G% commit -m x   [rc=0]
---
> main     DENY    | #x%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | ls #a%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | #x%BS%%NL%%G% push   [rc=0]
> main     DENY    | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | echo a%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | echo %SQ%a%BS%%NL%%SQ%%G% commit -m x   [rc=0]
300c300
< main     silent  | %G% commit%BS%%CR%%NL%-m x   [rc=0]
---
> main     DENY    | %G% commit%BS%%CR%%NL%-m x   [rc=0]
310,312c310,312
< agent/x  silent  | #x%BS%%NL%%G% push origin %M%   [rc=0]
< agent/x  silent  | #x%BS%%NL%%G% push -f   [rc=0]
< agent/x  silent  | echo a%BS%%BS%%NL%%G% push origin %M%   [rc=0]
---
> agent/x  DENY    | #x%BS%%NL%%G% push origin %M%   [rc=0]
> agent/x  DENY    | #x%BS%%NL%%G% push -f   [rc=0]
> agent/x  DENY    | echo a%BS%%BS%%NL%%G% push origin %M%   [rc=0]
332,339c332,339
< main     silent  | #x%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | ls #a%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | #x%BS%%NL%%G% %P%   [rc=0]
< main     silent  | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
< main     silent  | #x%BS%%CR%%NL%%G% commit -m x   [rc=0]
< main     silent  | #x%BS%%NL%%BS%%NL%%G% commit -m x   [rc=0]
---
> main     DENY    | #x%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | ls #a%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | #x%BS%%NL%%G% %P%   [rc=0]
> main     DENY    | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
> main     DENY    | #x%BS%%CR%%NL%%G% commit -m x   [rc=0]
> main     DENY    | #x%BS%%NL%%BS%%NL%%G% commit -m x   [rc=0]
343,344c343,344
< main     silent  | #x%BS%%NL%%U% COMMIT -m x   [rc=0]
< main     silent  | #x%BS%%NL%%G%%BS%%NL% commit -m x   [rc=0]
---
> main     DENY    | #x%BS%%NL%%U% COMMIT -m x   [rc=0]
> main     DENY    | #x%BS%%NL%%G%%BS%%NL% commit -m x   [rc=0]
346,348c346,348
< main     silent  | echo a%BS%%BS%%BS%%NL%%G% commit   [rc=0]
< main     silent  | echo %SQ%a%BS%%NL%%SQ%%G% commit   [rc=0]
< main     silent  | echo %DQ%a%BS%%BS%%DQ%%BS%%NL%%G% commit -m x   [rc=0]
---
> main     DENY    | echo a%BS%%BS%%BS%%NL%%G% commit   [rc=0]
> main     DENY    | echo %SQ%a%BS%%NL%%SQ%%G% commit   [rc=0]
> main     DENY    | echo %DQ%a%BS%%BS%%DQ%%BS%%NL%%G% commit -m x   [rc=0]
354,362c354,362
< agent/x  silent  | #x%BS%%NL%%G% %P% origin %M%   [rc=0]
< agent/x  silent  | #x%BS%%NL%%G% %P% -f   [rc=0]
< agent/x  silent  | echo a%BS%%BS%%NL%%G% %P% origin %M%   [rc=0]
< agent/x  silent  | #x%BS%%NL%%G% %P% origin HEAD:%M%   [rc=0]
< agent/x  silent  | # C:%BS%tmp%BS%%NL%%G% %P% --all   [rc=0]
< agent/x  silent  | #x%BS%%NL%%G% %P% origin +x   [rc=0]
< agent/x  silent  | #x%BS%%NL%%G% %P% --mirror   [rc=0]
< agent/x  silent  | #x%BS%%CR%%NL%%G% %P% origin %M%   [rc=0]
< agent/x  silent  | echo a%BS%%BS%%BS%%BS%%NL%%G% %P% --force   [rc=0]
---
> agent/x  DENY    | #x%BS%%NL%%G% %P% origin %M%   [rc=0]
> agent/x  DENY    | #x%BS%%NL%%G% %P% -f   [rc=0]
> agent/x  DENY    | echo a%BS%%BS%%NL%%G% %P% origin %M%   [rc=0]
> agent/x  DENY    | #x%BS%%NL%%G% %P% origin HEAD:%M%   [rc=0]
> agent/x  DENY    | # C:%BS%tmp%BS%%NL%%G% %P% --all   [rc=0]
> agent/x  DENY    | #x%BS%%NL%%G% %P% origin +x   [rc=0]
> agent/x  DENY    | #x%BS%%NL%%G% %P% --mirror   [rc=0]
> agent/x  DENY    | #x%BS%%CR%%NL%%G% %P% origin %M%   [rc=0]
> agent/x  DENY    | echo a%BS%%BS%%BS%%BS%%NL%%G% %P% --force   [rc=0]
```

### Table A diffs between modes
```
# host no-jq vs image no-jq (empty = identical)
# image no-jq vs image jq
239,240c239,240
< agent/x  silent  | %G% %P% origin ma%NUL%in   [rc=0]
< agent/x  silent  | %G% %P% origin %M%%NUL%   [rc=0]
---
> agent/x  DENY    | %G% %P% origin ma%NUL%in   [rc=0]
> agent/x  DENY    | %G% %P% origin %M%%NUL%   [rc=0]
274c274
< main     silent  | %G%%NUL% commit -m x   [rc=0]
---
> main     DENY    | %G%%NUL% commit -m x   [rc=0]
```

### Table A diff: rework 3 vs scratch space variant (host)
```
316c316
< agent/x  silent  | %G% push origin x%BS%%NL%%M%   [rc=0]
---
> agent/x  DENY    | %G% push origin x%BS%%NL%%M%   [rc=0]
319c319
< agent/x  silent  | %G% push%BS%%NL%origin %M%   [rc=0]
---
> agent/x  DENY    | %G% push%BS%%NL%origin %M%   [rc=0]
363c363
< agent/x  silent  | %G% %P% origin x%BS%%NL%%M%   [rc=0]
---
> agent/x  DENY    | %G% %P% origin x%BS%%NL%%M%   [rc=0]
```

### Table A: host, no jq, rework 3 hook (373 rows)
```
main     DENY    | %G% commit -m x   [rc=0]
main     DENY    | %G% commit   [rc=0]
main     DENY    | %G% push   [rc=0]
main     DENY    | %G% commit -m "x"   [rc=0]
main     DENY    | %G%_AUTHOR_NAME=a %G% commit -m x   [rc=0]
main     DENY    | bash -c "%G% commit -m x"   [rc=0]
main     silent  | %G% ci -m x   [rc=0]
main     DENY    | %G% -c alias.c=commit c -m x   [rc=0]
main     silent  | gh pr merge 1 --merge   [rc=0]
main     silent  | gh api repos/o/r/%G%/refs/heads/main -X PATCH   [rc=0]
main     silent  | eval "$(echo Z2l0IGNvbW1pdA== | base64 -d)"   [rc=0]
main     DENY    | g=%G%; $g commit -m x   [rc=0]
main     DENY    | %G% merge feature   [rc=0]
main     DENY    | %G% merge   [rc=0]
main     DENY    | %G% cherry-pick abc   [rc=0]
main     DENY    | %G% am p.patch   [rc=0]
main     DENY    | %G% rebase x   [rc=0]
main     DENY    | %G% revert abc   [rc=0]
main     silent  | %G% pull   [rc=0]
main     silent  | %G% pull origin main   [rc=0]
main     silent  | %G% reset --hard x   [rc=0]
main     silent  | %G% commit-tree HEAD^{tree} | xargs %G% update-ref refs/heads/main   [rc=0]
main     silent  | echo digital push-ups   [rc=0]
main     DENY    | %G% log --grep=push   [rc=0]
main     silent  | %G% status   [rc=0]
main     silent  | ls -la   [rc=0]
agent/x  DENY    | %G% push origin HEAD:main   [rc=0]
agent/x  DENY    | %G% push origin agent/x:main   [rc=0]
agent/x  DENY    | %G% push origin "HEAD:main"   [rc=0]
agent/x  DENY    | %G% push origin "main"   [rc=0]
agent/x  DENY    | %G% push origin 'main'   [rc=0]
agent/x  DENY    | %G% push origin main   [rc=0]
agent/x  DENY    | %G% push origin HEAD:refs/heads/main   [rc=0]
agent/x  DENY    | %G% push origin :main   [rc=0]
agent/x  DENY    | %G% push --delete origin main   [rc=0]
agent/x  DENY    | %G% push --force origin main   [rc=0]
agent/x  DENY    | %G% push --force origin agent/x   [rc=0]
agent/x  DENY    | %G% push -f   [rc=0]
agent/x  DENY    | %G% push --force-with-lease   [rc=0]
agent/x  DENY    | %G% push origin +agent/x   [rc=0]
agent/x  DENY    | %G% push origin +HEAD:main   [rc=0]
agent/x  DENY    | %G% push --mirror   [rc=0]
agent/x  DENY    | %G% push --all origin   [rc=0]
agent/x  DENY    | %G% push origin ma\in   [rc=0]
agent/x  DENY    | %G% push origin $(echo main)   [rc=0]
agent/x  silent  | %G% push origin refs/heads/*:refs/heads/*   [rc=0]
agent/x  silent  | %G% checkout main && %G% commit -m x   [rc=0]
agent/x  silent  | %G% switch main; %G% commit -m x   [rc=0]
agent/x  silent  | %G% -C ../other-main-checkout commit -m x   [rc=0]
agent/x  silent  | %G% update-ref refs/heads/main HEAD   [rc=0]
agent/x  silent  | %G% push origin agent/x   [rc=0]
agent/x  silent  | %G% push -u origin agent/x   [rc=0]
agent/x  silent  | %G% push   [rc=0]
main     DENY    | (%G% commit -m x)   [rc=0]
main     DENY    | { %G% commit -m x; }   [rc=0]
main     DENY    | if true; then %G% commit -m x; fi   [rc=0]
main     DENY    | time %G% commit -m x   [rc=0]
main     DENY    | command %G% commit -m x   [rc=0]
main     DENY    | env %G% commit -m x   [rc=0]
main     DENY    | ! %G% commit -m x   [rc=0]
main     DENY    | exec %G% commit -m x   [rc=0]
main     DENY    | true & %G% commit -m x   [rc=0]
main     DENY    | >/dev/null %G% commit -m x   [rc=0]
main     DENY    | echo $(%G% commit -m x)   [rc=0]
main     DENY    | echo `%G% commit -m x`   [rc=0]
main     DENY    | xargs %G% commit -m x < /dev/null   [rc=0]
main     DENY    | cd . && %G% commit -m x   [rc=0]
main     DENY    | %G% --no-pager commit -m x   [rc=0]
main     DENY    | %G% -P commit -m x   [rc=0]
main     DENY    | %G% --git-dir=.git commit -m x   [rc=0]
main     DENY    | %G% -C . -c user.name=a commit -m x   [rc=0]
main     DENY    | %G% commit -m "$(cat <<'EOF'\nmsg\nEOF\n)"   [rc=0]
main     DENY    | "%G%" commit -m x   [rc=0]
main     DENY    | g''it commit -m x   [rc=0]
main     DENY    | /usr/bin/%G% commit -m x   [rc=0]
main     DENY    | %G%.exe commit -m x   [rc=0]
main     DENY    | %G% -c core.hooksPath=/dev/null commit -m x   [rc=0]
main     DENY    | echo $((1<<2))\n%G% commit -m x   [rc=0]
main     DENY    | cat <<EOF\nhi\nEOF\n%G% commit -m x   [rc=0]
main     DENY    | cat <<'EOF' > f\ngit push origin main\nEOF   [rc=0]
agent/x  DENY    | %G% push origin $'main'   [rc=0]
agent/x  DENY    | %G% push origin m"a"in   [rc=0]
agent/x  DENY    | %G% push origin HEAD:MAIN   [rc=0]
agent/x  DENY    | %G% push origin main:main   [rc=0]
agent/x  DENY    | %G% push --force-if-includes origin agent/x   [rc=0]
agent/x  DENY    | %G% push origin --force   [rc=0]
agent/x  DENY    | %G% push -v -f   [rc=0]
agent/x  DENY    | %G% push --repo=origin main   [rc=0]
agent/x  DENY    | %G% push origin HEAD:refs/heads/master   [rc=0]
agent/x  DENY    | %G% push origin refs/heads/agent/x:refs/heads/main   [rc=0]
agent/x  DENY    | %G% push upstream main~0   [rc=0]
agent/x  DENY    | %G% push origin @:main   [rc=0]
agent/x  DENY    | echo $((1<<2))\n%G% push origin main   [rc=0]
agent/x  DENY    | %G% commit -m "push to main"   [rc=0]
agent/x  DENY    | %G% commit -m "x" -m 'git push -f'   [rc=0]
agent/x  DENY    | echo "git push origin main"   [rc=0]
agent/x  silent  | %G% log --oneline main   [rc=0]
main     DENY    | bash -c "%G% commit -m x"   [rc=0]
main     DENY    | sh -c '%G% commit -m x'   [rc=0]
main     DENY    | xargs %G% commit -m x < /dev/null   [rc=0]
main     DENY    | echo "$(%G% commit -m x)"   [rc=0]
main     DENY    | cat <<'EOF' > f\n%G% commit -m x\nEOF   [rc=0]
main     DENY    | %G% commit -m x; echo %SOH%x   [rc=0]
main     DENY    | %G% push; echo a%SOH%b   [rc=0]
main     DENY    | "g"it commit -m x   [rc=0]
main     DENY    | gi\t commit -m x   [rc=0]
main     DENY    | %G% co''mmit -m x   [rc=0]
main     DENY    | %G% c\ommit -m x   [rc=0]
main     DENY    | %G% "commit" -m x   [rc=0]
main     DENY    | %U% commit -m x   [rc=0]
main     DENY    | Git commit -m x   [rc=0]
main     DENY    | %G%.EXE commit -m x   [rc=0]
main     silent  | $'\x67'it commit -m x   [rc=0]
main     silent  | %G% pull   [rc=0]
main     silent  | %G% pull --no-rebase origin main   [rc=0]
main     DENY    | nohup %G% commit -m x   [rc=0]
main     DENY    | timeout 60 %G% commit -m x   [rc=0]
main     DENY    | ((x=1<<2))\n%G% commit -m x   [rc=0]
main     DENY    | echo $((%G% commit -m x) )   [rc=0]
master   DENY    | %G% commit -m x   [rc=0]
master   DENY    | %G% push   [rc=0]
agent/x  DENY    | (%G% push origin main)   [rc=0]
agent/x  DENY    | { %G% push origin main; }   [rc=0]
agent/x  DENY    | if %G% push origin main; then :; fi   [rc=0]
agent/x  DENY    | true & %G% push origin main   [rc=0]
agent/x  DENY    | >/dev/null %G% push origin main   [rc=0]
agent/x  DENY    | 2>&1 %G% push origin main   [rc=0]
agent/x  DENY    | echo $(%G% push origin main)   [rc=0]
agent/x  DENY    | echo `%G% push origin main`   [rc=0]
agent/x  DENY    | echo $((1<<2))\n%G% push origin main   [rc=0]
agent/x  DENY    | echo $((1<<2)) && %G% push origin main   [rc=0]
agent/x  DENY    | while %G% push origin main; do :; done   [rc=0]
agent/x  DENY    | until %G% push -f; do :; done   [rc=0]
agent/x  DENY    | ! %G% push origin main   [rc=0]
agent/x  DENY    | time %G% push origin main   [rc=0]
agent/x  DENY    | command %G% push origin main   [rc=0]
agent/x  DENY    | env %G% push origin main   [rc=0]
agent/x  DENY    | exec %G% push origin main   [rc=0]
agent/x  DENY    | X=1 Y=2 %G% push origin main   [rc=0]
agent/x  DENY    | %G% push -fu origin agent/x   [rc=0]
agent/x  DENY    | %G% push -uf origin agent/x   [rc=0]
agent/x  DENY    | %G% -c x=y push origin main   [rc=0]
agent/x  DENY    | %G% -C . push origin main   [rc=0]
agent/x  DENY    | %G% push origin HEAD:refs/heads/main   [rc=0]
agent/x  DENY    | %G% push origin :main   [rc=0]
agent/x  DENY    | %G% push --force-with-lease=agent/x origin agent/x   [rc=0]
agent/x  DENY    | %G% push origin HEAD:master   [rc=0]
agent/x  DENY    | %G% commit -m "fix push to main docs"   [rc=0]
agent/x  DENY    | %G% commit -m "note push -f is denied"   [rc=0]
agent/x  DENY    | %G% commit -m "$(cat <<'EOF'\nsee git push to main\nEOF\n)"   [rc=0]
agent/x  DENY    | echo "git push origin main"   [rc=0]
agent/x  silent  | %G% log --grep push   [rc=0]
agent/x  DENY    | echo "$(%G% push origin main)"   [rc=0]
agent/x  DENY    | bash -c "%G% push origin main"   [rc=0]
agent/x  DENY    | sh -c '%G% push origin main'   [rc=0]
agent/x  DENY    | xargs %G% push origin main < /dev/null   [rc=0]
agent/x  DENY    | ((x=1<<2))\n%G% push origin main   [rc=0]
agent/x  DENY    | echo $[1<<2]\n%G% push origin main   [rc=0]
agent/x  DENY    | cat <<"E"OF\nbody\nEOF\n%G% push origin main   [rc=0]
agent/x  DENY    | cat <<E"OF"\nbody\nEOF\n%G% push origin main   [rc=0]
agent/x  DENY    | cat <<\EOF\nbody\nEOF\n%G% push origin main   [rc=0]
agent/x  DENY    | cat <<< word\n%G% push origin main   [rc=0]
agent/x  DENY    | cat <<<word\n%G% push origin main   [rc=0]
agent/x  DENY    | x=1; echo ${#x}; %G% push origin main   [rc=0]
agent/x  DENY    | echo ${#x}\n%G% push origin main   [rc=0]
agent/x  DENY    | echo $(( 1 + $(%G% push origin main) ))   [rc=0]
agent/x  DENY    | echo $((%G% push origin main) )   [rc=0]
agent/x  DENY    | %G% push origin main; echo %SOH%x   [rc=0]
agent/x  DENY    | nohup %G% push origin main   [rc=0]
agent/x  DENY    | timeout 60 %G% push origin main   [rc=0]
agent/x  DENY    | nice %G% push origin main   [rc=0]
agent/x  DENY    | sudo %G% push origin main   [rc=0]
agent/x  DENY    | env -i %G% push origin main   [rc=0]
agent/x  DENY    | command -p %G% push origin main   [rc=0]
agent/x  DENY    | time -p %G% push origin main   [rc=0]
agent/x  DENY    | %G% --config-env x=Y push origin main   [rc=0]
agent/x  DENY    | %U% push origin main   [rc=0]
agent/x  DENY    | %G% push origin "ma"in   [rc=0]
agent/x  DENY    | %G% push origin m\ain   [rc=0]
agent/x  DENY    | %G% push origin 'HEAD:main'   [rc=0]
agent/x  DENY    | %G% push origin HEAD:refs/heads/main --dry-run   [rc=0]
agent/x  DENY    | case x in x) %G% push origin main;; esac   [rc=0]
agent/x  DENY    | f() { %G% push origin main; }; f   [rc=0]
agent/x  DENY    | for b in a; do %G% push origin main; done   [rc=0]
agent/x  DENY    | %G% push origin main # c   [rc=0]
agent/x  DENY    | echo hi # %G% push origin main   [rc=0]
agent/x  DENY    | echo a#b; %G% push origin main   [rc=0]
agent/x  DENY    | timeout 60 %G% %P% origin %M%   [rc=0]
agent/x  DENY    | nohup %G% %P% origin %M%   [rc=0]
agent/x  DENY    | sudo %G% %P% origin %M%   [rc=0]
agent/x  DENY    | nice %G% %P% origin %M%   [rc=0]
agent/x  DENY    | env -i %G% %P% origin %M%   [rc=0]
agent/x  DENY    | command -p %G% %P% origin %M%   [rc=0]
agent/x  DENY    | time -p %G% %P% origin %M%   [rc=0]
agent/x  DENY    | %G% --config-env x=Y %P% origin %M%   [rc=0]
agent/x  DENY    | %U% %P% origin %M%   [rc=0]
agent/x  DENY    | %Gc% %P% origin %M%   [rc=0]
agent/x  DENY    | %G% %P% origin ma%BS%in   [rc=0]
agent/x  DENY    | %G% %P% origin m%BS%ain   [rc=0]
agent/x  DENY    | %G% %P% %BS%%NL%  origin %M%   [rc=0]
agent/x  DENY    | %G% %P% %BS%%NL%  -f   [rc=0]
agent/x  DENY    | %G% %P% --force %BS%%NL%  origin agent/x   [rc=0]
agent/x  DENY    | %G% commit -m %DQ%a%BS%%DQ%b%DQ%; %G% %P% origin %M%   [rc=0]
agent/x  DENY    | echo a%BS%%BS%b; %G% %P% origin %M%   [rc=0]
agent/x  silent  | %DQ%C:%BS%Program Files%BS%Git%BS%cmd%BS%%G%.exe%DQ% %P% origin %M%   [rc=0]
agent/x  silent  | C:%BS%%BS%Program%BS% Files%BS%%BS%Git%BS%%BS%cmd%BS%%BS%%G%.exe %P% origin %M%   [rc=0]
agent/x  DENY    | %DQ%C:/Program Files/Git/cmd/%G%.exe%DQ% %P% origin %M%   [rc=0]
agent/x  DENY    | /c/Program%BS% Files/Git/cmd/%G%.exe %P% origin %M%   [rc=0]
agent/x  silent  | %G% %P% origin ${B:-%M%}   [rc=0]
agent/x  silent  | %G% %P% origin ${B-%M%}   [rc=0]
agent/x  silent  | %G% %P% --branches origin   [rc=0]
agent/x  silent  | %G% %P% --mirr origin   [rc=0]
agent/x  silent  | %G% %P% --al origin   [rc=0]
agent/x  DENY    | %G% %P% origin %M%%CR%   [rc=0]
agent/x  DENY    | %G% status%CR%%NL%%G% %P% origin %M%%CR%%NL%   [rc=0]
agent/x  DENY    | %G% %P% -f%CR%%NL%   [rc=0]
agent/x  DENY    | %G% %P% origin agent/x%SOH%; %G% %P% origin %M%   [rc=0]
agent/x  DENY    | %G% %P% origin %M%; echo %SOH%x   [rc=0]
agent/x  silent  | %G% %P% origin %SQ%refs/heads/*:refs/heads/*%SQ%   [rc=0]
agent/x  DENY    | %G% %P% origin HEAD:refs/heads/%M%   [rc=0]
agent/x  DENY    | %G% %P% origin HEAD --force-if-includes   [rc=0]
agent/x  DENY    | %G% %P% origin agent/x%TAB%-f   [rc=0]
agent/x  DENY    | %G% %P% origin agent/x%TAB%--force   [rc=0]
agent/x  DENY    | %G%%TAB%%P%%TAB%origin%TAB%%M%   [rc=0]
agent/x  silent  | %G% %P% origin agent/x   [rc=0]
agent/x  silent  | %G% %P% -u origin agent/x   [rc=0]
agent/x  silent  | %G% %P% origin agent/fix-foo   [rc=0]
agent/x  silent  | %G% %P% origin agent/x:agent/main-notes   [rc=0]
agent/x  DENY    | %G% commit -m %DQ%fix %P% to %M% docs%DQ%   [rc=0]
agent/x  silent  | cat <<%SQ%EOF%SQ%%NL%note %P% to %M%%NL%EOF   [rc=0]
agent/x  silent  | %G% %P% origin%NL%%M%   [rc=0]
agent/x  DENY    | ((x=1<<2))%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY    | $((1<<2))%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY    | x=$[1<<2]%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY    | cat <<<word%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY    | echo ${#x} %G% %P% origin %M%   [rc=0]
agent/x  silent  | %G% %P% origin ma{i,}n   [rc=0]
agent/x  silent  | $%SQ%%BS%x67%SQ%it %P% origin %M%   [rc=0]
agent/x  silent  | %G% %P% origin ma%NUL%in   [rc=0]
agent/x  silent  | %G% %P% origin %M%%NUL%   [rc=0]
agent/x  DENY    | %G% -c alias.p=%P% p origin %M%   [rc=0]
agent/x  DENY    | %G% %P% origin @:%M%   [rc=0]
agent/x  DENY    | %G% %P% origin %M%~0   [rc=0]
agent/x  DENY    | %G% %P% origin +agent/x   [rc=0]
agent/x  DENY    | %G% %P% origin %SQ%+agent/x%SQ%   [rc=0]
agent/x  DENY    | %G% %P% -fu origin agent/x   [rc=0]
agent/x  DENY    | %G% %P% -uf origin agent/x   [rc=0]
agent/x  DENY    | %G% %P% --force-with-lease=agent/x origin agent/x   [rc=0]
agent/x  DENY    | %G% %P% origin --delete %M%   [rc=0]
agent/x  DENY    | %G% %P% origin :%M%   [rc=0]
agent/x  silent  | %G% log --oneline %M%   [rc=0]
agent/x  silent  | %G% %P% origin %M%-old   [rc=0]
main     DENY    | g%SQ%%SQ%it commit -m x   [rc=0]
main     DENY    | %DQ%g%DQ%it commit -m x   [rc=0]
main     DENY    | gi%BS%t commit -m x   [rc=0]
main     DENY    | %G% co%SQ%%SQ%mmit -m x   [rc=0]
main     DENY    | %G% c%BS%ommit -m x   [rc=0]
main     DENY    | %U% commit -m x   [rc=0]
main     DENY    | %Gc% commit -m x   [rc=0]
main     DENY    | timeout 60 %G% commit -m x   [rc=0]
main     DENY    | sudo %G% commit -m x   [rc=0]
main     DENY    | nohup %G% commit -m x   [rc=0]
main     DENY    | nice %G% commit -m x   [rc=0]
main     DENY    | %G% --config-env x=Y commit -m x   [rc=0]
main     silent  | %DQ%C:%BS%Program Files%BS%Git%BS%cmd%BS%%G%.exe%DQ% commit -m x   [rc=0]
main     silent  | C:%BS%%BS%Program%BS% Files%BS%%BS%Git%BS%%BS%cmd%BS%%BS%%G%.exe commit -m x   [rc=0]
main     DENY    | %DQ%C:/Program Files/Git/cmd/%G%.exe%DQ% commit -m x   [rc=0]
main     DENY    | /c/Program%BS% Files/Git/cmd/%G%.exe commit -m x   [rc=0]
main     DENY    | %G% commit -m x; echo %SOH%x   [rc=0]
main     DENY    | %G% commit%CR%%NL%   [rc=0]
main     DENY    | %G%%CR% commit -m x   [rc=0]
main     DENY    | %G% commit -m x%CR%%NL%   [rc=0]
main     DENY    | %G%%TAB%commit%TAB%-m%TAB%x   [rc=0]
main     silent  | %G%%NUL% commit -m x   [rc=0]
main     silent  | %G% commit-tree HEAD^{tree} | xargs %G% update-ref refs/heads/%M%   [rc=0]
main     silent  | %G% pull   [rc=0]
main     DENY    | %G% merge x   [rc=0]
main     DENY    | %G% rebase x   [rc=0]
main     DENY    | %G% am x.patch   [rc=0]
main     DENY    | %G% cherry-pick x   [rc=0]
main     DENY    | %G% revert x   [rc=0]
main     DENY    | %G% -c alias.c=commit c -m x   [rc=0]
main     silent  | %G% ci -m x   [rc=0]
main     DENY    | sh -c %DQ%%G% commit -m x%DQ%   [rc=0]
main     DENY    | bash <<EOF%NL%%G% commit -m x%NL%EOF   [rc=0]
main     DENY    | %G% status%NL%%NL%%NL%echo commit   [rc=0]
main     silent  | %G% status   [rc=0]
main     silent  | ls -la   [rc=0]
main     DENY    | #x%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | ls #a%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | #x%BS%%NL%%G% push   [rc=0]
main     DENY    | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | echo a%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | echo %SQ%a%BS%%NL%%SQ%%G% commit -m x   [rc=0]
main     DENY    | %G%%BS%%NL% commit -m x   [rc=0]
main     DENY    | gi%BS%%NL%t commit -m x   [rc=0]
main     DENY    | %G% com%BS%%NL%mit -m x   [rc=0]
main     DENY    | %G% commit%BS%%CR%%NL%-m x   [rc=0]
main     DENY    | %G% commit%CR%%NL%   [rc=0]
main     DENY    | %G%%CR% commit -m x   [rc=0]
main     DENY    | %CR%%G% commit -m x   [rc=0]
main     silent  | x%CR%%G% commit -m x   [rc=0]
main     DENY    | %G% com%CR%mit -m x   [rc=0]
main     DENY    | gi%CR%t commit -m x   [rc=0]
main     DENY    | %G%%CR%%CR% commit   [rc=0]
main     DENY    | %G% commit -m x%BS%r   [rc=0]
main     silent  | echo %G%%BS%r commit   [rc=0]
agent/x  DENY    | #x%BS%%NL%%G% push origin %M%   [rc=0]
agent/x  DENY    | #x%BS%%NL%%G% push -f   [rc=0]
agent/x  DENY    | echo a%BS%%BS%%NL%%G% push origin %M%   [rc=0]
agent/x  DENY    | %G% push origin %M%%CR%   [rc=0]
agent/x  DENY    | %G% push origin ma%CR%in   [rc=0]
agent/x  DENY    | %G% push origin %M%%BS%%NL%   [rc=0]
agent/x  silent  | %G% push origin x%BS%%NL%%M%   [rc=0]
agent/x  DENY    | %G% push origin x %BS%%NL%%M%   [rc=0]
agent/x  DENY    | %G% %P%%BS%%NL% origin %M%   [rc=0]
agent/x  silent  | %G% push%BS%%NL%origin %M%   [rc=0]
agent/x  DENY    | %G% push origin %M%%CR%%NL%   [rc=0]
agent/x  DENY    | %G% status%CR%%NL%%G% push origin %M%%CR%%NL%   [rc=0]
agent/x  DENY    | %G% push origin +x%CR%   [rc=0]
agent/x  DENY    | %G% push %CR%-f origin x   [rc=0]
agent/x  DENY    | %G% push origin %CR%+x   [rc=0]
agent/x  silent  | %G% push origin %M%%BS%r   [rc=0]
agent/x  DENY    | %G% push origin %M%%BS%%CR%   [rc=0]
agent/x  silent  | %G% push origin %M%%BS%%BS%r   [rc=0]
agent/x  DENY    | %G% push origin %CR%%M%   [rc=0]
agent/x  DENY    | %G% push --mir%CR%ror   [rc=0]
agent/x  silent  | %G% push origin agent/x%CR%%NL%   [rc=0]
agent/x  silent  | ls -la%CR%%NL%   [rc=0]
main     DENY    | #x%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | # copy to C:%BS%out%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | ls #a%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | #x%BS%%NL%%G% %P%   [rc=0]
main     DENY    | echo a%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | echo a%BS%%BS%%BS%%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | #x%BS%%CR%%NL%%G% commit -m x   [rc=0]
main     DENY    | #x%BS%%NL%%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | #x%BS%%NL%%NL%%G% commit -m x   [rc=0]
main     DENY    | #x%BS%%NL%  %G% commit -m x   [rc=0]
main     DENY    | #x%BS%%NL%%TAB%%G% commit -m x   [rc=0]
main     DENY    | #x%BS%%NL%%U% COMMIT -m x   [rc=0]
main     DENY    | #x%BS%%NL%%G%%BS%%NL% commit -m x   [rc=0]
main     silent  | #x%BS%%NL%%G% commi%BS%%NL%t -m x   [rc=0]
main     DENY    | echo a%BS%%BS%%BS%%NL%%G% commit   [rc=0]
main     DENY    | echo %SQ%a%BS%%NL%%SQ%%G% commit   [rc=0]
main     DENY    | echo %DQ%a%BS%%BS%%DQ%%BS%%NL%%G% commit -m x   [rc=0]
main     DENY    | x=1 #%BS%%NL%%G% merge y   [rc=0]
main     DENY    | cat <<E%NL%a%BS%%NL%E%NL%%G% commit -m x   [rc=0]
main     silent  | #x%BS%%NL%ls   [rc=0]
main     silent  | echo a%BS%%NL%b   [rc=0]
main     silent  | #c%BS%%NL%%G% status   [rc=0]
agent/x  DENY    | #x%BS%%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY    | #x%BS%%NL%%G% %P% -f   [rc=0]
agent/x  DENY    | echo a%BS%%BS%%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY    | #x%BS%%NL%%G% %P% origin HEAD:%M%   [rc=0]
agent/x  DENY    | # C:%BS%tmp%BS%%NL%%G% %P% --all   [rc=0]
agent/x  DENY    | #x%BS%%NL%%G% %P% origin +x   [rc=0]
agent/x  DENY    | #x%BS%%NL%%G% %P% --mirror   [rc=0]
agent/x  DENY    | #x%BS%%CR%%NL%%G% %P% origin %M%   [rc=0]
agent/x  DENY    | echo a%BS%%BS%%BS%%BS%%NL%%G% %P% --force   [rc=0]
agent/x  silent  | %G% %P% origin x%BS%%NL%%M%   [rc=0]
agent/x  DENY    | %G% %P%%BS%%NL% origin %M%   [rc=0]
agent/x  DENY    | %G% %P% origin %BS%%NL%%M%   [rc=0]
agent/x  DENY    | %G% %P% %BS%%NL%-f   [rc=0]
agent/x  DENY    | %G% %P% origin%BS%%NL% %M%   [rc=0]
agent/x  DENY    | %G% %BS%%NL%%P% origin %M%   [rc=0]
agent/x  DENY    | %G% %P% origin %M%%BS%%NL%   [rc=0]
agent/x  silent  | #x%BS%%NL%%G% %P% origin agent/x   [rc=0]
agent/x  DENY    | %G% %P% origin agent/x%BS%%NL%; echo %M%   [rc=0]
agent/x  silent  | #x%BS%%NL%%G% %P%   [rc=0]
agent/x  silent  | echo a%BS%%NL%b   [rc=0]
```

### Table B diffs (132 rows each)
```
# rework 2 vs rework 3, host (empty = identical)
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

### Table C: 5 MB payloads (host no-jq | image jq | image no-jq)
```
main     DENY    commit-bsl-end           4464 m|   521 m|  2200 m
main     DENY    commit-bsnl-end          6802 m|   711 m|  2049 m
main     DENY    commit-crlines-end       6940 m|   556 m|  1794 m
main     DENY    commit-crs-end           3629 m|   437 m|  1886 m
main     DENY    commit-escq-end          4208 m|   519 m|  2202 m
main     DENY    commit-heredoc-end       9360 m|   578 m|  1885 m
main     DENY    commit-lines-end         7452 m|   543 m|  1815 m
main     DENY    commit-short-end         2934 m|   822 m|  1897 m
main     DENY    commit-start-token       2968 m|   652 m|  1660 m
main     DENY    commit-token-end         2881 m|   736 m|  1832 m
main     DENY    push-bsl-end             4441 m|   549 m|  2332 m
main     DENY    push-bsnl-end            6836 m|   748 m|  2094 m
main     DENY    push-crlines-end         6830 m|   563 m|  1870 m
main     DENY    push-crs-end             3704 m|   435 m|  1866 m
main     DENY    push-escq-end            4208 m|   517 m|  2115 m
main     DENY    push-heredoc-end         9427 m|   663 m|  1914 m
main     DENY    push-lines-end           7451 m|   622 m|  1852 m
main     DENY    push-short-end           2909 m|   827 m|  1891 m
main     DENY    push-start-token         2905 m|   616 m|  1708 m
main     DENY    push-token-end           2848 m|   721 m|  1799 m
agent/x  DENY    push-bsl-end             4482 m|   458 m|  2096 m
agent/x  DENY    push-bsnl-end            6671 m|   615 m|  2010 m
agent/x  DENY    push-crlines-end         6840 m|   511 m|  1838 m
agent/x  DENY    push-crs-end             3572 m|   426 m|  1900 m
agent/x  DENY    push-escq-end            4202 m|   444 m|  2116 m
agent/x  DENY    push-heredoc-end         9399 m|   547 m|  1838 m
agent/x  DENY    push-lines-end           7319 m|   596 m|  1800 m
agent/x  DENY    push-short-end           2857 m|   696 m|  1818 m
agent/x  DENY    push-start-token         2778 m|   652 m|  1765 m
agent/x  DENY    push-token-end           2902 m|   577 m|  1648 m
```

### Host re-time and variant timings (agent/x unless noted)
```
r3 push-heredoc-end main 9244/9406/9403 ms, agent/x 9296/9303/9316 ms
r3 push-lines-end    main 7495/7359/7447 ms, agent/x 7329/7354/7254 ms
r3 push-bsnl-end     main 6863/6809/7026 ms, agent/x 6763/6750/6676 ms
space variant: heredoc 9379 ms, bsnl 6679 ms, lines 7345 ms (all DENY)
3pass variant: heredoc 11791 ms, bsnl 8448 ms, lines 9364 ms (all DENY)
```

### verify.sh sentinel probe (scratch copy, fake test.sh, KE_IN_GATES=1, fast)
```
real-shape control: rc=0 PASS | temp files left: 0
sub-suite test with same name: rc=0 PASS | temp files left: 0
sentinel skipped, reason has ok: rc=0 PASS | temp files left: 0
test prints the strings itself: rc=0 PASS | temp files left: 0
fail after forged lines (exit 1): rc=1 FAIL (test.sh exited non-zero) | temp files left: 0
no sentinel: rc=1 FAIL (sentinel did not report ok) | temp files left: 0
```
