# ci-speed rework 3/5: reviewer verdict

**Verdict: PASS** (no blocking findings; 7 nits, the first 3 are docs drift worth fixing in the same commit)

Reviewed: `git diff HEAD` (round 3: the revert) and `git diff 0b874c2` (whole item), plus the untracked
`scripts/resource_probe.sh` and `tests/test_resource_probe.py`. Read the handoff (HUMAN RULINGS and the round-3
lines), architecture §2.2.1-r3, requirements Item ci-speed and Item test-diet, and rework3/diagnosis.md,
red-verify-fast.txt, tester-hook-cpu-mutants.txt, green-verify-fast.txt and green-verify-full.txt (PASS, 558 s).

## What was checked

- **§2.2.1-r3 conformance.** `scripts/test.sh` matches decisions 1-5 and 7. There is one top-level `coverage run -p
  --data-file=<dir>/<name>.toplevel -m unittest -v --durations 10 <mods>` in glob order. Sub-package and integration
  runs follow with labels `tests.<pkg>` / `tests.integration`. The data path comes from the coverage API and an empty
  or failed lookup fails. Each run must leave data, `combine` gets an explicit list, and a leftover file fails naming
  its label. No pool machinery is left. `verify.sh`, `ci.yml`, the sentinel and `[tool.coverage]` are unchanged
  against 0b874c2 (CS-6).
- **test.sh failure path.** `unit_runs || unit_rc=$?` then the probe's `end`, then `exit "$unit_rc"`. Every
  failure inside `unit_runs` returns explicitly (errexit is off in a `||` context). A failing unit run still fails the
  run, the end line prints, and neither integration nor combine starts. Mutants T1, T2, T3 and T6 are killed.
- **Labels.** No label is a dot-prefix of another. Mutant T4 (label `tests`) is killed by 12 subtests.
- **Removed tests.** Each one belongs to withdrawn §2.2.1 decisions 1-4 (pool, logs, summary lines, per-module
  `Ran` check, INT/TERM trap). Four were adapted rather than dropped: durations, combine-leftover, no-data, and the
  verify sentinel/Ran check. The SystemExit(0)-at-import guard moved to verify.sh level, and mutant T10 shows that
  test is discriminating. Still present: CS-5 `test_nested_test_sh_leaves_gate_coverage_data_alone`, CS-8
  `HookHeaderTest`, `test_data_file_comes_from_coverage_api_not_debug_config`,
  `test_printf_formats_hold_no_literal_newline`, and the VerifyRequiresTestsRunTest suite. No test that guards kept
  behaviour was removed.
- **Hook CPU conversion.** `RUSAGE_CHILDREN` counts terminated, waited-for children and every descendant they waited
  for. The hook's jq/tr/sed are pipeline or command-substitution children that bash waits for, so they are counted.
  In the gates image `sh` is dash, and the busy grandchild in `test_busy_grandchild_is_counted` really is a grandchild
  (ppid != test pid). Only un-waited background work escapes, which does not affect what the budget is for. The
  intent (linear cost, L8/L9/L21/M3) is a CPU property, so it is kept. The budgets are unchanged (3/5/9 s). The 60 s
  `timeout` stays on the same `subprocess.run`. Tester mutants: CPU burn in the hook or a child fails 18/18, sleep 12
  passes (the accepted consequence), sleep 70 hits TimeoutExpired. Reviewer mutants H1 (RUSAGE_SELF) and H2 (no
  timeout) are both killed.
- **resource_probe.sh.** It uses bash builtins and `nproc` only. stderr goes to /dev/null at the top. Every printed
  value goes through `num`/`nummax` or a regex check, and `phase` is whitelisted. All 19 keys were populated inside
  the gates image (green-verify-full.txt:297, :1372). The always-exit-0 contract holds:
  - `set -u` is safe, because every variable is assigned before use;
  - a missing file or a directory read fails silently;
  - an octal-invalid `/proc/stat` field (`08`) aborts only the `if` compound, the line still prints and the exit is 0
    (checked by hand).

  Mutants P1-P6 are killed: raw value, stderr, exit 1, total without steal (a real leak path), raw phase, and `max`
  allowed on peak.
