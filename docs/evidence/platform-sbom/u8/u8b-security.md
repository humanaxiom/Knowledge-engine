# U8b security audit (platform-sbom), 2026-10-28

Scope: `git diff HEAD` (docker-compose.sources.yml, scripts/offline_check.sh,
scripts/sources_lock.sh, scripts/bundle.sh, README.md, CLAUDE.md, tests,
fake_docker.py) plus the staged `scripts/bundle_fetch.sh` and the untracked
`tests/test_bundle_fetch.py`. The U8a client `scripts/sources_fetch.py` at
HEAD (audited in `u8a-security.md`) is in scope only as the thing driven.
Probes and raw output: `u8b-security-probes.txt` (fake docker only; no
real daemon, no network).

## Verdict: PASS (no critical, no high, no medium; 2 low, 7 info; none blocking)

Security PASS does not stand in for the gate's `verify.sh full`, which is
still red at the first real sample fetch (gitlab.alpinelinux.org
unreachable from this host; the design fails closed, Q61). The real
sample and full-set runs (O-1) and R9/O-2 remain open for the orchestrator.

## What was checked and holds

- **sources-fetch service** (rendered by the real compose CLI with no
  daemon, probes Part B): `ke-gates:${KE_IMAGE_TAG:-local}`,
  `pull_policy: never` and the run's `--pull never`; `read_only`, tmpfs
  `/tmp`, `cap_drop: [ALL]`, `no-new-privileges:true`, `user` from
  `${KE_SOURCES_USER:?}` checked numeric by the script; the effective
  network is only `ke-fetch-<hex>_default` (no `networks`, `network_mode`,
  ports, dns, extra_hosts, privileged, socket; never backend/edge);
  environment exactly `PYTHONDONTWRITEBYTECODE=1`, with
  KE_MODEL_UPSTREAM/HTTPS_PROXY/GITHUB_TOKEN set in the caller's shell
  absent from the model; six long-form binds, five read-only, `/out` the
  only writable one; no checkout, no uv.lock, no /in. The
  test_stack_compose exemption is an exact set of the six mounts.
- **bundle_fetch.sh injection** (P1-P3, P7): `--set`/`--arch` are
  allowlisted before any docker call (exit 2, 0 calls, also for 40 random
  bytes); `--out` is always made absolute, double-quoted and `--`-guarded
  (a value holding `$()`, backticks, `;`, a newline and a leading `-rf` was
  passed literally; no marker created); the daemon's arch string is mapped
  to two literals and printed only through `printf %q` (a newline cannot
  forge a FAIL line); the project name is `ke-fetch-` + 8 hex from
  /dev/urandom (pipefail stops the script before the trap if `od` fails);
  KE_IMAGE_TAG is only ever a quoted argument and an image ref.
- **--out and fetch.json**: a symlink, a file, a non-empty dir (dotfile
  included; P5 a pre-existing fetch.json) are refused before the trap is
  installed, so a refused dir is never emptied; the trap removes a dir it
  created, and empties a given dir only when it is a directory and not a
  link (`find -P`, `rm -rf` on entries never follows links); after the
  client, `fetch.json` must be a regular file, not a link (Linux rows ok in
  u8b-green-verify-full.txt).
- **Trap teardown scope** (P8a): `down --volumes` on its own `-p
  ke-fetch-<hex>` and `-f docker-compose.sources.yml` only, with
  KE_SOURCES_OUT=/nonexistent (never the real out); INT/TERM/HUP map to
  exit 130/143/129 through the EXIT trap.
- **No network step but the service; no retry**: no URL, host, curl or
  wget literal; one `config --images sbom` (digest pattern enforced), one
  `compose pull sbom` (digest-pinned, as N1 U2), one `run --rm --pull never
  sources-fetch`; no loop. Caller COMPOSE_FILE/PROFILES/PATH_SEPARATOR are
  unset, `-p` beats COMPOSE_PROJECT_NAME for run/down, `--env-file
  .env.example` keeps `.env` unread, and the caller's KE_SOURCES_*=/etc,0:0
  never reach the run (P9).
