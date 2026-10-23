# platform-sbom: design notes for ADR-KE-016 (architect, 2026-10-22)

Detail behind `docs/architecture.md` ADR-KE-016. The ADR wins where the two
differ. Nothing here was fetched from the network; facts about upstream
tools and hosts marked *confirm at GREEN* are design-time expectations that
the developer checks against the pinned tool or the real host, and records.
Amended 2026-10-22 for the human's Q64 ruling and the orchestrator's Q65
and Q66 (N0 added; the `srpm` kind, `vault.centos.org`, the
vendored-library injection and table, and the two-way drift check are
gone; N12 records why).

## N0. U0: psycopg built on Debian's libpq (Q64, Q65, Q66, PSC-25)

Not checked online: this role has no network. The uv features used
(dependency groups, `--no-binary-package`, `[tool.uv]
no-build-isolation-package`, `[[tool.uv.dependency-metadata]]`, exact
`uv sync`, inexact `uv run`, `uv export`) and the psycopg facts (`[c]`
extra, sdist-only `psycopg-c`, `pg_config` needed,
`psycopg.pq.__impl__`/`version()`/`__build_version__`) come from their
documentation as known at design time. *Confirm at GREEN* each one
against uv 0.11.21 (`uv sync --help`) and the psycopg 3.3.6 sdist, and
record the result in `docs/evidence/platform-sbom/u0-psycopg-c.md`.

### How the lock, hosts and images resolve psycopg (Q65)

Constraint: the shipped `ke-app` has no psycopg-binary and uses psycopg-c
built on Debian's libpq. Hard limits: no CLAUDE.md/AGENTS.md change, no C
toolchain on dev hosts, `--locked` everywhere, and `uv run ... log_event`
keeps working on Windows.

`pyproject.toml`:
- `dependencies`: `psycopg>=3.3.6` with no extra. This is pure Python and
  loads a `pq` implementation when imported.
- `[dependency-groups]`:
  - `pq-c = ["psycopg[c]>=3.3.6"]`. psycopg's `c` extra pins
    `psycopg-c == <its own version>`, so the two stay in step.
  - `pq-build = [<psycopg-c 3.3.6's [build-system] requires, each ==>]`,
    read from the sdist's `pyproject.toml` at GREEN (expected: setuptools,
    plus wheel or Cython if listed). Bumping psycopg means reading them
    again.
- `[tool.uv] no-build-isolation-package = ["psycopg-c"]`. uv then builds
  the sdist in the target venv, so the build backend comes from
  `pq-build`, which `uv.lock` hash-locks. *Why not isolation:* `uv.lock`
  does not lock build dependencies, so an isolated build pulls unhashed
  code from PyPI, and `build-constraint-dependencies` pins versions only.
- If `uv lock` would have to build psycopg-c to read its metadata (it is
  sdist-only), declare it in `[[tool.uv.dependency-metadata]]` (name,
  version, `requires-dist`, `requires-python`, copied from the sdist's
  PKG-INFO). Then resolving never compiles. `uv lock` runs in the gates
  image anyway (CLAUDE.md, Generated artifacts).

Who gets what:
- **Dev hosts (Windows, macOS, a Linux box).** The default groups stay
  `["dev"]`, so `uv run --locked ...` (log_event) installs pure psycopg,
  never psycopg-c, and compiles nothing. Nothing on a host imports
  psycopg; only `engine/readiness.py` does, and it runs in `ke-app` and
  `ke-gates`. A host import fails with psycopg's "no pq wrapper
  available", which is accepted: verification runs in the gates.
- **`ke-app` builder:** `--no-dev --group pq-c` (below).
- **`ke-gates`:** a compiler is acceptable there (Q65), because the image
  is not shipped. It builds psycopg-c the same way and keeps both groups,
  so the tests import the same implementation that ships.
- **psycopg-binary:** not in the lock at all. No marker and no extra keeps
  it, so the lock test can also check that it is absent.
- *Rejected:* `psycopg[c]; sys_platform == 'linux'` plus
  `[binary]` elsewhere: every Linux host's `uv run` would compile, and
  those hosts need pg_config, which breaks the hard limit. Conflicting
  extras (`c` vs `binary` with `[tool.uv] conflicts`): more machinery,
  and the hosts would still have to choose one.

`uv.lock` after `uv lock`:
- no `psycopg-binary`;
- `psycopg-c` 3.3.6 with `sdist = { url, hash = "sha256:..." }` and no
  `wheels` (PyPI publishes none);
- the `pq-build` packages with their wheel hashes.

**Today `uv.lock` has no psycopg-c entry** (psycopg-binary 3.3.6 has
wheels only and no sdist), so the `pypi:psycopg-c` source needed the PyPI
JSON API. After U0 both `pypi` entries come from `uv.lock` with no network,
and `pypi.org` leaves `hosts`.

### `docker/app.Dockerfile`

- `ARG LIBPQ_VERSION=<Debian version, e.g. 15.N-0+deb12uM>` once, before
  the first `FROM`, then `ARG LIBPQ_VERSION` again in the builder and in
  the last stage. The developer reads the current bookworm version (main
  or `-security`) from the base's apt at GREEN.
- Builder: `apt-get update && apt-get install -y --no-install-recommends
  gcc libc6-dev libpq-dev=${LIBPQ_VERSION} && rm -rf /var/lib/apt/lists/*`.
  `libpq-dev` brings `pg_config`, and `libpq5` at the same version. No
  `python3-dev`: that package is Debian's 3.11, and the base's CPython 3.12
  under `/usr/local` ships its own headers.
