# Security re-check: platform-supply-chain unit 2, rework round 1/5

- Author: security, 2026-10-21. Branch `agent/platform-supply-chain` at 8900766 plus uncommitted U2 and rework 1.
- Scope: `scripts/scan.sh` (rework), the 9 new tests in `tests/test_image_scan.py`, `tests/fake_docker.py`
  (container model, FAKE_DOCKER_SAVE_MODE, `stat` hook, FAKE_DOCKER_RECORD_ENV), and the new evidence files.
  Read against `security-u2.md` (M-1, L-1..L-3, I-1..I-3) and the orchestrator's rework-1 rulings.
- Probes: scratch copies only, in the gates image `ke-gates:wt-f8924d658b0a` (bash 5.2, docker CLI),
  `--network none`, every container and volume labelled `com.docker.compose.project=ke-secu2r1-*`.
  None left afterwards. Raw output: `security-u2-r1-probes.txt`.

## Verdict: PASS

All four prior findings are closed. No critical or high finding. One new low (L-4) and four infos,
all non-blocking. I-1..I-3 from `security-u2.md` are unchanged and still accepted.

## Prior findings

| ID | Status | Where | Evidence |
|---|---|---|---|
| M-1 | closed | `scripts/scan.sh:79-82` | `chmod 0644 -- "$KE_SCAN_IN/ke-app.tar"` at :82 comes right after `docker save` (:79-80) and before the first `docker compose` (:87). Under `set -e` a failed chmod ends the run, and the run fails closed. `docker-compose.scan.yml:9-17` still has `cap_drop: [ALL]`, `no-new-privileges` and `read_only: true`. There is no `cap_add`, `privileged`, DAC capability or `user:`. The only chmod in scan.sh is 0644. `test_scan_does_not_widen_scanner_privileges` pins all of this. Semantics probe: the file is uid 1000, the dir is 0755, and the reader is root with `--cap-drop ALL` (CapEff 0). The reader is **denied** at 0600 and **reads** at 0644 after the owner's chmod. Control: a 0700 dir denies even a 0644 file, and `mkdir -m 0755` (:71) covers that. Real Linux end to end: still due on the first CI run after PSC-6. |
| L-1 | closed (shell level) | `scripts/scan.sh:46-48` | Cleanup sets INT and TERM to ignored (an empty trap action) at :48. Probe: a second TERM or INT to the whole process group, 0.5 s into a 3 s teardown. "teardown start" and "teardown end" are both logged, `dist/` is empty, and the exit codes are 143 and 130. The control (pre-fix `trap - INT TERM` on a scratch copy) logs no "teardown end" and leaves `dist/` with 1 entry. See L-4 for the in-flight docker client. |
| L-2 | closed | `scripts/scan.sh:70-71` | `mkdir -p dist && mkdir -m 0755 -- "$KE_SCAN_IN"`. Probe: `dist/ke-scan-*` was planted as a dir holding a fake tar, and separately as a symlink. Both runs: rc=1, "File exists", 0 save and 0 compose calls. Cleanup's `rm -rf --` removed only the link, and the symlink target's `sentinel` was intact. See I-5 for the residual. |
| L-3 | closed | `scripts/scan.sh:34` | `DOCKER_DEFAULT_PLATFORM` is in the `unset`. `.env.example` does not set it. `test_scan_clears_caller_docker_default_platform` checks every docker call and teardown.sh. |

## Cleanup step `docker ps -aq --filter label=...=$project | docker rm -f` (`scripts/scan.sh:51-57`)

- **Exact match:** probe. The label filter matched only `ke-secu2r1-12`. It did not match `-123`, `-1`,
  the uppercase form, a trailing space, or the key variants `<key>.x` and `x<key>`. A look-alike or
  prefix project is never removed. The 12-hex short IDs come from the daemon. An ambiguous prefix makes
  `docker rm` error rather than pick a container.
- **Hostile container:** labels cannot change after a container is created. A container that carries
  `ke-scan-<N>` was created with that label by whoever made it, so cleanup can only remove the
  attacker's own container. It cannot be pointed at a victim's container. To plant one, the attacker
  needs daemon access, and daemon access is root on the host. With it they could equally pre-create
  `ke-scan-<N>_scan-db` with a poisoned DB, or tamper directly. The project name is not a trust
  boundary against that actor.
