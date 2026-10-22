# Review, platform-supply-chain unit 4 (reviewer, 2026-10-21)

Scope: git diff 769b507 (uncommitted U4): scripts/verify.sh, scripts/scan.sh,
docker/app.Dockerfile, tests/test_stack_scripts.py, test_stack_model_keys.py,
test_harness_port.py, test_image_scan.py, CLAUDE.md, README.md; evidence u4-*;
PSC-6, PSC-7 (D6), carry-ins r3-1, r3-2, r3-3, L-1, I-1; D9 docs.
Probes: review-u4-probes.txt (read-only; container labelled ke-reviewer=psc-u4).
No mutants of my own were needed: the tester's 16 guard and 28 RED mutants
(u4-red-mutants.txt) already cover each wiring shape I would have tried
(no scan, before teardown, after offline_check, "|| true", warn-only,
backgrounded, twice, in fast, second teardown, argument, wrong tag; L-1 and
I-1 variants).

## Verdict: CHANGES REQUESTED

The code, tests and D9 text pass review. The two blocking findings are about
the PSC-7 record (where it is saved, and where the outcome is written down),
not the code.

## Blocking

B1. The PSC-7 / D6 record is not at the path the criteria name.
- docs/requirements.md:2836-2837 (PSC-7) and docs/architecture.md:6065
  (D6), plus the first-tests list at docs/architecture.md:4103, name
  docs/evidence/platform-supply-chain/l13-psycopg-libs.md. That file does
  not exist. The content (correct, and complete per D6 steps 1-3) is in
  u4-psc7-psycopg-libs.txt.
- docs/architecture.md:6062-6063 (D6) names scan-full.txt for "one real
  full run's scan output". That file does not exist either. The output is
  in u4-green-verify-full.txt:1601-1914.
- Why blocking: PSC-7 is a deliverable of this unit, and its acceptance
  criterion points at a file that is not there. Once the handoff is
  archived, nothing leads a reader from PSC-7 to the result.
- Fix (developer): save the record as l13-psycopg-libs.md, either by
  renaming u4-psc7-psycopg-libs.txt or by copying it and leaving a one-line
  pointer. Save scan-full.txt (lines 1601-1914 of u4-green-verify-full.txt,
  with the command and tag in a header). The other option is for the
  architect and analyst to repoint those three lines at the u4- files. Pick
  one; the pointers and the files must agree.

B2. No durable doc records the PSC-7 outcome. The orchestrator's GREEN
acceptance ("the docs must say so") is not yet met.
- Today the result is only in evidence and in the handoff. requirements,
  architecture and open-questions still give it as a condition:
  - docs/requirements.md:2832-2835: "If it reported none, L-13 stays a
    documented residual";
  - docs/architecture.md:5822-5824 (ADR-KE-013 Consequences): "Whether
    grype sees ... is recorded at implementation";
  - docs/architecture.md:6074-6075 (D6): "If no component is found ...";
  - docs/open-questions.md:346-348 (Q42): "If the scanner does not see
    psycopg_binary.libs at all ...".
- None of these claims coverage, so the "no doc claims the scan covers it"
  half of PSC-7 holds. What is missing is the "documented residual" half.
