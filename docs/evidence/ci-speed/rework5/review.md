# ci-speed rework 5/5 (last round): reviewer verdict

**Verdict: APPROVED** (no blocking findings; follow-ups F1-F4, none can turn red into green)

Reviewed: the round-5 working tree on agent/ci-speed (HEAD a375a4e + rounds 3-5, uncommitted), as the files
themselves: tests/test_block_main_commit_hook.py:798-974, tests/test_resource_probe.py (whole file),
docs/architecture.md §2.2.1-r3 decision 4 (:895-949), decision 6 (:981-1036), Alternatives (:1039-1071),
Consequences (:1072-1095), docs/requirements.md CS-11 (:2452-2504), CS-12 (:2505-2543), Follow-ups (:2551-2564).
Read rework4/review.md (nits 1-5), the round-5 handoff lines, rework5/verify-fast.txt (PASS, Ran 724, cov 90%)
and rework5/mutants.txt. Production files are untouched in round 5: scripts/test.sh, scripts/resource_probe.sh
and the hook have mtimes before the round-4 review; only the two test files and docs changed, and verify fast
ran after the last test edit.

Reviewer probes ran on scratch copies only, in containers labelled `com.docker.compose.project=ke-reviewer-cs5`
(ke-gates:wt-33a132fbfdd7, --network none, uid 10001, repo mounted ro, python -B). Output: review/.

## 1. Round-4 nits

| Nit | Status | Where |
|---|---|---|
| 1 nested-shell false negatives | closed | tests/test_block_main_commit_hook.py:807-822 (_SHELL_WORD, NESTED_SHELL, PIPE_INTO_SHELL, SOURCE_STDIN); all 10 round-4 misses now in the flagged list :889-895, :906-912. Further misses found this round: F1 |
| 2 R6/R7/R9/R18 test gaps | closed | tests/test_resource_probe.py:351-387 (test_each_reader_caps_bytes_and_lines, precondition :383-384), :517-526 (two extra R18 runs); all four killed (rework5/mutants.txt §1) |
| 3 OMP spelling + SC1007 | closed | docs/architecture.md:938-943 |
| 4 `\|&` in docs; "every read of a source" | closed | docs/architecture.md:903-906, :1004-1005; docs/requirements.md:2472-2477, :2522-2523 |
| 5 silent inotify fallback | closed | tests/test_resource_probe.py:537-541 (skipped subTest naming the reason), :549-566 (watch_tree returns the reason) |

## 2. Detector vs decision 6 / CS-12