- **Docs.** CHANGELOG, requirements (CS-1/2/3/9 withdrawn with history kept, CS-4/7/8 amended, CS-10/11/12 added,
  4f reworded with the original wording kept), architecture (§2.2.1 marked withdrawn, §2.2.1-r3 added) and
  open-questions (Q-CS1 amended) agree with the code, except for nits 1-3.
- **test-diet item.** It is well formed. It names its outcome metric (neither directly, with the reason), its status,
  dependency, scope and exclusions. TD-1 (traceability) and TD-2 (one mutant per cut) guard against gaming. TD-5 is a
  same-commit CI A/B with a numeric pass rule (A's slower run beats B's faster run, and median <= 0.85) and a
  no-adjust clause. TD-6 is the re-measure.
- **Observability.** Not applicable: no agent loop, model call, retrieval or tool call changed.

## Findings

| # | Severity | Where | Finding |
|---|---|---|---|
| 1 | nit (docs drift; fix in this commit) | docs/open-questions.md:267-276; docs/requirements.md:2501-2503 | The orchestrator accepted A-CS2 on 2026-10-21 (handoff line 90), but both files still list Q-CS2 as "Open" and "A-CS2 (assumed)". Mark it resolved (orchestrator ruling, value unchanged), as Q-CS1 is. |
| 2 | nit (docs drift) | docs/architecture.md:768 | The §2.2.1-r3 heading still says **proposed 2026-10-21**. The orchestrator confirmed it (handoff line 90), the code implements it, and requirements line 2312 calls it "in force". Change it to accepted/confirmed. |
| 3 | nit | docs/requirements.md:2378 | CS-4 cites `[unit: test_combine_gets_an_explicit_file_list]`, but the test is `test_coverage_combine_gets_an_explicit_file_list` (tests/test_harness_followups.py:679). |
| 4 | nit (commit hygiene) | scripts/resource_probe.sh (untracked) | `core.fileMode=false` on this checkout, so a plain `git add` records 100644. All 14 other `scripts/*.sh` are 100755. Stage it with `git add --chmod=+x scripts/resource_probe.sh`. It works without the bit, because test.sh calls it through `bash`. |
| 5 | nit (test gap) | tests/test_resource_probe.py:97-103, 168-216 | Every probe test passes `root`, so the "reads no environment variable" rule is not tested on the path test.sh actually uses (no `root`). Mutant P7 (`pr_root="${2:-${ROOT:-/}}"`) survives all tests (review/mutants.txt). Suggested fix: one case with no `root` argument, env `ROOT`/`root` pointing at a planted canary tree, asserting no canary number appears. |
| 6 | nit | scripts/resource_probe.sh:72-78, 100 | `cpu_total_ticks` is a bash sum printed without `num`. Fields near 2^63 wrap to a negative number (checked by hand: `cpu_total_ticks=-9223372036854775459`), which breaks the value pattern. Unreachable from a real `/proc/stat`. Passing the sum through `num` would close it. |
| 7 | nit (scope) | docs/knowledge-engine-claude-code-prompt.md (untracked) | Not part of ci-speed. Leave it out of this commit (stage by explicit paths). `docs/evidence/ci-speed/ci/` (the CI logs cited by the handoff) belongs to this item. |

No blocking findings. The tests were not weakened: the budgets are unchanged and the conversion is per the human
ruling, every removed test maps to a withdrawn decision, and every reviewer mutant except P7 is killed (18 of 20).

## Evidence

- Mutant output: `docs/evidence/ci-speed/rework3/review/mutants.txt` (control: Ran 35, OK; T1-T11, P1-P7, H1-H2).
- Mutant generator and runner: `review/make_mutants.py.txt`, `review/run.sh.txt`. Scratch copies only, run in
  `ke-gates:wt-33a132fbfdd7` with `--network none`, uid 10001 and a read-only mount, in containers `ke-reviewer-cs3-*`.
- Re-run before commit (orchestrator): `scripts/verify.sh full`. The paths touch `scripts/` and tests.