- **Exit codes and FAIL lines**: the script prints only its own texts
  (paths, arch, the validated ref) and the client's rc; the client's lines
  pass `_safe` (queries dropped; P8 shows `?<query omitted>`). Client rc is
  passed through.
- **offline_check.sh**: only U2's interim generator pull block is replaced
  (3 hunks: header, trap `rm -rf` list, the block); `dist/` exists (`mkdir
  -p dist`) and is git/docker-ignored; the sample dir is a sibling of the
  bundle dir, never inside it or under KE_OFFLINE_BUNDLE (the only path the
  dind/offline-client stack mounts); the trap removes it pass or fail; the
  dind offline proof, net_isolated.sh and the base pulls are unchanged;
  COMPOSE_FILE/COMPOSE_PROJECT_NAME exported by offline_check are
  neutralised inside bundle_fetch.sh.
- **sources_lock.sh SBOM copies**: `mkdir` without `-p` refuses any
  existing entry (dangling links included); each source must be a regular
  file, not a link; `cp -P`; any failure fails before the lock moves.
  Names come from the six pinned images' refs (pattern-checked).
- **Docs**: the CLAUDE.md sentence equals Q73 option 2 (whitespace-normalised)
  and is the only CLAUDE.md hunk; README and the bundle.sh header claim
  nothing the code does not do (sources-fetch pulls nothing; bundle_fetch
  pulls the generator; the set is not read by bundle.sh until U9).
- **Secrets**: 0 secret-pattern hits in the diff and new test file; the new
  u8/ evidence files carry no signed query, profile path, SID or token.

## Findings

| ID | Sev | Blocking | Finding | Recommendation |
|---|---|---|---|---|
| L-1 | low | no | The `--out` symlink refusal can be bypassed: `${out%/}` strips one slash, so `--out link//` or `--out link/.` makes `[ -L ]` follow the link, and an empty target is accepted and bound (U8-1 says a symlink is refused). Intermediate path components are not checked, and there is a check-to-bind TOCTOU window. Impact is bounded: the operator supplies the path, the target must be empty, the bytes are lock-verified, and on failure the trap removes only what was written there. offline_check passes a fixed `dist/` path. | Strip every trailing `/` and refuse a last component of `.` or `..` (or compare `cd -P` + `pwd -P` with the logical path for the last component). Add a test row for `link//` and `link/.`. |
| L-2 | low | no | `fetch_service_problems` (tests/test_bundle_fetch.py) is a denylist: `uts`, `cgroup`, `runtime`, `platform`, `ulimits`, `shm_size`, `init`, `stdin_open`/`tty` and per-bind sub-keys (`bind.propagation`, `bind.create_host_path`, `consistency`) are not pinned, so a future loosening could pass. The current service is correct. | Pin the exact key set of the service (image, pull_policy, user, read_only, tmpfs, cap_drop, security_opt, entrypoint, volumes, environment) and the exact key set of each bind. |
| I-1 | info | no | The client's FAIL line gives only the exception type (`OSError`), without the errno. This is **not a security finding**: the line fails closed, and leaving out `str(exc)` is the safer default, because `ssl.SSLError` (an OSError subclass) and HTTP exceptions carry peer-influenced text. It is a diagnosability gap only (errno 101 had to be found by hand). | If it is wanted, append only the integer errno (`OSError [errno 101]`), never `str(exc)` or `strerror`, keep `_safe` on the line, and add a test row. |
| I-2 | info | no | `--out /` becomes the empty path, giving `FAIL (stage out: cannot create ; ...)`. It fails closed and touches nothing (P6). | Treat `/` as existing and not empty, or refuse an empty path after normalisation. |
| I-3 | info | no | sources_lock.sh reports any `mkdir` failure of `<evdir>/sboms` as "exists" (permission errors included). It fails closed; only the message is wrong. | Name the mkdir failure generically, or test `-e`/`-L` first. |
| I-4 | info | no | The `config --images sbom` and `pull sbom` calls have no `-p`, so the caller's COMPOSE_PROJECT_NAME and unrelated KE_SOURCES_* reach them. This is harmless: neither call creates resources or reads those keys. The caller's KE_IMAGE_TAG chooses the local ke-gates tag by design (as sources-resolve), and `pull_policy: never` keeps it local. | None needed. |
| I-5 | info | no | The FAIL lines print the operator's `--out` path, the same class as carried I-7. Evidence copies must redact profile paths. | Keep the redaction rule. |
| I-6 | info | no | Outside this diff: the untracked `docs/handoffs/NEXT-SESSION.md` l.109 holds an unredacted profile path (a WinGet package path under the user profile AppData). | Redact it before that file is staged (user ruling: profile paths are redacted). |
| I-7 | info | no | sources-fetch sets no pids, memory or tmpfs-size limit. The client caps bytes per file (lock size) and text at 1 MiB, unpacks nothing and writes only `/out`. | Optional: `pids_limit`, `tmpfs` with `size=`; not needed for U8. |

