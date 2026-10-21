# Re-review: harness-followups, rework 4 (security M6, L21, I1; review N14, N17)

Reviewer, 2026-10-18. Round 4 of 5. Bar: block only on a spec violation, a broken gate, silent
test loss, or a regression against the base hook a11842d. Diff against a11842d (uncommitted):
the hook, `scripts/verify.sh`, `scripts/test.sh`, `.github/workflows/ci.yml`, and the three test
files. Plan docs are out of scope. Notation as in the security reports: %G% the version-control
word, %P% the upload verb, %M% the default branch, <bs> backslash, <NL> newline, <CR> carriage
return. The hook denied the first draft of this file because one line held all three words: an
accepted fail-safe false positive.

Verdict: APPROVED (0 blocking, 3 new nits, carried nits listed for the docs gate)

## Method
- Hook probes: 49 shapes (my rework-3 set rebuilt, Table M rows 1-16, q1, q2, N14 multi-line
  controls, a CR separator) x %M%/agent/x x 3 modes (gates image jq 1.6; image with jq shadowed
  by a stub exiting 127; Windows Git Bash with no jq). The base hook came from
  `show a11842d:...`. Payloads were written to files by `json.dumps` and piped on stdin into
  throwaway repos.
- Mutants: run on a scratch copy of the repo (`.venv` and `.git` excluded) in
  `knowledge-engine-gates:latest`, with `--network none` and `KE_IN_GATES=1`. The repo scripts
  were never edited. The scratch copies were deleted afterwards.
- Raw output for everything below: `docs/evidence/harness-followups/review-rework4-raw.txt`.

## 1. M6: FIXED, no regression against a11842d or rework 3
- Table M rows 1-11, q1 and q2 deny off the default branch in all 3 modes (base also denied
  them; rework 3 was silent on rows 1-10, q1 and q2). Rows 13 and 16 deny on the default
  branch. Row 12 is silent.
- Base vs new over 98 rows x 3 modes: **no DENY to silent caused by rework 4.** The only
  DENY-to-silent row is `cr-sep` (%G%<CR>%P% origin %M%, jq mode only; with no jq it was
  already silent on base). It comes from the PS-0.4 CR deletion, which has been in place since
  rework 1. Bash reads the glued pair as one word, and PS-0.4 requires "deny as without the CR".
  Recorded, not a finding.
- Against rework 3, by its recorded columns: `cont-originmain` and `cont-gitpush-glued` off the
  default branch are back to DENY, as on base, because text (b) now joins with a space. **The
  N16 "intended behaviour change" is obsolete.** Do not document it; record these as fail-safe
  false positives instead (bash reads one glued word).
- Rows that newly deny relative to base (all fail safe): `cont-mid-word` and
  `cont-gitword-split` (the PS-0.5 join), `crlf-cont`, `cr-literal` (no jq), `sq-literal`.
- Benign controls (`benign`, `benign-cont`, `benign-ls`, `plan-item-cont`, `ml-*`) are silent.
- L21: the case guard on the base text matches only a backslash-newline. It does not match a
  bare newline or a lone backslash, and CRLF is normalised first. Host timing evidence: 4.9 s
  with one pass, 6.8 s with two, against the 10 s timeout. Accepted.
- Mutant hA (text (b) back to a newline) turns 24 subtests RED, so the M6 tests bite.

## 2. N17 / I1: RESOLVED
| Mutant | Result |
|---|---|
| s0 baseline | PASS, 97 tests |
| s1 sentinel check deleted from verify.sh | caught: 8 subtests (old B3 and new N17/I1 tests) |
| s2 m1 + tests/unit + sentinel moved into tests/unit | **RED now** (was a silent PASS in rework 3; module id differs) |
| s3 sentinel skipped, reason x / s3b reason "... ok" | RED / RED |
| s4 sentinel fails | RED (rc) |
| s5 sentinel file deleted | RED |
| s6 m1 + same class and method names in tests/unit | RED |
| s7 m1 + skip reason newline + full sentinel line | RED (unittest prints the repr, so the line stays one line) |
| f4 m1 + skip reason = full sentinel line | RED |
| s9 only the first top-level module runs | RED |
| s8 top-level glob narrowed to tests/test_sent*.py | PASS, 1 test (carried N13) |
| f3 m1 + a test that writes newline + exact sentinel line to stderr | PASS (deliberate forgery; outside the threat model per security I1) |

