# Reviewer: platform-supply-chain close-out (PSC-9, PSC-12, status table, Done check)

Date 2026-10-22. Base `34fc0c1` (HEAD) plus the uncommitted close-out. Read-only review.
Inputs: `git diff 34fc0c1` (ci.yml, tests/test_stack_ready_docs.py, docs/requirements.md,
handoff, docs/log.md); untracked psc9/, ci/, psc12-*; `gh run view` for both runs; commits
8900766..34fc0c1; docs/handoffs/README.md (Done check); archive/ci-speed.md (precedent).

## Verdict: CHANGES REQUESTED (1 blocking, docs/evidence only; 8 nits)

The code half (ci.yml timeout and the test pin) is correct and may stand as is. The blocker is
in the close-out status table: PSC-4's named manual evidence does not exist.

## Checks

1. **Recompute 37 (gh).** 39713504156 push, success, head 34fc0c1: startedAt 02:49:44,
   updatedAt 03:14:13 = 1469 s = 24.48 min (job 02:49:47-03:14:13 = 1466 s). 39713519072
   pull_request, success, head 34fc0c1: 02:49:55-03:12:55 = 1380 s = 23.0 min. Slower run
   x 1.5: 24.48 x 1.5 = 36.73, or 24.5 x 1.5 = 36.75 (job: 36.65). Rounded up, all give **37**. OK.
   Log lines checked: `verify full: PASS (1461s)` / `(1372s)`, `Ran 767 tests in 1001.955s` /
   `934.776s`, scan save 2/2 s, scan-db 90/81 s, scan 6/5 s. Total 98/88 s, under Q60's 180 s. OK.
2. **ci.yml.** The diff is line 17 only (`timeout-minutes` 32 -> 37 plus its comment). Kept:
   the single `./scripts/verify.sh full` step, `runs-on: ubuntu-24.04`, checkout
   `@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09` with `persist-credentials: false`, and
   `permissions: contents: read`. OK.
3. **Agreement.** `CI_TIMEOUT_MINUTES = 37`, the assertion message, the module docstring, the
   comment above the constant, the ci.yml comment, PSC-9 MET and psc9/ci-timeout.md all cite
   the same runs, minutes and 36.75 -> 37. RED->GREEN is real:
   - psc9/red-verify-fast.txt:1238 FAIL only on test_ci_job_has_timeout (767 run);
   - green-verify-fast.txt:1075 ok, OK (skipped=8);
   - green-verify-full.txt:2150 `PASS (641s)`.
   OK.
