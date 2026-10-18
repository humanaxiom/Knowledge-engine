# Re-review: harness-followups, rework 5 (review N19, N21; docs gate N15a/b/c, L23)

Reviewer, 2026-10-18. Round 5 of 5 (final). Bar: block only on a spec violation, a broken gate,
silent test loss, or a regression against a11842d. Diff against a11842d, uncommitted. The
platform-skeleton plan sections are out of scope. Raw output: `review-rework5-raw.txt`.

Verdict: APPROVED (0 blocking; N19, N21, N15a, N15b resolved; N15c mostly resolved; 3 new nits)

## Method
- Read review-rework4.md, the tester and developer rework-5 sections, green-rework5.txt, and
  `git diff a11842d` for scripts/verify.sh, ci.yml, CLAUDE.md, AGENTS.md, README.md and
  ADR-KE-001 (architecture.md L862-987).
- Reproduction and mutants ran on a scratch copy in `knowledge-engine-gates:latest` with
  `--network none` and `KE_IN_GATES=1`. Repo scripts were never edited.
- My own `scripts/verify.sh full`: PASS, Ran 98 tests, OK, smoke pass (raw section 4).

## 1. N19: RESOLVED
- verify.sh:39 now runs `grep -Pq '^...ok\r?$' "$log"` on the file. There is no pipe, so no
  SIGPIPE under pipefail.
- Reproduction, 10 runs each at 60, 70, 100, 200 and 1024 KB after the sentinel:
  - new verify.sh: 0 failures at every size;
  - control (rework-4 `tr | grep -Eq` restored in the copy): 2/10 at 100 KB, 10/10 at 200 KB
    and at 1 MB.
- So the harness still reproduces the bug, and the fix removes it.
- The new test `test_sentinel_followed_by_large_output_passes` (about 320 KB, 5 attempts x 2
  modes) bites: mutant k8 (pipeline restored) gives 10 failing subtests.

## 2. N21: RESOLVED
The test now builds the line from the live `TopLevelSuiteSentinelTest(...).id()`, parses the
one single-quoted pattern out of verify.sh, and checks both anchors plus prefix and suffix
rejection. Mutants:
- class renamed in the module only (k1): RED, and verify on the copy FAILs;
- class renamed in the module and in verify.sh (k2): RED;
- class renamed in the pattern only (k3): RED;
- method renamed (k4): RED;
- module moved to `tests/sub/` (k7): RED;
- `$` dropped, `\r?$` dropped, or `^` dropped (k5, k5b, k6): RED.

The name is now really guarded.

## 3. `grep -P` outside the gates image
- CI does not set `KE_IN_GATES`, so `./scripts/verify.sh full` re-execs into the image. The
  only place `KE_IN_GATES=1` is set is `docker/gates.Dockerfile`.
- The gates branch runs outside the image in only two cases:
  - (a) a caller exports `KE_IN_GATES=1` on the host. This is the accepted override from
    security L5.
  - (b) someone runs `VerifyRequiresTestsRunTest` directly on the host, not through
    test.sh. Its copies of verify.sh then use the host's grep.
- Neither case is a documented workflow.
- Host Git Bash grep 3.0 supports `-P` (probed). A grep with no PCRE support, such as BSD grep,
  exits 2, `if !` treats that as no match, and verify FAILs. So it fails closed.
- Not a finding. N24 records it.

## 4. Docs accuracy: matches the code
- ADR-KE-001 Decision (L927-951) matches the hook:
  - CR deleted;
  - text (a) joins backslash-newline to nothing;
  - text (b) is built only under the `case` guard and turns backslash-newline into a space;
  - deny if either text matches;
  - no awk, never prints `allow`.
- Consequences (L952-981) list:
  - the three false positives I asked for;
  - the off-main L23 / Table M 14-15 bypass;
  - the on-main Table M 14-15 bypass;
  - the %G%<CR>%P% bypass;
  - L21 timing.
- N16 is correctly not recorded.
- The sentinel as-built bullet (L882-892) states the exact line and the rename rule, matching
  verify.sh. N3 (CR in the Normalise bullet) is closed too.
- CLAUDE.md, AGENTS.md and README.md claims checked against test.sh, verify.sh and ci.yml:
  - Ran N > 0;
  - the sentinel;
  - a missing `__init__.py` fails at any depth;
  - integration runs only in full;
  - ubuntu-24.04;
  - checkout pinned to a SHA;
  - `persist-credentials: false`.
  All accurate.
- The suite (98 tests, including the port-mirror and wording tests) is green on my run, so the
  mirrored blocks and banned words are intact.

## 5. Tests: none weakened
98 tests (97 in rework 4, plus 1 for N19). N21 was rewritten in place and is stricter. No skip
or expectedFailure lines in the full run.

## New findings (all nits)
### N22 (nit): the `\r?` CRLF branch of the sentinel pattern is untested
Mutant k9 (`grep -Pq` changed to `grep -Eq`, same pattern) passes all 11 verify tests. In ERE,
`\r` is a literal `r`, so a CRLF log would false-FAIL. This fails closed, and the image emits
LF. Optional: add a fake test.sh that prints the sentinel with a CRLF ending.
### N23 (nit): stale wording in the N21 test
`verify_sentinel_pattern` still calls the pattern an "ERE". It is PCRE now, and the test uses
Python `re` as a proxy for it. The two agree for this pattern.
### N24 (nit, record): verify.sh now needs a PCRE-capable grep
This holds only on the `KE_IN_GATES=1` host-override path, and it fails closed there. Worth one
line in the verify.sh header if the override is ever documented.

## Open non-blocking findings across all rounds (item-close record)
| Id | Source | Status | Note |
|---|---|---|---|
| N4 | review r0 | open | No-jq path reads `\uXXXX` escapes as letters. Pre-existing. Still not listed with the accepted bypasses in ADR-KE-001 |
| N10 | review r2 | open | Symlinked test package skipped silently (find does not follow links) |
| N11 | review r2 | open | `2>&1 \| tee` merges stderr and maps every test.sh failure to rc 1. Not commented in verify.sh |
| N12 | review r2 | open | Dead `tests/__pycache__` case in the test.sh loop |
| N13 | review r3 | partly open | s8 (top-level glob narrowed) and f3 (deliberate stderr forgery) still pass. Both need targeted edits |
| N15c | review r3/r4 | mostly closed | CLAUDE.md, AGENTS.md, README.md and the ADR state the contract. The verify.sh header still has only the inline comment. No doc mentions the optional trailing CR |
| N20 | review r4 | open | L21 timing test does not discriminate in the image. Host evidence only (hook-timing-host-r4.txt) |
| N22-N24 | review r5 | open | Above |
| L21 | security r3/r4 | partly fixed, low | 5 MB+ commands with a backslash-newline: 9.2-9.8 s worst case vs the 10 s timeout on host |
| L23 | security r4 | accepted, low | Off-main word-split after a comment or even run. Recorded in the ADR |

Closed this round: N19, N21, N15a, N15b, N3. Closed earlier: B1-B3, N1, N2, N5-N9, N14, N16
(obsolete), N17.
