# security-u1-r2: narrow re-check of unit 1 after rework round 2/5 (tests and docs only)

- Date: 2026-10-21. Role: security. Branch `agent/platform-supply-chain`, uncommitted working tree.
- Prior verdict: `security-u1-r1.md` (PASS; M-U1R1-1 medium, L-U1R1-2 low, I-U1R1-3 info).
- **Verdict: PASS.** 0 critical, 0 high, 0 medium. M-U1R1-1 is closed. L-U1R1-2 (low) stays open in a narrower form; it is wider than "printf %.0s only" (see section 3). I-U1R1-3 is unchanged.
- Evidence:
  - `docs/evidence/platform-supply-chain/security-u1-r2-mutants.txt`: mutant and regression run, plus the dash runtime check;
  - `docs/evidence/platform-supply-chain/security-u1-r2-mutants.py.txt`: the driver (r1 driver, S2 fixed, cases added).
- Scratch only. `docker/gates.Dockerfile`, `tests/test_gates_docker_cli.py` and `tests/test_gate_least_privilege.py` were sha256-hashed before the run and re-checked after it (all OK). No repo file was written except this verdict, the two evidence files, the handoff line and the log.

## 1. M-U1R1-1: closed
- I re-ran my r1 driver against the current `tests/test_gates_docker_cli.py`. **S1** (`... | sha512sum -c - | echo "<empty>  /dev/null" | sha512sum -c -`) is **KILLED** by the subtest "the check cannot be masked ...". Two rules kill it: exactly two stages (`_psa_check_masking`, the `len(stages) != 2` branch), and exactly one `sha512sum` word in the expanded RUN.
- **The tester's driver-bug claim is correct.** In `security-u1-r1-mutants.py.txt`, S2 is `f'printf "%.0s%s\n" ...'`, a non-raw f-string, so it writes a real newline into the Dockerfile. That breaks the RUN's line continuation, and 4 unrelated subtests fail, including "a RUN after the final FROM starts pwsh". I kept that form as `S2-r1`, which is KILLED (4 failures), as an artefact. The intended form writes a literal backslash-n (`S2`). It **SURVIVES**, as does `S2b`. My r1 statement that S2b survived was correct. Only the S2 row in the r1 output was wrong.
- The r1 S4 row also had an escaping slip. It wrote a literal backslash-n where a line continuation was meant. In r2 it uses a real continuation and is still KILLED (one-sha512sum rule).

## 2. Regressions: none
- G0: the current repo Dockerfile passes all 27 tests.
- The two new rules cannot reject today's file. Its check is `echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c -;`, `docker/gates.Dockerfile:45`. That is 2 stages with an `echo` feed, and `sha512sum` is the RUN's only one (lines 42-49; the other hash checks are `sha256sum` in other RUNs, and the count is per module RUN).
- Reasonable `printf` feeds **pass** (G1-G4, each 27/27):
  - `printf '%s  %s\n' "$PSSCRIPTANALYZER_SHA512" /tmp/psa.nupkg | sha512sum -c -`;
  - the same with double quotes;
  - `printf '%s  /tmp/psa.nupkg\n' "$PIN"`;
  - `printf '%s\n' "$PIN  path"`.
- Also passing: `sha512sum --strict -c -` (G5) and `${PSSCRIPTANALYZER_SHA512}` with braces (G6).
- At runtime, G1 with a wrong pin fails under `set -eu` (`/tmp/psa.nupkg: FAILED`, exit 1).
- Info only: `_segments` splits on `;` inside quotes. A feed whose quoted text contains `;` is rejected (S3c is killed only for that reason). The error is fail-closed: a legitimate feed with `;` in its quoted text would be rejected, and nothing slips through.

## 3. What still survives (L-U1R1-2, I-U1R1-3; low/info, N7 class, non-blocking)
All of these need a deliberate, visible edit to the module RUN or the Dockerfile. Each passes all 27 tests.
- **The checked file is not the download.**
  - **S2/S2b**: a `printf %.0s` feed.
  - **S8** (new): a parameter-expansion feed, `echo "${PSSCRIPTANALYZER_SHA512:+<empty-hash>}  /dev/null${PSA_UNSET:+/tmp/psa.nupkg}"`.
  - With a wrong pin, dash checks only `/dev/null` and reports OK, for both S2 and S8.
