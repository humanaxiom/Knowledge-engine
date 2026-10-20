# Security audit: offline-check unit (PS-3.2, PS-3.3, PS-3.9 N6, PS-3.4), 2026-10-19

**Verdict: PASS.** No critical or high finding. Two medium and three low findings, all non-blocking.
Scope: `git diff HEAD` on f7e9074 plus the untracked `docker-compose.offline.yml`,
`scripts/offline_check.sh`, `scripts/net_isolated.sh` and `engine/netprobe.py`, with the changes to
`smoke.sh`, `verify.sh`, `teardown.sh`, `docker-compose.yml`, `.env.example` and `ci.yml`.
Probes ran only under the projects `ke-sec-oc-{cfg,live,pull,fast}` and the scratch dirs, and every
one was torn down (0 containers, networks or volumes left). Raw output is in `security-oc-probes.txt` (P1..P9).

## Focus answers
- **Privileged dind.** It is on one network only, `<project>_offline`, which is internal with
  `gateway_mode_ipv4=isolated`. It has no gateway and no default route. It has no bind mounts, only
  the certs volume and the anonymous `/var/lib/docker`. Port bindings are empty and it shares no PID
  or IPC namespace with the host (P3). From inside it, connects to the internet and to host addresses
  fail, DNS returns SERVFAIL and `docker pull` fails in 0.02 s. Even after forcing a default route
  with its privileges, ARP finds no peer (P3). The privilege itself remains an accepted risk under
  architecture §2.5 (I-OC3).
- **Digest provenance.** I checked it three ways on my own and all agree on
  `sha256:3e5756e2…d4e` for `docker:29.9.1-dind`: the registry `Docker-Content-Digest` header, the
  sha256 of the index bytes I fetched (TLS-verified, `--proto =https --tlsv1.2`), and
  `buildx imagetools inspect`. It is an OCI index with amd64 and arm64 entries (P1).
- **TLS.** offline-client sees only `/certs/client`, read-only. `/certs/ca` and `/certs/server` do
  not exist in it, and writes fail (P4). Plaintext 2375 is closed, and 2376 refuses both non-TLS
  requests and TLS without a client certificate (P4). Certs volume lifecycle:
  `teardown.sh --volumes --profile offline` removed both the named certs volume and the anonymous
  dind store volume (P4b).
- **Exposure.** No `ports:` in the offline file. Neither container has a docker socket mount, and
  `/var/run/docker.sock` is absent from the client (P2, P4). `test_no_docker_socket_mounted` now
  covers both services.
- **No-pull proof.** The proof has three layers: the host `net_isolated.sh` check runs before the
  client, the pre-run pull must fail, and the install override sets `pull_policy: never`. Together
  these hold, because a pull cannot succeed. The final name-set comparison could not detect a pull
  on its own (M-OCa).
- **netprobe.** Its only inputs are argv. Every word except `connected` exits 1, so it fails
  closed. Output is one word, or `error:<errno name>`, and carries no secret. The IPv4-only rule is
  enforced by `is_ipv4` in smoke.sh, not by netprobe itself (L-OCc).
- **KE_IMAGE_TAG.** `verify.sh full` unsets caller `KE_*` and then derives `wt-%08x%04x` from
  `$PWD`. That value is integer-formatted, so nothing can be injected, and it never equals `local`.
  `bundle.sh` only tags `ke-*:bundle-<sha12>` and `ke-vendor/*`. **Live `ke-app:local` and
  `ke-gateway:local` are never moved.** However, `verify.sh fast` does not apply N6 (M-OCb), and
  bundle tags persist and are shared between worktrees (L-OCa).
- **Cleanup.** I ran the real script with stub docker, bundle and teardown (P9). On bundle failure,
  client failure, success, SIGINT and SIGTERM, teardown ran exactly once with
  `--volumes --profile offline`, under its own `ke-offline-<n>` project (a caller
  `COMPOSE_PROJECT_NAME` is overridden) and with `.env.example`. Only `dist/ke-offline-<n>-amd64`
  and its record were removed. A pre-existing `dist/knowledge-engine-amd64` and a decoy
  `dist/ke-offline-userown-amd64` survived. There was no PASS line on any failure.