- **Random part:** `${RANDOM}${RANDOM}` gives at most 2^30 values, from a non-cryptographic LCG seeded
  from time and pid. A probe shows bash does not import `RANDOM` from the environment, so the caller
  cannot fix the name. This is enough for its real job, avoiding collisions between concurrent runs.
  Cleanup does run on an early `mkdir` failure, so a collision would tear down the other run's project.
  The odds are about 1e-9 per pair. Optional hardening is I-6.
- **Fails closed:** if `docker ps` fails, `mapfile` still returns 0 with an empty list and nothing is
  removed. `teardown.sh` then fails, which sets status 1 and prints the hand command, so the run is red,
  not silent.

## New findings (non-blocking)

| ID | Sev | Where | Finding | Recommendation |
|---|---|---|---|---|
| L-4 | low | `scripts/scan.sh:48,53,58` | Ignoring INT and TERM in cleanup protects bash and `teardown.sh`. A docker CLI already running during cleanup (`docker rm -f`, or `docker compose down` inside teardown.sh) is a Go program. Go reinstalls its own SIGTERM handler even when the signal is inherited as ignored, and the CLI handles SIGINT. Probe (child = the real docker CLI blocked on an unanswering socket): a second TERM kills it with rc=143, and a second INT with rc=130. teardown.sh then fails under `set -e`, scan.sh prints the hand command, sets status 1 and still removes `dist/<project>`. **Fails loudly, never green.** It needs two group-wide signals inside the cleanup window, which means a double Ctrl-C. A CI cancel signals the step process, not the group. | Accept, or run cleanup's docker calls in their own session (`setsid -w`, Linux only) so a group signal cannot reach them. Same pattern as the `offline_check.sh` follow-up. |
| I-4 | info | `scripts/scan.sh:46-48` | Microsecond window: a second signal after `trap - EXIT` (:46) and before the ignore at :48 runs `exit 143` with no EXIT trap left. | Optional: swap :46 and :48 so INT and TERM are ignored first. |
| I-5 | info | `scripts/scan.sh:70` | `mkdir -p dist` accepts a symlinked or other-writable `dist/`. Anyone who can write to `dist/` can still rename the fresh dir and substitute it during scan-db. Same premise as L-2: that actor can already edit scan.sh. Cleanup `rm -rf` also deletes a pre-existing dir planted at this run's own name. It is gitignored, so this is harmless. | None. Human ACL note from L-2 stands. |
| I-6 | info | `scripts/scan.sh:31` | `RANDOM` is a 15-bit LCG. | Optional: `ke-scan-${SRANDOM}` (bash 5.1+; gates image 5.2, Git Bash 5.3). |
| I-7 | info | `docker-compose.scan.yml:53-56` | The ignore-file bind has the same M-1 mechanics. A checkout made under umask 077 makes it 0600, and the cap-dropped `scan` cannot read it. That fails closed. CI's checkout runs under umask 022 and gives 0644. | None. Note for a dev host with a strict umask. |

## Tests and fake

- `tests/test_image_scan.py` (new tests at :843-1116) has no `shell=True`, `eval`, `pickle` or unsafe
  YAML. Subprocesses take argv lists and a built env.
- The L-2 planter writes only under the test tmp dir, through `FAKE_REAL_PATH` tools.
- The B1 test asserts that no rm, filter or prune names a decoy, including a look-alike `ke-scan-1`.
- `tests/fake_docker.py`:
  - `FAKE_DOCKER_RECORD_ENV` copies only the variables it names, into the tmp JSON log.
  - The label filter is an exact `==`, the same as the real daemon (probe above).
  - An unmodelled filter or template exits 2, failing closed.
  - All of it is inert unless its variable is set.

## Evidence sweep

- **Files:** all 46 changed and untracked files, plus the reviewer's `review-u2-r1*` files that
  appeared during this audit (as of the time I read them).
- **Patterns:** AWS, GitHub, Slack, OpenAI and Anthropic keys, Google API keys, JWTs, PEM private
  keys, credentials in URLs, password/token/api-key assignments, `S-1-5-21-` SIDs, `C:\Users`,
  `/c/Users`, `/mnt/c/Users`, `AppData`, `/home/<user>`, scratch paths.
- **Hits:** none in the change. The two pattern hits are the pre-existing placeholder
  `changeme-postgres-password` in `docs/architecture.md:1264`, which is not in the diff, and the
  pattern list in `security-u2.md`. "scratchpad" in `u2-rework1-mutants.txt:1` is prose, not a path.
- **Hosts and addresses:** the URLs are public download hosts, `grype.anchore.io`, `.invalid`
  test hosts and 127.0.0.1. The IPs are Docker-internal. No model-host value appears in the diff.