- **Self-hash in a quoted substitution with another hasher.** **S3d**: `$(cksum -a sha512 --untagged /tmp/psa.nupk? | cut -c1-128)` inside the feed quotes. Its output is `/tmp/psa.nupkg: OK` with pin `00f`. (S3 is killed, but only because its hasher is the word `sha512sum`.)
- **Pin overwritten with another hasher.** **S4c** (assignment) and **S4d** (`export`) both use python3 hashlib on `/tmp/psa.nupk?`. S4d gives OK with pin `00f`. (S4/S4b are killed only because they call `sha512sum`.)
- **sha512sum shadowed from an earlier layer.** **S10**: `COPY` a fake binary plus `ENV PATH=/opt/fakebin:$PATH` before the module RUN. A function defined inside the RUN (S9) is now killed.
- **S6/S7**: a later layer overwrites the module dir (I-U1R1-3 / R1-N2).
- Killed by rework 2, beyond S1: S3, S4, S4b, S5 (sed stage), S9 (function).
- **Status of the claim "only `printf %.0s` (S2/S2b) and the later-layer overwrite (S6/S7) survive":** it is true for the r1 S-set only. It is not true of the class. The docs must not state it.

## 4. Docs vs tests: N7 lines in `docs/requirements.md` that are now inaccurate
Correct these in a later docs pass. They are not blocking.
- **2964-2965**: "redefining `sha512sum` through a function, alias or `PATH`".
  - What is wrong: a function or alias defined in the module RUN is now rejected (one-`sha512sum` rule, S9).
  - What survives: a `PATH` shadow set in an earlier layer (S10), or a name built at runtime.
- **2966**: "a `$(sha512sum ...)` self-hash".
  - What is wrong: this exact form is now killed (S3).
  - What survives: a quoted `$(...)` self-hash with another hasher, e.g. `cksum -a sha512` (S3d).
- **2966-2967**: "overwriting the SHA `ARG` (assignment, `read`, `export`)".
  - What is wrong: the r1 examples (S4/S4b, which call `sha512sum`) are now killed.
  - What survives: an assignment or `export` from a non-`sha512sum` hasher (S4c/S4d). Keep the item, qualified as "with a hasher other than `sha512sum`".
- **2967**: "or a `sed` stage".
  - What is wrong: any extra pipeline stage is now rejected (S5 killed). Delete it, or move it to "closed in PSC-10, port to the other pins".
- **2965-2966**: "`/dev/null` as the checked file" is still accurate. Add the parameter-expansion feed (S8) next to `printf %.0s`.
- **2957-2960**: the PSC-10 rules N7 would port to the other pins name only "the pipeline ends in the sha checker", not to M-U1R1-1. This is an omission, not an error. Add "exactly two stages (`echo`/`printf` feed, then the checker) and exactly one checker word in the RUN".
- **2968-2970**: the optional hardening is still right, and would kill S2/S2b/S8/S3d. Add "no assignment, `read` or `export` of the pin in the RUN" (S4c/S4d) and "no `PATH` change in an earlier layer" (S10).
- `docs/architecture.md` (about lines 4007-4014 and 6076-6083) describes the rules and the killed mutants accurately. It makes no survivor claim, so it needs no change.

## 5. Evidence scan (rework2-*)
- Files scanned: `rework2-docs-verify-fast.txt`, `rework2-mutants.py.txt`, `rework2-mutants.txt`, `rework2-verify-fast.txt`.
- Profile paths: 0. SIDs: 0. Secrets: 0.
- Patterns checked: key/token/password/bearer assignments, private-key headers, AWS/GitHub/OpenAI/Slack/Google/JWT shapes, credentialed URLs and IPv4 addresses. The scratch dir is written as `<scratch>`.
- Long hex strings are the base-image digests, the Dockerfile's public pins and a build manifest digest.
- `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` do not appear.
- Diff secret grep (`git diff -- tests docker`): nothing found.

## Traces
Not applicable. No span, retriever, model or agent step changed.
