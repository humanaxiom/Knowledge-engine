# Review: offline check unit (PS-3.2, PS-3.3, PS-3.9 N6, PS-3.4) - 2026-10-19

Reviewer, plan item `platform-offline`, base HEAD f7e9074 (`git diff HEAD` + untracked
`docker-compose.offline.yml`, `scripts/offline_check.sh`, `scripts/net_isolated.sh`,
`engine/netprobe.py`, `tests/test_offline_check.py`, `tests/test_offline_netprobe.py`).
Read: handoff (tester RED, rulings 1-4, developer GREEN), architecture §2.5 / §2.6 items 7-12 /
ADR-KE-009, requirements PS-3.2/3.3/3.4/3.9, `green-oc-verify-full.txt`.

## Verdict: CHANGES REQUESTED (2 blocking, 8 non-blocking)

## Blocking

**B1. The no-pull assertion does not see a digest-pinned pull.** `scripts/offline_check.sh:79`
- The awk drops every `repo:<none>` row (`$0 !~ /:<none>$/`), not only dangling `<none>:<none>`.
  PS-3.2 *No pull happened* and §2.5 client step 6 exclude only dangling entries.
- On the containerd store (the pinned dind's store, S1), a `name:tag@sha256:...` pull lists as
  `name:<none>`. Host probe, read-only: `docker:<none> sha256:3e5756e2...` (the pinned dind
  digest) and `postgres:<none>`. Every vendor ref in this stack is digest-pinned. So the pull
  this step exists to catch (a service the override missed) would be filtered out.
- Proof, scratch only: with the client fixture and
  `FAKE_DOCKER_LS_AFTER = AS_SET + ["postgres:<none>"]`, today's script exits 0 and prints
  "image names equal the bundle's; nothing was pulled".
- With the filter narrowed to `awk '$0 != "<none>:<none>"'`, that case fails and names
  `postgres:<none>`. All 20 `OfflineCheckScriptTest` tests stay green.
- install.sh:614-617 requires the loaded name to equal `as`, so install itself should leave
  no `repo:<none>` rows.
- Fix:
  - developer: narrow the filter, then re-run `verify.sh full` to confirm the real dind
    store shows nothing else after install. If it does show something, record why in §2.5 and
    match on the digest instead.
  - tester: add a `repo:<none>` "extra" subcase to
    `test_offline_check_fails_when_tag_set_differs_from_as_set`.

**B2. Nothing guards the exec bit on the two new scripts that are called directly.**
`scripts/verify.sh:106` (`scripts/offline_check.sh`) and `scripts/smoke.sh:91`
(`scripts/net_isolated.sh`) call them without `bash`.
- Both files are untracked, and `core.filemode=false` on this host. A plain `git add` records
  100644, and the ubuntu-24.04 CI checkout then gets "Permission denied". This is the RB2c
  precedent.
- A Windows-host verify cannot see the problem: Git Bash runs shebang files regardless of mode.
- `ExecBitTest.test_operator_scripts_are_executable_in_git`
  (`tests/test_offline_bundle.py:3929`) lists only bundle/install/launch/teardown.
- Fix:
  - tester: extend that test to `scripts/offline_check.sh` and `scripts/net_isolated.sh`;
  - developer: stage both with `git add --chmod=+x` (or call them with `bash`, as
    offline_check.sh already does for its own callees).

## Non-blocking

- **N1. The KE_IMAGE_TAG hash is 32 bits, not 48.** `scripts/verify.sh:55-57`
  - CRC is linear. For equal-length paths, `cksum(x) XOR cksum(y) == cksum(p+x) XOR cksum(p+y)`
    (5/5 random pairs). So whenever the first cksum collides, the second does too, and the
    second cksum adds no entropy.
  - Collision found by a 2^16 birthday search, confirmed with real `cksum` and the exact
    formula: `/home/u/wt/14591828` and `/home/u/wt/40040200` both give `wt-b2405df97d12`.
  - In practice: with a handful of worktrees on one host the chance is about n^2/2^33, so
    negligible.
  - Stable across runs: `cd "$(dirname "$0")/.."` gives the same `$PWD` for `scripts/...`,
    `./scripts/...` and absolute calls (a symlinked path gets a new tag, which is harmless).
  - Fix: either say "32-bit" in the comment, or use one real hash (`md5sum` or
    `git hash-object --stdin`; neither is forbidden by `test_verify_sh_has_no_inlined_commands`).
- **N2.** `scripts/smoke.sh:168`: the control `docker run` should pass `--pull never`. On an
  operator host with the image missing, it would otherwise try docker.io.
- **N3.** `scripts/smoke.sh:154,163`: two `compose config` calls (JSON for the port, YAML + awk
  for the image), and the awk depends on compose's YAML indentation. Acceptable without jq;
  a comment would help.
- **N4.** `scripts/offline_check.sh:201`: the Compose minimum 2.27 for `volume.subpath` is
  unmeasured, but §2.5 says "measured at implementation". Measure it, or record it in §2.5 as
  an unmeasured conservative bound.
- **N5.** `scripts/bundle.sh:206` (not in this diff): `net_isolated.sh` is copied only
  `if [ -f ]`, but the bundled smoke.sh now needs it. Make the copy unconditional, or pin it in
  PS-3.8 `test_bundle_contents`.
- **N6.** `engine/netprobe.py:31,50`: `--within` and the port are not range-checked.
  `--within 0` gives `error:EINPROGRESS`, and port 70000 gives an OverflowError traceback with
  no word printed. Both fail closed in smoke.
- **N7.** `scripts/verify.sh` fast path: it still builds `ke-gates:${KE_IMAGE_TAG:-local}` and
  does not drop a caller's KE_IMAGE_TAG. N6 covers `full` only, and this was already so before
  this change. Info.
- **N8.** CI disk: the 10 GiB floor sits on the runner's root fs after the build. The first CI
  run (R5/R6) will show whether it trips. Info.

## Judgements requested

- **Conformance.**
  - The standalone `docker-compose.offline.yml` matches ruling 1 and §2.5 field by field:
    pinned dind 29.9.1 digest, alias `docker`, TLS env, client 10001:10001, certs `client`
    subpath read-only, bundle bind read-only, `/install` and `/tmp` exec tmpfs, `offline`
    internal + isolated, no restart.
  - The host-half order and exports come before the trap. Teardown takes `--profile offline`
    only. PS-3.4 timeout is 20 (R5).
- **sh portability.**
  - offline_check.sh is dev/CI-only (it needs bundle.sh's Linux host, R1), so bash 4/GNU there
    is in scope.
  - The teardown.sh changes stay bash 3.2-safe (while/shift and the `${a[@]+...}` idiom).
  - The smoke.sh additions are bash 3.2 constructs, and smoke is not run on the Mac (Q53).
- **verify.sh order and single teardown.**
  - The order is build, launch, gates-it, smoke, `teardown_verify`, offline_check.
  - `torn_down=1` is set before teardown runs, so the trap never repeats it. A failed teardown
    exits 1 before offline_check. On interrupt, offline_check's own trap removes its project.
  - Correct per ruling 2. Mutants M5 and M6 are killed.
- **ci/offline control logic.**
  - IPv4 is validated before any probe.
  - The control must print exactly `connected`; anything else, empty included, is
    "inconclusive" and fails.
  - api and worker must each print exactly `no_route`; `timeout`, `refused`, `connected` and
    empty fail and name the service.
  - Correct. M4, M8 and M12 are killed.
- **netprobe.**
  - Errno mapping matches §2.5. `TimeoutError` is caught before `OSError`, the socket is closed
    in `finally`, and only `connected` exits 0.
  - No span is correct here: §2.5 says it is not an agent step. Observability OK.
- **Fixture fixes: legitimate harness repairs, not weakening.** I undid each one in a scratch
  copy against the correct implementation:
  - F1, `_stub` order: the stubs record `@NAME@`, so the client half fails with
    "Lists differ: ['install'] != [...]".
  - F2, double mkdir: FileExistsError x10.
  - F3, duplicate env: TypeError "multiple values for keyword argument 'FAKE_DOCKER_ROOT_DIR'".
  - F4, no `offline_check` stage stub in `test_stack_model_keys`: verify exits 127, 8 failures.
  - No assertion changed, and the test count is the same RED -> GREEN (631).

## Mutants (scratch copies, gates image `ke-gates:local`, `--network none`, read-only mount)

The baseline of the targeted modules is 54 tests OK. All 14 mutants are killed:

| Mutant | Killed by |
|---|---|
| M1 drop the tag-set check (`if false`) | `..._tag_set_differs...` x3 |
| M1b missing names only | the `extra` subcase |
| M2 classic store accepted | `test_offline_dind_uses_containerd_store` (classic) |
| M3 netprobe always `no_route` | NetprobeTest, 9 failures |
| M3b other errors -> `no_route` | EACCES and EADDRNOTAVAIL |
| M4 skip the control (`control=connected`) | 9 failures (control-fails x5, probes x4) |
| M5 no `torn_down=1` | VerifyHostHalfTest x4 |
| M6 offline_check before teardown | x4 |
| M7 constant tag | `test_verify_full_uses_per_worktree_image_tag` |
| M8 accept `timeout` | timeout subcases x2 |
| M9 drop the Internal check | `not internal` |
| M10 skip the pull probe | x2 |
| M12 probe api only | x9 |
| M13 any profile | TeardownShScopeTest x6 |

The surviving gap is B1: no `repo:<none>` case.

## Runs

- Reviewer `COMPOSE_PROJECT_NAME=ke-review-oc scripts/verify.sh fast`: PASS, 631 tests
  (skipped=8), lint PASS. Output: `docs/evidence/platform-offline/review-oc-verify-fast.txt`.
- I did not run `full` myself. The developer's full run is PASS (454 s): `green-oc-verify-full.txt`.
  - It shows the inner `ci/offline` `no_route` for api and worker, the containerd store, a
    failed pull and an equal name set.
  - The host has no `ke-offline-*` container, volume or network left, and no anonymous volume
    from that run.
- B1 needs a new full run.
