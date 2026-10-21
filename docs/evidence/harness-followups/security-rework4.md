# Security re-audit: harness-followups rework 4 (2026-10-18)

Scope: `git diff a11842d` (uncommitted) for scripts/hooks/block-main-commit.sh, scripts/verify.sh, scripts/test.sh,
.github/workflows/ci.yml, tests/test_block_main_commit_hook.py, tests/test_harness_followups.py, tests/test_sentinel.py
and all of docs/evidence/. Audited snapshot (sha256):
- scripts/hooks/block-main-commit.sh 4f7d313e64b66b11c3cd75b7bf89d8a84dd3f5b7857db3bd5a897efca5ea3baf
- scripts/verify.sh ab9ef8b0c2f86f07d960463ca52cee7d1a91f860ac06bfcd0f5561a86c26977d
- scripts/test.sh 057e4682... and .github/workflows/ci.yml b1a3e54c... (both unchanged since rework 3)
- tests/test_harness_followups.py 66ba4d87..., tests/test_block_main_commit_hook.py 9156b0ce..., tests/test_sentinel.py 1fb16a81... (unchanged)
Notation as in security.md: %G% the version-control word, %P% the upload verb, %M% the default branch name,
%BS% backslash, %NL% newline, %CR% carriage return, %NUL% NUL.

## Verdict: PASS (0 critical, 0 high; M6 fixed, I1 fixed, L22 fixed; L21 partly fixed, stays low; 1 low new)

## Method
Same as rework 3: payloads only, piped to byte-for-byte copies of the hooks in throwaway repos. The probe6 generators
and tables are reused unchanged; the r3 outputs were reproduced byte for byte first, so the harness is the same.
Three modes: Windows host Git Bash with jq stubbed (exit 127); gates image knowledge-engine-gates (jq 1.6, bash
5.2.15, network none); the same image with the jq stub. Hooks compared: r4 (this round), r3, base a11842d.
Tables: A 373 rows, M 16 rows, B 66 malformed x 2 branches, C 30 rows of 5 MB, plus X (12 new rows, below) and 5 new
5 MB timing shapes. Live run of q1/q2 with host bash in a scratch clone with a scratch bare remote.

## 1. M6: fixed
- Table M rows 1-10 are DENY in all three modes (were silent on r3). Rows 11, 13, 16 DENY; row 12 silent; rows 14/15
  silent (accepted bypass, silent on base too). Table M is identical across the three modes.
- r4 equals the scratch "space" variant I proposed in rework 3 on all 373 Table-A and 16 Table-M rows.
- DENY->silent rows, r4 against r3: 0 in every table and mode (A, M, B, C, X; host, image jq, image no-jq).
- DENY->silent rows, r4 against base a11842d: 0 on host and image no-jq. Image jq: 1 row, `x%CR%%G% commit -m x` on
  main. It is not a rework-4 change: r3 is also silent (CR deleted since rework 2), the base hook is silent on the host
  for the same row, and bash reads x<CR>%G% as one word, so nothing runs. No PS-0.5 join row turns silent; the
  PS-0.5 joins show only as silent->DENY.
- silent->DENY, r3 -> r4: 3 rows on Table A (`%G% %P% origin x%BS%%NL%%M%` and similar, which bash reads as one
  joined word) and 10 on Table M. These 3 are the fail-safe false positives predicted in rework 3. The base hook
  also denied them.
- Why it cannot lose a deny: text (a) is unchanged. Text (b) is now the base normalisation plus early CR deletion.
  It is skipped only when the text has no backslash-newline, and then (a) = (b) byte for byte, because sed -z on
  a text without the pair is a no-op and bash variables hold no NUL. The rules' anchors are all (^|W) or (W|end of
  line), and space is in W, so the space text matches wherever the old newline text did.
- Table B: r4 = r3 in all three modes (132 rows each). Table C: all 30 rows DENY in all three modes. Never allow:
  0 allow outputs, every exit code 0.
- Live (host bash, scratch clone, scratch bare remote seeded by clone --bare): q1 and q2 DENY with "Pushing to
  main/master is not allowed." on r4 (and base). The script runs only if the hook is silent, and it did not run:
  remote %M% stayed at the seed commit. The r3 positive control (remote %M% moved) is the rework-3 proof; I did not
  repeat it, to avoid executing a real upload.

