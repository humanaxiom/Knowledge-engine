# Review u1: PSC-11 (pwsh telemetry ENV) and PSC-10 (PSScriptAnalyzer by SHA-512)

Reviewer, 2026-10-21. Diff: `git diff agent/ci-speed-closeout` on `agent/platform-supply-chain`, uncommitted working tree
(docker/gates.Dockerfile, tests/test_gates_docker_cli.py, docs/requirements.md, docs/architecture.md, docs/open-questions.md, handoff).

## Verdict: CHANGES REQUESTED (2 blocking, 8 nits)

The Dockerfile itself is correct. It matches D7 and PSC-10/11, and a wrong, empty or version-skewed hash fails the real build at
`sha512sum -c` before anything unpacks or loads the package. The blocking gap is the test: it does not enforce the fail-fast property it
claims to, and six mutants that disable the check pass it. One of those mutants was built for real with a wrong hash, and the build
succeeded (exit 0).

## What was checked
- Dockerfile against D7 / PSC-10 / PSC-11: the ENV comes right after the final FROM and before any RUN. Each key is set once, and the late ENV
  block no longer has them. The tarball RUN has no trailing pwsh. The module RUN runs: `set -eu` -> curl `--proto =https --proto-redir =https
  --tlsv1.2 -fsSL` to /tmp -> `echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c -` (the last command in its pipeline, so with
  set -e a mismatch stops the RUN) -> `python3 -I -m zipfile -e` -> rm of the packaging files and the .nupkg -> `Import-Module -ErrorAction Stop`.
  There is no `||`, no `--ignore-missing` and no gallery install. There is one SHA512 ARG, and it has 128 lowercase hex characters.
- Real builds (evidence `review-u1-mutation-builds.txt`). Each override was passed with `--build-arg`; no file was edited.
  - A wrong hash, a version-only bump to 1.24.0 and an empty hash each exit 1 at the sha512sum line. Neither zipfile nor pwsh runs.
- Built image `ke-gates:wt-33a132fbfdd7` (run with `--network none` as uid 10001):
  - both ENV keys are present;
  - `/usr/local/share/powershell/Modules/PSScriptAnalyzer/1.25.0` has no `_rels`, `package`, `[Content_Types].xml` or `.nuspec`, and no
    percent-encoded names;
  - `Get-Module -ListAvailable` reports 1.25.0, and `Invoke-ScriptAnalyzer` works.
- Provenance (`psscriptanalyzer-sha512.txt`): the gallery base64 PackageHash, converted to hex, equals the local sha512, which equals the ARG.
- Evidence read:
  - red-psc10-11-verify-fast.txt: 5 failures, all the new subtests;
  - green fast and full: PASS, full in 572 s. lint ran PSScriptAnalyzer on 4 files. The module layer shows `CACHED` in the full log, so the
    live fetch and verify are shown by the reviewer builds above;
  - red-psc10-11-mutants.txt: 22 of 22 killed;
  - guard-psa-version-*.txt: 4 of 4 killed, and the guard passes.
- Telemetry spans: not applicable (no agent loop, model call, retrieval or tool call).

## Blocking

**B1. The PSC-10 test does not enforce that the check gates the unpack.**
- Location: tests/test_gates_docker_cli.py:677 (`_is_sha512_check`), :806-841 (the fail-fast, check and first-reader subtests).
- The test asserts only three things: `set -eu` comes first, no `||` follows the check segment, and the check is the first segment that names
  the download.
- These mutants pass all three tests in `GatesImagePowerShellSupplyChainTest`. The scratch driver, `review-u1-static-mutants.py.txt`, reports
  6 of 6 survived in `review-u1-static-mutants.txt`.
  1. `... | sha512sum -c - | cat`: the pipeline exit status is masked; dash has no pipefail.
  2. `if echo ... | sha512sum -c -; then :; fi`: set -e is off inside the condition.
  3. `! echo ... | sha512sum -c -`.
  4. `... | sha512sum -c - &`: backgrounded.
  5. `set -eu; set +e;` before the fetch.
  6. A second `curl -o /tmp/psa.nupkg <other url>` between the check and the unpack.
- Mutant 1 plus a wrong hash, built for real from a truncated scratch copy, **succeeded (exit 0)**: sha512sum printed FAILED, and the package
  was unpacked and imported anyway. Evidence: `review-u1-mutation-builds.txt`, the "control" entry.