N13 is half closed (s2 is now caught). s8 and f3 need deliberate, targeted edits. They stay nits.

## 3. Tests: none weakened
- Hook test file vs a11842d: +202/-0. Test count is 89 -> 97, which is exactly the 5 new hook
  methods plus the 3 new sentinel methods. No skips or expectedFailure were added, and no
  existing assertion changed.
- Table M rows 14 and 15 left unpinned: **agreed.** They are silent on base, rework 2,
  rework 3 and rework 4 in all 3 modes (re-probed). Asserting None would pin a bypass as
  desired behaviour, and asserting deny would be a new requirement, not a fix. The test
  comment records them as an accepted bypass. They should go in the ADR (see N15b).

## Findings

### N19 (nit, high priority, fails closed): new sentinel pipeline can false-FAIL a correct run
`scripts/verify.sh:38` pipes `tr -d` (CR removal) into `grep -Eq` under `set -o pipefail`.
When more than about 64 KB of output follows the sentinel line, `grep -q` exits on the match,
`tr` gets SIGPIPE (141), the pipeline fails, and verify reports "sentinel ... did not report ok".
Reproduced: 1/10 failures at 60 KB after the sentinel, 2/10 at 70 KB, 10/10 at 200 KB (raw,
section 4). It does not fire today: the sentinel prints near the end of a ~12 KB log. test.sh
prints every sub-package and integration suite *after* the top-level run, though, so the first
sizeable integration suite (platform-skeleton) will make the gate red, first intermittently and
then always. It fails closed and cannot let bad code through, so it does not block under the
bar for this round. Rework 3 read the file directly and did not have this problem.
Fix, one line: grep the log file directly with no pipe and allow an optional trailing CR in the
pattern, or keep the pipe and drop -q (count matches to /dev/null). Add a verify test whose
fake test.sh prints the sentinel followed by more than 200 KB. Recommendation: fix it now, or
make it the first task of platform-skeleton, before any sub-package or integration suite lands.

### N20 (nit): the L21 timing test does not discriminate in the gates image
Mutant hB (guard removed, text (b) always built) passes all hook tests. Two passes take at most
about 2.3 s in the image, under the 3 s bound. This is a performance-only mutant: without a
backslash-newline, text (b) equals text (a). L21 is therefore guarded only by the host evidence
(hook-timing-host-r4.txt). Optional: assert the structure instead, or accept it as is.

### N21 (nit): test_sentinel_line_is_the_exact_full_line is a tautology
It compares the class constant to the same literal. It pins the string but adds no behaviour
check. Harmless.

### Docs gate: open doc nits (architect/documenter)
- **N15a, ADR-KE-001 Decision** (docs/architecture.md ~L919): "Normalise: join line
  continuations" is stale. It should say:
  - CR deleted (PS-0.4);
  - text (a): backslash-newline joined to nothing (PS-0.5, M5);
  - text (b): built only when a backslash-newline is present (L21); backslash-newline becomes a
    space (M6);
  - deny if either text matches.
- **N15b, ADR-KE-001 Consequences:**
  - Add the accepted false positives: backslash-newline inside single quotes (sq-literal),
    a continuation glued with no space (bash reads one word, e.g. origin<bs><NL>%M%), and
    comment or even-run shapes.
  - Add the accepted bypasses: Table M rows 14 and 15 (a continuation that splits the %G% or
    commit word after a comment or even run, on the default branch), and %G%<CR>%P%.
  - Drop N16 (the rework-3 behaviour change no longer exists).
- **N15c, sentinel contract:** neither CLAUDE.md, AGENTS.md nor the verify.sh header says that
  verify requires the exact line
  "test_top_level_unit_suite_ran (tests.test_sentinel.TopLevelSuiteSentinelTest.test_top_level_unit_suite_ran) ... ok".
  They also do not say that tests/test_sentinel.py must stay top-level with its module, class
  and method names unchanged, or that renaming any of them turns every verify run red.
  verify.sh has an inline comment only.

### Carried (nits, unchanged)
N10, N11, N12 (test.sh is byte-identical to rework 2). N13 is partly closed (s8 remains). N14
is resolved (test_multiline_without_backslash_newline_unchanged,
test_real_continuation_of_plan_item_push_stays_silent). N17 is resolved.