- The syncs, all `--locked`, with `UV_PROJECT_ENVIRONMENT=/opt/venv` as
  today:
  1. `uv sync --locked --no-dev --group pq-build --no-install-project`
  2. `uv sync --locked --no-dev --group pq-build --group pq-c
     --no-binary-package psycopg-c --no-install-project` (this compiles)
  3. after the code is copied: `uv sync --locked --no-dev --group pq-c
     --no-binary-package psycopg-c --no-editable && rm -f /opt/venv/.lock`.
     This sync is exact by default, so `pq-build` (setuptools and the rest)
     is removed and does not ship. `--no-binary-package` is a guard: if
     PyPI ever adds a psycopg-c wheel and a re-lock picks it up, the image
     still compiles.
- Last stage, one layer, before `useradd`:
  `apt-get update && apt-get install -y --no-install-recommends
  libpq5=${LIBPQ_VERSION} && rm -rf /var/lib/apt/lists/*`.
  - Nothing else is named. Apt adds the libpq5 dependencies the base
    lacks. Measured at GREEN (U0 security I-5, green-verify-full lines
    177-184): apt added only libpq5, libldap-2.5-0, libsasl2-2 and
    libsasl2-modules-db. krb5 (libgssapi-krb5-2, libkrb5-3, libk5crypto3,
    libkrb5support0) and libkeyutils1 were already in the pinned base.
  - The slim base keeps `/usr/share/doc/*/copyright`, so syft gets their
    licences.

### `docker/gates.Dockerfile`

- The same `ARG` and the builder's apt line (gcc, libc6-dev,
  `libpq-dev=${LIBPQ_VERSION}`).
- Syncs 1 and 2 (without `--no-dev`), then today's `uv sync --locked` with
  `--group pq-build --group pq-c --no-binary-package psycopg-c` added.
- `uv run --locked` in `test.sh` is an inexact sync, so psycopg-c stays
  installed. If it does not, the gates psycopg test (below) catches it.
  `UV_OFFLINE=1` is unchanged.

### Drift and pin signals

- **Debian publishes a postgresql-15 update.** The old version leaves
  deb.debian.org, apt fails with `Version '<v>' for 'libpq5' was not
  found`, and `build.sh` goes red by name.
  - Fix: bump `LIBPQ_VERSION` (reviewed) and re-lock the sources. Never
    unpin.
  - A local build with a cached layer sees this later than CI.
- **The base digest moves.** libpq5's dependency versions may change. syft
  records them, and `sbom_check.py index` fails on a GPL-family deb source
  version with no lock entry, naming it (N5).
- **The base leaves bookworm.** `test_libpq_pin_matches_bookworm_base`
  fails: it checks `+deb12u` against `-bookworm` in both `FROM` lines.

### Runtime proof: where and how

- Why not a `full` test: the gates have no Docker socket (ADR-KE-009), so
  no `full` test can run `ke-app`.
- The smoke stage's host half already runs commands in the live `api`
  (`compose exec -T api python -m engine.readiness`). It gains a step,
  `== smoke: psycopg ==`:
  1. `compose exec -T api python -I -c '<print pq.__impl__, pq.version(),
     pq.__build_version__ and the psycopg_c extension path>'`;
  2. `compose exec -T api ldd <that path>`.
- It fails, naming the value, unless all of these hold:
  - the impl is `c`;
  - no `psycopg_binary*` entry (package, `.libs`, `-*.dist-info`) is under
    `/opt/venv`, and `find_spec("psycopg_binary")` is None;
  - `version()` == `__build_version__` == the *installed* libpq5 version
    from `dpkg-query -W` in `api` (`15.N-...` -> `150000+N`), not the
    Dockerfile pin: the offline client has no Dockerfile. The version is
    matched by a strict regex (`^([0-9]+)\.([0-9]+)-[0-9A-Za-z.+~]+$`)
    before any arithmetic, and anything else fails closed by name
    (security M-1); the two psycopg numbers are string-compared against the
    digit-only expected value (no `^[0-9]+$` regex exists);
  - ldd's `libpq.so.5 =>` path is under `/usr/lib/<x86_64|aarch64>-linux-gnu/`
    or the merged-usr alias `/lib/<triplet>/` (bookworm's ldd prints the
    alias); smoke resolves it with `realpath` in `api`, and
    `dpkg-query -S` must attribute the resolved file to `libpq5`.
- `ldd` is in libc-bin (Essential); *confirm at GREEN*.
- The step runs in `verify.sh full` and in the offline client's smoke, so
  the installed bundle is proven too.

### Effects

- **Scan (ADR-KE-013).** grype catalogues libpq5 and the new dependencies
  from the dpkg db. The 15 unseen files go, so PSC-7/L-13 closes once
  security confirms. Bookworm's krb5 and openldap CVEs are mostly unfixed
  or low, so `--only-fixed --fail-on high` is expected to stay green. A
  fixed High is fixed by bumping the pin (Q42), never by an ignore.
- **Size.** The wheel's ~10 MB of vendored libraries go; libpq5, its
  dependencies and the compiled extension come in. Expected to be within a
  few MB of today; record `docker image inspect` sizes before and after at
  GREEN. The compiler adds ~150 MB to the builder and to `ke-gates`, and
  neither ships. Build time grows by one compile, measured on CI (CPU
  time).
- **libpq version.** The vendored 18 becomes bookworm's 15, against the
  postgres 16 server. The protocol is compatible, and psycopg 3.3 supports
  libpq >= 10.
- **`gssencmode="disable"`** (PS-2.5) stays and its tests are unchanged:
  Debian's libpq is built with GSSAPI too.
- **Q66 (orchestrator, ruled).** Debian 12's libpq 15 is accepted, and
  apt.postgresql.org is not used. libpq 15 has no `require_auth` (16+), so
  security re-rates the `auth-audit` hardening follow-up at the U0 review.
  With krb5 now a scanned Debian package, the vendored-krb5 reason for that
  follow-up is gone.
- **Docs in U0's commit.**
  - `NOTICE.md`'s "psycopg" section names psycopg-c instead of
    psycopg-binary, with its locked sdist URL and SHA-256.
  - README's L-13 paragraph changes when security confirms the close
    (documenter).
  - The stubbed `psycopg-binary` fixtures in `tests/test_offline_bundle.py`
    are the tester's call.