Conforms, and is stricter than the text in places:
- Printable ASCII + \t\n: NOT_PRINTABLE :805, enforced in check_hook :869-874 and hook_findings :851-857.
- Split on "\n" only, comment lines scanned: :835 (no comment skip). Shebang `#!/usr/bin/env bash` stays allowed (:927).
- `&` rule: NON_BACKGROUND_AMP :826 removes `&&`, `|&`, `N>&M`/`<&`/`>&-`, `&>`, `&>>`. Matches the doc list.
- `${BASH}`: yes (:811, `\$\{?(?:BASH|SHELL)\}?`), also `${SHELL}` and `${SHELL:-sh}`; flagged cases :892, :906-908.
- ksh: yes (:810; also mksh, ash); `ksh -c true` :906.
- `source`/`.` of /dev/stdin: yes (:821-822), also /dev/fd/N and /proc/*/fd/N, quoted or not (:898-899, :911-912).
- "any options before -c": code allows any words of the same simple command before a `-…c…` or `-…s…`
  cluster (:815), so `bash -s`, `sh -s`, `bash -xs` are flagged (stricter than "bash -s").
- Allowed forms (:917-928) are all non-launching; near misses (`bash -n script.sh`, `grep -c sh file`,
  `true | push -c`, `source ./lib.sh`, `cat /dev/stdin`) pass.
- Detector mutants (review/detector-mutants.txt): 8/8 killed - comment skip (round-4 behaviour), splitlines(),
  no printable check, no SOURCE_STDIN, no PIPE_INTO_SHELL, `-s` dropped, `$BASH/$SHELL` dropped, shell list
  cut to bash|sh.

False negatives inside the listed categories remain (F1). Each was run for real and leaves a `sleep 3` running
after bash returns (review/detector-false-negatives.txt):
- `bash \<newline>  -c "…"` (option on a continuation line; the hook already uses `\` continuations, :35);
- `printf … |<newline>  bash` (pipe at line end; the hook's own style, :32-34);
- `bash <<<"…"`, `bash /dev/stdin <<<"…"` (shell fed by here-string or script operand, no `-s`);
- `source -- /dev/stdin <<<"…"`;
- `… | nice -n 5 bash` (a wrapper with an option argument; also `timeout 5 bash`).
Same class and severity as round-4 nit 1: low risk (S4/S10 accepted), today's hook has none, a human reviews
every hook change, and the deferred allow-list (requirements:2558) subsumes all of them, since `bash`,
`source` and `nice` would be off-list command words on whatever line they sit. Not a defect of this change.
The doc sentence "The test fails on any of these" (architecture:1003, requirements:2519-2521) over-claims; see F1.

## 3. No test weakened

- The two cases moved allowed -> flagged ("# setsid nohup … >(y)" and "    # an indented comment: sleep 9 &",
  :887-888) are a tightening: the round-4 detector skipped `#`-led lines (rework4/s4-mutants.txt, "allowed:
  whole-line comment"), the round-5 one scans them, so its findings are a superset. Splitting on "\n" only
  gives fewer, longer lines; every regex is a substring search with character-class lookbehinds that no
  separator satisfies, so nothing flagged before is missed now, and any separator byte is rejected outright.
- Every round-4 flagged case is still in the flagged list; nothing that was flagged moved to allowed. The
  remaining allowed comment lines (:920) contain no listed construct.
- test_hook_launches_no_background_work now runs check_hook (printable + full scan): stricter.
- test_no_root_path_reads_no_env keeps the round-4 run and checks and adds two runs; the inotify check
  becomes a visible skip only where inotify is missing (it is present in the gates image: no skip in 20 runs).
- No budget, cap, guard or threshold changed; PROBE_HANG_S stays 10 s.

## 4. Flakiness

review/flakiness.txt: tests.test_resource_probe + HookLaunchesNoBackgroundWorkTest, 10/10 idle (0.83-1.36 s)
and 10/10 with 6 busy loops on --cpus 2 (3.69-4.09 s for all 13 tests). The detector tests are pure string
work. The new probe cases are deterministic files (largest 270 KB) under the 10 s per-call guard. Markers are
random 18-digit values (collision negligible); the inotify watch is armed after all fixture writes and the
precondition run, as in round 4.

## Follow-ups (non-blocking; for the orchestrator to place)

| # | Severity | Where | Finding |
|---|---|---|---|
| F1 | nit (docs now, code with the allow-list) | docs/architecture.md:1003-1023; docs/requirements.md:2519-2536; tests/test_block_main_commit_hook.py:814-822 | Six on-list spellings still launch un-waited work undetected (§2). Either name the limits in the residual-risk text ("the scan is per physical line, so a construct split by a `\` continuation or a line-ending `\|` is not seen; a shell fed by a here-string, redirect or `/dev/stdin` operand without `-s`, and `source --`, are not listed") or join `\`-newline and line-ending `\|` before scanning. The S10 allow-list follow-up closes all six. |
| F2 | nit | tests/test_block_main_commit_hook.py:937, :958, :967 | Literal U+2028/U+2029 characters in the test source. Legal Python, but editors and `splitlines()` tools show them as line breaks. Use `" "`/`" "` escapes. |
| F3 | nit | tests/test_block_main_commit_hook.py:963 | Mutant "#-line in a quoted heredoc fed to a shell" is caught by the plain `sleep 9 &` line, not by comment scanning or by detecting a heredoc fed to `bash`. Rename it, or make the payload `bash <<'EOF'` + `#` + a `$a`-built `&` so it shows the F1 gap. |
| F4 | nit | docs/requirements.md:2495-2504 | CS-11's test list omits `ResourceProbeTest.test_each_reader_caps_bytes_and_lines` (rework 5). |

Commit hygiene carried: `git add --chmod=+x scripts/resource_probe.sh`; exclude
docs/knowledge-engine-claude-code-prompt.md; include docs/evidence/ci-speed/ci/, rework3/, rework4/, rework5/.
Round 5 has verify fast only; the orchestrator's pre-commit `scripts/verify.sh full` covers gate 4.
