# Re-review u1 after rework round 1/5: PSC-11 and PSC-10

Reviewer, 2026-10-21. Diff: `git diff agent/ci-speed-closeout` on `agent/platform-supply-chain` (uncommitted working tree).
Prior review: `review-u1.md` (B1, B2, N1-N8).

## Verdict: APPROVED (0 blocking, 5 nits)

B1 and B2 are closed. The Dockerfile change is one line since round 0 (`"$dir/.signature.p7s"` added to the rm). No test assertion was
removed (`git diff ... -- tests/` has no `-` lines). Telemetry spans: not applicable (no agent loop, model call, retrieval or tool call).

## B1: closed
- The hardened test is in tests/test_gates_docker_cli.py:
  - helper `_psa_check_masking` at :711-768, with `_errexit_off` at :699-708 and `_unquoted` at :694-696;
  - detector self-checks at :867-878;
  - the subtest "the check cannot be masked and the download is not replaced after it" at :943-947.
- The rules are checked at these lines:
  - the pipeline ends in `sha512sum -c -`: :732-737;
  - no leading `!`, `if`, `elif`, `while`, `until`, `then` or `else`, and no assignment prefix: :727-729;
  - no `!`, group, subshell or substitution: :730-731;
  - no lone `&` in the RUN: :720-722;
  - no `set +e`, `+u` or `+o errexit|nounset`: :723;
  - the check is not an AND-OR member on either side: :738-743;
  - the check is not inside an if/while/until/for, a group or a subshell: :744-753;
  - nothing touches, fetches, copies, moves or redirects the download between the check and the unpack: :754-765;
  - the unpack is not in a pipeline: :766-767.
- Re-run on scratch copies. Driver `review-u1-r1-mutants.py.txt`, output `review-u1-r1-mutants.txt`.
  - Baseline passes.
  - My 6 mutants from review-u1 (R1 `| cat`, R2 `if`, R3 `!`, R4 `&`, R5 `set +e`, R6 re-fetch after the check) are all killed by the
    masking subtest.
- New attempts:
  - Killed: N2 (the check in a function, then `chk || true`), N3 (`sh -c` around the check, then `|| true`), N4 (`set -u +e`), N5
    (`... || :`) and N6 (`ln -sf` over the download after the check).
  - N1 and N7 survive. Both need a deliberate second download, not a masked exit status; see nits R1-N1 and R1-N2.
- The accepted residual (redefining sha512sum through a function, alias or PATH) stays open as a follow-up (orchestrator ruling).
- The tester's evidence agrees with these results:
  - rework1-mutants.txt: 26/26 killed;
  - rework1-red-verify-fast.txt:1167: the one failure is the packaging-files subtest (`.signature.p7s`);
  - rework1-green-verify-fast.txt:41-42: the module layer was rebuilt, and the log shows `/tmp/psa.nupkg: OK`;
  - rework1-green-verify-full.txt: `verify full: PASS (546s)`.

## B2: closed
- architecture.md:552-566 (section 2.2) now describes the as-built path (curl, then sha512sum -c against ARG PSSCRIPTANALYZER_SHA512,
  then zipfile, then rm including `.signature.p7s`). "not this branch" and "As built it is Install-Module" are gone from this bullet.
- `psa-hash.md` no longer appears anywhere. The evidence file is named `psscriptanalyzer-sha512.txt` at architecture.md:566, :4089 and
  :6103, and at requirements.md:2911. That file exists.

## Docs agree with the test
- PSC-10 (requirements.md:2868-2912), D7 (architecture.md:6054-6107) and section 2.6 item 2 (architecture.md:3982-4017) state the same
  rules:
  - SHA-512 ARG, 128 hex;
  - curl `--proto` and `--proto-redir '=https'`, `--tlsv1.2`;
  - the check is the first reader, with no `||` and no `--ignore-missing`;
  - the masking rules (pipeline ends in sha512sum; not `!`, `if`, `elif`, `while`, `until` or `&`; no `set +e` or `+o errexit`; no write
    to the download path between the check and the unpack);
  - `python3 -I -m zipfile -e` into the module path;
  - rm of `_rels`, `package`, `[Content_Types].xml`, `*.nuspec`, `.signature.p7s` and the `.nupkg`;
  - `Import-Module -ErrorAction Stop`, the first pwsh RUN;
  - the R1-R6 mutant run recorded.