- **Secrets.** The secret-pattern grep over the diff and the untracked files found nothing besides
  the existing `changeme` placeholders. Profile paths, SIDs, host names and user names: 0 in the
  untracked files and the diff (P7). The real `.env` is never read (`--env-file .env.example`). The
  model keys that verify exports do not reach dind or the client, because their environments are
  explicit.

## Findings
- **M-OCa (medium, developer + tester).** The client "nothing was pulled" comparison drops
  `repo:<none>` entries. A pull of a digest-pinned ref (`name:tag@sha256:…`, the form every vendor
  ref takes) lands in the containerd store as `name:<none>`, so the awk filter removes it and the
  check passes (P5: `busybox:<none>` became an empty list). The test models a pull as
  `postgres:16-bookworm`, which the real store does not produce. Fix: in the client, fail on any
  `<none>` entry, since the store starts empty and only load and tag run. Alternatively, compare the
  image count with the `as` count. Add a `postgres:<none>` case to
  `test_offline_check_fails_when_tag_set_differs_from_as_set`, and amend §2.5 Client step 6
  ("dangling entries excluded").
- **M-OCb (medium, developer + tester; design conformance).** §2.1 says verify exports the
  per-worktree tag "in both modes". In practice `verify.sh fast` runs `exec ... run --build gates`
  before the tag is computed and without unsetting a caller `KE_IMAGE_TAG`. It therefore builds
  `ke-gates:local`, or whatever tag the caller sets (P8). That moves the `ke-gates:local` tag that
  `build.sh` sets, and lets two worktrees race on it in fast runs. It is not a live-stack image, so
  this is not high. Fix: compute and export `KE_IMAGE_TAG` before the fast branch, and add a B6 test
  for fast.
- **L-OCa (low, architect).** The offline check runs `bundle.sh` on the host, which leaves
  `ke-*:bundle-<HEAD12>` and `ke-vendor/*` tags behind. Observed: `ke-app:bundle-f7e9074f7462` has
  the same ID as `ke-app:wt-a292aa7482b0`. The first-party bundle tag is the same for every worktree
  at one HEAD, so concurrent verify runs can tag over each other between `docker tag` and
  `docker save`, and one bundle can hold another tree image. Options: a per-run `as` namespace for
  the check, or untagging what the check created.
- **L-OCb (low, developer).** The CA key stays out of the client only because Compose applies
  `volume.subpath`. The 2.27 minimum is unmeasured and the daemon API version is not checked. Add a
  fail-closed assertion in the client half that `/certs/client/ca` and `/certs/client/server` are
  absent.
- **L-OCc (low, developer).** `netprobe` resolves hostnames (DNS: `localhost` and `.invalid` were
  looked up). A port outside 0-65535 or a negative `--within` raises a traceback instead of a word.
  All of these still exit 1 (P6). Fix: use `ipaddress.IPv4Address` as the argparse type, port
  1..65535, and `within > 0`.

## Info (no action required)
- I-OC1: the pre-run pull check counts any failure, including rate limits, as "no route". The
  design accepts this (§2.5 Client step 1), with `net_isolated.sh` as the authoritative proof.
- I-OC2: the §2.5 residual "DNS on internal networks may forward outward" was not seen here.
  Lookups from the `offline` network got SERVFAIL on Docker Desktop 29.5.2 (P3).
- I-OC3: the dind privilege is the accepted risk in §2.5. The probes found no added exposure (no
  binds, ports, host namespaces or second network).
- I-OC4: §2.1 says the `wt-` tag comes from SHA-256, but the code uses two POSIX `cksum` (CRC32)
  values. That is safe (no injection), but the doc and code disagree (reviewer).
- I-OC5: offline-client has no `pull_policy: never`. A missing `ke-gates` tag would try
  `docker.io/library/ke-gates`, which is the official namespace and cannot be squatted. Adding
  `never` is cheap.
- I-OC6: cleanup removes `dist/ke-offline-<n>-<arch>` even if bundle.sh refused because that exact
  random name already existed. This is practically unreachable.
- Host-side `unittest` of the stub tests is not representative here because `bash` resolves to WSL.
  I relied on P9 (Git Bash) and the developer in-container green run.