- Fix (tester, then the developer if needed). The check segment must be a bare command, or a pipeline that ends in `sha512sum`: nothing after
  it in the pipeline, no leading `!`, `if`, `while`, `until` or `elif`, and not backgrounded. No `set +e` and no `set +o errexit` anywhere in
  the RUN. Between the check and the unpack, nothing may write the download path (`curl`/`wget -o|-O`, `cp`, `mv`, `>`, `tee`). Add the six
  mutants above to the recorded mutant run as killed.
- Pre-existing and out of scope: the same masking gap exists in `_is_sha_check` and `_assert_pinned` for the pwsh, docker and compose pins
  (tests/test_gates_docker_cli.py:143-217). See N7.

**B2. The docs contradict the code and the evidence.** The fix is the architect's, docs only.
- docs/architecture.md:4060 and :6058 name `docs/evidence/platform-supply-chain/psa-hash.md`. The real file is `psscriptanalyzer-sha512.txt`,
  and the orchestrator ruled that the docs follow the real file.
- docs/architecture.md:553-555 (§2.2) still says "(... not this branch)" and "As built it is `Install-Module -RequiredVersion` from a gallery
  set `Trusted`, with no hash or signature check". After this diff, that statement about the built image is false. It should describe the
  as-built hash path, or point to D7, and drop "not this branch".

## Nits
- N1. docker/gates.Dockerfile:46-47: `dir=` is set, but the unpack repeats the literal module path instead of using `"$dir"`. The test
  literal-path regex (tests/test_gates_docker_cli.py:850-852) forces this. Either let the test accept `"$dir"` when `dir=` expands to the module
  dir, or drop `dir`. The drift guard already covers both paths, so this is not a defect.
- N2. docker/gates.Dockerfile:49: the Import-Module command is double-quoted, while D7 (docs/architecture.md:6037-6038) says "a fixed
  single-quoted literal". The two behave the same here because the string has no `$`. Align one or the other.
- N3. docker/gates.Dockerfile:18: the comment "PSScriptAnalyzer 1.25.0 (ARG below)" exists only to satisfy the regex in
  tests/test_stack_scripts.py:1625.
  - Stronger fix: have that test compare `(Get-Module PSScriptAnalyzer).Version`, which it already reads, with `ARG PSSCRIPTANALYZER_VERSION`.
    The comment and its guard would then be unnecessary.
  - For now, the guard `test_gates_image_psscriptanalyzer_version_agrees` contains the drift.
- N4. The guard test `test_gates_image_psscriptanalyzer_version_agrees` is not listed in PSC-10 (docs/requirements.md:2895) or in §2.6
  item 2 (docs/architecture.md:3970).
- N5. Two stale lines in docs/architecture.md:
  - :5792: amendment 1 status still reads "proposed for the Plan gate (orchestrator confirms)", but it was accepted on 2026-10-21.
  - :3954: says "D1–D8". This is fine if intended, since D9 has no test; say so.
- N6. Handoff line 111: the developer note "Stale wording remains in requirements/D7/§2.6 (sha256)" is out of date. The architect aligned
  the wording at 16:51, and a grep finds no SHA-256 wording left for PSScriptAnalyzer. A later section can note this; earlier sections are not
  rewritten.
- N7. Follow-up, not this unit: harden `_is_sha_check` for the pwsh, docker and compose pins the same way as B1.
- N8. `docs/knowledge-engine-claude-code-prompt.md` is untracked and not part of this plan item. Do not stage it with this unit.

## D1–D9 readiness for the scanner TDD
The design is coherent enough to start. Points checked:
- teardown.sh inherits COMPOSE_FILE and accepts no extra profile. D1 and D4 therefore need no F3 change.
- verify.sh exports a `wt-<12 hex>` KE_IMAGE_TAG, which matches the format D4 step 1 expects.
- ke-app is about 99 MB, so the D1 tmpfs `/tmp` unpack is not a memory risk.
- The two D5 uncertainties (the `until` key, and suppressed rows being shown) each have a confirm-at-GREEN step with a named fallback.

Points to carry, none blocking:
- (a) D1 runs `scan-db` and `scan` with a `read_only` root filesystem. Confirm at GREEN that grype writes nowhere except `/db` and `/tmp`
  (HOME/XDG cache, its config lookup), with the same confirm-and-fallback form as D5.
- (b) §2.6 (docs/architecture.md:3958-3959) says the proposed names go into "PSC-3", but `test_scan_refuses_malformed_image_tag` is listed
  under PSC-2.