## 2. L21 (low, partly fixed; headroom unchanged for one shape)
- Table C host maximum 7.04 s (was 9.43 s). Heredoc rows fell from 9.4 s to 6.8-7.0 s (one pass now).
- Re-time, 3 runs each, host, no jq, about 6 MB of payload JSON:

  | Shape | no backslash-newline | one backslash-newline |
  |---|---|---|
  | lines (echo x, 750k lines) | 5.37-5.50 s | 7.26-7.60 s |
  | heredoc (1M lines) | 6.77-7.09 s | 9.22-9.56 s (DENY), 9.61-9.82 s (silent tail) |

- The developer's 4.9 s / 6.8 s match a lighter shape. The worst case is a many-line command with one backslash-newline
  anywhere: the second pass runs again over all 5 MB, and that is back at 9.2-9.8 s against the 10 s timeout, the same
  as rework 3. Headroom without backslash-newline: about 30%. With one: 2-8%.
- Still low: 5 MB is not a realistic agent-mistake shape, the push rows stay under 10 s, and the 9.8 s row is a benign
  command (a timeout there fails open on a command that should be allowed anyway).
- Optional hardening (not blocking): a fail-safe size cap. If the command is over, for example, 1 MB and contains the
  word %G%, deny without normalising. Or build text (b) from the lines around each backslash-newline only.

## 3. I1: fixed (residual is inherent, info)
Scratch copy of verify.sh with a fake test.sh (KE_IN_GATES=1, fast). Exact line: PASS. Exact line with CRLF: PASS.
FAIL (sentinel message) for: same name in a sub-package module (rework-3 case 1), module suffix, module prefix,
skipped with "... ok" in the reason (case 2), plain skip, expected failure, "not ok", trailing text, leading space,
the line embedded after another test's dots, and a dot used as a wildcard (dots are escaped). Non-zero test.sh: FAIL
(pipefail). No sentinel: FAIL. Temp files left: 0 in every case.
Residual (info): a test that prints the exact full line on its own line still passes (rework-3 case 3). Any log grep
has this limit. It needs a deliberately forged line, and it cannot hide a failing test, because the exit code still
gates.

## 4. L22 and new evidence: fixed, clean
- review-rework1-probes.txt line 18 now reads <scratch>.
- Searched all of docs/evidence/ (every plan item, including platform-skeleton and README) for the JSON-escaped and
  plain profile-path forms named in the brief, the forward-slash form, AppData, the host username, the session id,
  the scratch prefix and emails. The only hits are security reports (this one included) describing their own search
  patterns. hook-live-host-r4.txt, hook-timing-host-r4.txt, green-rework4.txt and red-rework4.txt are clean.
- Secrets sweep (AWS/GitHub/OpenAI/Anthropic/Slack/Google key shapes, private keys, JWTs, URL credentials, key/token/
  password assignments, Bearer) over the whole diff plus untracked files (8878 lines): no hits.

## 5. Other files
- verify.sh: the only change is the anchored grep, on a CR-stripped stream through tr. That is a fixed pattern
  with no injection surface. A tr failure makes the "if !" fail closed.
- test.sh and ci.yml are unchanged since the rework-3 audit (sha above). L20 (persist-credentials) is still in place.
- Tests: subprocess is argv-only (no shell=True), with temp repos and dirs cleaned up, cwd set to the temp repo,
  output captured, and no network.

## 6. L23 (low, new to this report; not a regression, also silent on base)
Off main, after a comment or even run that ends in a backslash-newline, a continuation that splits a word in the
upload line stays silent on r4, r3 and base. Bash joins the word, so the command is real. Rows 1-5 of Table X below
(pu%BS%%NL%sh, ma%BS%%NL%in, --for%BS%%NL%ce). This is the off-main form of the accepted main rows 14/15:
a contrived shape, and branch protection (Q18) is the control.
Ask (architect/documenter): add the off-main form next to rows 14/15 in the ADR's accepted bypasses. No code change
needed.

## Process note (disclosure)
During this audit my first Table-B host run had an unguarded cd into a scratch repo that failed. Its
symbolic-ref calls ran in this repository and pointed HEAD at an unborn agent/x branch. I restored HEAD to
agent/harness-followups at once. git status --short then matched the session-start snapshot exactly, and no
ref, index or working-tree change was made. The run was repeated with a guarded runner, which checks that the git dir
is the scratch .git before any git call. Twice the repo's own PreToolUse hook denied my probe commands for their
text. I switched to the placeholder generator and a clone --bare seed instead of working around the hook.

## Raw output
Columns where shown: base | r3 | r4. "silent" = no output, exit 0.