4. **PSC-12.** psc12-windows-run.txt is at HEAD 34fc0c1 (lines 104-106, 773). It follows the
   A34/PS-2.9 template structure:
   - metadata, Windows 10.0.26200, leftovers, temp .env;
   - build.ps1 exit 0;
   - launch.ps1 with 7/7 healthy, /healthz and /readyz 200, 127.0.0.1-only listeners and a
     non-loopback connect False;
   - shim self-check, then the PS-2.14 refusal (exit 1, compose up never reached);
   - teardown.ps1 with and without -Volumes, then `docker ps -a` by project label showing none
     (the same check the template uses);
   - cleanup, and the 7 Windows-only tests OK.

   The scope cuts from the 2b template (gateway, bad port, L-9) are stated and justified,
   since no .ps1 changed. I confirmed `git diff --stat 8900766~1 34fc0c1` touches no
   scripts/*.ps1. It touches docker-compose.scan.yml, app.Dockerfile, gates.Dockerfile and
   scan-ignore.yaml, so a fresh run was needed. `git diff 34fc0c1 --name-only` touches no .ps1,
   compose file or Dockerfile, so the proof is current. The sweep of the new evidence and the
   CI logs found no profile paths, SIDs or tokens. OK.
5. **Status table, re-derived from the commit messages and `git log -S` on the test defs.**
   - Unit mapping is correct: u1 PSC-10/11; u2 PSC-1/2/3/5/8; u3 PSC-4/17; u4 PSC-6/7;
     u5 PSC-18.
   - PSC-4 is split, though. test_scan_fails_on_fixed_high,
     test_scan_reports_but_passes_unfixed_and_lower and
     test_scan_command_is_exactly_the_d5_policy landed in 769b507.
     test_verify_full_fails_when_image_scan_fails landed in e6e1d28 (moved by the architect).
   - Evidence: see B1 and N1-N5.
6. **Done check.** It follows the README template's five fields and matches the ci-speed
   precedent. Figures checked:
   - 88-98 s (logs);
   - 423 -> 265 MB (u3-no-uv-in-ke-app.txt:1);
   - 37 min;
   - last milestone ci-speed at 32 (0148907).

   Blocker "none" is correct. As at ci-speed, it is documenter-drafted for the orchestrator to
   confirm. OK.
7. **Handoff length.** 117 lines before this review's line. Under 200. OK.

## Findings

### Blocking
- **B1. PSC-4's required manual evidence is missing, but the table lists PSC-4 as shipped.**
  requirements.md:2786-2787 requires "a recorded red run of the real scan with a mutant policy
  (no `--only-fixed`, `--fail-on negligible`) fails on the real image". The tags summary at
  :3033 also lists "mutant policy" among the recorded red runs.
  - I searched docs/evidence/platform-supply-chain/** for `negligible`, `only-fixed`,
    `mutant polic*` and `fail-on negligible`. No such run exists.
  - The only mention is the plan line in archive/platform-supply-chain-part1.md:68.
  - The unit-3 row lists u3-green-verify-full.txt, u3-real-scan.txt, u3-no-uv-in-ke-app.txt and
    security-u3.md. All of them are real-policy runs or analysis.
  - Related evidence exists but is not the named control:
    - u2-green-real-scan.txt:314, the real policy failing on certifi/quinn-proto;
    - security-u3.md §4, which reports 82 High/Critical suppressed only by `--only-fixed`;
    - review-u3 m4/m5b, fake-docker flag mutants.

  Fix, either:
  - (a) the tester records the run against ke-app at HEAD and saves it, for example
    `psc4-mutant-policy-red.txt`, with the exit code and the failing rows. Then add it to the
    unit-3 row. Or
  - (b) the orchestrator records a ruling in requirements PSC-4 that accepts the above as
    equivalent, with the reason, and the table cites it.

  Do not close the item with the table as written.

### Nits
- **N1.** The evidence column omits the other named manual evidence. The `review-u*.md` /
  `security-u*.md` globs do not match .txt files. Missing:
  - PSC-3 unresolvable host: review-u2-red-unresolvable-host.txt;
  - PSC-5 planted ignore: u2-green-confirm-d3-d5.txt (D5 block, exit=2, certifi `(suppressed)`);
  - PSC-10 wrong-hash mutation: review-u1-mutation-builds.txt;
  - PSC-7 output: u4-green-verify-full.txt lines 1601-1914 (named in PSC-7 itself).
- **N2.** The unit-3 row lists security-u3.md but not review-u3.md (and review-u3-mutants.txt).
  Every other row lists both.
- **N3.** PSC-4 spans units 3 and 4: test_verify_full_fails_when_image_scan_fails is in
  e6e1d28. Say "3 (+4)" or footnote it.
- **N4.** "each with its tests in `scripts/verify.sh full`" is not true for PSC-7. By design it
  is "Evidence, checked by the reviewer and security; no unit test" (:2854).
- **N5.** The PSC-2/Q59 arm64 scan evidence (`arm64/`) is not recorded. That is correct per the
  Q59 ruling (it comes with the next recorded arm64 bundle run). Say so in the table, so the
  close-out does not read as full coverage.
- **N6.** The handoff's Summary block (lines 7-12) is stale: "Commits so far: 8900766", "State:
  U2 GREEN". It is moot if the doc is archived at this commit; otherwise refresh it.
- **N7.** The orchestrator's "PR #10 CI GREEN x2" handoff entry has no docs/log.md line. Its
  "job 24.5 min" is the run duration; the job was 24.4 min. ci-timeout.md already says this,
  and the result is unchanged (same as ci-speed review N1).
- **N8.** psc12-verify-fast.txt ran on `34fc0c1+dirty` while the PSC-9 edits were in flight.
  It is supplementary, not part of the A34 proof (the PowerShell run is), so this is no issue.
  Just don't cite it as a clean-HEAD run.

## Observability
No agent loop, model call, retrieval or tool call was added. No span is required.

## Next
- Developer/tester/documenter: close B1 by option (a) or (b).
- Optionally fold N1-N5 into the same table edit.
- Then reviewer re-check of the table only. The code half needs no re-review.

## Re-check (2026-10-22, reviewer): PASS

Scope: the "Status at close-out" table (requirements.md:3039-3055) and psc4-mutant-policy-red.txt only.
HEAD is still `34fc0c1`. `git diff --stat 34fc0c1` lists only ci.yml, the handoff, log.md,
requirements.md and tests/test_stack_ready_docs.py, so no Dockerfile, compose file, scan.sh or
scan-ignore.yaml changed. Read-only.

- **B1: closed.** The PSC-4 row (:3053) cites `psc4-mutant-policy-red.txt`, and that file exists.
  - Image: ke-app:wt-33a132fbfdd7, rebuilt at 34fc0c1 in the tester's own project. Its RootFS layers
    match `ke-app:bundle-34fc0c10a498` byte for byte. It is 265 MB.
  - Mutants: scratch copies only, and the `diff -u` against the repo compose is shown. Mutant A
    deletes only `--only-fixed`. Mutant B changes only `high` to `negligible`. I confirmed both
    lines in the repo's docker-compose.scan.yml (:38-40). The control copy is identical to the
    repo (empty diff).
  - Mutant A: scan.sh exit 1, `scan: FAIL (stage scan: grype exited 2 ...)` (:471), and grype's
    threshold ERROR (:469). I recounted the full table (:180-468): 289 rows, 82 High/Critical, and
    none of the 82 has a fixed version. So removing `--only-fixed` alone trips the fail.
  - Mutant B: exit 1, `grype exited 2` (:789). The 13 unsuppressed rows are all Medium/Low/Negligible
    (python 3.12.15 binary, pip 25.0.1). So the lowered threshold alone trips the fail.
  - Control: exit 0, `== scan: done ==` (:1106). The same 13 sub-High rows are unsuppressed and do
    not fail. This shows the policy, not the image, makes the difference.
  - Cleanup and redaction: no ke-scan-* container, network or volume is left over, and the scratch
    path is redacted.
  - Repo files: no repo file was modified (git status agrees).
- **N1: addressed.** The table now names review-u2-red-unresolvable-host.txt (PSC-3),
  u2-green-confirm-d3-d5.txt (PSC-5), review-u1-mutation-builds.txt (PSC-10) and
  u4-green-verify-full.txt lines 1601-1914 (PSC-7). The PSC-7 output starts at :1601 and ends at
  ~1914, before offline_check. All the cited files exist.
- **N2: addressed.** The unit-3 row lists review-u3.md. Residual nit, optional:
  review-u3-mutants.txt is still not listed. review-u3.md references it, so this is not a gap.
- **N3: addressed.** The row reads "PSC-4 (units 3 and 4)" / "3 (PSC-4 also 4)" and names e6e1d28
  for test_verify_full_fails_when_image_scan_fails.
- **N4: addressed.** The preamble says "Criteria with unit or integration tests have them in
  verify full" and "PSC-7 is evidence-only by design".
- **N5: addressed.** The preamble says the arm64 scan evidence (PSC-2, Q59) is deferred to the next
  recorded arm64 bundle run and is not in this table.
- **Agreed follow-up (orchestrator):** scan.sh's FAIL text hard-codes "a fixed High or Critical
  match". Under a mutant policy that names the wrong trigger. It is cosmetic and does not affect
  the gate.

Observability: no agent loop, model call, retrieval or tool call was added, so no span is needed.
