# platform-sbom U2 (PSC-20): security audit of the integration

2026-10-23, security. Diff: `git diff 23e3c9b` plus untracked
`docker-compose.sbom.yml`, `tests/test_sbom_generator.py`, `u2/`.
Raw probes: `u2/security-u2-probes.txt`. No syft container was run.

**Verdict: PASS.** No critical, high or medium findings. 2 low and 3 info,
none blocking.

## 1. `docker-compose.sbom.yml` hardening: holds

- The resolved model (`config sbom`, P3) has network_mode none, read_only,
  tmpfs `/tmp` only, cap_drop ALL, no-new-privileges, no socket, no
  `DOCKER_*`, no env_file, `/in` bound read-only, `/out` the only writable
  bind, and environment of literals only (TMPDIR plus the 8 keys). Nothing
  from the repo-root `.env` reaches it: that file is present on this host
  and does not appear in the model.
- Remote lookups in the v1.54.1 config dump (`syft-v1.54.1-config.txt`):
  the update check, java use-network and resolve-transitive, golang remote
  licences and use-packages-lib, javascript and python remote licences,
  and the vcpkg git clone. All 8 are set to `false`. `enrich: []` is the
  default and an explicit key wins over it. URL keys (maven, npm, pypi,
  goproxy) are used only once a lookup is on. Registry and auth keys do not
  apply to `docker-archive:`. `attest` (Sigstore) is a subcommand that is
  never invoked. The keys are complete, and `network_mode: none` is the
  real control behind them.
- Reach and write surface. The image (inspect, no run) has WorkingDir
  `/tmp`, no User and Env of PATH only. syft searches for config in cwd
  `/tmp` (container-private tmpfs) and in HOME/XDG under the read-only
  pinned root, so a host-supplied config cannot load. Its cache dir
  (`~/.cache/syft`) is on the read-only root, and the cache only holds
  downloads, of which there are none. The only writes go to `/tmp` and
  `/out`.

## 2. `bundle.sh` refusal read: injection-safe, never pulls, never loads `.env`

- The output of `config --images sbom` is a value, never code. It must be
  one line and match `ref_re` (the C locale is exported) plus `@sha256:`.
  It is used only quoted, in `[[ ]]`, in `docker image inspect "$sbom_ref"`
  and in die messages (`%q` for the pattern failure). In the harness S1-S9,
  every crafted output (`;`, `$(...)`, backticks, two lines, a tag only,
  empty, an ESC sequence, compose failing) either refuses or, for a valid
  pinned ref, continues. Nothing executes. Flag-shaped refs that pass
  `ref_re` make the real `docker image inspect` exit non-zero, which is a
  refusal (F1).
- `.env.example` values with `$(...)` or backticks are printed as literals
  (E3). With `--env-file`, Compose 5.1.4 does not load `.env` (E1 vs E2). A
  missing env file is an error, so the read fails closed (E4).
  `bundle.sh` cds to the repo root and unsets COMPOSE_FILE and
  COMPOSE_PROFILES first, and `-f` wins over both.
- No pull: the read is `config`, and the harness logs only `compose config`
  and `image inspect`. One exception is a file-content one, see L-1.

## 3. `offline_check.sh` pull: no new egress; the CLAUDE.md sentence holds

- The host Docker daemon makes the pull, in the `full` host half
  (verify.sh -> offline_check.sh host half, after the disk and Compose
  checks), from docker.io. The same run already pulls from docker.io,
  including anchore/grype (`green-verify-full.txt` l.1677-1678). There is
  no new host and no new network for any gate service, and the offline
  client still pulled nothing (l.2206). The CLAUDE.md wording "In `full`
  the host half also builds and pulls images" still holds unchanged. This
  confirms the architect.
- It fails closed: `|| die` with no loop, the EXIT trap tears down, and
  `test_offline_check_stops_when_sbom_pull_fails` passes. The digest is
  verified by the daemon's content addressing.

## 4. Pin consistency: agrees

The pin `anchore/syft:v1.54.1@sha256:3eb5379b...49b1aa` matches in four
places:
- `docker-compose.sbom.yml`, which is the only place outside docs/ and
  tests/ that holds it.
- `generator-provenance.md`: the index digest appears 3 times, with v1.54.1
  and the amd64/arm64 digests.
- design-notes N1.
- The local RepoDigests/Id.

The PSC-8 form test `test_bundle_has_no_sbom_generator` passes in green
full, and the real offline client's image names equal the bundle's.

## 5. Evidence sweep of `u2/`: clean

No profile paths, SIDs, tokens, keys or connection strings. The IPs are
Docker bridge addresses from the smoke stage. The config dump holds only
empty `password: ''` template fields. The model keys do not appear.
Secret-pattern grep over the full diff: no hits.

## Findings

- **L-1 low (non-blocking; test gap).** The hardening checks read raw YAML.
  Compose 5.1.4 `config` fetches a top-level remote `include` (C1 made an
  HTTPS request), and a service `extends` merges `network_mode: host` and
  extra binds into `sbom` (C2) without either check seeing it. A file edit
  could therefore undo "bundle.sh makes no network call" or the hardening
  and stay green. Fix: in `hardening_problems`/`pin_problems`, allow only
  `services` (and `x-*`) at top level and forbid `extends` on `sbom`. The
  same gap exists already in `docker-compose.scan.yml`. Fold it in or note
  it.
- **L-2 low (carry to U3; nothing runs at U2).** `sbom` sets no `user:`
  and the image has no User, so syft runs as uid 0. At U3 it writes to the
  host bind `/out`. Without DAC_OVERRIDE that may be refused, and if it
  succeeds it leaves root-owned files that `bundle.sh` cannot remove. Set
  `user:` to the caller's uid:gid as N4's `sources-fetch` does
  (`${KE_SOURCES_USER:?}`), and confirm at U3 that `/out/tmp` holds only
  layer blobs.
- I-1 info: `ref_re` lets a ref start with `-`. It still fails closed (F1).
  This is the same pre-existing pattern as line 140. Optional: require
  `[a-z0-9]` as the first character.
- I-2 info: if U3 needs the HOME/XDG fallback that the test allows under
  `/out/tmp`, syft's config search path moves into the host-writable work
  dir. Prefer `/tmp` (tmpfs), or keep the work dir fresh and 0700.
- I-3 info: "no retry" is true of the script. The daemon's own per-layer
  download attempts apply to every pull, as before.
