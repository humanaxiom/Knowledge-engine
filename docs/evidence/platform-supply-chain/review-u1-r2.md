# Re-review u1 after rework round 2/5: M-U1R1-1 (tests and docs only)

Reviewer, 2026-10-21. Scope: the round-2 changes to `_psa_check_masking` (tests/test_gates_docker_cli.py:732-748), its self-check
samples (:879-896), PSC-10 and Follow-ups (requirements.md:2868-2977), and D7 step 2 and §2.6 item 2 (architecture.md:6075-6083,
:3998-4016). Prior: `review-u1-r1.md` (APPROVED), `security-u1-r1.md` (M-U1R1-1).

## Verdict: APPROVED (0 blocking, 3 nits)

- This round touches only tests and docs. docker/gates.Dockerfile was last modified at 10:51, before the round-1 review (11:13), and
  its sha256 is 4d7ef127...e201. `git diff -- tests/` has no removed lines, so no assertion was weakened.
- Both `rework2-verify-fast.txt` (11:25) and `rework2-docs-verify-fast.txt` (11:23) ran after the last edit (11:17). Each reports
  `Ran 727 tests`, `OK (skipped=8)` and `verify fast: PASS`, and the PSC-10 test is `ok` (:538).
- Telemetry spans: not applicable (no agent loop, model call, retrieval or tool call).

## The new rules are correct
- **Two-stage rule (:738-744).** The check segment, with quotes emptied (`_unquoted`), is split on `|`. It needs exactly 2 stages,
  and the first word of stage 1 must be `echo` or `printf`.
  - `||` cannot reach this point: `_segments` splits on it, and the round-1 separator rules reject it.
  - A `|` inside quotes is emptied first, so the feed's quoted argument cannot add a stage.
  - An escaped `\|` would count as an extra stage and be rejected. That fails closed.
  - Substitutions, groups and `!` are already rejected at :730-731, so no pipe can hide inside `$(...)`.
- **One-sha512sum rule (:745-748).** It counts whole words in the expanded RUN, quoted text included.
  - The lookbehind does not exclude `/`, so `/usr/bin/sha512sum` counts (probe P6, killed).
  - With exactly one sha512sum, the check `_is_sha512_check` finds is the only one. A decoy check before or after it is gone (M3-M5).
- **The rules close M-U1R1-1.**
  - In the tester's run, M1-M5 are killed. S3, S4, S4b and S5 are killed too, as a side effect.
  - My probes add P3 (a second check stage through `shasum -a 512 -c -`), P4 (a `| cat |` middle stage) and P5 (a `sed` feed).
    All three are killed.

## Today's Dockerfile cannot be rejected
- The module RUN (docker/gates.Dockerfile:42-49) has one check segment,
  `echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c -`.
  - That is 2 stages with an `echo` feed.
  - `sha512sum` appears once in the expanded RUN.
  - Neither ARG value contains the word.