Carried: nothing new to U9 from security beyond U9's own `fetch.json`
refusal (A76) and its check that `--out` holds only 64-hex regular files plus
the record.

## Rework round 1 (2026-10-28)

Scope: staged `scripts/bundle_fetch.sh` and the `fetch_service_problems`
allowlist in `tests/test_bundle_fetch.py`. Evidence: `u8b-r1-red-verify-fast.txt`,
`u8b-r1-controls.txt`, `u8b-r1-green-verify-fast.txt` (1195 tests OK, 8 skipped; the new
rows run in the gates image: linked out behind slashes or dot, unlistable out,
second signal, compose 125, caller platform/env files, allowlist). Probes:
`u8b-r1-security-probes.txt` (Windows with fake docker, no host links; link cases inside
ke-gates:local with network none, read-only, uid 1000, fake docker, no socket).

### Verdict: PASS (L-1 and L-2 closed; nothing weaker than the U8b PASS)

| Item | Status | Evidence |
|---|---|---|
| L-1 | closed | Every trailing `/` is stripped, and a last component of `.` or `..` is refused before any docker call. `link`, `link/`, `link//` and `link///` are refused as a symlink; `link/.`, `link/./`, `link//.`, `.`, `..`, `d/.` and `d/x/..` are refused as a dot component; the link target is untouched (L1, R3-R6). `d///` on an empty dir is accepted as `d` (R7). Residual (info, accepted): a link as a middle component is followed (L6), the same as any path through a linked directory. |
| L-2 | closed | The service keys are an exact allowlist (10 keys), and each bind may hold only type, source, target and read_only, so `bind.*`, `consistency` and `volume` are refused. The new row covers 16 loosenings. |
| B-1 | holds | An unlistable non-empty `--out` (0300, uid 1000) is refused, with no write and no emptying (L7). |
| B-2 | holds | The cleanup sets `trap '' INT TERM HUP` before it clears EXIT, so the teardown runs to the end (row ok). The window between entering cleanup and that line is one builtin: negligible. |
| N-2 | holds | DOCKER_DEFAULT_PLATFORM and COMPOSE_ENV_FILES are unset and reach no docker call (R15/R15b). This also closes a cross-arch generator pull. |
| N-3 | holds | `given=1` only when stage 2 saw an empty dir, and only that dir is emptied. An absent `--out` is made with a plain `mkdir`, and if the dir appears after the check the run fails with nothing touched. A given empty dir is emptied on a client failure and its sibling is kept (R14). |
| N-5/O-8 | holds | The run's exit code passes through (125, 2). The FAIL line names compose only for 125-127 and holds no URL or output of the client (R12, R13). Exit 2 can therefore mean a client usage error as well as a bad argument to the script, as O-8 accepts (info). |

Re-checked unchanged: no injection through `--out` (`$()`, backticks, `;`, a newline,
`-rf`, random bytes), through `--set` (random bytes), or through the daemon arch string
(a newline plus `$()`; it is still printed only through `%q`); `fetch.json` that is a link
before the run (L4) or after the client (L8) is refused, and a created `--out` is removed.
Unchanged info: I-2 (`--out /` and `//` give the empty path and a blank name in the message;
the run fails closed and touches nothing), I-1, I-3..I-7.