### U0 RED tests

Fast unless stated; the tester names and places them.
- `test_ke_app_resolves_psycopg_c_not_binary`. Checks what the
  `ke-app` builder resolves, offline from the lock (in the gates:
  `uv export --locked --no-dev --group pq-c --no-hashes`, or by walking
  `uv.lock` from the project with `--no-dev` and `pq-c`). The set has
  `psycopg-c` at psycopg's version and no `psycopg-binary`. In `uv.lock`,
  `psycopg-c` has an `sdist` with a `sha256:` hash and no wheels, and
  `psycopg-binary` is absent. RED: psycopg-binary is in the builder's set.
- `test_pyproject_puts_psycopg_c_in_image_groups_only`. `dependencies`
  has `psycopg` with no extra; `pq-c` and `pq-build` exist;
  `no-build-isolation-package` is `["psycopg-c"]`; the default groups
  exclude both. RED: `psycopg[binary]`.
- `test_app_dockerfile_builds_psycopg_c_on_pinned_libpq`:
  - one global `ARG LIBPQ_VERSION=` matching
    `^\d+\.\d+-\d+\+deb12u\d+$`;
  - the builder installs `libpq-dev=${LIBPQ_VERSION}` and a compiler;
  - every `uv sync` has `--locked`;
  - every sync naming `pq-c` has `--no-binary-package psycopg-c`;
  - the final sync names `pq-c` and not `pq-build`.
- `test_runtime_stage_has_no_compiler`. The last stage has one
  `apt-get install`, of exactly `libpq5=${LIBPQ_VERSION}` with
  `--no-install-recommends`, and `rm -rf /var/lib/apt/lists/*` in the
  same `RUN`. No compiler and no `-dev` package.
- `test_libpq_pin_matches_bookworm_base`. The pin has `+deb12u`, and both
  base `FROM` lines are `-bookworm` with the same digest.
  `gates.Dockerfile` uses the same pin.
- `test_gates_psycopg_is_c_impl_on_debian_libpq`. Runs in `ke-gates` with
  a real import: `psycopg.pq.__impl__ == "c"`; `version()` ==
  `__build_version__` == the pin's number; `find_spec("psycopg_binary")`
  is None. RED: the impl is `binary`.
- `test_smoke_checks_psycopg_c_impl_in_api` (static, with the fake
  docker). Smoke runs the check in `api` and fails on `binary`. The other
  failure cases live in four new `SmokePsycopgTest` methods:
  - `test_smoke_fails_when_psycopg_binary_is_beside_psycopg_c`: a
    co-installed `psycopg_binary*`;
  - `test_smoke_checks_dpkg_libpq5_owns_the_loaded_libpq`: a version
    mismatch with dpkg's libpq5, or a libpq path dpkg does not attribute
    to libpq5;
  - `test_smoke_never_evaluates_the_libpq5_version`: a malformed dpkg
    version (no host arithmetic, M-1);
  - `test_smoke_fails_closed_on_dpkg_query_errors`: dpkg-query errors.
  The real run is the `full` smoke stage.
- `test_notice_psycopg_section_matches_lock`. Every psycopg package in
  the builder's locked set is named in `NOTICE.md` with its sdist URL and
  hash. RED: psycopg-c is not named.


## N1. The SBOM generator run (`sbom` service)

`docker-compose.sbom.yml`, standalone, no profiles (as `docker-compose.scan.yml`,
ADR-KE-013 am. 1 D1). Never in the stack's `COMPOSE_FILE`, never copied by
`bundle.sh`. Two services: `sbom` (this note) and `sources-fetch` (N4).

