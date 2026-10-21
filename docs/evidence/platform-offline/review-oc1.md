# Review: offline-check rework round 1/5 (scoped confirmation) - 2026-10-19

Reviewer, plan item `platform-offline`, HEAD f7e9074, working tree + index (`git diff HEAD`,
staged `scripts/offline_check.sh` / `scripts/net_isolated.sh`, untracked `scripts/image_tag.sh`).
Read: `review-oc.md`, handoff (orchestrator round-1 line, tester RED, developer GREEN),
`architect-oc1.md`, `green-oc1-verify-full.txt`, `green-oc1-attempt1-verify-full.txt`.
All probes and mutants ran on a scratch copy (tracked + untracked files) in
`ke-gates:wt-33a132fbfdd7`, `--network none`, scratch mounted read-only.

## Verdict: APPROVED (0 blocking, 4 non-blocking)

## Findings confirmed fixed

| Item | Fix | Test | Mutant(s), killed by |
|---|---|---|---|
| B1 / M-OCa | `offline_check.sh:91` awk `$0 != "<none>:<none>"` | `test_offline_check_fails_when_tag_set_differs_from_as_set` (+ `postgres:<none>`, `docker:<none>`; `<none>:<none>` control) | MB1 (old filter) -> 2 subcases fail |
| B2 | index 100755 for `offline_check.sh`, `net_isolated.sh` (`git ls-files -s`) | `ExecBitTest` extended to both | n/a (static; index verified) |
| N1 | `scripts/image_tag.sh`: `wt-` + sha256(`pwd -P`)[:12] | `test_verify_image_tag_*` x3, `ImageTagHelperTest` x3 | MT1 `$PWD` (symlink x2), MT2 cksum (12), MT5 8 hex (14), MT6 trailing newline (12), MT7 shasum w/o `-a 256` (1) |
| M-OCb / N7 | tag computed + exported before the fast/full branch, kept past the `KE_*` unset loop | `..._is_sha256_of_the_real_path_in_both_modes` (caller None/local/attacker) | MT3 caller wins (5), MT4 unset loop drops it (6) |
| N2 | smoke control `docker run --rm --pull never` | `test_ci_offline_control_never_pulls` | MN2 (1) |
| N5 | bundle.sh copies `net_isolated.sh` unconditionally | `test_bundle_always_ships_net_isolated` | MN5 old guard (2) |
| N6 / L-OCc | netprobe: IPv4 literal, port 1-65535 ASCII, finite `--within` > 0, `bad_arguments` | `test_netprobe_rejects_bad_arguments_with_one_word`, `..._accepts_the_bounds`, `..._cli_bad_arguments_have_no_traceback` | MP1 port (3), MP2 nan (2), MP3 <=0 (2), MP4 host (5) |
| L-OCb | client refuses `${DOCKER_CERT_PATH:-/certs/client}/{ca,server}`, `-e` or `-L`, before any docker call | `test_offline_check_client_refuses_ca_or_server_certs` | MC1 no check (5), MC2 no `-L` (link:ca), MC3 hard-coded path (5), MC4 `ca` only (2) |
| I-OC5 | `offline-client` `pull_policy: never` | `test_offline_client_never_pulls` | MI5 (1) |

## Re-run proofs

- **B1 scratch proof** (client fixture, `FAKE_DOCKER_LS_AFTER = AS_SET + [x]`):
  - `postgres:<none>` -> rc 1, "not in the bundle: postgres:<none>"
  - `docker:<none>` -> rc 1, "not in the bundle: docker:<none>"
  - `<none>:<none>` -> rc 0; `[]` -> rc 0 ("nothing was pulled").
  - Real store: `green-oc1-verify-full.txt:1625` "image names equal the bundle's; nothing was pulled" on
    the dind containerd store, so install leaves no `repo:<none>` row.
- **CRC collision pair** (real paths, root in a throwaway container):
  - `/home/u/wt/14591828` cksum 2990562809 -> `wt-f0b61c9b4765`
  - `/home/u/wt/40040200` cksum 2990562809 -> `wt-504b4389252c`
  - The cksums still collide, but the tags differ and equal sha256[:12]. A symlink to the
    first gives `wt-f0b61c9b4765`, and so does an absolute call from `/`.
- `green-oc1-verify-full.txt`: fast build uses `ke-gates:wt-33a132fbfdd7`; 644 OK (skipped=8), 11 integration
  OK, ci/offline `no_route` for api and worker (outer and inner), offline_check PASS 91 s, verify full PASS 449 s.