- The version guard is listed (requirements.md:2905-2907, architecture.md:4011-4017).
- The test is a strict superset of the documented rules. It also rejects `&&` before the check, groups, subshells, `export`, `+u`, and
  any copy, write or interpreter tool between the check and the unpack. The orchestrator ruled that these stay. Nothing in the docs
  contradicts them.
- Follow-ups (requirements.md:2940-2955) list N3 and N7. The sha512sum-redefinition residual is not written there; see nit R1-N3.

## .signature.p7s
- docker/gates.Dockerfile:48: `"$dir/.signature.p7s"` is in the rm. The test asserts it at tests/test_gates_docker_cli.py:968-970.
- I checked the built image `ke-gates:wt-33a132fbfdd7` (created 2026-10-21T17:52Z, run with `--network none` as uid 10001):
  - `ls -A .../Modules/PSScriptAnalyzer/1.25.0` lists no `.signature.p7s`, `_rels`, `package`, `[Content_Types].xml` or `.nuspec`;
  - `/tmp` holds no `.nupkg`;
  - `Get-Module -ListAvailable` reports 1.25.0.

## Could the stricter-than-ruling checks reject a reasonable future edit?
Probe B1-B7 in `review-u1-r1-mutants.txt`.
- Accepted:
  - `sha512sum --check --strict --quiet -`;
  - `printf` in place of `echo`;
  - `mkdir -p "$dir"` between the check and the unpack;
  - `2>&1` on curl;
  - an architecture `case ... esac` with a `$(dpkg ...)` subject before the fetch.
- Rejected:
  - B6 `sha512sum -c - >/dev/null`: the last word must be `-` (:733-735);
  - B7 a checksum file (`echo ... > /tmp/psa.sha512; sha512sum -c /tmp/psa.sha512`).
- By reading the code, these would also be rejected: `install -d "$dir"` between the check and the unpack (`install` is in `_REWRITER`,
  :690), `cd /tmp && <check>` (:741), and an env-assignment prefix on the check (:727).
- None of these is a defect:
  - each fails closed, with a message that names the rule;
  - D7 prescribes the stdin form;
  - `--quiet` and `--status` already cover the "less output" case.
- Not blocking. If an edit of this kind is ever wanted, relax the rule then.

## Nits (none block)
- **R1-N1.** The check matches the download by substring, at tests/test_gates_docker_cli.py:936 (`assertIn(path, exp[check])`). Mutant N1
  survives:
  - it first fetches a known-good file to `/tmp/psa.nupkg.ok`;
  - it checks that file;
  - it unpacks the unchecked `/tmp/psa.nupkg`.
  This needs a deliberate second download, the same class as the accepted residual. An accidental typo fails at build time, because the
  file is missing. Fix with a whole-word match (no word, dot, slash or dash character on either side of the path). Fold it into follow-up
  N7.
- **R1-N2.** Nothing stops a later RUN from unpacking an unchecked package into `/Modules/PSScriptAnalyzer/<v>` (mutant N7 survives). This is
  outside B1, which covers the module RUN. A cheap guard is to assert that only the module RUN names the module path; `_psa_version_drift`
  already collects those paths at :812. Follow-up.
- **R1-N3.** The orchestrator accepted the redefinition residual (sha512sum redefined through a function, alias or PATH) and ruled that it
  joins N7. That is recorded in the handoff, but not in requirements.md "Follow-ups (not in platform-supply-chain)" (:2950-2955). Add one
  line to N7 at the next docs pass.
- **R1-N4.** architecture.md:95, :3228 and :4757 still say "platform-supply-chain, not this branch" about the scanner. That stays true until
  the scan unit lands, so update them in that unit.
- **R1-N5.** Carried from round 0 and accepted: N1 (the literal path repeated instead of `"$dir"`), N2 (double quotes, while D7 says
  single-quoted), and N8 (do not stage `docs/knowledge-engine-claude-code-prompt.md`).

## Evidence
- `docs/evidence/platform-supply-chain/review-u1-r1-mutants.py.txt` (driver; `@@` = newline token)
- `docs/evidence/platform-supply-chain/review-u1-r1-mutants.txt` (R1-R6 killed, N1-N7 with 2 surviving, B1-B7 probe)