| | `sbom` |
|---|---|
| Image | `anchore/syft:v<X.Y.Z>@sha256:<64 hex>` (multi-arch index digest) |
| Command | `docker-archive:/in/<name>.tar --scope all-layers -o spdx-json=/out/raw.spdx.json` (the developer may pass the tar name as an argument of `compose run`) |
| Network | `network_mode: none` |
| Mounts | `${KE_SBOM_IN:?}` at `/in` **read-only** (the bundle's `images/`); `${KE_SBOM_OUT:?}` at `/out` read-write, a per-image work dir **outside** `--out`; nothing else, no checkout |
| Root FS | `read_only: true`; tmpfs `/tmp` (small: syft's unpack goes to `/out/tmp`, see below) |
| Hardening | `cap_drop: [ALL]`, `no-new-privileges:true`; no socket, no `DOCKER_HOST`, no `ports`, not privileged |
| Environment (literals) | `SYFT_CHECK_FOR_APP_UPDATE=false`, `TMPDIR=/out/tmp`, `SYFT_JAVA_USE_NETWORK=false`, `SYFT_GOLANG_SEARCH_REMOTE_LICENSES=false`, `SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES=false` |

- `bundle.sh` runs it as `docker compose -p <project>-sbom -f docker-compose.sbom.yml run --rm --pull never sbom ...`,
  so the container's compose project label is `<project>-sbom` (PSC-20; as
  the notices run's `<project>-notices`). Its EXIT trap runs
  `docker compose -p <project>-sbom -f docker-compose.sbom.yml down` and
  removes the work dir.
- *Why `/out/tmp`:* syft unpacks every layer of the tar into its temp dir.
  phoenix and neo4j unpack to an estimated 1-2 GB, which on a `/tmp` tmpfs
  is memory on a runner that also has to run the stack later. On disk the
  peak is the bundle plus one unpacked image, below the dind-store peak the
  7 GiB floor already covers (R6). *Confirm at GREEN:* syft (Go
  `os.TempDir`) honours `TMPDIR`, and with `read_only` it writes nowhere but
  `/out` and `/tmp` (fallback as D1 of ADR-KE-013 am. 1: a literal `HOME` /
  `XDG_CACHE_HOME` under `/out/tmp`).
- *Why `--scope all-layers`:* the tar carries every layer, so a package
  deleted in an upper layer is still redistributed object code. The
  squashed view would hide it. Duplicates across layers collapse to one
  index component (N5) by source key.
- *Presence check (PSC-20):* before any write, `bundle.sh` reads the
  reference with `docker compose -f docker-compose.sbom.yml config --images`
  (single line, `ref_re` plus a mandatory `@sha256:`), and runs
  `docker image inspect <ref>`. Absent: `bundle: the SBOM generator image is not present (<ref>); run scripts/bundle_fetch.sh first; this script never pulls`, exit 1, `--out` untouched.

## N2. Generator provenance (PSC-1 form; security records it)

`docs/evidence/platform-sbom/generator-provenance.md`, before the pin is
committed. The ADR-KE-013 am. 1 D2 procedure, unchanged in form:
1. release tag, date, index digest and the linux/amd64 and linux/arm64
   digests, from `docker buildx imagetools inspect` (no pull, no run);
2. `cosign verify` of the index digest with the certificate identity of
   anchore/syft's release workflow for that tag and the GitHub Actions OIDC
   issuer;
3. if the image carries no verifiable signature: verify the cosign
   signature of the release's `checksums.txt`; check the per-platform
   release archives against it; `docker create` + `docker cp /syft` out of
   the image for each platform (never `run`); each copied binary's SHA-256
   must equal the binary inside the matching verified archive;
4. neither 2 nor 3: the pin is not committed; back to the orchestrator.

## N3. `scripts/sbom_check.py`: the one checker

Standard library only, Python 3.12, always run with `python -I`, never
imported by `engine/`, never shipped in an image (precedent:
`scripts/smoke_otlp.py`). Every subcommand reads read-only mounts and
writes only stdout; the calling shell writes files. Unit tests import it
by path (`importlib.util.spec_from_file_location`). Build-time tool, not an
agent step: no spans (as `engine.notices`).

Where it runs:
- at bundle time, inside the `ke-app` image being bundled, as the notices
  run: `docker run --rm --network none --read-only --cap-drop ALL
  --security-opt no-new-privileges --pull never --label
  com.docker.compose.project=<project>-sbomcheck --entrypoint python -v
  <checkout>/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro ...` (the
  `ke-app` venv is not used; `-I` keeps it out). It runs there because the
  runtime-package check must list the real installed distributions;
- at e2e time, inside the offline client (`ke-gates` image, system
  `python3`), mounted read-only next to `offline_check.sh`;
- in `fast`, imported by the unit tests.

Subcommands (names are the developer's to adjust):
- `finish <name> <ref> <arch> <git_sha> <bundle_uuid>`: reads
  `/work/raw.spdx.json` and `/images/<name>.tar` (only the `manifest.json`
  member, with `tarfile`, no extraction) and prints the final SPDX
  document (N6). For `ke-app` it also runs the runtime-package check
  (N7).
- `index <arch> <set>`: reads every final SBOM, `docker/source-policy.json`,
  `docker/sources.lock.json` and the fetched directory, all read-only;
  classifies (N8), maps each GPL-family package to a lock entry, checks
  coverage and exemptions, re-hashes every fetched file it will ship, and
  prints `sources/index.json` (N9). Exit 1 on any gap, naming image,
  package and the fix.
- `notices`: prints the generated "Source code" section of
  `THIRD_PARTY_NOTICES.md` from the index (N10).
- `plan <arch> <set>`: prints the fetch plan (url, sha256, upstream check)
  for `bundle_fetch.sh` (N4). Sample selection lives only here.
- `verify <bundle_dir> <installed_dir>`: the PSC-19 e2e checks (N11).

## N4. The fetch step: `scripts/bundle_fetch.sh` and `sources-fetch`

Host script, verify-time and build-host, Linux and Git Bash (not bundled,
not held to bash 3.2). The bundle's only network step besides `build.sh`.

```
scripts/bundle_fetch.sh --set full|sample --out <dir>
```
1. `== sources: pull ==` `docker compose -f docker-compose.sbom.yml pull sbom`
   (the generator; PSC-20 "the step that pulls it"). One call; failure:
   `bundle_fetch: FAIL (stage pull: pulling the SBOM generator <ref> failed; no retry)`.
2. `== sources: fetch ==` `compose run --rm --pull never sources-fetch`.
   Its client script first runs `python3 -I sbom_check.py plan` (reads
   only the lock and the policy), then fetches the plan. The service:
   - image `ke-gates:${KE_IMAGE_TAG:-local}`, `pull_policy: never` (built
     by `build.sh`, as `offline-client`); curl, jq, sha256sum, sha512sum,
     python3 are in it;
   - the project's `default` bridge, the only route out in the file;
   - mounts: `./docker/sources.lock.json`, `./docker/source-policy.json`,
     `./scripts/sources_fetch_client.sh`, `./scripts/sbom_check.py`, all
     read-only; `${KE_SOURCES_OUT:?}` read-write (the only writable mount);
   - `read_only: true`, tmpfs `/tmp`, `cap_drop: [ALL]`,
     `no-new-privileges`, `user: ${KE_SOURCES_USER:?}` (the caller's
     uid:gid, set by the script, so the files are the caller's);
   - environment: literals only, no pass-through; no `KE_*` key, no model
     key, no token (PSC-23, PSC-6).
3. `== sources: done ==` with seconds per stage (CI timestamps are the
   measurement, PSC-16).
Own project `ke-sources-<random>`, `teardown.sh --volumes` on every exit
path as `scan.sh` (D4), and on failure `rm -rf` of `--out`.

The client loop (`sources_fetch_client.sh`), per planned file, once:
```
curl -q --proto '=https' --proto-redir '=https' --tlsv1.2 -sS --fail \
  --max-time <N> -o <tmp> -w '%{http_code} %{redirect_url}' <url>
```
- `-q` first: no `.curlrc`. No `-L`: a 3xx is followed by the script, at
  most 5 hops, and every hop's host must be in `hosts` (exact match, after
  lower-casing; no wildcard) and its scheme `https`; otherwise fail.
- After the last hop: `sha256sum` of the file must equal the lock's
  `sha256` before anything else reads it (one pipeline ending in
  `sha256sum -c -`, the D7 rules); then it is renamed to `<out>/<sha256>`.
  It is never unpacked, built or run.
- Q61 (ruled): any non-2xx, timeout, hop refusal or mismatch ends the run
  at once: `bundle_fetch: FAIL (stage fetch: <host>: <file name>: <why>; no retry)`.
  The partial `--out` is removed; `bundle.sh` is never reached.

Hosts (`docker/source-policy.json` `hosts`, the SFU egress list; *confirm
at GREEN* the redirect targets from real fetches):

| Host | Kind |
|---|---|
| `snapshot.debian.org` | `deb` (`.dsc`, `.orig*`, `.debian.tar.*`, `.diff.gz`) |
| `gitlab.alpinelinux.org` | `apk` (APKBUILD and local patches, raw at the aports commit) |
| `distfiles.alpinelinux.org` | `apk` (upstream tarballs mirrored by Alpine) |
| `github.com`, `codeload.github.com` | `neo4j` (tag tarball), `temurin` (release asset, first hop) |
| `objects.githubusercontent.com`, `release-assets.githubusercontent.com` | `temurin` (release asset redirect targets) |
| `files.pythonhosted.org` | `pypi` (sdist URLs from `uv.lock`; `pypi.org`'s API is no longer needed, N0) |

The generator pull uses the registry hosts `build.sh` already needs.

## N5. The lock: `docker/sources.lock.json` (generated, reviewed)

Why a lock: with the reduced verify set (Q63, ruled), every run must still
build the full index (every GPL-family package mapped to URL and upstream
checksum). Resolving that at bundle time would fetch every `.dsc` and every
API page on every run (hundreds of calls, most to snapshot.debian.org). A
committed lock makes the index offline, makes every checksum reviewable
once (Q48), and keeps the verify run's network exposure to the sample.

Shape (one JSON object; keys sorted; written by the tool, never by hand
except the `manual` entries below):
```
{"format": 1,
 "components": {
   "deb:openssl@3.0.22-1~deb12u1": {
     "kind": "deb", "arches": ["amd64", "arm64"], "origin": "generated",
     "files": [
       {"name": "openssl_3.0.22-1~deb12u1.dsc",
        "url": "https://snapshot.debian.org/file/<sha1>",
        "sha256": "<64 hex>", "size": 1234,
        "upstream": {"alg": "sha1", "value": "<40 hex>", "from": "snapshot.debian.org mr/package fileinfo"}},
       {"name": "openssl_3.0.22.orig.tar.gz", "url": "...", "sha256": "...", "size": ...,
        "upstream": {"alg": "sha256", "value": "...", "from": "openssl_3.0.22-1~deb12u1.dsc Checksums-Sha256"}}]}}}
```
- Component keys: `deb:<source>@<source version>`, `apk:<origin>@<version>`
  (+ `"commit"` and `"branch"` fields), `neo4j:neo4j@<tag>`,
  `temurin:<release tag>`, `pypi:<name>@<version>`.
- Per kind, where the upstream checksum comes from (PSC-15, Q48 form):
  - `deb`: snapshot.debian.org only (stable URLs; deb.debian.org drops
    superseded versions, and the images are pinned so their versions age).
    The `.dsc` by the SHA-1 snapshot publishes for it (its URL is
    content-addressed by that SHA-1); every other file by the `.dsc`'s
    `Checksums-Sha256`. Lock time fetches only the `.dsc` files.
  - `apk`: the installed db's origin (`o:`) and aports commit (`c:`) come
    from the lock tool's syft-json run. Files are the `sha512sums=` lines
    of the APKBUILD at that commit (read as text; the APKBUILD is never
    sourced or run). A name that exists in the aports directory at that
    commit is fetched raw from gitlab at the commit; any other from
    distfiles.alpinelinux.org for the image's Alpine branch. Each checked
    by the APKBUILD SHA-512; the APKBUILD itself by its git blob id from
    gitlab's tree listing at the commit, plus its recorded SHA-256.
  - `neo4j`: `https://github.com/neo4j/neo4j/archive/refs/tags/<tag>.tar.gz`.
    No published checksum: trust on first use under Q48 (the developer
    records the SHA-256) plus a second, independent fetch by security on a
    different host or network, recorded in
    `docs/evidence/platform-sbom/sources-provenance.md`.
  - `temurin`: the exact build from the neo4j image's
    `/opt/java/openjdk/release` (`IMPLEMENTOR_VERSION`/`JAVA_RUNTIME_VERSION`,
    read by the lock tool from the tar, not by running the image); the
    Adoptium release's `*-jdk-sources_*.tar.gz` asset, checked against the
    release's published `.sha256.txt`.
  - `pypi`: `psycopg` and `psycopg-c` from `uv.lock` (`sdist` URL and
    hash, no network; N0).
- `origin: manual` entries (the singletons, if the developer prefers to
  write them by hand with their provenance) are kept as they are by the
  tool; `generated` entries are rewritten.
- `arches`: the tool merges; it never drops another arch's entries
  unless `--prune <arch>` is given. arm64 entries are added from the
  recorded arm64 run (PSC-21).
- Regenerate: `scripts/sources_lock.sh` (maintainer tool, network; runs
  `build.sh` images through the `sbom` service with `-o syft-json` to a temp
  dir, then the `sources-fetch` image in a resolve mode). Drift check:
  `bundle.sh` (via `sbom_check.py index`) fails when an SBOM's GPL-family
  package has no lock entry, naming it and the tool. A CLAUDE.md
  "Generated artifacts" row is needed (the human's file; N13).
- Security reviews every lock diff (as PSC-5 for scan ignores).

Sample (Q63, ruled): for each `kind` present in the lock for this arch,
the entry with the smallest total `size` (ties by key). `neo4j` and
`temurin` have one entry each, so both are always fetched (estimate: the
sample is a few hundred MB, dominated by those two).

## N6. The final SPDX document

`finish` keeps syft's packages, files and relationships and changes only:
- `name`: the `bundle.json` `ref`;
- `documentNamespace`:
  `https://spdx.knowledge-engine.invalid/<git_sha>/<arch>/<name>/<bundle_uuid>`,
  `bundle_uuid` generated once per `bundle.sh` run (so unique per bundle);
- `creationInfo.creators`: syft's `Tool: syft-<version>` kept, plus
  `Tool: knowledge-engine-bundle-<git_sha[:12]>`;
- three document `annotations` (`annotationType: OTHER`, annotator
  `Tool: knowledge-engine-bundle-...`): `ke:ref=<ref>`,
  `ke:image-config=sha256:<64 hex>` (the `Config` entry of the tar's
  `manifest.json`), `ke:arch=<amd64|arm64>`;

Then `finish` validates, and exits 1 naming the first failure:
`spdxVersion == "SPDX-2.3"`, `dataLicense == "CC0-1.0"`,
`SPDXID == "SPDXRef-DOCUMENT"`, non-empty `name`, `documentNamespace` an
absolute `https` URI containing the uuid, `creationInfo.created` an RFC 3339
UTC time, creators include a `Tool: syft-` entry; every package has a
unique `SPDXID` matching `^SPDXRef-[A-Za-z0-9.-]+$`, a `name` and a
`downloadLocation`; exactly one `DESCRIBES` from the document; every
relationship end resolves. This is the SPDX 2.3 required-field set PSC-13
tests, not the full JSON schema (rejected: a schema-validator dependency).

*Image identity (flagged to the orchestrator):* the value is the config
digest, not "the ID install reports". Install prints `Loaded image: <as>`
on a named load, and the loaded ID differs by store (R2, spike S1); the
config digest is the classic store's image ID and is the same on both. The
e2e (N11) re-reads it from the installed bundle's tar, which the manifest
proved byte-identical to the one install loaded.

## N7. `ke-app` runtime packages (PSC-13), and what replaced the injection

- Runtime packages: every distribution in `/opt/venv` (importlib.metadata,
  as `engine.notices`) except `knowledge-engine` must appear as a
  `pkg:pypi/<pep503 name>@<version>` package, and its version must equal
  `/app/uv.lock`'s (`tomllib`). "Installed" means what `uv sync --locked
  --no-dev --group pq-c` installed (N0), so the check uses that set
  without re-resolving markers. `psycopg-c` is in it; `pq-build` is not.
- There is no vendored-library injection and no drift check (Q64), because
  there is no `psycopg_binary.libs`. libpq5 and its dependencies are dpkg
  packages, which syft's dpkg cataloguer reads from `/var/lib/dpkg/status`.
  U4's `full` test asserts that `ke-app`'s SBOM lists
  `pkg:deb/debian/libpq5@<pin>` (upstream `postgresql-15`) and
  `pkg:pypi/psycopg-c@3.3.6`, and has no `psycopg-binary`.

## N8. The licence classifier (PSC-15 forms, PSC-22)

Input: a package's `licenseDeclared` (else `licenseConcluded`; else the
list syft gives, joined with AND).
- Unlicensed: absent, empty, `NONE` or `NOASSERTION`: reported per image
  with a count (PSC-22), printed by `bundle.sh` and kept in the index.
- Parse as an SPDX expression: ids, `(`, `)`, `AND`, `OR`, `WITH`
  (operators case-insensitive, so Debian's `with` parses).
  `needs(OR) = all(needs(child))`, `needs(AND) = any(needs(child))`,
  `needs(X WITH e) = gpl(X)`, `needs(id) = gpl(id)`. So
  `LGPL-2.1-or-later OR Apache-2.0` needs no source (the permissive
  alternative is elected); `MIT AND GPL-2.0-only` does.
- `gpl(id)`: strip a leading `LicenseRef-` (and syft's
  `LicenseRef-...` mangling), lower-case, then match
  `^(a|l)?gpl(-?v?\d+(\.\d+)*)?(\+|-only|-or-later)?(-with-[a-z0-9-]+-exception)?$`.
  Covers `GPL-2.0`, `GPL-2.0-only`, `GPL-2.0-or-later`, `GPL-2.0+`,
  `GPL-3.0-with-GCC-exception`, `LGPL-2.1`, `LGPL-3.0-only`, Debian's
  `GPL-2`, `GPL-2+`, `LGPL-2.1+`, `GPL`, `LGPL`, and also `AGPL-3.0*`,
  `GPL-1.0*`, `LGPL-2.0*` (wider than PSC-15's list: conservative,
  flagged). `GFDL*` does not match.
- Unparseable text: needs source if it contains `gpl` as a word
  (case-insensitive), and is listed as "unparsed" in the index for
  security.
- The `always` list (N10) overrides: matching packages need source
  whatever `needs()` says.
Pure functions, no I/O: the first fast tests.

## N9. `sources/index.json` and the stored names (PSC-15, PSC-24)

Stored names are content-addressed: `app/sources/files/<sha256>`
(64 lowercase hex; passes the manifest rule, never case-clashes, never a
Windows reserved name, and dedups a file two components share).
```
{"format": 1, "set": "full"|"sample", "arch": "amd64", "git_sha": "...",
 "components": [
   {"key": "deb:openssl@3.0.22-1~deb12u1", "kind": "deb",
    "status": "shipped"|"not-shipped"|"exempt", "reason": "(exempt only)",
    "packages": [{"image": "ke-app", "spdxid": "...", "purl": "...", "licence": "..."}],
    "files": [{"name": "<upstream name>", "url": "...", "sha256": "...",
               "upstream": {...}, "path": "sources/files/<sha256>"}]}],
 "unlicensed": {"ke-app": {"count": 0, "packages": []}, ...},
 "unparsed": [...]}
```
- `path` is relative to the installed root (`app/` in the bundle).
- `not-shipped` exists only when `set` is `sample`; a `full` bundle with
  any `not-shipped` component fails. Mapping SBOM package to key: deb by
  the purl's `upstream` qualifier (source name, and version when it
  differs) else the package name/version; apk by `upstream` (origin);
  `pkg:maven/org.neo4j/*` and `com.neo4j/*` at the image's Neo4j version
  to the `neo4j` entry; the JVM package to `temurin`; pypi by name.
  *Confirm at GREEN* each mapping against the real SBOMs (U3); an
  unmappable GPL-family package fails with its purl, never passes.
- Manifest size: each source line is 64 + 2 + 87 + 1 = 154 bytes, so the
  1 MiB cap allows about 6,800 files. Estimate for the full set: under
  1,000 (PSC-16 measures).

## N10. Committed files and their rules

- `docker/source-policy.json` (hand-written, security reviews every diff):
  ```
  {"hosts": ["snapshot.debian.org", ...],
   "always": [{"image": "valkey", "match": "pkg:apk/alpine/busybox", "why": "PSC-22"}, ...],
   "exempt": [{"image": "postgres", "package": "pkg:deb/debian/foo@1.2-3",
               "reason": "...", "reviewed": "security 2026-10-30"}]}
  ```
  `always` (PSC-22): busybox, apk-tools, ssl_client (valkey, ke-gateway);
  the Temurin JVM (neo4j); Neo4j Community (neo4j); psycopg and
  psycopg-c (ke-app); glibc (`upstream=glibc`, every Debian image). libpq5
  and its dependencies are ordinary dpkg packages under the classifier
  (libkeyutils1 is LGPL by its copyright file). An `always` entry with no
  matching package in its image fails ("expected component not
  catalogued"): the generator cannot hide one by missing it. An exemption
  names a versioned purl, so a version bump voids it and forces a new
  review. Schema test:
  exactly these three keys; `reason` non-blank; `reviewed` matches
  `^security \d{4}-\d{2}-\d{2}$`; purl has `@<version>`; no duplicates;
  hosts are lower-case DNS names with no wildcard; every lock URL host is
  in `hosts`.
- `NOTICE.md` (PSC-14) gains one section and one pointer:
  - "Base of `ke-app`":
    - the base reference, byte for byte from `docker/app.Dockerfile`;
    - CPython 3.12.x under `/usr/local` (PSF-2.0);
    - the base's Debian 12 packages, plus libpq5 at `LIBPQ_VERSION` and
      the dependencies apt adds (N0), with their licences in
      `/usr/share/doc/*/copyright` and the SBOM;
    - the base's pip `<version>` in the system site-packages (MIT),
      outside `uv.lock` and the generated table (the developer confirms
      the version in the image);
    - no uv.

    A static fast test pins the reference and the libpq pin to the
    Dockerfile. There is no image-side drift check.
  - A pointer: "`THIRD_PARTY_NOTICES.md` says, for each GPL-family
    component, whether its source is in `sources/` of this bundle." The
    committed file claims nothing per component, because the same file
    ships in sample and full bundles.
- Generated `THIRD_PARTY_NOTICES.md` gains "## Source code": one row per
  index component; `shipped` says "source in `sources/` (see
  `sources/index.json`)", anything else keeps the L-NT1 wording
  "Upstream source: <url>". A `sample` bundle's section starts with
  "Verification bundle: this source set is a sample and is not complete;
  do not distribute this bundle." Security reviews the wording.
- Under `app/` (so install publishes them; install publishes only `app/`):
  `app/sboms/<name>.spdx.json`, `app/sources/index.json`,
  `app/sources/files/*`, and copies of `NOTICE.md`,
  `THIRD_PARTY_NOTICES.md`, `LICENSE` and `licenses/` (the root copies
  stay where they are).

## N11. PSC-19 e2e (`ci/deployable-offline`)

In the client half of `offline_check.sh`, after `install.sh` and before
`launch.sh` (the stack is not needed, and memory is lower before launch):
`python3 -I /opt/ke/sbom_check.py verify /bundle "$target"`. Checks, reading
the installed copy for SBOMs, index, sources and notices, and `/bundle` only
for `bundle.json`, `MANIFEST.sha256` and the tars' `manifest.json`:
- every `app/sboms/*` path is listed in `MANIFEST.sha256` (as
  `app/sboms/...`) and the installed file's SHA-256 equals it; same for every
  `app/sources/**` file;
- one SBOM per `bundle.json` entry, by name; each passes the N6 field
  checks; its `ke:ref` equals the entry's `ref`; its `ke:image-config`
  equals the `Config` of `/bundle/images/<name>.tar`'s `manifest.json`;
  its `ke:arch` equals the header arch;
- the N8/N10 coverage rule holds on the installed SBOMs and index
  (re-computed, not trusted from the index);
- every `shipped` file's SHA-256 equals the index and the lock-recorded
  upstream value where it is SHA-256 (a SHA-1 or SHA-512 upstream value is
  re-computed with `hashlib`);
- the installed `THIRD_PARTY_NOTICES.md` has the "Source code" section and
  claims "in `sources/`" only for `shipped` components.
`docker-compose.offline.yml` gains the read-only mount of
`scripts/sbom_check.py` at `/opt/ke/sbom_check.py`.

Full operator set (Q63, ruled): the same checks, by
`scripts/offline_check.sh --sources full` run by hand on a host with the
memory (N14), saved under `docs/evidence/platform-sbom/` before any bundle
is handed over.

## N12. The vendored LGPL libraries (resolved by Q64)

`psycopg_binary.libs` held LGPL-2.1 libcrypt and libkeyutils from the
wheel's el7 build image, at a release the wheel does not record. The human
ruled Q64 (2026-10-22): build psycopg on Debian's libpq (N0). With that:
- the directory goes;
- the libraries are Debian packages of the `deb` kind;
- there is no `srpm` kind and no `vault.centos.org` host.

L-13 closes once security confirms it on the U0 image.

## N13. Wording that needs the human (PSC-23)

Proposed, landing in the unit that wires the fetch (U8). The orchestrator
takes the CLAUDE.md text to the human at U8 (ruling 6):
- CLAUDE.md, § Verification, the sentence "In `full` the host half also
  builds and pulls images, runs the smoke check's network-control probe on
  the stack's `edge` network, and runs `scan-db`, a one-shot that fetches
  the image scanner's vulnerability database." gains: "and
  `sources-fetch`, a one-shot that pulls nothing and fetches a sample of
  the bundle's third-party source code over HTTPS from the hosts listed in
  `docker/source-policy.json`." The rest is unchanged.
- CLAUDE.md "Generated artifacts" table: a row `docker/sources.lock.json` |
  the image digests, `uv.lock` | `scripts/sources_lock.sh` (network,
  maintainer) | `bundle.sh` coverage check fails on a package with no
  entry.
- `scripts/bundle.sh` header: "makes no network call" stays true and
  gains "the source set it ships is fetched beforehand by
  `scripts/bundle_fetch.sh`, the only bundle step with a route out".
- README: the operator build sequence becomes `build.sh`, then
  `bundle_fetch.sh --set full`, then `bundle.sh --sources`.

## N14. `/install` tmpfs (PSC-16)

Install stages the whole bundle in the target's parent and publishes `app/`
by rename (`mv`), so the tmpfs holds about the bundle's size during
install, and `app/` (now with `sources/`) for the rest of the client run,
while the stack runs. Today's `/install` tmpfs has no size, so an overrun
is host memory pressure, not a named failure.
- `docker-compose.offline.yml`: `/install:exec,mode=1777,size=${KE_OFFLINE_INSTALL_TMPFS:?set by scripts/offline_check.sh}`.
- `offline_check.sh` host half sets it to the bundle's byte size plus
  512 MiB, rounded up to MiB, after `bundle.sh`. On Linux it reads
  `MemAvailable` from `/proc/meminfo` and fails before `dind` starts when
  it is below that size plus 2 GiB (the stack's working set; PSC-16
  re-derives the 2 GiB from the measurement), naming both numbers. On
  Docker Desktop memory is not measurable from the host: it prints so, as
  for `df`.
- Install's own free-space check then refuses a bundle that does not fit,
  with its existing message, instead of the host running out.
- The client logs `df -Pk /install` after install and after smoke.
- Verify carries only the sample (Q63, ruled), so CI stays near today's
  memory use. The full-set recorded run sizes the same way; it needs a host
  with that memory, and the pre-check says so before anything starts.

## N15. TDD units (one commit each)

Every commit runs `scripts/verify.sh full` first (CLAUDE.md); the loop
column is the mode for the red/green loop.

| # | Unit | Loop | Windows (A34) |
|---|---|---|---|
| U0 | PSC-25 psycopg on Debian libpq (N0): `pyproject.toml` groups and `uv.lock`; `app.Dockerfile` builder and `libpq5` pin; `gates.Dockerfile`; the smoke `psycopg` step; NOTICE.md psycopg section | full | yes (Dockerfiles) |
| U1 | PSC-14 NOTICE.md "Base of `ke-app`" section and pointer, plus static tests | fast | no |
| U2 | PSC-20 `docker-compose.sbom.yml` `sbom`, pin and provenance, presence refusal in `bundle.sh` | full | yes (compose) |
| U3 | PSC-13 `bundle.sh` save -> syft -> `finish`; `sbom_check.py` N6 and runtime packages; Neo4j jars decided (ruling 5) | full | no |
| U4 | PSC-22: `ke-app` SBOM lists libpq5 (dpkg) and psycopg-c with no psycopg-binary; unlicensed report per image | full | no |
| U5 | PSC-15 classifier (N8), pure functions | fast | no |
| U6 | `docker/source-policy.json` and schema test; `always` rule | fast | no |
| U7 | lock: `docker/sources.lock.json`, `scripts/sources_lock.sh`, provenance evidence (security's second fetch) | full | no |
| U8 | PSC-23 `bundle_fetch.sh`, `sources-fetch` and client loop, wired into `offline_check.sh`; README and header wording; CLAUDE.md text to the human (ruling 6) | full | yes (compose) |
| U9 | PSC-15/24 `index`, content-addressed copy, notices section, no-partial tests, install tamper tests (sh and ps1) | full | only if `install.ps1` changes |
| U10 | PSC-19 e2e `verify`, `/install` size and memory pre-check | full | yes (compose) |
| U11 | PSC-16 two CI runs, floor re-derivation, Q62 trigger, PS-3.4; full operator recorded run (Q63) | full (CI) | no |
| U12 | PSC-21 recorded arm64 run (Q51 form) | full (arm64) | no |

Dropped by Q64: U4's vendored injection and two-way drift check, and U1's
vendored table. First tests for U1, U2 and U5 are unchanged:
- U1: `test_notice_has_ke_app_base_paragraph` (it now also names libpq5).
- U2: `test_sbom_generator_is_pinned`,
  `test_sbom_generator_runs_without_network_or_privileges` and
  `test_bundle_refuses_when_sbom_generator_absent` (`--out` stays empty).
- U5's classifier table:
  - `GPL-2+`, `MIT AND GPL-3.0-or-later` and
    `GPL-2.0-only WITH Classpath-exception-2.0` need source;
  - `LGPL-2.1-or-later OR Apache-2.0` does not;
  - `NOASSERTION` is unlicensed;
  - junk containing "GPL" needs source and is listed as unparsed.
