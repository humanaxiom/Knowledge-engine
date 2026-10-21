# Security confirmation: offline-check rework round 1 (M-OCa, M-OCb, L-OCb, L-OCc, I-OC5), 2026-10-19

**Verdict: PASS.** All five findings from `security-oc.md` are fixed. Nothing is critical, high or
medium. One new low finding (L-OC1a) and three info notes, all non-blocking.
Scope: HEAD f7e9074 plus the working tree: `scripts/offline_check.sh`, the new `scripts/image_tag.sh`,
`scripts/verify.sh`, `engine/netprobe.py` and `docker-compose.offline.yml`. I read
`architect-oc1.md` and `green-oc1-verify-full.txt`: 644 + 11 tests OK, offline stage PASS (91 s)
with "nothing was pulled", verify full PASS (449 s).
Probes ran only in projects `ke-sec-oc1-{pull,pp,cd}` and the scratch dir, and all were torn down
(0 containers, networks or volumes left). No images were built and none of the user's tags were
touched. HEAD and the index are unchanged. Raw output: `security-oc1-probes.txt` (P1 to P7).

## Confirmations
- **M-OCa: fixed.** `offline_check.sh:91` now drops only `<none>:<none>`.
  - P1b: a digest-pinned pull into a real containerd-store dind (pinned `docker:29.9.1-dind`)
    lists as `busybox:<none>`, and that row now survives the new filter.
  - P2: the real client half, run with a stub docker, fails for `postgres:<none>`,
    `busybox:<none>` and `<none>:16-bookworm`, naming each one as "not in the bundle".
  - P2 controls: an exact match passes, and an extra `<none>:<none>` row also passes.
- **M-OCb: fixed.** verify.sh sets `KE_IMAGE_TAG="$(bash scripts/image_tag.sh)"` before the fast
  branch. The value is unconditional and survives the `KE_*` unset loop (exact-match `grep -vx`).
  - P4: a scratch checkout with stub docker sees only `wt-<sha256(pwd -P)[:12]>`, in fast (1 call)
    and in full (all 6 build/launch/compose/smoke/teardown/offline stages). This held for a caller
    `KE_IMAGE_TAG=local`, `=wt-000000000000` and `=x;$(id)`, and for a hostile `.env`
    (`KE_IMAGE_TAG=from-dotenv`).
  - P4b: real `docker compose config` resolves `ke-{app,gates,gateway}:wt-…` with that `.env`
    present, because `--env-file .env.example` keeps `.env` out of interpolation. The offline
    client inherits `ke-gates:wt-…`.
  - A missing `sha256sum` or `shasum` fails closed (rc 127, P5f), and `set -e` stops verify at the
    assignment.
- **image_tag.sh** reads no variable except `$0`. KE_IMAGE_TAG, PWD, HOME, OLDPWD and LC_ALL noise
  leave the tag unchanged (P5, P5f).
  - On Linux, a symlinked checkout gives the target's tag whether you cd in or use an absolute
    `$0`, and a repointed link follows its new target, so two trees never share a tag (P5f).
  - Paths with spaces and quotes work. Output is always `wt-` plus 12 hex, so nothing can be
    injected. Exception: CDPATH, see L-OC1a.
- **L-OCb: fixed.** P3 ran in Linux with real symlinks. With `ca` or `server` present as a
  directory, empty file, dangling link, link to a directory, link to a file, self-loop or mode-000
  directory, or both present, the client exits rc 1 with the named message and makes **0 docker
  calls**. Controls: a clean client dir and an uppercase `CA` both proceed.
- **L-OCc: fixed.** P6 ran under strace with `python3 -I` on a byte-identical `netprobe.py`.
  - Hostnames (`localhost`, `docker`, `.invalid`), IPv6, shorthand, hex, leading zeros,
    out-of-range octets, trailing spaces and empty strings all print `bad_arguments` with rc 1 and
    0 bytes on stderr. Each run makes **0 `socket()` calls, opens no resolv.conf, hosts or
    nsswitch file, and sends nothing to port 53**.
  - Ports 0, 65536, -1, +80, " 80", Arabic-Indic digits, 1e3 and 0x50 are rejected the same way.
  - `--within` 0, -0, -1, nan, ±inf, 1e309 and abc are rejected the same way.
  - Missing `--within`, extra arguments, the `--with` abbreviation and `-h`/`--help` are rejected
    the same way.
  - Valid IPv4 literals make exactly one socket and one connect, with no resolver files.
  - On the host, the `-m` form gives the same words with no traceback.
- **I-OC5: fixed.** The rendered config has `pull_policy: never`. In P7 (project `ke-sec-oc1-pp`), a
  missing `ke-gates:sec-oc1-absent` fails in 1 s with "No such image" and nothing is pulled.
- **Secrets and identifiers:** the pattern grep over `git diff HEAD` and the new files finds
  nothing. Profile paths, temp dirs, SIDs, user names and host names: 0 hits, including in
  `security-oc1-probes.txt`.

## Findings
- **L-OC1a (low, developer + tester; non-blocking).** `image_tag.sh:8` runs
  `cd "$(dirname "$0")/.."` with a relative `$0` (`scripts`), and verify.sh calls it as
  `bash scripts/image_tag.sh`. An exported `CDPATH` therefore applies, and bash prints the new
  directory to stdout, so it ends up in the tag.
  - With `CDPATH=<other worktree>`, the value is `<wt2 path>\nwt-<wt2 hash>` (P5, P5c).
  - With the common `CDPATH=.:…`, the value is `<own path>\nwt-…`, with no redirect at all (P5e).
  - Impact: this **fails closed**. compose config accepts the value, but Docker rejects it as
    "invalid reference format" (P5d). verify breaks for anyone with CDPATH exported, and it never
    silently shares another tree's tag. It also contradicts the "reads no environment variable"
    claim.
  - `verify.sh:16` (pre-existing) uses the same pattern. With CDPATH, the whole run can move to
    another checkout.
  - Fix: `CDPATH= cd -- "$(dirname -- "$0")/.."` (or `unset CDPATH` first) in image_tag.sh and
    verify.sh. In verify.sh, check `[[ $KE_IMAGE_TAG =~ ^wt-[0-9a-f]{12}$ ]]`. Add a test that runs
    image_tag.sh with `CDPATH=.` exported and expects exactly one line.

## Info
- I-OC1a: in the containerd store, a `repo:<none>` row disappears once the same content gets a tag
  (P1d to P1f; P1c kept it, so the behaviour is not consistent). This is unreachable today: install
  tags only at step 7, before launch, and no later step tags anything. If a tag step is ever added
  after launch, the no-pull check could miss a pull.
- I-OC1b: on Windows, Git Bash resolves an NTFS junction (P5b) but may spell the same tree another
  way, through the `/tmp` mount alias or a different letter case. The same tree then gets a second
  tag. That direction is safe: a tag is never shared across trees.
- I-OC1c: the caller's PATH (`sha256sum`, `dirname`) and `BASH_ENV` still run code in
  image_tag.sh. The caller is trusted to run code, so this is not a boundary.