- Controls pass in both the tester's run and mine (baseline PASS).
- False-positive probe: these reasonable edits are accepted:
  - round-1 B1-B5 (`--check --strict --quiet`, `printf`, `mkdir -p`, `2>&1` on curl, an architecture `case`);
  - B8, the feed and the pipe split over a `\` continuation;
  - B9, `/usr/bin/sha512sum`;
  - B10, `--check --strict -`;
  - B11, `2>/dev/null` on the feed.
- B6 (`>/dev/null` on the check) and B7 (a checksum file) are still rejected, as in round 1, and fail closed.

## The self-check covers the new rules
- Each new rule has at least one sample that only that rule catches. The tester's before/after finding counts in
  rework2-mutants.txt show this:
  - two-stage rule: the `tee` middle stage, 0 -> 1 findings;
  - feed rule: the `cat` feed, 0 -> 1;
  - one-sha512sum rule: a separate second check after the check, 0 -> 1.
- Some samples are caught by both rules: M-U1R1-1 verbatim (0 -> 2) and the 1-stage `sha512sum -c - < file` (1 -> 2).
- The new `printf '%s\n'` good case passes, so the feed rule accepts `printf`.
- The `assertTrue(findings)` form does not pin which rule fired. The before/after counts make up for that; see nit R2-N3.

## The docs state the same rules as the test
- These places all state the two-stage rule and the one-sha512sum rule:
  - PSC-10 (requirements.md:2887-2890);
  - §2.6 item 2 (architecture.md:4007-4010);
  - D7 step 2 (architecture.md:6080-6083).
- The same three places record M-U1R1-1 as a killed mutant (also requirements.md:2910 and architecture.md:4014-4015).
- Follow-ups (requirements.md:2955-2977) now hold R1-N1, R1-N3 and L-U1R1-2 under N7, and R1-N2 / I-U1R1-3 as their own item. That
  closes my round-1 nit R1-N3.
- One stale clause remains; see R2-N2.

## Round-1 driver re-run (no regression)
- I ran `review-u1-r1-mutants.py.txt` unmodified, on scratch copies. The results match round 1 exactly:
  - baseline PASS;
  - R1-R6 killed;
  - N2-N6 killed;
  - N1 and N7 survive (already recorded as follow-ups R1-N1 and R1-N2);
  - B1-B5 accepted, B6 and B7 rejected.
- Output is in `review-u1-r2-mutants.txt`, Part 1.

## Nits (none block)
- **R2-N1. A redirect attached to a flag word changes what the check reads.** Probes P1 and P2 survive (review-u1-r2-mutants.txt,
  Part 2). P1:
  `echo "<sha512 of empty>  /dev/null" > /tmp/good; ...; echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c --strict</tmp/good -`
  - The last-stage rule (:733-737) only checks that every word starts with `-`. `--strict</tmp/good` passes that check, but the shell
    reads it as `--strict` plus a stdin redirect. The redirect replaces the pipe, so sha512sum checks /dev/null and the RUN goes on.
    Part 3 shows this in a shell.
  - It needs a known-good list planted on purpose before the check. That makes it the L-U1R1-2 class (hash-input tampering via
    /dev/null), which the orchestrator ruled into N7. It is not an accidental mask.
  - The fix is one line: reject any `<` or `>` in the check's last stage, e.g. `re.search(r"[<>]", _unquoted(stages[-1]))`, and add
    a self-check sample for it.
  - Do it now if the orchestrator wants to close it in this round. Otherwise add it to the N7 list.
- **R2-N2. A stale "bare command" clause.** requirements.md:2882 ("is a bare command or a pipeline whose last command is
  `sha512sum`") and architecture.md:4000 ("the check is a bare command, or a pipeline ...") still allow a 1-stage check.
  - The next clause in the same bullet, and the test, now require exactly two stages. The tester's sample `sha512sum -c - < file` is
    rejected.
  - D7 step 2 does not have this clause.
  - Drop "a bare command or" in both places at the next docs touch. The test fails closed, with a message that names the rule, so
    nothing is mis-built in the meantime.
- **R2-N3. The self-check samples assert only that something was found.** They use `assertTrue(findings)` and do not check which
  rule fired.
  - A later edit that breaks one rule could still pass a sample that another rule also catches. For example, the M-U1R1-1 sample is
    caught by both new rules.
  - The isolated samples (tee, cat, separate second check) do pin each rule today. Optional: assert a substring of the expected
    message.

## Evidence
- `docs/evidence/platform-supply-chain/review-u1-r2-mutants.txt`: Part 1, the round-1 driver re-run; Part 2, the round-2 probes
  P1-P6 and B8-B11; Part 3, the shell demonstration of P1.
- `docs/evidence/platform-supply-chain/review-u1-r2-probes.py.txt`: the probe driver. It works on scratch copies only, and `@@` is the
  newline token.
- Relied on: `rework2-verify-fast.txt`, `rework2-docs-verify-fast.txt`, `rework2-mutants.txt`.