## Judgements requested

- **Fixture fix, `tests/test_stack_model_keys.py`: a harness repair, not a weakening.**
  - verify.sh now runs `bash scripts/image_tag.sh`, and this fixture copies the real
    verify.sh into a temporary directory.
  - Without the helper, every case exits 127 ("image_tag.sh: No such file", the 8 failures in
    `green-oc1-attempt1-verify-full.txt`).
  - It copies the real helper, not a stub, which matches the `env_value.sh` precedent.
  - No assertion changed, and the test count is 644 in both RED and GREEN.
- **Tester `_client` default `DOCKER_CERT_PATH=/certs/client`: a harness repair, not a weakening.**
  - `_clean_env` builds the env from scratch, so this default equals both the script's
    own fallback and the compose value (`OfflineComposeTest` asserts compose sets
    `DOCKER_CERT_PATH=/certs/client`).
  - Merging it through `defaults.update(extra)` lets a test override it without a
    duplicate-kwarg TypeError (the F3 class).
  - No existing assertion changed.
  - Side effect: the `:-/certs/client` fallback is not exercised. Mutant MC5
    (`${DOCKER_CERT_PATH:-}`) survives. See NB3.
- **`scripts/image_tag.sh` at 100644, called through `bash`: fine.**
  - `verify.sh:30` runs `bash scripts/image_tag.sh`, so the mode bit is never consulted.
    This is the same call shape §2.1 names for `env_value.sh`.
  - It is verify-only and not bundled (the tester pins that). B2 applied only to
    scripts called directly.
  - Precondition for the commit: the file is untracked (`??`) today and has to be staged with
    the commit. Otherwise a CI checkout fails at `verify.sh:30`. `ImageTagHelperTest` would
    also go red there, so this cannot slip through silently.

## Non-blocking (no new design questions)

- **NB1. netprobe `--within 1e300` still prints a traceback.**
  - Output: `OverflowError: timestamp out of range for platform time_t` from `sock.settimeout`
    (`engine/netprobe.py:37`).
  - It is finite and > 0, so validation passes. It fails closed (non-zero, no `no_route`).
    smoke passes only 2 or 5.
  - Fix: an upper bound on `within`, or catch `OverflowError` and return `bad_arguments`,
    plus one BAD_ARGS case.
- **NB2. Two netprobe branches have no test.**
  - MP5: drop the `_Parser.error` override. Missing or extra arguments would then exit 2
    with argparse usage, not `bad_arguments`.
  - MP6: drop `isascii()`. Then `'١'` is accepted as port 1.
  - Both mutants survive. The behaviour is correct today (probed: missing `--within`, an
    extra argument and `١` each print `bad_arguments`). Fix: add those three to `BAD_ARGS`.
- **NB3. MC5 survives.**
  - The fallback path is reachable only if compose stops setting `DOCKER_CERT_PATH`, and
    `OfflineComposeTest` pins that.
  - A unit test cannot create `/certs/client` without root. Accepted as is; info.
- **NB4. Per-worktree `ke-gates:wt-*` / `ke-app:wt-*` images now build up in fast mode too.**
  - Example on this host: `ke-gates:wt-a292aa7482b0` from the old formula.
  - This is a known-limit class next to L-OCa. Housekeeping only.
- Carried, unchanged: N3 (comment on the YAML awk), N4 and L-OCa (now recorded as known limits
  in §2.5), N8 (after the first CI run).

## Runs

- `COMPOSE_PROJECT_NAME=ke-review-oc1 scripts/verify.sh fast`: PASS, 644 tests OK
  (skipped=8), lint PASS, image `ke-gates:wt-33a132fbfdd7`.
  Output: `docs/evidence/platform-offline/review-oc1-verify-fast.txt`.
- Mutants: 24 in total. 21 are killed (MB1, MC1-4, MI5, MN2, MN5, MT1-7, MP1-4).
  3 survive (MC5, MP5, MP6), and NB2/NB3 above cover them.
  - One run was a harness artefact: MC3's first run hit MSYS path conversion of the mutant
    text. I re-ran it with `MSYS_NO_PATHCONV=1`, and it is killed.
- I did not run `full`. The developer's `green-oc1-verify-full.txt` is PASS, and the orchestrator
  re-runs full before the commit.
