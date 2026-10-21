# Review: platform-supply-chain unit 3 (PSC-4, PSC-17/D10, carry-ins N1, r1-a, r1-b, I-4, I-6)

- Reviewer, 2026-10-21. Diff read: `git diff 8b20fa5` (scan.sh, app.Dockerfile, uv.lock, fake_docker.py,
  test_image_scan.py, architecture.md).
- Own checks: `review-u3-mutants.txt` (driver `review-u3-mutants.py.txt`): 12 mutants on a scratch copy
  in ke-gates:wt-33a132fbfdd7, `--network none`, label `ke-reviewer-psc-u3`. Repo files untouched.
  shellcheck 0.9.0 on scan.sh: clean.

## Verdict: PASS (APPROVED). 0 blocking, 5 nits (r3-1 is a carry-in for the PSC-6 RED)

## What was checked

- **app.Dockerfile against D10.** Three stages: `uv`, `builder`, final. Both python `FROM`s are the same
  reference, byte for byte. The final stage has only `COPY --from=builder /opt/venv /opt/venv` and
  `COPY --from=builder /app /app`, with no `--chown`. Its ENV is `PATH=/opt/venv/bin:$PATH` and
  `PYTHONUNBUFFERED=1`, with no `UV_*`. `WORKDIR /app`, `useradd --uid 10001 ke`, `USER ke` and the `CMD`
  are kept. The final stage has no uv.
- **Layer caching (N11).** The dependency layer stays cached in `builder`. A code change reruns the
  project sync and the final venv COPY, which is a local copy with no download. This is sensible and is
  what D10 point 2 records.
- **Existing tests.** `test_dockerfiles_pin_base_images_by_digest` and `test_env_example_not_in_app_image`
  are both `ok` in u3-green-verify-full.txt. The final `FROM` is the pinned image, not `builder`, and
  nothing COPYs `.env`.
- **Other users of ke-app.** None relies on uv:
  - the api and worker healthchecks run `python -c`;
  - smoke runs `compose exec ... python -m engine.readiness` and `engine.netprobe`;
  - bundle.sh:266 runs `--entrypoint python ... -m engine.notices`;
  - smoke.sh:25 and test.sh call `uv run`, but only in the gates image (`KE_IN_GATES`);
  - offline_check, install and the ps1 scripts have no uv reference.
  - u3-no-uv-in-ke-app.txt shows: `command -v uv`/`uvx` give 127, notices exits 0, certifi is
    2026.10.19, uid is 10001, and /app and /opt/venv are root-owned.
- **uv.lock.** One hunk, certifi only (version, sdist/wheel URLs, hashes, sizes, upload times). There is
  no header or revision change. It was generated with host uv 0.11.21, the same version as the pin.
  `uv sync --locked` passed in the image build and in the gates, and that sync checks the hashes.
- **scan.sh.**
  - r1-a: the listing is captured with `if ! listing="$(...)"` (no `local` masking), and a failure sets
    status 1 with a FAIL line naming the project.
  - r1-b: the hand command is `docker rm -f $(docker ps -aq --filter label=...=<project>)` (escaped, so
    it expands when run by hand).
  - I-4: `trap '' INT TERM` comes before `trap - EXIT`.
  - I-6: the project is `ke-scan-${SRANDOM}`. The caller cannot override SRANDOM through the environment
    (checked: `SRANDOM=5 bash -c 'echo $SRANDOM'` prints a random value).
  - shellcheck is clean.
- **N1 pin.** `test_scan_command_is_exactly_the_d5_policy` checks the exact list in order, no
  entrypoint, and GRYPE_* limited to D1's three keys.
  - The tester killed all 6 of the reviewer's U2 N1 mutants (c_no_fail_on .. c_output_json) and 5
    more, in u3-red-mutants.txt Phase A and Phase B'.
  - My own mutants were also killed: an extra flag (m4) and a different config path (m5b).
- **Real scan.** u3-real-scan.txt exits 0 with no certifi, quinn-proto or rustls rows. The fixed rows
  that remain are Medium or Low (python binary, pip).
- **Observability.** No agent loop, model call, retrieval or tool call was added, so no span is needed.

## Findings

1. **r3-1 (nit; a test must land in the PSC-6 RED). The empty-listing guard is not tested.**
   - Location: scripts/scan.sh:57 (`elif [ -n "$listing" ]`).
   - This guard matters on every real run: `mapfile -t ids <<<""` gives one empty element, and real
     `docker rm -f ""` exits 1 ("container name cannot be empty"). Without the guard, every clean scan
     would fail.
   - Mutant m1 (`elif` changed to `else`) survives the whole module. This is because the fake exits 0
     for `rm` unless `FAKE_DOCKER_CONTAINERS` is set, and no test sets it with no own containers.
   - Today's code is correct, and the real scan exit 0 proves it. A regression would fail loudly
     (closed), not silently.
   - Fix: add a test that sets `FAKE_DOCKER_CONTAINERS` to decoys only. It asserts exit 0, no
     `scan: FAIL`, and no `docker rm` call.
2. **r3-2 (nit). D10 test 1 checks only the final stage's text.** Location: tests/test_image_scan.py,
   `AppImageTest.test_app_image_final_stage_has_no_uv`.
   - Mutants m8 (builder `cp /usr/local/bin/uv /opt/venv/bin/uv`) and m9 (builder
     `COPY --from=uv /uv /app/bin/uv`) survive. Both carry uv into the final image through the two
     allowed COPYs.
   - This matches D10 test 1 as specified. The manual behaviour check, and the scan once PSC-6 wires
     it, are the backstops.
   - Optional fix: in `builder`, the only `--from=uv` target is `/usr/local/bin/uv`, and no RUN or COPY
     writes a `uv`/`uvx` path under /opt/venv or /app.
3. **r3-3 (nit). Formatting regression.** Location: tests/test_image_scan.py:1396 reads
   `_TAR_CHMOD =re.compile(`; the space before `re` is gone (it was `_TAR_CHMOD = re.compile(` at
   8b20fa5).
4. **r3-4 (nit, process).** uv.lock was regenerated with host uv on Windows, not "inside the gates
   image" as the CLAUDE.md Generated-artifacts row says. The result is equivalent: the uv version is
   the same, the diff is certifi only, and `--locked` passed in the gates. Record this in the commit
   message or handoff, or regenerate inside the gates next time.
5. **r3-5 (nit). SRANDOM needs bash 5.1 or later.** Location: scripts/scan.sh:31.
   - On an older bash, `set -u` stops the script with "SRANDOM: unbound variable" before the trap. That
     fails closed, but the message is obscure.
   - Every supported host (Ubuntu 24.04, bookworm, Git Bash) has bash 5.2 or later.
   - Optional fix: a one-line `BASH_VERSINFO` guard with a `scan: FAIL` message.

## For the orchestrator

- Do not stage `docs/knowledge-engine-claude-code-prompt.md` (untracked).
- Re-run `scripts/verify.sh full` before the commit. The diff touches app.Dockerfile, uv.lock and
  scripts/.
- The PSC-12 Windows run at the branch head is still owed (D10 Consequences).