### Table M (host; image jq and image no-jq identical)
```
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% %BS%%NL%origin %M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% origin %BS%%NL%%M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% %BS%%NL%  origin %M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% %BS%%NL%-f origin x   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% %BS%%NL%--force   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% %BS%%NL%--all   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% origin %BS%%NL%HEAD:%M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | # push from C:%BS%repo%BS%%NL%%G% %P% %BS%%NL%  origin %M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | echo a%BS%%BS%%NL%%G% %P% %BS%%NL%origin %M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %BS%%NL%%P% origin %M%   [rc=0]
agent/x  DENY    |DENY    |agent/x  DENY    | %G% %P% %BS%%NL%origin %M% #x%BS%%NL%ls   [rc=0]
agent/x  silent  |silent  |agent/x  silent  | %G% %P% %BS%%NL%origin agent/x   [rc=0]
main     DENY    |DENY    |main     DENY    | #x%BS%%NL%%G% %BS%%NL%commit -m x   [rc=0]
main     silent  |silent  |main     silent  | #x%BS%%NL%%G% commi%BS%%NL%t -m x   [rc=0]
main     silent  |silent  |main     silent  | #x%BS%%NL%gi%BS%%NL%t commit -m x   [rc=0]
main     DENY    |DENY    |main     DENY    | # C:%BS%a%BS%%NL%%G% %BS%%NL%  commit -m x   [rc=0]
```

### Table X: new rows (host)
```
agent/x  silent  |silent  |agent/x  silent  | #x%BS%%NL%%G% pu%BS%%NL%sh origin %M%   [rc=0]
agent/x  silent  |silent  |agent/x  silent  | #x%BS%%NL%%G% %P% origin ma%BS%%NL%in   [rc=0]
agent/x  silent  |silent  |agent/x  silent  | echo a%BS%%BS%%NL%%G% %P% origin ma%BS%%NL%in   [rc=0]
agent/x  silent  |silent  |agent/x  silent  | #x%BS%%NL%%G% %P% --for%BS%%NL%ce   [rc=0]
agent/x  silent  |silent  |agent/x  silent  | #x%BS%%NL%%G% %P% origin %BS%%NL%ma%BS%%NL%in   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% %BS%%NL%%BS%%NL%origin %M%   [rc=0]
agent/x  silent  |silent  |agent/x  DENY    | #x%BS%%CR%%NL%%G% %P% %BS%%CR%%NL%origin %M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #x%BS%%NL%%G% %P% %BS%%NL%origin +HEAD:x   [rc=0]
agent/x  DENY    |DENY    |agent/x  DENY    | %G% status #x%BS%%NL%%G% %P% %BS%%NL%origin %M%   [rc=0]
agent/x  DENY    |silent  |agent/x  DENY    | #a%BS%%NL%#b%BS%%NL%%G% %P% %BS%%NL%origin %M%   [rc=0]
agent/x  silent  |silent  |agent/x  silent  | #x%BS%%NL%%G% %P% %BS%%NL%origin agent/x   [rc=0]
main     DENY    |DENY    |main     DENY    | #x%BS%%NL%%G% %BS%%NL%%P% origin x   [rc=0]
```

### Live run (host bash, scratch clone and bare remote)
```
r4 q1 branch=agent/x hook=DENY reason=Pushing to %M%/master is not allowed. remote-%M%=seed
r4 q2 branch=agent/x hook=DENY reason=Pushing to %M%/master is not allowed. remote-%M%=seed
base q1 branch=agent/x hook=DENY reason=Pushing to %M%/master is not allowed. remote-%M%=seed
base q2 branch=agent/x hook=DENY reason=Pushing to %M%/master is not allowed. remote-%M%=seed
```

