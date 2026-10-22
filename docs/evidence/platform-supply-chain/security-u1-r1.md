# security-u1-r1: re-check of unit 1 after rework round 1/5 (L-U1-1, hardened PSC-10 test)

- Date: 2026-10-21. Role: security. Branch `agent/platform-supply-chain`, base `agent/ci-speed-closeout`; `git diff agent/ci-speed-closeout -- docker tests`, uncommitted working tree.
- Prior verdict: `security-u1.md` (PASS, L-U1-1 low + I-U1-2..7 info).
- **Verdict: PASS.** 0 critical, 0 high, 1 medium, 1 low, 1 info (new). L-U1-1 is closed. Medium and low do not block, but M-U1R1-1 is the same class as review B1 and is cheap to close; see the recommendation.
- Evidence:
  - `docs/evidence/platform-supply-chain/security-u1-r1-checks.txt`: builds, image inspection, static mutant run, wrong-pin builds, evidence scan;
  - `docs/evidence/platform-supply-chain/security-u1-r1-mutants.py.txt`: static mutant driver.
- Scratch only. Build contexts were in the session scratch dir, and images `ke-sec-u1r1-psa:*` were labelled `ke.audit=security-u1-r1` and removed afterwards. No repo file was modified except this verdict, the two evidence files, the handoff line and the log.

## 1. L-U1-1: closed
- `docker/gates.Dockerfile:48`: the rm now names `"$dir/.signature.p7s"`. The Dockerfile diff since round 0 is that one token.
- No-cache scratch build of the Dockerfile head (lines 1-49): `/tmp/psa.nupkg: OK`. As uid 10001 with `--network none`:
  - the module dir has 16 entries (17 in round 0) and no `.signature.p7s`;
  - `find` finds no `*.p7s`, `*.nuspec`, `*.nupkg`, `_rels` or `[Content_Types].xml` anywhere on the root filesystem;
  - `/tmp` is empty;
  - only 1.25.0 at `/usr/local/share/...` resolves, and Import-Module loads its psm1.
- The developer's verify image `ke-gates:wt-33a132fbfdd7` (17:52Z) agrees: no signature or packaging files.
- The test asserts the rm (`tests/test_gates_docker_cli.py`, packaging-files subtest).

## 2. The hardened test as a security control
- **Fixtures are safe.** Detector self-checks pass literal strings to regex helpers. The version guard writes a temp Dockerfile in `tempfile.TemporaryDirectory()` and only reads it back. The diff has no `subprocess`, `exec`, `eval`, import hooks or network. The `cp`/`curl` samples are never executed. The evidence drivers (`*.py.txt`) are not collected by unittest, write only under `argv[1]`, and use only `https://example.invalid`.
- **What it now stops.** The reviewer's R1-R6 and the tester's X1-X19 are killed (re-confirmed from the drivers and the outputs). The control passes all 27 tests in `test_gates_docker_cli` and `test_gate_least_privilege`.
- **What it still misses** (`security-u1-r1-checks.txt` sections 4-5). None of these redefines sha512sum. Each survives all 27 tests, and each one I built with a WRONG pin (last hex digit changed) built OK with the module unpacked and imported:
  - **S1, exit-status masking:** `echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c - | echo "<sha512 of empty>  /dev/null" | sha512sum -c -`. Built OK. The rule "the pipeline ends in `sha512sum -c -`" holds, but the real check is a non-last pipeline stage, and dash has no pipefail. This is review B1's `| cat` again, through a second check.
  - **S2b, feed rewrite:** `printf "%.0s%s" "$PIN  /tmp/psa.nupkg" "<empty-hash>  /dev/null" | sha512sum -c -`. Only /dev/null is checked. Built OK.
  - **S3, self-hash in a quoted substitution:** `echo "${PSSCRIPTANALYZER_SHA512:+$(sha512sum /tmp/psa.nupkg | cut -c1-128)}  /tmp/psa.nupkg" | sha512sum -c -`. `_unquoted` empties the quotes before the `$(` check, so the substitution is never seen. Built OK.
  - **S4/S4b, the pin is shadowed:** `PSSCRIPTANALYZER_SHA512=$(sha512sum /tmp/psa.nupk? | cut -c1-128);` before the check. The glob keeps the path text out of the "first reader" scan. Built OK.
  - **S5:** `| sed "s#.*#<empty-hash>  /dev/null#" |` in the feed. Static only.
  - **S6/S7:** a later `COPY`, or an unpinned later RUN, that overwrites the module dir. Same as reviewer R1-N2; static only.

## Findings
| ID | Sev | Where | Finding | Action |
|---|---|---|---|---|
| L-U1-1 | low | docker/gates.Dockerfile:48 | `.signature.p7s` left in the module dir. | **Closed**: removed, and absent from both images. |
| M-U1R1-1 | medium | tests/test_gates_docker_cli.py `_psa_check_masking` (pipeline-end rule) | The check can still be masked by its exit status (S1). Only the last pipeline stage is inspected, so an earlier failing `sha512sum -c` is hidden by a second `sha512sum -c` of a known-good input. A wrong-pin build succeeds. Not blocking: today's Dockerfile is correct (wrong pins fail, round 0 section 1), and S1 needs a deliberate edit visible in the diff. It is still exactly the class B1 was meant to close. | Tester: the check's pipeline is exactly two stages (`echo`/`printf` feed → `sha512sum -c -`), and the module RUN contains exactly one `sha512sum` word. Add S1 as a mutant. |
| L-U1R1-2 | low | same helper; "fed the pinned hash" subtest | The feed is not pinned to the ARG (S2b, S3, S4/S4b, S5). A check that names `$PSSCRIPTANALYZER_SHA512` and the path can still verify /dev/null, or the download against itself. These need deliberate obfuscation, the same class as the accepted sha512sum-redefinition residual. | Join follow-up N7. Optional hardening: the feed's only argument is `"$PSSCRIPTANALYZER_SHA512  <path>"`; reject `$(`/backticks inside quotes in the check segment; reject any assignment, `read` or `export` of `PSSCRIPTANALYZER_SHA512` in the RUN. |
| I-U1R1-3 | info | Dockerfile, image-wide | Nothing checks that a later layer leaves the module dir alone (S6 COPY, S7 unpinned RUN). There is no image-wide "every fetch is hash-checked" invariant. Already noted by the reviewer as R1-N2. | Follow-up with N7; not in PSC-10 scope. |
- Carried unchanged from round 0: I-U1-2 (TOFU on the gallery PackageHash), I-U1-3 (other curls lack `--proto-redir`), I-U1-4 (cosmetic quoting). I-U1-5 is closed by the architect (psa-hash.md renamed). I-U1-6 and I-U1-7 are unchanged. I-U1-7 recurs in `rework1-green-verify-full.txt:1`: no model host was configured, and this diff touches no model path.

## 3. Evidence scan (rework1-*, review-u1*, including review-u1-r1*)
- Profile paths: 0. SIDs: 0. Secrets: 0. Checked key/token/password assignments, private-key headers, AWS/GitHub/OpenAI/Slack/Google/JWT shapes and credentialed URLs.
- `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST` appear only as names in skip messages. Long hex strings are image digests, build ids and the public pins.
- My files write the scratch dir as `<scratch>`.

## Secret grep of the diff
`git diff agent/ci-speed-closeout -- docker tests`: no keys, tokens, private keys, credentialed connection strings, profile paths or SIDs.

## Traces
Not applicable. No span, retriever, model or agent step changed.