- The Q42/PSC-5 psycopg-binary branch can now never trigger from the scan.
  It assumes the scanner can flag a vendored library: docs/requirements.md
  lines 2799-2804 ("If a newer psycopg-binary wheel fixes a flagged vendored
  library ...") and docs/architecture.md:6053-6056. A reader of those lines
  would expect a krb5 or openssl CVE in the wheel to turn full red. It
  never will.
- Fix (one dated line each, owner architect/analyst via the orchestrator):
  - In D6 (or the ADR-KE-013 Consequences bullet) and in PSC-7, record
    "2026-10-21: grype v0.120.1 catalogues none of the 15 files in
    psycopg_binary.libs (l13-psycopg-libs.md). L-13 is a residual mitigated
    only by gssencmode=disable (PS-2.5). The scan does not cover these
    libraries."
  - Mark the Q42 psycopg-binary branch as moot for the scan.
  - Whether to open the "psycopg on Debian's libpq" follow-up now is an
    orchestrator call.

## Nits (optional)

N1. README.md:163-166 (wording) and :169. "...then tears the stack down,
scans the ke-app image, and finally runs the offline check (stage order:
... teardown, scan, offline_check)" is followed by "full also runs the
offline check". The "also" now repeats the sentence before it, and the
parenthetical starts with an ellipsis. Drop the parenthetical or reword
:169. The rest of the README is accurate to the code:
- D9's two sentences are verbatim;
- grype.anchore.io matches SCAN_DB_URL (scan.sh:18);
- "fixed High or Critical" matches --only-fixed --fail-on high;
- "no retry and no skip" matches fail() in scan.sh;
- "fresh on every run" holds: own project, volume removed.
A one-clause caveat after "known vulnerabilities" would help readers: "it
does not see the native libraries vendored in psycopg-binary (L-13)". It is
not required, since no README line claims they are covered.

N2. CLAUDE.md:24. The D9 text is verbatim (checked word for word, see the
probes file) and nothing else in CLAUDE.md changed. But it went in as one
unwrapped line of about 600 characters, while the rest of the file wraps at
about 78. Rewrapping keeps the words verbatim.

N3. scripts/verify.sh:4-12. The usage and header comment still describe
full as build, launch, gates-it, smoke, teardown. It names neither the
offline check (already missing before this unit) nor the scan.

N4. tests/test_stack_model_keys.py:319. The subset assertion is
{"build","launch","smoke","teardown"}. The new scan stub's environment is
checked only because the glob happens to pick it up. Add "scan" (and
"offline_check"), so the PSC-6 bullet "the scan takes no key from the
caller's environment" is pinned rather than incidental.

N5. scripts/scan.sh:36-37. ^ke-scan-[0-9]+$ is matched without LC_ALL=C,
unlike verify.sh:35 and scan.sh:24. It is not exploitable: nothing that can
match [0-9] in any locale is "/", a space or a shell metacharacter. A
locale-proof form that avoids the SC2030/31 subshell the tester hit is
^ke-scan-[0123456789]+$. Security has the final call.

N6. u4-green-lock-absent.txt (122 bytes) has no command line and no image
tag. I re-probed ke-app:wt-33a132fbfdd7 (id sha256:9eb199cd..., created
23:16:29Z): /opt/venv/.lock is absent, and there is no other world-writable
regular file outside /proc, /sys, /tmp and /dev (review-u4-probes.txt
section 1). Next time, add the header.

N7. docs/architecture.md:358-359 (section 2.2 sequence diagram) and
:368-370 are plan text from before this unit ("this branch has no scan
stage (R3)"). The as-built diagram still goes teardown -> offline_check
with no scan.sh step. This is an architect follow-up, not developer work.

## Checks requested by the orchestrator

- verify.sh wiring per D4: OK.
  - scripts/verify.sh:113 is one line after "teardown_verify || exit 1"
    (:110) and before scripts/offline_check.sh (:116), host half of full
    only. fast execs into gates at :51 and never reaches it.
  - Fail-closed: set -euo pipefail (:15), so a non-zero scan.sh exits;
    cleanup sees rc != 0 and prints no PASS.
  - No second teardown: torn_down=1 was set at :87 before the scan, so
    cleanup (:96) skips it.
  - No arguments; KE_IMAGE_TAG is inherited.
  - grype is not inlined, and the forbidden list (test_harness_port.py:194)
    now includes it.
  - INT/TERM: the traps in scan.sh run its own cleanup. verify.sh then
    exits non-zero, through set -e (scan.sh exits 130 or 143) or through
    the signal, and its EXIT trap does no further teardown. Pinned by
    test_verify_full_fails_when_image_scan_fails (SIGINT and SIGTERM
    subtests: rc != 0, teardown count 1, no offline_check).
- Test changes: no existing guarantee is weakened.
  - FULL_ORDER gains scan. The exact order is still pinned by
    test_full_runs_stages_in_order_then_tears_down and the new
    test_verify_full_runs_scan_between_teardown_and_offline_check, and
    every stage, including scan, goes through
    test_each_failing_stage_fails_verify_and_still_tears_down.
  - In the offline_check-last test (test_stack_scripts.py:1251-1258),
    stages[-2:] == [teardown, offline_check] is relaxed to "last" plus
    "after teardown". Exact adjacency now lives in the FULL_ORDER tests, so
    nothing is lost.
  - The project and overlay checks skip scan the same way they skip
    offline_check. The scan project and compose file are pinned in
    test_image_scan.py.
  - The I-6 regex (test_image_scan.py:1331-1335) now also accepts the
    SRANDOM forms with a "-" or ":-" default and still rejects RANDOM. The
    new L-1 test makes up for this: 9 malformed cases plus a control, none
    reaching docker or mkdir, and each printing a FAIL line.
  - Additions that tighten:
    - assertNotIn("scan") on interrupts in earlier stages (:1098);
    - grype added to the forbidden list;
    - the scan stub in the model-keys harness.
  - The only removal is the R3 assertion (:1271), which the orchestrator
    accepted.
- CLAUDE.md: verbatim to D9; nothing else changed (N2 is formatting only).
- README: accurate (N1).
- PSC-7: the evidence is correct, and no doc claims scan coverage. The
  record path and the durable statement are B1 and B2, which list the lines
  to change.
- PSC-9 CI cost: the stage markers are enough. Each stage opens with a
  "== scan: STAGE ==" line, then "== scan: done ==", then the scan project
  teardown, then "offline: df start". From the runner's per-line
  timestamps:
  - save = t("== scan: scan-db ==") - t("== scan: save ==");
  - scan-db = t("== scan: scan ==") - t("== scan: scan-db =="). This
    includes the grype image pull. The "Pulled" line and the first
    "Network ke-scan-N_default Creating" line split pull from DB fetch if
    needed;
  - scan = t("== scan: done ==") - t("== scan: scan ==").
  - The scan project teardown (between done and "offline: df start") falls
    outside the three. It is about 1-2 s and bounded by those two lines.
  - The integer "scan: STAGE took Ns" lines are a cross-check
    (u4-green-verify-full.txt:1603-1915).
- Scope: no creep. The _TAR_CHMOD spacing (test_image_scan.py:1498) is
  r3-3. Observability: no agent loop, model call, retrieval or tool call is
  added, so no span is needed. Do not commit the untracked
  docs/knowledge-engine-claude-code-prompt.md.