### Table C: 5 MB (host r4 | image jq r4 | image no-jq r4 | host r3)
```
main     DENY    commit-bsl-end         |  4380 ms |   523 ms |  2217 ms |  4464 ms 
main     DENY    commit-bsnl-end        |  6832 ms |   792 ms |  2150 ms |  6802 ms 
main     DENY    commit-crlines-end     |  5384 ms |   492 ms |  1886 ms |  6940 ms 
main     DENY    commit-crs-end         |  3529 ms |   445 ms |  1888 ms |  3629 ms 
main     DENY    commit-escq-end        |  4133 ms |   500 ms |  2150 ms |  4208 ms 
main     DENY    commit-heredoc-end     |  6940 ms |   517 ms |  1835 ms |  9360 ms 
main     DENY    commit-lines-end       |  5639 ms |   501 ms |  1819 ms |  7452 ms 
main     DENY    commit-short-end       |  2572 ms |   702 ms |  1878 ms |  2934 ms 
main     DENY    commit-start-token     |  2553 ms |   501 ms |  1674 ms |  2968 ms 
main     DENY    commit-token-end       |  2526 ms |   625 ms |  1716 ms |  2881 ms 
main     DENY    push-bsl-end           |  4374 ms |   492 ms |  2162 ms |  4441 ms 
main     DENY    push-bsnl-end          |  7044 ms |   754 ms |  2086 ms |  6836 ms 
main     DENY    push-crlines-end       |  5314 ms |   484 ms |  1753 ms |  6830 ms 
main     DENY    push-crs-end           |  3543 ms |   446 ms |  1860 ms |  3704 ms 
main     DENY    push-escq-end          |  4127 ms |   471 ms |  2160 ms |  4208 ms 
main     DENY    push-heredoc-end       |  7015 ms |   492 ms |  1800 ms |  9427 ms 
main     DENY    push-lines-end         |  5623 ms |   515 ms |  1726 ms |  7451 ms 
main     DENY    push-short-end         |  2544 ms |   760 ms |  1820 ms |  2909 ms 
main     DENY    push-start-token       |  2524 ms |   556 ms |  1588 ms |  2905 ms 
main     DENY    push-token-end         |  2487 ms |   673 ms |  1726 ms |  2848 ms 
agent/x  DENY    push-bsl-end           |  4392 ms |   458 ms |  2152 ms |  4482 ms 
agent/x  DENY    push-bsnl-end          |  6694 ms |   658 ms |  1956 ms |  6671 ms 
agent/x  DENY    push-crlines-end       |  5296 ms |   467 ms |  1751 ms |  6840 ms 
agent/x  DENY    push-crs-end           |  3521 ms |   438 ms |  1876 ms |  3572 ms 
agent/x  DENY    push-escq-end          |  4157 ms |   437 ms |  1991 ms |  4202 ms 
agent/x  DENY    push-heredoc-end       |  6761 ms |   522 ms |  1711 ms |  9399 ms 
agent/x  DENY    push-lines-end         |  5550 ms |   467 ms |  1762 ms |  7319 ms 
agent/x  DENY    push-short-end         |  2432 ms |   578 ms |  1669 ms |  2857 ms 
agent/x  DENY    push-start-token       |  2395 ms |   591 ms |  1680 ms |  2778 ms 
agent/x  DENY    push-token-end         |  2436 ms |   469 ms |  1537 ms |  2902 ms 
```

### L21 re-time (host, no jq, agent/x)
```
heredoc-nobsnl run1 DENY 7086 ms
heredoc-nobsnl run2 DENY 6768 ms
heredoc-nobsnl run3 DENY 6924 ms
heredoc-1bsnl run1 DENY 9555 ms
heredoc-1bsnl run2 DENY 9410 ms
heredoc-1bsnl run3 DENY 9224 ms
lines-nobsnl run1 DENY 5460 ms
lines-nobsnl run2 DENY 5501 ms
lines-nobsnl run3 DENY 5368 ms
lines-1bsnl run1 DENY 7596 ms
lines-1bsnl run2 DENY 7264 ms
lines-1bsnl run3 DENY 7523 ms
heredoc-1bsnl-silent run1 silent 9824 ms
heredoc-1bsnl-silent run2 silent 9680 ms
heredoc-1bsnl-silent run3 silent 9609 ms
```

### I1 sentinel probe (scratch verify.sh copy, fake test.sh)
```
control: rc=0 PASS | temp left: 0
crlf: rc=0 PASS | temp left: 0
subpkg: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
subpkg2: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
modprefix: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
skipok: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
skipped: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
xfail: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
okplus: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
lead: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
prefix: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
notok: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
embedded: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
dotwild: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
printed: rc=0 PASS | temp left: 0
failafter: rc=1 verify fast: FAIL (test.sh exited non-zero | temp left: 0
none: rc=1 verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run | temp left: 0
```

### Table A mode parity, r4: host no-jq = image no-jq (identical); image no-jq vs image jq (known NUL rows)
```
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

### Table B: r4 vs r3 per mode
```
host: identical (132 rows)
imgjq: identical (132 rows)
imgnojq: identical (132 rows)
```

### Table A: host, no jq, r4 hook (373 rows)
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
agent/x  DENY    | %G% push origin x%BS%%NL%%M%   [rc=0]
agent/x  DENY    | %G% push origin x %BS%%NL%%M%   [rc=0]
agent/x  DENY    | %G% %P%%BS%%NL% origin %M%   [rc=0]
agent/x  DENY    | %G% push%BS%%NL%origin %M%   [rc=0]
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
agent/x  DENY    | %G% %P% origin x%BS%%NL%%M%   [rc=0]
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
