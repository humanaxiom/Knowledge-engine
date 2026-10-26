# platform-sbom U2 (PSC-20): review

Reviewer, 2026-10-23. Diff: `git diff 23e3c9b` plus the untracked
`docker-compose.sbom.yml`, `tests/test_sbom_generator.py`,
`docs/evidence/platform-sbom/generator-provenance.md` and `u2/`.

## Verdict: APPROVED (no blocking findings; 5 nits, 2 of them carried to U3)

## What was checked

- `docker-compose.sbom.yml`: pin `anchore/syft:v1.54.1@sha256:3eb5379b…49b1aa`
  equals the N1 amendment, ADR-KE-016 pt 1 amendment and generator-provenance.md
  (security PASS). Hardening matches PSC-20 bullets 2-3 and the grype precedent
  (`docker-compose.scan.yml` x-scanner): `network_mode: none`, `read_only`,
  tmpfs `/tmp`, `cap_drop: [ALL]`, `no-new-privileges:true`. Mounts: two binds,
  `${KE_SBOM_IN:?}`->/in read-only, `${KE_SBOM_OUT:?}`->/out (only writable).
  Environment: TMPDIR=/out/tmp plus the 8 `SYFT_*: "false"` keys, literals only.
  No top-level `name`, no `container_name`, no labels, no profiles, no socket,
  no DOCKER_*. Files equal the tester's targets (`diff` empty).
- `scripts/bundle.sh`: read uses the N1 U2 form (dummy `KE_SBOM_*`,
  `--env-file .env.example`, `-f docker-compose.sbom.yml config --images sbom`);
  COMPOSE_FILE/COMPOSE_PROFILES already unset above. Placed after the stack
  image loop and before "licence notices", i.e. before the first `mkdir` of
  `--out` (line ~294), any tag, save or notices run. One-line, `ref_re` +
  `@sha256:` checks; untrusted value `%q`-quoted in its error; refusal text is
  N1's exactly; no pull anywhere (static and dynamic tests).
- `scripts/offline_check.sh`: pull after the disk floor and Compose >= 2.27
  checks, immediately before `bash scripts/bundle.sh`; `-f` overrides the
  exported COMPOSE_FILE; not via `compose()` (no `--profile offline`); fails
  closed with N1's message, no retry, EXIT trap tears down.
- Tests: `test_sbom_generator.py` (4 PSC-20 tags, checks as problem-list
  functions), offline_check pull/fail tests, fake_docker per-file `config`
  and `${VAR:?}` emulation (inert unless FAKE_COMPOSE_FILE_IMAGES is set),
  compose_support helpers, `test_stack_compose` exemption scoped to
  file+service and backed by the row-by-row mount check. No test was
  weakened: the only existing-test edits add the sbom ref to the fake image
  table, copy the file into the bundle harness tree and add the exemption.
- Controls re-run by the reviewer on the real files (`--base repo`, in the
  existing ke-gates:local image, no build, `network_mode: none`, read-only
  checkout): **138 controls (116 must-fail, 22 must-pass), 0 unexpected** —
  `u2/review-controls-base-repo.txt`. Covers every hardening line, each of the
  8 keys (removed and `=true`), mounts, label leaks, pin shape/place,
  provenance shape, refusal placement (after `mkdir`), dummy vars, env-file,
  message wording (incl. the U8 wording too early), pull ordering/failure.
- Plan/design docs agree with the code (ADR-KE-016 pt 1 amendment, N1 table +
  presence check + "N1 amendment, U2", N4 step 1 for U8). PSC-20 "the ADR
  names the step that pulls it": yes (offline_check.sh until U8).
- Evidence: red-verify-fast FAIL 11 (all U2 tests, expected reasons);
  red-reach PASS; green-verify-fast PASS (798 tests, OK skipped=8, sentinel
  ok); green-verify-full PASS 703 s (798 unit + 15 integration, the pull line
  pulled the pinned ref, then "bundle written", offline_check PASS 95 s). No
  profile paths or SIDs in u2/*.txt.
- Observability: no agent loop, model call, retrieval or tool call; N/A.

## Findings

- **N1 (nit, carry to U3):** the U3 run form shown in design-notes N1
  ("`bundle.sh` runs it as `docker compose -p <project>-sbom -f
  docker-compose.sbom.yml run ...`" and its EXIT-trap `down`) and in the
  header comment of `docker-compose.sbom.yml` has no `--env-file
  .env.example`, and the `down` sets no `KE_SBOM_*`. The U2 test
  `_reads_env_example` already requires `--env-file .env.example` on every
  compose call naming the file, and compose refuses `down` with a `:?`
  variable unset (teardown would then fail). Amend both lines to the N1 U2
  form when U3 pins the command (tester item 8).
- **N2 (nit, carry to U3/PSC-21):** the presence check runs `docker image
  inspect` but does not assert the generator is `linux/$arch`, as the
  stack-image loop above it does. PSC-21 forbids emulation; add the
  `{{.Os}}/{{.Architecture}}` check with the U3 run.
- **N3 (nit):** `scripts/offline_check.sh` header stage list ("disk floor
  -> bundle.sh -> dind up ...") does not mention the interim generator pull.
- **N4 (nit):** design-notes *Env keys (U2)*: "The `SYFT_*` keys must be
  exactly these eight; extra keys are still allowed if they are `false`"
  contradicts itself; "must include these eight" is what the test enforces.
- **N5 (nit):** compose header "No top-level name, so that -p always wins":
  `-p` beats a top-level `name:` anyway. The reason is that the file must not
  fix a project name of its own; wording only.

## Tester open points 5 and 8 (deferred to U3)

Acceptable. U2 has no run of the generator, so there is nothing to observe
dynamically; the static guard is in place (no `name`, `container_name` or
`com.docker.compose.*` label; three must-fail controls). Condition: U3's RED
adds (5) a dynamic assertion that the run's project is `<project>-sbom`,
distinct from the stack's, and that its teardown targets that project, and
(8) a full argv pin of the run (`--env-file .env.example`, `-f`, `run --rm
--pull never sbom docker-archive:/in/<name>.tar --scope all-layers -o
spdx-json=/out/raw.spdx.json`), closing N1 and N2 with it.
