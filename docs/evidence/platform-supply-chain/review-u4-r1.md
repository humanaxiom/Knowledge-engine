# Re-review, platform-supply-chain unit 4, rework round 1/5 (reviewer, 2026-10-22)

Scope: git diff 769b507 (uncommitted U4 + rework 1). Prior findings:
review-u4.md (B1, B2, N1-N7), security-u4.md (M-1, L-1, L-2).
Evidence read: u4-rework1-red-verify-fast.txt (763 run, 6 failures, all the
new M-1 subtests, "PASS unexpectedly found"), u4-rework1-mutants.txt (8/8
green-shape mutants killed, N4 guard kills 2, control passes),
u4-rework1-green-verify-fast.txt (PASS), u4-rework1-green-verify-full.txt
(offline_check PASS, "== verify full: PASS (625s) ==").
My probes: review-u4-r1-probes.txt (real verify.sh host half, stub stages,
fake docker, gates image, --network none).

## Verdict: APPROVED

No blocking findings. B1 and B2 are closed, and so are N1 (in part), N2-N5 and N7.

## Closed

- B1 (record paths). Every pointer now names a file that exists:
  - requirements.md:2837-2838 and 2844 (PSC-7);
  - architecture.md:4096 and 4106 (first-tests list), and 6078-6081 (D6).
  - They point at u4-green-verify-full.txt lines 1601-1914 and
    u4-psc7-psycopg-libs.txt. No live doc names l13-psycopg-libs.md or
    scan-full.txt; the only remaining hits are in the handoff history.
- B2 (durable record). The dated 2026-10-21 result is recorded in:
  - PSC-7 (requirements.md:2845-2853);
  - ADR-KE-013 Consequences (architecture.md:5828-5835);
  - D6 (architecture.md:6092-6105);
  - Q42 (open-questions.md:308-309, 350-360).
  - Each says that grype v0.120.1 catalogues none of the 15 files, that the
    scan does not cover them, that L-13 is an accepted residual (low), and
    names the compensating control and the structural fix.
  - The psycopg-binary branch is marked MOOT for the scan in PSC-5
    (requirements.md:2805-2810), D5 (architecture.md:6067-6071) and Q42.
  - The follow-ups (require_auth, security I-2) are at
    requirements.md:2994-3010.
- N1 (in part). The repeated "also" is gone: README.md:170 now opens with
  "The offline check". The ellipsis parenthetical at README.md:165 is still
  there (see r1-n1).
- N2. CLAUDE.md:23-31 is wrapped at 78 columns or less.
- N3. scripts/verify.sh:12-14: the header names the scan and the offline
  check.
- N4. tests/test_stack_model_keys.py:321: the subset now names scan and
  offline_check. The N4 mutants were killed (u4-rework1-mutants.txt).
- N5. scripts/scan.sh:36: `^ke-scan-[0123456789]+$`, with no subshell.
- N6. Already accepted.
- N7. architecture.md:338 and 360: participant C scan.sh, and the H->>C
  step between teardown and offline_check. Lines 359 and 370-374 describe
  the as-built order, and "the trap skips it once done" is now correct.

## Orchestrator checks

- CLAUDE.md is word for word the approved text. This was checked
  programmatically with whitespace normalised:
  - the approved paragraph is present;
  - substituting the base sentence with it in the base file gives the
    working file exactly, so nothing else changed;
  - the file has LF endings only.
- verify.sh cleanup (verify.sh:88, 96-115, 130):
  - PASS is printed only when `rc -eq 0 && finished -eq 1`.
  - finished=1 is set only after offline_check.sh returns (:130),
    immediately before `exit 0`.
  - Every other path prints FAIL:
    - set -e, `teardown_verify || exit 1`, and INT/TERM/HUP all reach
      "FAIL (exit N)";
    - a fatal signal with no trap (for example USR1, where $? is 0)
      reaches "FAIL (stopped before the last stage; no PASS)".
  - Probes: TERM to the group gives 143/FAIL. HUP during smoke gives
    129/FAIL. USR1 to the group or to verify alone gives 138/"stopped
    before the last stage". TERM during offline_check gives 143/FAIL. The
    normal run gives 0/PASS.
  - Teardown once: torn_down=1 is still set on entry to teardown_verify,
    and every probe and test shows a single teardown.
  - fast is unaffected: it execs at verify.sh:53, before any trap is set.
- No doc claims the scan covers psycopg_binary.libs. A grep of all *.md
  finds only statements that it does not: README.md:180-183, PSC-5,
  PSC-7, D5, D6, ADR-KE-013 and Q42.
- Tests:
  - The M-1 subtests (test_stack_scripts.py:1325, :1375) send INT, TERM
    and HUP to the process group during scan and during smoke. They assert
    128+n, no PASS, and a single teardown.
  - No existing assertion was weakened in rework 1.

## Nits (optional)

- r1-n1. The parenthetical "(stage order: ... teardown, scan,
  offline_check)" at README.md:165 still opens with an ellipsis, and
  README.md:176 ("`full` also scans") repeats :164. README.md:158 runs to
  82 columns.
- r1-n2. Behaviour change, not a defect. A TERM or HUP sent to verify.sh
  alone, not to its group, now waits for the foreground stage to return
  before the trap exits 143/129. The probe waited 19 s of a 20 s stage.
  Before rework 1, bash died at once but printed PASS. INT already behaved
  this way (security I-3). Group signals from a terminal, timeout(1) or
  the test harness are immediate. Worth one line in the verify.sh M-1
  comment.
- r1-n3. The "stopped before the last stage" branch (verify.sh:102-104) is
  not covered by any test: with the traps in place, a mutant that drops
  the finished flag survives. A USR1 subtest would pin it; my probe shows
  that it works.
- r1-n4. Inside cleanup, INT/TERM/HUP still exit at once, so a second
  signal during the trap's teardown skips the FAIL line. This predates
  rework 1, and scan.sh handles it with `trap '' INT TERM`. It never
  produces a PASS.
