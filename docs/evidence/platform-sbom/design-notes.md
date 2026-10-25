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
- Last stage, one layer, before `useradd` (U1 round 2: this moves to stage
  `runtime`, which the last stage flattens; N10a):
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
| Image | `anchore/syft:v1.54.1@sha256:3eb5379ba7b409c3f4069b686110527af0c47df993fa5c10d13e7cf34f49b1aa` (multi-arch index digest; see *Pin (U2)* below) |
| Command | `docker-archive:/in/<name>.tar --scope all-layers -o spdx-json=/out/raw.spdx.json` (the developer may pass the tar name as an argument of `compose run`) |
| Network | `network_mode: none` |
| Mounts | `${KE_SBOM_IN:?}` at `/in` **read-only** (the bundle's `images/`); `${KE_SBOM_OUT:?}` at `/out` read-write, a per-image work dir **outside** `--out`; nothing else, no checkout |
| Root FS | `read_only: true`; tmpfs `/tmp:mode=1777` (U4 rework, review B1: *N1 amendment, U4 rework*; small: syft's unpack goes to `/out/tmp`, see below) |
| Hardening | `cap_drop: [ALL]`, `no-new-privileges:true`; no socket, no `DOCKER_HOST`, no `ports`, not privileged |
| User (U3) | `user: ${KE_SBOM_USER:?set by scripts/bundle.sh}`, the caller's numeric `id -u`:`id -g` (security L-2): syft reads the `0600` tars and writes the work dir as their owner, with no capability |
| Environment (literals) | `TMPDIR=/out/tmp` and, all `false`: `SYFT_CHECK_FOR_APP_UPDATE`, `SYFT_JAVA_USE_NETWORK`, `SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES`, `SYFT_GOLANG_SEARCH_REMOTE_LICENSES`, `SYFT_GOLANG_USE_PACKAGES_LIB`, `SYFT_JAVASCRIPT_SEARCH_REMOTE_LICENSES`, `SYFT_PYTHON_SEARCH_REMOTE_LICENSES`, `SYFT_CPP_VCPKG_ALLOW_GIT_CLONE` (U2, see *Env keys (U2)*) |

- *Run and `down` (U3; review N1; argv pinned by the tester,
  `u3/target-bundle.sh`).* `bundle.sh`, from the repo root, once per saved
  tar:
  ```
  MSYS_NO_PATHCONV=1 \
  KE_SBOM_IN="$(hostpath "$out/images")" KE_SBOM_OUT="$(hostpath "$work")" KE_SBOM_USER="$sbom_user" \
    docker compose -p "$sbom_project" --env-file .env.example -f docker-compose.sbom.yml \
    run --rm --pull never sbom "docker-archive:/in/$name.tar" --scope all-layers -o spdx-json=/out/raw.spdx.json
  ```
  `sbom_project` is `<project>-sbom`, so the container's compose project
  label is `<project>-sbom` (PSC-20; as the notices run's
  `<project>-notices`). `KE_SBOM_IN` is `<out>/images`; `$work` is
  `<sbom_work>/<name>`, mode 0700 with `tmp/` (the `TMPDIR`), under
  `<sbom_work>`, a `mktemp -d` beside `--out` and outside it (U4: *N1
  amendment, U4*; `hostpath` and `MSYS_NO_PATHCONV` are explained there); `sbom_user` is `$(id -u):$(id -g)`, refused
  unless it matches `^[0-9]+:[0-9]+$`. The EXIT trap runs, from the repo
  root and with the same three keys (`KE_SBOM_OUT=<sbom_work>`),
  `docker compose -p "$sbom_project" --env-file .env.example -f docker-compose.sbom.yml down`,
  warns on stderr if it fails, and removes `<sbom_work>`. Every call to
  this file therefore sets all three `KE_SBOM_*` keys and passes
  `--env-file .env.example`: the presence read below and `offline_check.sh`'s
  pull set `KE_SBOM_USER="$(id -u):$(id -g)"` next to the two dummies.
- *Why `/out/tmp`:* syft unpacks every layer of the tar into its temp dir.
  phoenix and neo4j unpack to an estimated 1-2 GB, which on a `/tmp` tmpfs
  is memory on a runner that also has to run the stack later. On disk the
  peak is the bundle plus one unpacked image, below the dind-store peak the
  7 GiB floor already covers (R6); true from U4, when the work dir moved
  beside `--out` (review N6; *N1 amendment, U4*). *Confirm at GREEN:* syft (Go
  `os.TempDir`) honours `TMPDIR`, and with `read_only` it writes nowhere but
  `/out` and `/tmp` (fallback as D1 of ADR-KE-013 am. 1: a literal `HOME` /
  `XDG_CACHE_HOME` at or under `/tmp`, the tmpfs, never under `/out`, so
  the work dir the checker reads holds only the unpack and `raw.spdx.json`;
  security I-2, amended U3). *Result (U3 GREEN):* syft tried
  `/.cache/syft`; U4 sets `XDG_CACHE_HOME: /tmp/cache` (N8a item 6), which
  works only with the tmpfs at mode 1777 (*N1 amendment, U4 rework*).
- *Why `--scope all-layers`:* the tar carries every layer, so a package
  deleted in an upper layer is still redistributed object code. The
  squashed view would hide it. Duplicates across layers collapse to one
  index component (N5) by source key.
- *Presence check (PSC-20):* before any write, `bundle.sh` reads the
  reference with
  `KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent KE_SBOM_USER="$sbom_user" docker compose --env-file .env.example -f docker-compose.sbom.yml config --images sbom`
  (single line, `ref_re` plus a mandatory `@sha256:`; U3: `ref_re` refuses
  a leading `-`, security I-1), and runs
  `docker image inspect <ref>`. Absent, from U2 until U8:
  `bundle: the SBOM generator image is not present (<ref>); pull it first with: docker pull <ref>; this script never pulls`,
  exit 1, `--out` untouched (`<ref>` is the value read, never a literal in
  `bundle.sh`). U8 replaces `pull it first with: docker pull <ref>` with
  `run scripts/bundle_fetch.sh first`, in the same commit that adds it.

### N1 amendment, U2 (architect, 2026-10-23)

Facts here were fetched (GitHub releases API, `docker pull`,
`docker buildx imagetools inspect`, and `syft config` run offline); the
note's "nothing fetched" header does not apply to this subsection.

- *Pin (U2).* `anchore/syft` **v1.54.1**, released 2026-10-06 (17 days
  old; v1.55.0 of 2026-10-19 is too new). It is the syft that the pinned
  grype v0.120.1 embeds (grype's `go.mod` at v0.120.1:
  `github.com/anchore/syft v1.54.1`), so SBOM and scan share catalogers.
  Index (OCI image index) `sha256:3eb5379ba7b409c3f4069b686110527af0c47df993fa5c10d13e7cf34f49b1aa`;
  linux/amd64 `sha256:507b76f097cd0f4a0f998a346afe61f5776329913d6ab3c0bd678b6635356120`;
  linux/arm64 `sha256:9c493ce4965bb26995e0f30b5a7799cb4628c83c1733cfca4dcd4ac2e92cb1a6`
  (the index also lists ppc64le, riscv64 and s390x; no attestation
  manifests). Security's N2 record checks these before the pin is
  committed.
- *Interim pull (U2 to U8).* `scripts/offline_check.sh`, host half, after
  the Compose version check and immediately before `bash scripts/bundle.sh`:
  ```
  echo "offline: pulling the SBOM generator (docker-compose.sbom.yml, service sbom)"
  KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent \
    docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom \
    || die "pulling the SBOM generator failed (docker-compose.sbom.yml, service sbom); no retry"
  ```
  Why there: it is the consumer's own script (as `scan.sh` pulls grype
  just before using it), it keeps `verify.sh` a list of gate scripts, it
  makes `offline_check.sh` run alone, and it is the line U8 replaces with
  `bash scripts/bundle_fetch.sh ...` (N15 U8: "wired into
  `offline_check.sh`"). Not `bundle.sh`, which never pulls. Not
  `build.sh`, which the operator runs too and which pulls only the stack.
  `-f` overrides the exported `COMPOSE_FILE`; the exported
  `COMPOSE_PROJECT_NAME` is harmless (pull creates nothing). On Git Bash
  MSYS rewrites `/nonexistent`; neither `pull` nor `config` reads the bind
  source.
- *Dummy values, not `--no-interpolate` (tester items 3 and 4).* Compose
  5.1.4 refuses the file with the `:?` variables unset, even for `config`.
  `config --no-interpolate --images sbom` and the dummy form both print the
  ref, but `pull` has no `--no-interpolate`. So both the read and every pull
  (U2 here, and U8's `bundle_fetch.sh` N4 step 1) use the one form,
  `KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent docker compose --env-file .env.example -f docker-compose.sbom.yml ...`.
  `--env-file .env.example` matches every other compose call in
  `bundle.sh`, `scan.sh` and `offline_check.sh`, so the repo-root `.env`
  (it holds the model keys) is never loaded for this file. Proven on this
  host with the real ref: pull, then `config --images`, then
  `docker image inspect` all exit 0; a wrong digest makes inspect exit 1.
- *Operator before U8.* `build.sh`, then the command the refusal prints,
  `docker pull <ref>`. This is the same daemon pull as the compose form:
  the digest wins and the tag is dropped (checked on this host). README
  wording waits for U8 (ruling 6). README may not name the ref (pin place).
- *Env keys (U2).* From `syft config` of v1.54.1, run with
  `--network none --read-only`: every key that makes syft reach the
  network, set to `false` (the Environment row). None needs a value other
  than `false`. Defaults: `check-for-app-update` is `true`. The others are
  unset (tri-state) or `false`, and `enrich: []` would turn them on; an
  explicit key wins over `enrich`. Not set: `SYFT_ENRICH` (a list, and
  covered by the explicit keys); the URL keys `SYFT_JAVA_MAVEN_URL`,
  `SYFT_JAVASCRIPT_NPM_BASE_URL`, `SYFT_PYTHON_PYPI_BASE_URL`,
  `SYFT_GOLANG_PROXY` (unused with lookups off, and not `false`); the
  registry keys and `SYFT_FROM` (the `docker-archive:` scheme never
  contacts a registry). `network_mode: none` is the control. The keys stop
  syft from trying, so a run does not wait on timeouts and the SBOM is the
  same on online and offline hosts. The `SYFT_*` keys must include these
  eight; extra `SYFT_*` keys are allowed only if `false` (review N4, U3).
- *CLAUDE.md:* no change. The `full` host half already "builds and pulls
  images"; this is one more pull, from the same registry host.

### N1 amendment, U4 (architect, 2026-10-23)

U4 rulings (orchestrator, tester points 1-8; handoff "U4 rulings").
- *Run forms (review N3).* The run above and N3's checker run are U3's
  Windows-host form. `hostpath` is `cygpath -m --` where `cygpath` is on
  PATH, else the path unchanged; it converts `KE_SBOM_IN`, `KE_SBOM_OUT`
  and every `-v` source. `MSYS_NO_PATHCONV=1` is set on the generator run
  and the checker run only, never on `docker save` (its `-o` is a host
  path Git Bash must convert). Directories: `mkdir`, then `chmod 0700`
  (`mkdir -m` fails on NTFS under Git Bash).
- *Work dir (point 5, review N6).*
  `sbom_work="$(mktemp -d "$(dirname -- "$out")/.ke-sbom.XXXXXXXX")"`,
  made after `--out` exists and removed by the EXIT trap. It is outside
  `--out`, so it is never in the manifest, and never under `TMPDIR`.
  **The 7 GiB floor covers it** once the floor is also measured on
  `dirname(--out)` (U4 rework, review N5: *N1 amendment, U4 rework*). The
  first form measured only the nearest existing ancestor of `--out`,
  which is `--out` itself when it already exists (empty), e.g. a mount
  point, so the unpack's filesystem went unmeasured. The peak in
  `bundle.sh` is the bundle (0.94 GiB) plus one image's unpack (1-2 GiB
  estimated), about 3 GiB. That is below the 4.3 GiB measured need, and
  the work dir is gone before `dind`, so R6's basis is unchanged. U11
  re-derives it from CI `df` logs (PSC-16). In `offline_check.sh`,
  `dirname(--out)` is `dist/`, already in `df_paths`. A SIGKILL can leave a
  `.ke-sbom.*` beside the bundle. It is outside the bundle and its
  manifest, so install never sees it.
- *Base image for the drift check (point 6, orchestrator ruling).*
  `offline_check.sh`, host half, right after the generator pull and before
  `bundle.sh`, so a pull failure costs seconds, not a bundle:
  ```
  base_ref="$(sed -n 's/^FROM \([^ ]*\) AS runtime$/\1/p' docker/app.Dockerfile)"
  [[ "$base_ref" =~ <the tester's pinned pattern: tag and @sha256 digest required, no leading '-'> ]] \
    || die "cannot read the ke-app base reference from docker/app.Dockerfile"
  echo "offline: pulling the ke-app base ($base_ref)"
  docker pull "$base_ref" > /dev/null || die "pulling the ke-app base failed ($base_ref); no retry"
  ```
  The drift step's "never pulls it" refusal is dropped. If the image is
  missing, `docker save` fails naming the ref. *Why pull:* BuildKit
  fetches the base into its own cache, which `docker save` does not read,
  and a CI runner starts empty. No `--platform`: the daemon takes its
  native entry of the index, which is the platform `build.sh` built
  `ke-app` on. *Confirm at GREEN:* `docker save` of the `name:tag@digest`
  form works on both stores. On the containerd store, if the save fails on
  the index's absent platforms, add `--platform linux/<daemon arch>` to the
  save.
  - *U8 does not take this over.* `bundle_fetch.sh` fetches what an
    operator bundle needs: the generator and the sources. The base is not
    an input to `bundle.sh`; only the gate's drift check reads it. U8
    replaces only the generator pull line, and this pull stays.
  - *CI egress (confirmed).* `python:3.12-slim-bookworm` is on Docker
    Hub, the registry of the generator and of the stack images `build.sh`
    already pulls (the same base, through BuildKit). The pull runs in the
    host half of `verify.sh full`, not in `gates`/`gates-it`, so no
    container network changes. CLAUDE.md already says the host half
    "builds and pulls images": **no CLAUDE.md change**, and N13's U8 text
    is unaffected.
- *Base SBOM run (point 7).* The same form as `bundle.sh`'s run
  (`MSYS_NO_PATHCONV=1`, the three `KE_SBOM_*` keys through `hostpath`,
  `--env-file .env.example -f docker-compose.sbom.yml run --rm --pull
  never sbom docker-archive:/in/<name>.tar --scope all-layers -o
  spdx-json=/out/<file>`) with **no `-p`**. It inherits the exported
  `COMPOSE_PROJECT_NAME`, the offline project, so it adds no project of
  its own to tear down. `run --rm` leaves no container. Its work dir is a
  `mktemp -d` under `dist/` (in `df_paths`), outside the bundle, removed
  on success and by the EXIT trap.
- *`ADDED_PACKAGES` (point 8).* Read by `ast` from
  `tests/test_notice_ke_app.py`, mounted read-only into the checker run.
  It is never imported, because importing a test module would run test
  imports inside `ke-app`. The U1 static test and the U4 image check share
  this one literal. A missing or non-literal value fails, naming the file.

### N1 amendment, U4 rework (architect, 2026-10-23)

Review B1 and N5, security L-2; evidence `u4/windows-run.txt` 3c.
- *tmpfs `/tmp:mode=1777` (B1).* `docker-compose.sbom.yml`, service
  `sbom`: `tmpfs: ["/tmp:mode=1777"]`; `XDG_CACHE_HOME: /tmp/cache` stays.
  - *Cause.* The syft image's own `/tmp` is `drwxr-xr-x 0/0` (3c part 2,
    from `docker export`). A tmpfs mounted over an image directory with no
    `mode=` takes that directory's mode, so the caller's uid cannot create
    `/tmp/cache` and syft warns on every run (7 of 7, U4 GREEN and A34).
    It is the image, not the engine, so Linux behaves the same. With
    `mode=1777` the same run prints no cache warning (3c part 2).
  - *Security.* A sticky world-writable `/tmp` is a risk only when a
    second principal shares it. Here: one process, one uid, `read_only`
    root, `network_mode: none`, `cap_drop: [ALL]`, `no-new-privileges`, a
    per-container tmpfs that dies with `run --rm`, and Docker's tmpfs
    defaults `noexec,nosuid,nodev` kept (no `exec` is added, unlike the
    gate services). syft can already write `/out`; this gives nothing new.
    The cache stays near-empty (every remote lookup off) and off the host
    (I-2, ADR-KE-013 am. 1 D1). Same form as the gates' tmpfs (PS-3.5).
  - *Tests.* The tmpfs entry carries `mode=1777` and no `exec`;
    `_tmpfs_targets` already strips options, so U2's pins hold. Proof: a
    real run with no `unable to get filesystem cache` line (A34 re-runs
    2b and 3b; the PR's CI run is the first Linux classic-store proof).
- *Disk floor on `dirname(--out)` too (N5; this rework, not later).*
  Choice: measure, do not refuse. `bundle.sh` runs the same floor check
  (nearest existing ancestor, `df -Pk`, 7 GiB, same message form
  `need 7 GiB free on <path>, found <N> GiB`) for `--out` and for
  `dirname(--out)`, skipping the second when it resolves to the same
  probe path (the usual case, `--out` absent). A pre-existing empty
  `--out` on another filesystem (a mounted stick) is a legitimate operator
  layout, so refusing it would be a behaviour change for no gain, and
  "is a mount point" has no portable test across Linux, macOS and Git
  Bash. Requiring 7 GiB on each filesystem is conservative (the bundle
  needs about 1 GiB on `--out`, the unpack 1-2 GiB beside it); U11
  re-derives the floor. Why now: the false claim and the work dir are
  both U4's, the fake `df` already answers per path
  (`FAKE_DF_AVAIL_BY_PATH`), and the fix is a few lines. First test:
  `--out` pre-created empty, `df` gives `--out` 50 GiB and its parent
  3 GiB: refused before any `docker save`, `--out` empty, no record, the
  message names the parent; the swapped case names `--out`; both 50 GiB
  passes. `offline_check.sh` is unchanged (`dist/` is in `df_paths`).

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
  run (U3, pinned in `u3/target-bundle.sh`):
  ```
  MSYS_NO_PATHCONV=1 \
  docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pull never \
    --user "$sbom_user" --label "com.docker.compose.project=${project}-sbomcheck" \
    -v "$(hostpath "$repo_root")/scripts/sbom_check.py:/opt/ke/sbom_check.py:ro" -v "$(hostpath "$work"):/work:ro" -v "$(hostpath "$out/images"):/images:ro" \
    --entrypoint python "$app_ref" -I /opt/ke/sbom_check.py finish \
    --name "$name" --ref "$ref" --arch "$arch" --git-sha "$git_sha" \
    --raw /work/raw.spdx.json --tar "/images/$name.tar" "${site_args[@]}" \
    > "$app/sboms/$name.spdx.json"
  ```
  with `site_args` = `--site /opt/venv/lib/python3.12/site-packages --lock
  /app/uv.lock` for `ke-app` only (`hostpath`, `MSYS_NO_PATHCONV`: N1
  amendment, U4). The label is `<project>-sbomcheck`, its
  own, distinct from `<project>-sbom`. The `ke-app` venv is not used (`-I`
  keeps it out). It runs there because the runtime-package check must list
  the real installed distributions;
- at e2e time, inside the offline client (`ke-gates` image, system
  `python3`), mounted read-only next to `offline_check.sh`;
- in `fast`, imported by the unit tests.

Subcommands (names are the developer's to adjust):
- `finish --name N --ref R --arch A --git-sha S --raw PATH --tar PATH
  [--site DIR --lock PATH]` (U3; no `--uuid`, N6 makes the namespace):
  reads the raw document and the tar (only the `manifest.json` member,
  with `tarfile`, no extraction) and prints the final SPDX document (N6).
  With `--site` and `--lock` (`ke-app`; they go together) it also runs the
  runtime-package check (N7).
- *Argv-path rule (U3):* the checker opens only paths named on its argv;
  it holds no container path, mount point or default location of its own.
  The caller maps them (`-v` above; the unit harness remaps them the same
  way), so one file serves the `ke-app` run, the e2e client and tests.
- *Interface:* `validate(doc) -> list[str]`, `[]` when valid, one message
  per failure; `finish` prints the first 20 to stderr and exits 1. Exit 2
  is a bad argument (pattern, arch).
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
1. `== sources: pull ==` `KE_SBOM_IN=/nonexistent KE_SBOM_OUT=/nonexistent docker compose --env-file .env.example -f docker-compose.sbom.yml pull sbom`
   (the N1 U2 form; it replaces `offline_check.sh`'s interim pull, and the
   refusal's `pull it first with: docker pull <ref>` becomes
   `run scripts/bundle_fetch.sh first`)
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
| `repo1.maven.org` | `maven` (sources jars; jaxb-api, ruling 5, N8a) |

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
  `temurin:<release tag>`, `pypi:<name>@<version>`,
  `maven:<group>:<artifact>@<version>` (ruling 5, N8a).
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
  - `maven`: `https://repo1.maven.org/maven2/<group path>/<artifact>/<version>/<artifact>-<version>-sources.jar`,
    checked by the `.sha1` Maven Central publishes beside it (jaxb-api).
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

### N5 amendment, U7 (architect, 2026-10-25)

This amendment makes U7 implementable in TDD units (N15 row U7; Q69 gcc
ships as `deb`; ruling 5 / N8a 2, jaxb-api is `maven`). It supersedes, for
U7 only, N13's draft "Generated artifacts" row (item 7) and N5's
"`origin: manual` (the singletons, if the developer prefers)" (item 4:
`neo4j` is always `manual`, and every other kind is always `generated`).
Fixture facts are from `tests/fixtures/sbom-u3/*.pkgs.tsv`, read through
`classify_document(image, doc, always, exempt)` with the committed
`docker/source-policy.json` at 66781a9. Tests read fixture `neo4j` as image
`ke-neo4j` (U6 `U6_FIXTURE_OF`).

**1. Split: four commits, one TDD loop each.** Every commit runs `verify.sh
full` first (CLAUDE.md). The arch is amd64 now: every entry is written
`"arches": ["amd64"]`, and arm64 merges in at U12 (PSC-21, N5 `arches`).
| Unit | Scope | Loop | A34 |
|---|---|---|---|
| U7a | `sbom_check.py`, pure: `lock_needs`, `lock_problems`, `sample_keys`, `lock_text`, the `lock-check` subcommand; carry rows (item 6). No lock is committed yet. | `fast`; `full` before the gate (scripts/) | no |
| U7b | `scripts/sources_resolve.py` (stdlib, the hop-checked fetcher, the pure parsers, the routes for the single-file kinds `neo4j`, `temurin`, `pypi`, `maven`); `scripts/sources_lock.sh`; `docker-compose.sources.yml` service `sources-resolve`; `sbom_check.py lock-needs` with `--tar` (Temurin release file). A real run of the single-file kinds is recorded as evidence, and security's second fetch of the neo4j tarball goes in `sources-provenance.md`. | `full` | no (maintainer tool; record the host the real run used) |
| U7c | The `deb` route (snapshot.debian.org), the `apk` route (aports + distfiles), and `pgdg` if O1 is ruled (a); `lock-needs --syft` (apk commit). Fake-network tests; a real run of one component per route is recorded as evidence. | `fast` loop (the parsers and the fake opener); `full` before the gate | no |
| U7d | The real full amd64 run; `docker/sources.lock.json` committed; the committed-lock test; sizes recorded; security reviews the lock diff; the CLAUDE.md row (the human's approval, same commit). | `full` | no |
*Why four, not three:* U7c's routes test against a fake network, while
U7d is data plus one test and a security review. That review covers about
180 entries, so it should not share a rework loop with parser code.
*Why no lock before U7d:* the committed-lock test (item 6, U7d) asserts
`== []` for every kind. A partial lock would need a per-kind allowance in
the test, which is a weaker gate.

**2. Coverage rule: which packages get an entry.** For each bundled image,
the rows of `classify_document(image, doc, policy["always"],
policy["exempt"])` with `needs == True`, and only those. A row that is
`unparsed` or `unidentified` with `needs == False` is listed only (U9's
index) and gets no entry. In the fixtures these are 42 `ke-neo4j` maven rows
(URL-folded `LicenseRef-` ids, among them javassist, which is exempt). jna is
exempt and has no entry. `component_key(image, row, ctx) -> (key | None,
problem | None)` reads the purl only. syft writes the purl version
percent-encoded, with the Debian epoch kept (`libattr1@1%3A2.5.1-4`), and
the `upstream` qualifier as `<src>` or `<src>%40<srcver>`. `_qualifiers`
decodes both.
- `pkg:deb/debian/<name>@<ver>`: the key is
  `deb:<src>@<srcver>`. `<src>` and `<srcver>` come from
  `upstream=<src>@<srcver>` when present (e.g. `bash@5.2.15-2+b13`
  `upstream=bash%405.2.15-2` gives `deb:bash@5.2.15-2`, and `sqv@1.3.0-3+b2`
  gives `deb:rust-sequoia-sqv@1.3.0-3`). With `upstream=<src>` alone, the
  version is the binary's (`libattr1` gives `deb:attr@1:2.5.1-4`, `libgcc-s1`
  gives `deb:gcc-12@12.2.0-14+deb12u1`). With no qualifier the key is
  `deb:<name>@<ver>` (dpkg's `Source:` rule). If `<srcver>` contains
  `.pgdg`, the key is `pgdg:<src>@<srcver>` (O1).
- `pkg:apk/alpine/<name>@<ver>`: the key is `apk:<origin>@<ver>`, where
  origin is `upstream=` if present, else `<name>`. Alpine subpackages share
  the origin's `pkgver-rpkgrel` (`libstdc%2B%2B@15.2.0-r2` with
  `upstream=gcc` gives `apk:gcc@15.2.0-r2`; `musl@1.2.5-r21` gives
  `apk:musl@1.2.5-r21`).
- `pkg:maven/<g>/<a>@<v>`, where `<g>` is `org.neo4j`, `com.neo4j` or
  starts with `org.neo4j.` or `com.neo4j.` (`org.neo4j.app/neo4j-server`),
  and `<v>` equals the version of the image's `pkg:maven/org.neo4j/neo4j`
  row: the key is `neo4j:neo4j@<v>`. If there is no such row, every
  neo4j-group row is a problem. At another `<v>`, the row falls to `maven:`.
- `pkg:generic/oracle/openjdk@<v>` (syft's name for the Temurin JVM;
  `repository_url` names adoptium) gives `temurin:jdk-<v minus "-LTS">`
  (`21.0.12.1%2B1-LTS` gives `temurin:jdk-21.0.12.1+1`).
  `pkg:maven/jrt-fs/jrt-fs@<v>` maps to that same key when `<v>` equals the
  openjdk version before `+`. Otherwise it is a problem: "`<image>: jrt-fs
  <v> is not the image's Temurin build <t>`". This is the N10 jrt-fs check,
  moved from U9 to here.
- Any other `pkg:maven/<g>/<a>@<v>` gives `maven:<g>:<a>@<v>`.
- `pkg:pypi/<name>@<v>` gives `pypi:<PEP 503 name>@<v>`.
- Anything else with `needs` set is a problem, never a pass: "`<image>:
  <purl> needs source and maps to no lock kind: back to the architect`". A
  row with no purl is named by SPDXID.
- Fixture result (architect's run, 1015 rows): 182 keys. By kind: `deb`
  152, `pgdg` 3, `apk` 19, `neo4j` 1 (73 rows), `temurin` 1 (2 rows),
  `maven` 1 (jaxb-api), `pypi` 5 (`psycopg`, `psycopg-c` in ke-app;
  `autocommand`, `ldap3`, `pandas` in phoenix; O2). Distinct Debian sources
  per image: ke-app 70, ke-neo4j 61 (Debian 13), phoenix 21, postgres 78
  (+3 pgdg). Shared: 152 in total. Q69 holds: `deb:gcc-12@12.2.0-14+deb12u1`
  (ke-app, postgres) and `deb:gcc-14@14.2.0-19` (ke-neo4j, phoenix).
  `openldap` and `cyrus-sasl2` are there. So are `linux@6.12.113-1` (ke-neo4j
  `linux-libc-dev`) and both perl `5.36.0-7+deb12u3`/`u4` (postgres carries
  both).

**3. Where the lock tool runs.**
`scripts/sources_lock.sh --arch amd64|arm64 [--refresh] [--prune <arch>]`
is a maintainer tool. It runs on a Linux or Git Bash host, never in verify
and never in CI, and is not bundled.
1. Refuse unless the six bundled images exist locally at the tags
   `build.sh` gives them: "`sources_lock: FAIL (images: <ref> not found:
   run scripts/build.sh first; the lock is unchanged)`". It checks the 7 GiB
   floor (R6) on its work dir, which is `mktemp -d`, removed by `trap` on
   every exit path.
2. `docker save` each image into the work dir, then run the `sbom` service
   (N1: pinned, `--network none`) with `-o spdx-json=... -o syft-json=...`.
3. `sbom_check.py lock-needs --policy P --sbom IMG=PATH... [--syft
   IMG=PATH...] [--tar ke-neo4j=PATH]` runs in `ke-gates`
   (`--network none --read-only --cap-drop ALL`, ro mounts, argv paths
   only). It prints `needs.json`: per key the kind, the packages
   (image, purl, SPDXID) and the route inputs. These are deb `{src, ver}`;
   apk `{origin, ver, commit, branch}`, with `commit` from syft-json (apk
   `c:`; the exact field name is *confirm at U7c*), branch `v3.23` from
   `distro=alpine-3.23.3`, and two commits for one key a problem; neo4j
   `{ver}`; temurin `{tag, implementor_version}`, from
   `/opt/java/openjdk/release` read out of the tar (no run), where the tag
   differs from the SBOM's is a problem; pypi `{name, ver, from: uv.lock |
   pypi}`, with ke-app's two read from `uv.lock` (no network, N0); maven
   `{g, a, v}`.
4. Resolve: `docker compose --env-file .env.example -f
   docker-compose.sources.yml -p ke-sources-<random> run --rm --pull never
   sources-resolve`. The service is `ke-gates`, `pull_policy: never`, on the
   project's default bridge (the file's only route out). It has
   `read_only`, tmpfs `/tmp`, `cap_drop: [ALL]`, `no-new-privileges`, and
   `user: ${KE_SOURCES_USER:?}`. Its mounts are `sources_resolve.py`,
   `needs.json`, the committed lock, the policy and `uv.lock`, all ro, plus
   `${KE_SOURCES_OUT:?}` rw, the only writable mount. Its environment is
   literals only: no `KE_*` key, no model key, no token, no `.env` read for
   values (PSC-6, PSC-23). `teardown.sh --volumes` runs on every exit path.
   U8 adds `sources-fetch` to the same file.
5. `sources_resolve.py` (stdlib, `python3 -I`) writes only
   `$KE_SOURCES_OUT/lock.new.json`. Every request goes through one opener.
   It has no redirect handler; a 3xx is followed by hand, at most 5 hops,
   each `https`, each host in the policy `hosts` (exact, after lower-casing;
   the N4 rules) plus O2's metadata host, if ruled. TLS uses
   `ssl.create_default_context()` with TLS 1.2 as the floor and
   `ProxyHandler({})`. A per-request timeout and an overall byte deadline
   apply, with one call and no retry (Q61's rule, applied to the tool too).
   A file it needs to hash is *streamed into the hashers and never stored*,
   so nothing is unpacked or kept. It skips any key whose `generated`
   entry already exists for that arch, unless `--refresh` is given. It never
   rewrites a `manual` entry.
6. `sbom_check.py lock-check --lock lock.new.json --policy P --arch A
   --sbom IMG=PATH...` (the U7a function, on the fresh SBOMs). On `[]` the
   script writes `docker/.sources.lock.json.<random>` in `docker/`, `mv`s it
   over `docker/sources.lock.json` and prints `git diff --stat`. Exit 0.
   If the only problems are missing `neo4j` keys (item 4), it writes the
   file, prints the TOFU candidate and exits 3. Any other problem means
   exit 1, and the committed file is untouched.
Merge (N5 `arches`): for the run's arch, entries no image needs lose that
arch, and an entry left with no arch is removed. Other arches' entries are
untouched unless `--prune <arch>` is given. A `manual` entry no image needs
is not removed; lock-check reports it as stale, and the maintainer deletes
it by hand (a reviewed diff).

**4. Checksums and provenance per kind (Q48 form).** In every `files[]`
entry, `sha256` is the file's own SHA-256 (U8's content-addressed name and
first check). `upstream` is the published check the tool verified, or for
`neo4j` the second fetch.
- `deb`: `GET https://snapshot.debian.org/mr/package/<src>/<urlquote(ver)>/srcfiles?fileinfo=1`.
  Its single `.dsc` is named `<src>_<ver without epoch>.dsc` and archived
  under `debian` or `debian-security`. Fetch it from
  `https://snapshot.debian.org/file/<sha1>`. The lock records
  `upstream {sha1, <sha1>, "snapshot.debian.org mr/package/<src>/<ver>/srcfiles"}`,
  the SHA-256 computed, and the size. Parse the `.dsc`: strip the
  clearsign armour and undo the dash escapes, but do not verify the
  signature (no keyring, as the ADR's route). `Source` and `Version` must
  equal the key. `Checksums-Sha1`, `Checksums-Sha256` and `Files` must list
  the same names and sizes. Every SHA-1 must be among mr's srcfiles hashes.
  Each other file gets `url .../file/<its sha1>`, its `sha256` and `size`
  from `Checksums-Sha256`, and `upstream {sha256, <same>, "<dsc name>
  Checksums-Sha256"}`. The `orig` and `debian` tars are not fetched at lock
  time.
- `pgdg` (O1 (a)): the same `.dsc` chain from
  `https://apt-archive.postgresql.org/pub/repos/apt/pool/main/<p>/<src>/`.
  The `.dsc`'s SHA-256 comes from that archive's suite `Sources` index
  (`upstream.alg` sha256, `from` naming the index URL). The paths and suite
  names are *confirm at U7c*.
- `apk`: GitLab's
  `api/v4/projects/alpine%2Faports/repository/tree?path=<repo>/<origin>&ref=<commit>`
  for `repo` in `main` and `community`. A hit in exactly one is required,
  else it fails. The APKBUILD comes from
  `.../repository/files/<repo>%2F<origin>%2FAPKBUILD?ref=<commit>`
  (`content_sha256`) and its raw
  `https://gitlab.alpinelinux.org/alpine/aports/-/raw/<commit>/<repo>/<origin>/APKBUILD`.
  The APKBUILD is read as text and never sourced or run. Its `upstream` is
  `{sha256, content_sha256, "gitlab.alpinelinux.org files API at <commit>"}`.
  This replaces N5's git blob id, so `alg` stays in {sha1, sha256, sha512}.
  `pkgver=` and `pkgrel=` must be literals equal to the key, else it fails.
  Each name in `sha512sums=` is fetched raw from GitLab at the commit if
  it is in the tree listing, and otherwise from
  `https://distfiles.alpinelinux.org/distfiles/<branch>/<name>` (*confirm
  at U7c*; a missing file fails closed and comes back to the architect,
  per N10 amendment U6 item 2). The lock records `upstream {sha512,
  <from APKBUILD>, "APKBUILD sha512sums at <commit>"}`, with the SHA-256
  and size computed. The entry gets `commit` (40 hex), `branch` (`v\d+\.\d+`)
  and `repo`.
- `neo4j`: `https://github.com/neo4j/neo4j/archive/refs/tags/<ver>.tar.gz`.
  The redirect target is `codeload.github.com`. There is no published
  checksum, so the tool streams it once and prints the candidate (sha256,
  size, UTC date, its host). It never writes the entry. Security then
  fetches it independently, from another host or network. Security records
  in `docs/evidence/platform-sbom/sources-provenance.md` the command, host,
  date, SHA-256, size, and the tag's commit from `git ls-remote
  https://github.com/neo4j/neo4j refs/tags/<ver>` (for information). When
  the two agree, the developer writes the entry by hand: `origin: manual`,
  with `upstream {sha256, <same>, "second fetch: security <YYYY-MM-DD>,
  docs/evidence/platform-sbom/sources-provenance.md"}`. A disagreement goes
  to the orchestrator. Risk: GitHub-generated archives are not promised to
  be byte-stable. If they change, U8's fetch fails closed (Q61), and the
  fix is a re-TOFU plus a second fetch, never a skip.
- `temurin`: `https://github.com/adoptium/temurin<feature>-binaries/releases/download/<urlquote(tag)>/OpenJDK<feature>U-jdk-sources_<ver with + as _>.tar.gz`
  and the `.sha256.txt` beside it. That file must be exactly one line,
  `<64 hex>` followed by whitespace and the asset name. The lock records
  `upstream {sha256, <that>, "<asset>.sha256.txt"}`, and the stream must
  match it. The asset name and tag form are *confirm at U7b* (404 fails).
- `pypi`: from `uv.lock` (ke-app), the `sdist` url, `hash` and `size`, with
  `upstream {sha256, <hash>, "uv.lock"}` and no network. For phoenix (O2),
  `https://pypi.org/pypi/<name>/<ver>/json` must have exactly one
  `packagetype: sdist` in `urls` (url host `files.pythonhosted.org`). The
  lock records `upstream {sha256, digests.sha256, "pypi.org JSON <name>
  <ver>"}`, and the stream must match it.
- `maven`: `https://repo1.maven.org/maven2/<g as path>/<a>/<v>/<a>-<v>-sources.jar`
  and `<...>.sha1`. The `.sha1` body's first token must be 40 hex. The lock
  records `upstream {sha1, <that>, "<name>.sha1"}`, and the stream must
  match it, with the SHA-256 computed. A missing sources jar fails closed
  and comes back to the architect (N8a 2).

Failure messages (Q61: fail closed, naming the stage, host and file; SBOM
strings via `_clean`) take the form `sources_lock: FAIL (<stage>: <key>:
<why>; the lock is unchanged)`. Stages are `images`, `sbom`, `needs`,
`resolve` and `check`. The `<why>` texts, exact:
`<host>: HTTP <code>: <url>`; `<host>: timeout after <n> s: <url>`;
`redirect to <host> refused: not in hosts`; `redirect to a non-https URL
refused: <url>`; `more than 5 redirects: <url>`; `<name>: <alg> mismatch:
got <x>, <from> says <y>`; `no <src>_<ver>.dsc in snapshot.debian.org
srcfiles`; `two .dsc files named <name> in snapshot.debian.org srcfiles`;
`<dsc>: Source/Version is <x>, want <y>`; `<dsc>: Checksums-Sha1,
Checksums-Sha256 and Files list different files`; `<name>: sha1 not in
snapshot.debian.org srcfiles`; `<name>: not a safe file name`; `<origin>:
in both main and community at <commit>`; `<origin>: in neither main nor
community at <commit>`; `APKBUILD at <commit>: pkgver/pkgrel <x> is not
<y>` (also when either is not a literal); `APKBUILD at <commit>: no
sha512sums`; `temurin: release file says <x>, SBOM says <y>`; `pypi
<name> <ver>: <n> sdists, want 1`; `maven <g>:<a>@<v>: <name>.sha1 is not
40 hex`. Exit codes: 1 is a fail with nothing written; 2 is a bad
argument; 3 means written, with manual `neo4j` entries pending (item 3.6).

**5. Size budget (PS-3.4, Q62, R6; PSC-16).**
- Verify fetches nothing at U7. The sample arrives with U8, so U7 moves
  neither the floor nor CI time.
- The sample is `sample_keys(lock, arch)`: per kind, the smallest total
  `size`, with ties broken by key, so one per kind. That gives 7 with
  `pgdg` (6 without). `neo4j` and `temurin` are singletons. Estimate:
  about 200-300 MB, dominated by the Neo4j tag tarball and Temurin's
  jdk-sources, plus a few MB for the smallest deb, pgdg
  (`postgresql-common`), apk, pypi (`psycopg`, 168 kB per `uv.lock`) and
  jaxb-api.
- Full set, an estimate and not a measurement: 152 Debian sources, about
  0.9-1.1 GB, of which `gcc-12` and `gcc-14` orig are 80-100 MB each, `linux`
  is about 150 MB, and glibc, postgresql-15/16/18, icu, python3.13,
  systemd, openssl and perl add more. Alpine adds about 150 MB (`gcc` 15.2.0
  once: two `gcc` keys share the tarball, deduplicated by N9's
  content-addressed name; gettext and util-linux too). Neo4j and Temurin
  add about 200-250 MB. The total is about 1.3-1.6 GB, inside PSC-15's
  1-2.5 GB.
- U7d measures this from the lock with no extra fetch. deb and pgdg sizes
  come from the `.dsc` files; apk, neo4j, temurin and maven sizes are
  streamed; pypi sizes come from `uv.lock` and the JSON. It writes
  `docs/evidence/platform-sbom/u7/lock-sizes.txt`: per kind, the full set,
  the sample, and the ten largest files, plus the full set's manifest line
  count against N9's ~6,800 cap.
- U11 re-derives the R6 floor and the `/install` size (N14). By the
  estimate, a full operator bundle (fetch dir + bundle copy + install
  staging) exceeds today's 7 GiB on the same derivation, so the operator
  host needs more. That is U11's to state.

**6. First tests.**
U7a: pure, in `tests/test_sources_lock.py`, plus the carry rows in the
U6 test classes. They run in `fast` RED; the developer runs `full`.
- (a) *Needs from the fixtures.* `lock_needs` over the six fixtures with
  the committed policy gives exactly item 2's 182 keys, with these kind
  counts. Named rows: `deb:gcc-12@12.2.0-14+deb12u1` (ke-app gcc-12-base,
  libgcc-s1, libstdc++6), `deb:gcc-14@14.2.0-19`, `deb:attr@1:2.5.1-4`,
  `deb:bash@5.2.15-2`, `deb:rust-sequoia-sqv@1.3.0-3`, `deb:linux@6.12.113-1`,
  `deb:openldap@2.5.13+dfsg-5`, `deb:cyrus-sasl2@2.1.28+dfsg-10`,
  `pgdg:postgresql-common@293.pgdg12+1`, `apk:gcc@15.2.0-r2`,
  `apk:musl@1.2.5-r21`, `neo4j:neo4j@5.26.32` (73 packages incl.
  `org.neo4j.app/neo4j-server`), `temurin:jdk-21.0.12.1+1` (openjdk and
  jrt-fs), `maven:javax.xml.bind:jaxb-api@2.2.12`, the five `pypi:` keys.
  jna and javassist and the other 41 listed-only rows give no key.
- (b) *Mapping table* (synthetic rows): `pkg:npm/x@1` with `needs` set is
  a problem naming image and purl; so are a no-purl row (by SPDXID) and
  `pkg:deb/ubuntu/...`; `org.neo4j` at another version gives `maven:`; a
  jrt-fs version mismatch is a problem; neo4j-group rows with no
  `org.neo4j/neo4j` row are a problem; `needs` False gives no key.
- (c) *Schema* on a synthetic good lock (one entry per kind) gives `[]`.
  Each bad shape gives one problem. Top keys not exactly `format` and
  `components`; `format` != 1; text != `lock_text(parsed)` (`json.dumps(...,
  indent=1, sort_keys=True, ensure_ascii=True) + "\n"`: "not in canonical
  form: regenerate"). The key grammar per kind:
  - `deb`/`pgdg`: `<src>` `[a-z0-9][a-z0-9+.-]+`, version
    `([0-9]+:)?[0-9][A-Za-z0-9.+~-]*`, and `pgdg` iff it contains `.pgdg`;
  - `apk`: origin `[a-z0-9][a-z0-9+._-]*`, `@<v>-r<n>`;
  - `neo4j:neo4j@\d+(\.\d+)+`;
  - `temurin:jdk-\d+(\.\d+)*\+\d+`;
  - `pypi:[a-z0-9]+(-[a-z0-9]+)*@<v>`;
  - `maven:<g>:<a>@<v>`.
  - `kind` != the key prefix;
  - `arches` empty, unsorted, duplicated, or not in {amd64, arm64};
  - `origin` not in {generated, manual}; `neo4j` not `manual`, or any
    other kind `manual`;
  - a `neo4j` `upstream.from` not exactly `second fetch: security
    YYYY-MM-DD, docs/evidence/platform-sbom/sources-provenance.md`, or
    dated after today (UTC);
  - `files` empty; a file without exactly `name`, `url`, `sha256`, `size`,
    `upstream`;
  - `name` outside `[A-Za-z0-9][A-Za-z0-9._+~-]{0,254}` (so `/`, `..` and a
    leading `.` fail), or a name duplicated within the entry;
  - `url` not `https`; carrying userinfo, a port, a query or a fragment;
    or a host not in the policy `hosts` (`deb.debian.org`,
    `evil.github.com`, `Snapshot.debian.org`);
  - `sha256` not 64 lower-case hex (63, 65, upper case);
  - `size` not an int > 0 (0, -1, `true`, `"1"`);
  - `upstream` without exactly `alg`, `value`, `from`; `alg` not in {sha1,
    sha256, sha512} (`md5`); `value` not lower-case hex of 40/64/128 for
    its `alg`; `alg` sha256 but `value` != `sha256`; `from` blank;
  - per kind:
    - deb: not exactly one `.dsc`; the `.dsc` name not
      `<src>_<ver without epoch>.dsc`; the `.dsc` not `sha1` with its url
      `https://snapshot.debian.org/file/<that sha1>`; another file not
      `sha256` from `<dsc name> Checksums-Sha256` with a `/file/<40 hex>`
      url;
    - apk: no `commit`, `branch` or `repo`; not exactly one `APKBUILD`
      (`sha256`); another file not `sha512`;
    - maven: not one `-sources.jar` with `sha1`;
    - temurin, pypi: not one file with `sha256`.
- (d) *Coverage* (`lock_problems(lock, policy, docs, arch)`). A synthetic
  lock built from (a)'s keys (one valid file each) gives `[]`. Drop one
  key: one problem per affected package, exactly "`<image>: <purl> needs
  source; the lock has no <key> for <arch>: run scripts/sources_lock.sh
  --arch <arch>`". An extra key gives "`lock: <key> is listed for <arch>
  but no image needs it: run scripts/sources_lock.sh --arch <arch>`". An
  entry with `arches: ["arm64"]` does not cover amd64.
- (e) *Sample* (`sample_keys(lock, arch)`): the smallest total size per
  kind, ties broken by key, only entries for that arch, one key per kind
  present, singletons always in. `plan` (U8) is its only other caller; N3's
  "sample selection lives only in `plan`" now reads "only in
  `sample_keys`, which `plan` calls".
- (f) *`lock-check` CLI*: argv paths only (N3). It prints `lock-check: ok
  (<n> components, <arch>)` with exit 0. With problems, the first 20 go to
  stderr with exit 1. A bad arch exits 2.
- (g) *Carry, review U6 N3 / security I-1.* The U6 policy oracle
  (`u6_policy_problems`) rejects `reviewed: security <tomorrow, UTC>` and
  accepts today's date. Compare with `datetime.now(timezone.utc).date()`,
  never local time: the committed `2026-10-25` was written at 03:49Z,
  still the 24th on a Pacific-time host. Add the bad shape to the oracle's
  controls.
- (h) *Carry, review U6 N5.* `exempt_matches` flags a package whose purl is
  `pkg:maven/com.sun.jna/jna@5.15.0#sub/path`, and also one ending
  `?type=jar#sub`, for the committed jna entry, because the subpath is
  stripped on the package side.
U7b first tests are against a fake opener; no network in verify:
- hop rules, each with its item-4 message: an unlisted host, http,
  6 hops, non-2xx, timeout;
- `.sha256.txt`, `.sha1` and `uv.lock` sdist parsers;
- pypi JSON: exactly one sdist;
- the release file parser and the tag check;
- the neo4j candidate is printed and never written (exit 3);
- `sources_lock.sh` with `tests/fake_docker.py`:
  - it refuses when an image is absent and leaves the lock untouched on
    every failure;
  - it keeps `manual` entries byte-identical;
  - it merges arches;
  - it passes no `-e`/`--env-file` value and no `KE_*`;
  - the compose service's hardening is pinned;
  - `test_verify_full_takes_no_caller_ke_key_but_the_model_keys` stays
    green.
U7c: the `.dsc` parser (armour, dash-escape, section mismatch, epoch
dropped from the name); the mr fileinfo choice (missing or two `.dsc`
files); the APKBUILD (`sha512sums` block, non-literal `pkgver`); the
main/community choice; the `pgdg` `Sources` parse. U7d:
`lock_problems(committed lock, committed policy, six fixtures, "amd64") ==
[]` and `lock_text(lock) == file text`.

**7. CLAUDE.md "Generated artifacts" row (the human's file; draft for the
orchestrator, U7d, same commit as the lock; supersedes N13's row):**
```
| `docker/sources.lock.json` | the bundled images' SBOMs (from `scripts/build.sh` images) and their upstream source metadata (snapshot.debian.org, Alpine aports, GitHub, PyPI, Maven Central); `docker/source-policy.json`; `uv.lock` | `scripts/sources_lock.sh --arch <arch>` (maintainer, network; never run by verify or CI); security reviews every diff | `tests/test_sources_lock.py` runs `sbom_check.py`'s lock check on the committed lock in every verify run; from U9, `bundle.sh` (`sbom_check.py index`) refuses a package with no entry |
```

**Open, for the orchestrator or the human (before U7c unless stated).**
- *O1, a new host (human: the SFU egress list).* The `postgres` image's
  `postgresql-16 16.15-1.pgdg12+2`, `postgresql-18 18.6-1.pgdg12+2` (its
  `libpq5`) and `postgresql-common 293.pgdg12+1` come from PGDG. They are
  not on snapshot.debian.org. Options:
  - (a) Recommended: kind `pgdg` and a tenth host,
    `apt-archive.postgresql.org` (PGDG's archive of every published
    version). This needs the U6 host-set test amended, ADR-KE-016 point 4
    amended and security's review.
  - (b) Upstream PostgreSQL tarballs. Not recommended: they lack PGDG's
    `debian/` packaging and patches, so they are not the corresponding
    source.
  - (c) Exempt them. Not recommended: `postgresql-common` is GPL-2.0, and
    there is no OR to elect.
- *O2, a metadata host (orchestrator; human if it counts as egress).*
  Phoenix's `autocommand 2.2.2` (`LicenseRef-LGPLv3`), `ldap3 2.9.1`
  (`LicenseRef-LGPL-v3`) and `pandas 2.3.3` (a hash-only id, so fail
  closed) are not in `uv.lock`. ADR-KE-016 point 4's "no API call" does not
  cover them. Options:
  - (a) Recommended: `pypi.org` JSON at lock time only. It is never in a
    lock URL, so `hosts` is unchanged, and lock-check rejects it as a file
    host.
  - (b) The BLAKE2b path in `files.pythonhosted.org` URLs. This adds an
    `alg` and relies on Warehouse internals.
  pandas could instead get a security-reviewed `exempt` entry (its
  `LICENSE` is BSD-3-Clause). That is not needed: about 4.5 MB ships by
  default.
- *O3, fixture versus fresh images (U7d).* The committed-lock test uses
  the U3 fixtures, but the lock comes from freshly built images. `ke-app`'s
  apt dependencies may have moved since U3 (only libpq5 is pinned). The
  developer diffs the fresh package lists against the fixtures first. Any
  difference stops U7d and goes to the orchestrator, because refreshing the
  fixtures re-pins U4-U6's real-row tests.
- *O4, to confirm, not to rule.* The Temurin tag form `jdk-21.0.12.1+1`
  (U7b), the syft-json apk commit field, and the distfiles path (U7c).

No spans: a build-time maintainer tool, not an agent step (N3).

*Resolution endpoints (architect, 2026-10-25; PSC-23 "N5 lists the
resolution endpoints"; O2 ruled):* `sources_resolve.py` makes exactly
these calls. No other endpoint is used.
- **No GitHub API call:** nothing goes to `api.github.com`.
  - The Temurin tag comes from `/opt/java/openjdk/release` in the tar,
    cross-checked against the SBOM.
  - The tool streams the asset
    `https://github.com/adoptium/temurin<feature>-binaries/releases/download/<urlquote(tag)>/<asset>`
    and reads `<asset>.sha256.txt` at the same path. Both are plain
    github.com file URLs, and their redirects go only to
    `objects.githubusercontent.com` or `release-assets.githubusercontent.com`.
  - Neo4j is the file URL
    `https://github.com/neo4j/neo4j/archive/refs/tags/<ver>.tar.gz`
    (redirect to `codeload.github.com`).
  - Security's `git ls-remote` is part of the manual second fetch, not a
    tool call.
- **snapshot.debian.org:**
  - `GET /mr/package/<urlquote(src)>/<urlquote(ver, safe="")>/srcfiles?fileinfo=1`;
  - `GET /file/<sha1>` (the `.dsc`).
- **gitlab.alpinelinux.org:**
  - `GET /api/v4/projects/alpine%2Faports/repository/tree?path=<repo>/<origin>&ref=<commit>&per_page=100`,
    for `repo` in `main` and `community`. A non-empty `X-Next-Page`
    response header fails closed: "`<origin>: more than 100 files at
    <commit>`";
  - `GET /api/v4/projects/alpine%2Faports/repository/files/<repo>%2F<origin>%2FAPKBUILD?ref=<commit>`
    (`content_sha256`);
  - `GET /alpine/aports/-/raw/<commit>/<repo>/<origin>/<name>` (the
    APKBUILD and local files).
- **distfiles.alpinelinux.org:** `GET /distfiles/<branch>/<name>`.
- **pypi.org:** `GET /pypi/<name>/<ver>/json`. This is phoenix only. It is
  a resolution host on the maintainer host and is never a lock file URL
  (O2 ruling: `hosts` governs file URLs only). The opener's allowlist is
  `hosts` ∪ {`pypi.org`}.
- **files.pythonhosted.org:** the sdist URL from that JSON (streamed).
  ke-app's two packages come from `uv.lock`, with no call.
- **repo1.maven.org:** `GET /maven2/<g path>/<a>/<v>/<a>-<v>-sources.jar`
  and the same path plus `.sha1`.
- **pgdg:** waits on Q71.

**Rework round 1 (orchestrator rulings, 2026-10-25).** These come from the
U7a review (`u7a/review.md`, B1, B2 and N1-N7). They add to item 6 (c),
and every rule fails closed: a breach is a named problem, never a pass and
never a crash.
1. **B1, neo4j binding.** A `neo4j` entry has exactly one file. Its
   `upstream` must be `{alg: "sha256", value: <equal to that file's
   sha256>, from: "second fetch: security YYYY-MM-DD,
   docs/evidence/platform-sbom/sources-provenance.md"}` (the date rule as
   before). Anything else is a problem. Bad-shape rows:
   - two files;
   - `alg` sha1 with a 40-hex value;
   - `alg` sha512 with a 128-hex value;
   - sha256 with a different value.
2. **B2, charset before parsing.** `_url_problems` refuses a `url` unless
   every character is in 0x21-0x7e. That excludes space, tab, CR, LF, NUL,
   DEL and non-ASCII. The check runs before `urlsplit`, so the host check
   sees the literal string U8 will request. The same rule (0x21-0x7e) holds
   for `name` and for every other string field of an entry: the component
   key, `kind`, `origin`, each `arches` item, `sha256`, `upstream.alg`,
   `upstream.value`, and apk's `commit`, `branch` and `repo`.
   *Architect's precision:* the one exception is `upstream.from`. Its
   recorded forms have spaces (`second fetch: security ...`, `<dsc name>
   Checksums-Sha256`), so `from` allows 0x20-0x7e. Space is allowed there,
   but no other whitespace or control character. Rows:
   - a tab in the url host;
   - a space or an LF in the url path;
   - a NUL in `name`;
   - a non-ASCII `name`;
   - a tab in `from`.
3. **N1, per-kind host and name rules** (N4; N10 am. U6 item 2). A file is
   a problem unless its url host and its name fit its kind.
   - *Every kind:* `name` matches `[A-Za-z0-9][A-Za-z0-9._+~-]{0,254}`. So
     no `/`, NUL or leading `-` or `.`, and also no `..` anywhere in the
     name. The url path has no `..` segment. Its last segment equals `name`,
     except for `deb` (below).
   - *`deb`:* host `snapshot.debian.org` only. The path is `/file/<40 hex>`,
     which is content-addressed, so for `deb` this form replaces the
     last-segment rule (architect's precision: snapshot URLs carry no file
     name). The `.dsc` url's SHA-1 equals its `upstream.value`, as in U7a.
   - *`pgdg`:* host `apt-archive.postgresql.org` once Q71 is ruled. Until
     then the kind has no allowed host, so every `pgdg` file is a problem.
     The tests stop adding the pgdg host to their policy for this check.
     U7c writes pgdg's path rule with Q71.
   - *`apk`:* host `gitlab.alpinelinux.org`, with path
     `/alpine/aports/-/raw/<commit>/<repo>/<origin>/<name>`, where commit,
     repo and origin are the entry's and the key's. Or host
     `distfiles.alpinelinux.org`, with path
     `/distfiles/<branch>/<name>`, where branch is the entry's. The
     APKBUILD must be the GitLab form.
   - *`neo4j`:* host `github.com`, path
     `/neo4j/neo4j/archive/refs/tags/<ver>.tar.gz`, and name
     `<ver>.tar.gz`, where `<ver>` is the key's version.
   - *`temurin`:* host `github.com`. The path starts
     `/adoptium/temurin<N>-binaries/releases/download/`, where `<N>` is the
     key's feature version, the digits before the first `.`. The name
     matches `*-jdk-sources_*.tar.gz` (as regex
     `[A-Za-z0-9]+-jdk-sources_[A-Za-z0-9._]+\.tar\.gz`). `upstream.from`
     equals `<name>.sha256.txt`.
   - *`pypi`:* host `files.pythonhosted.org`. The name is
     `<dist>-<ver>.tar.gz`, with `<ver>` the key's version and the url path
     ending in `/<name>`.
     *Architect's precision, flag:* the ruling's "`<name>` (PEP 503 name)"
     would refuse the real `psycopg_c-3.3.6.tar.gz` in `uv.lock`, because
     PEP 625 sdists use `_`. So `<dist>` must PEP 503-normalise to the
     key's name: lower-case it and turn each run of `-`, `_`, `.` into `-`.
     Then `psycopg_c` and `psycopg-c` both match `pypi:psycopg-c`.
     `<dist>` itself matches `[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?`.
   - *`maven`:* host `repo1.maven.org`. The path is
     `/maven2/<g with . as />/<a>/<v>/<a>-<v>-sources.jar`, and its last
     segment equals `name`. `<g>`, `<a>` and `<v>` come from the key.
   - Rows, one per breach:
     - a maven jar named `evil-1.0-sources.jar`;
     - a maven jar on `files.pythonhosted.org`;
     - a pypi sdist of another package;
     - a temurin asset on `repo1.maven.org`;
     - a neo4j tarball at `github.com/attacker/...`;
     - `../..` in a path;
     - an apk file on GitLab at another commit;
     - a url whose last segment is not `name`;
     - any pgdg file.
     The good pypi rows are `psycopg-3.3.6.tar.gz` and
     `psycopg_c-3.3.6.tar.gz`.
4. **N2, deb completeness.** A `deb` (and later `pgdg`) entry has the
   `.dsc` plus at least one file that is not a `.dsc`. U7c's resolver
   writes the entry from the fetched `.dsc` (item 4). U8's fetch checks
   that the fetched `.dsc`'s `Files` and `Checksums-Sha256` list exactly
   the entry's other files, by name, size and sha256. A mismatch is
   `<dsc>: Files/Checksums-Sha256 differ from the lock entry` (Q61). An apk
   entry with only the APKBUILD stays legal: some APKBUILDs have no
   sources.
5. **N4, exact key sets.** An entry has exactly `kind`, `arches`, `origin`
   and `files`, and also exactly `commit`, `branch` and `repo` for `apk`.
   Each file has exactly `name`, `url`, `sha256`, `size` and `upstream`,
   and `upstream` has exactly `alg`, `value` and `from`. An extra or a
   missing key is a problem naming the key. Row: `"skip": true` on a deb
   entry.
6. **N5, wrong types.** Any field of the wrong JSON type is a problem,
   never a `TypeError` or `KeyError`. That covers top-level `components`
   not an object, an entry not an object, `arches` not a list or holding a
   non-string (checked before any `sorted` or `set`), `files` not a list, a
   file or `upstream` not an object, and a string field holding a number,
   list or null. Rows: `arches` holding `["amd64", 1]`, `[["amd64"]]` and
   `"amd64"`; `files: {}`; `upstream: null`. `lock_problems` returns
   normally on every row.
7. **N6, line endings (U7d).** The U7d commit adds
   `docker/sources.lock.json text eol=lf` to `.gitattributes`. The canonical
   text check stays byte-exact, which keeps it correct on a
   `core.autocrlf=true` checkout (A34).
8. **N7, sharper rows.** Each bad-shape row asserts that the problem list
   contains that row's targeted substring: the field and the rule, e.g.
   `host files.py\thon...` or `neo4j: upstream alg`. A non-empty list is
   not enough, so an unrelated problem from the same mutation cannot mask
   the row. The good lock stays `[]`.
N3 (pgdg rules) goes to U7c with Q71, per item 3's pgdg bullet.
9. **Security I-1, scheme (orchestrator, 2026-10-25).** The url's scheme
   must be exactly `https` in lower case, compared on the literal string
   before `urlsplit` (which lower-cases it). Rows: `HTTPS://...` and
   `Https://...`.
10. **Security I-2, size cap (orchestrator, 2026-10-25).** `size` must be
    an int with 0 < size <= 4294967296 (4 GiB). Anything larger is a
    problem naming the file. Rows: 4294967297 and 10**20.
11. **Security I-4/L-3, no crash and clean output (orchestrator,
    2026-10-25).** Three rules:
    - `lock-check` catches every exception, `RecursionError` included
      (for example from deeply nested JSON). It exits 1 with a single
      line, `lock-check: FAIL (<exception class>: <message passed through
      _clean>)`, and prints no traceback.
    - `sample_keys` is called only after a check that returned `[]`.
    - Every component key, purl, name and url in a problem message passes
      through `_clean`.

    Rows:
    - a lock nested 100000 levels deep (exit 1, one line, no
      `Traceback`);
    - a key and a purl carrying ESC and LF are printed cleaned;
    - `sample_keys` is not reached when the check fails.

**Rework round 2 (orchestrator rulings, 2026-10-25).** These come from the
U7a re-check (`u7a/review-r1.md`, R1-B1, R1-N1, R1-N2). They add to round
1 and fail closed.
1. **R1-B1, plain URL paths (every kind).** Each check reads the literal
   string after round 1's charset and scheme checks. A url is a problem,
   with the one text `url path is not a plain path`, when any of these
   holds:
   - it contains a backslash anywhere;
   - its path has an empty segment (`//`, or a trailing `/`);
   - a segment is `.` or `..`;
   - the path holds a `%`, except a literal `%2B` inside the temurin tag
     segment (item 2).

   This closes `%2e%2e`, `%2E.`, `.%2e`, `..\`, `\..\` and `%2f` variants
   in both the shared rule and round 1's last-segment rule. The query and
   fragment stay refused (U7a). Rows:
   - `/a/%2e%2e/b`, `/a/%2E%2E/b`, `/a/.%2e/b`;
   - `/a/..%5cb`, `/a\..\b`;
   - `/a//b`, `/a/./b`;
   - `%2B` outside the temurin tag segment;
   - `%2b` in lower case inside it, because only the literal `%2B` is
     allowed.
2. **R1-N1, temurin binding.** From the key `temurin:jdk-<ver>`, `<N>`
   is the digits before the first `.` of `<ver>`. The rule:
   - url path exactly
     `/adoptium/temurin<N>-binaries/releases/download/jdk-<ver with + as %2B>/<asset>`;
   - `name` == `<asset>` == `OpenJDK<N>U-jdk-sources_<ver with + as _>.tar.gz`;
   - `upstream.from` == `<asset>.sha256.txt`.

   For `temurin:jdk-21.0.12.1+1` that is
   `/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`.
   This replaces round 1 item 3's prefix rule and the
   `*-jdk-sources_*.tar.gz` pattern. U7b confirms the real asset name and
   tag form against the release page. If they differ, the architect amends
   this exact form; it is never loosened to a prefix or a pattern. Rows:
   - another `<N>`, tag or asset version;
   - `+` left unencoded in the tag;
   - a JRE or JDK binary asset name;
   - `from` naming another asset.
3. **R1-N2, the CLI failure line.** For every exception `lock-check`
   catches, read errors (`OSError`, `UnicodeDecodeError`,
   `json.JSONDecodeError`) and `RecursionError` included, it writes
   exactly `lock-check: FAIL (<ExceptionClass>: <message passed through
   _clean>)` on stderr and exits 1. There is no traceback and no other
   line. `<ExceptionClass>` is `type(e).__name__`. This supersedes round 1
   item 11's `<exception class>` wording. Problems found by a check that
   ran cleanly keep U7a's form: the first 20 on stderr, exit 1. The test
   pins the exact line for three cases: a missing file, invalid JSON, and
   the 100000-deep nesting.
4. **Security R1-L1, linear name checks (`u7a/security-r1.md`).**
   `PYPI_DIST_RE` takes quadratic time on over-long names: `a-` repeated
   50000 times takes 7 s.
   - `_binding_problems` runs no regex on a `name` that has already failed
     `LOCK_FILE_NAME_RE`. That leaves one problem, the name rule's.
   - `PYPI_DIST_RE` is rewritten so that no two repetitions can match the
     same characters, which makes it linear.
   - *Architect's suggestion (the developer's choice of means):* take the
     version from the key. First check `name.endswith(f"-{ver}.tar.gz")`
     and strip that fixed suffix with string operations. Then check the
     `<dist>` part without a backtracking pattern: it is non-empty, its
     first and last characters are ASCII alphanumerics, and every
     character is in `[A-Za-z0-9._-]`. Then compare its PEP 503 form with
     the key's name.
   - Rows:
     - a 255-character adversarial name (`a-` repeated, then `-1.tar.gz`)
       is checked in under 0.1 s, timed in the test;
     - a 50000-character `a-` name gives the name-rule problem only, also
       under 0.1 s;
     - `psycopg_c-3.3.6.tar.gz` stays good.
*Architect's precision, pypi (for confirmation; R1-B1 names pypi):* item 1
removes the dot-segment bypass. The binding beyond the last segment is
Warehouse's content-addressed layout, which `uv.lock` (e.g.
`/packages/76/26/<60 hex>/psycopg-3.3.6.tar.gz`) and the JSON both use.
Proposed exact rule: the path is
`/packages/<2 hex>/<2 hex>/<60 hex>/<name>`, lower-case hex. A path of
another shape is a problem. The architect recommends adding it in this
round. It has no effect on real data, since both `uv.lock` sdists match.
5. **Confirmed (orchestrator, 2026-10-25): the pypi path rule is in for
   round 2.** A `pypi` file's url path must be exactly
   `/packages/<2 hex>/<2 hex>/<60 hex>/<name>`, in lower-case hex. Any
   other shape is a problem. Rows: upper-case hex, a 59- or 61-hex third
   segment, an extra or a missing segment, a path that does not start
   with `/packages/`.

**U7b interface pins (orchestrator accepted, 2026-10-25).** These come
from the U7b RED (the tester's section in the handoff). They are written
down here so that GREEN, review and U7c work from the same interfaces.
1. **Fake-network hook.** `scripts/sources_resolve.py` has a module-level
   `OPENER(url, timeout)`, and every request goes through it (item 3.5's
   hop rules run on top of it). Tests import the module by path (N3) and
   patch `OPENER`. There is no flag, no test mode, and nothing is read
   from the environment to select it.
2. **`needs.json`.** `sbom_check.py lock-needs --policy P --sbom IMG=PATH...
   --tar ke-neo4j=PATH [--syft IMG=PATH...]` prints
   `{"format": 1, "needs": {<key>: {"kind": ..., "packages": [{image,
   purl, spdxid}], "route": {...}}}}`, with `route` holding item 3.3's
   per-kind inputs. For `temurin`, `route` also carries the text of
   `/opt/java/openjdk/release`, read from the saved tar without running
   anything. If more than one layer has the file, the top layer's copy
   wins. The resolver derives the tag from that text and cross-checks it
   against the SBOM purl's tag. A mismatch is item 4's `temurin: release
   file says <x>, SBOM says <y>`. This reconciles item 3.3 with the ruling
   that the tag comes from the saved tar.
3. **U7b scope.** In U7b the resolver skips `deb`, `apk` and `pgdg` keys
   and names each one on stderr. `lock-check` then fails the run on those
   coverage misses, so U7b never writes a partial lock that passes.
   `--prune` is not in U7b; it lands with U12's arm64 merge or earlier if
   it is needed.
4. **Exit lines.** A resolver failure prints `sources_lock: FAIL
   (resolve: <key>: <why>; the lock is unchanged)` and exits 1. The
   `<why>` texts are item 4's, cleaned. A `neo4j` TOFU candidate exits 3
   (item 3.6).
5. **Compose bind mounts.** The bind-mount rule in
   `tests/test_stack_compose.py` gains a `sources-resolve` exemption shaped
   like `sbom`'s. It names that service and its exact mounts, and grants
   no general allowance.
6. **Provenance on record** (`docs/evidence/platform-sbom/sources-provenance.md`,
   security's second fetch).
   - Neo4j 5.26.32 tag tarball: sha256
     `182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3`,
     20907800 bytes, tag commit `27f24499b751708815d42c8cf26bfb6597b3516c`.
   - Temurin: the sidecar confirms the tag `jdk-21.0.12.1+1` and the asset
     `OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`, so round 2 item 2's exact
     form holds unchanged. Its sha256 is `573057d0...8234`, given in full
     in the provenance file.
   - The redirect target was `release-assets.githubusercontent.com`.
     `objects.githubusercontent.com` was not used. U8 confirms from real
     fetches whether to drop it from `hosts`; that would be a reviewed test
     change (N10 am. U6 item 2).
   - Size note: the Neo4j tarball is about 20 MB, not item 5's 60-100 MB
     guess, so the sample and full-set estimates fall by that much. U7d
     measures them.
7. **Third fetch (orchestrator ruling).**
   - Security's second fetch is independent of the developer's tool by
     process, so it stands for U7b.
   - Before U7d commits the lock, a third fetch of the Neo4j tarball runs
     over a different network path: the ARM model host or the CI runner.
     It is recorded in `sources-provenance.md` with its host, date,
     sha256 and size.
   - A mismatch fails closed. The lock is not committed, and the
     disagreement goes to the orchestrator.
   - The manual entry's `upstream.from` keeps the second-fetch form
     (round 1 item 1). The third fetch is evidence only, not a new field.

**U7b rework round 1 (orchestrator rulings, 2026-10-25).** These come from
`u7b/review.md` (B1, B2, N1-N6) and security's U7b audit (PASS with M-1 =
B2, L-1 = N1, L-3/L-4 = B1, plus L-2, L-5, I-1, I-3). Every rule fails
closed: a named failure, never a traceback and never a pass.
1. **B1, transport errors, deadline and byte cap.**
   - Every error raised while opening a URL or reading its body becomes a
     `ResolveError` with item 4's text:
     - timeouts (`TimeoutError`, `socket.timeout`): `<host>: timeout after
       <n> s: <url>`;
     - everything else, which covers `OSError` (incl.
       `ConnectionResetError`), `http.client.HTTPException` (incl.
       `IncompleteRead`, `BadStatusLine`) and `ValueError` (incl.
       `InvalidURL`): `<host>: <error class>: <url>`.
   - Each file has a wall-clock deadline of 600 s (default; item 3.5). On
     breach: `<host>: deadline <n> s passed: <url>`.
   - Streaming has a byte cap of 4294967296 (4 GiB, as U7a round 1 item
     10). The read aborts the moment the cap is passed, before more is
     hashed: `<host>: more than 4294967296 bytes: <url>`.
   - `main` catches every exception into the one line `sources_lock: FAIL
     (resolve: <key or "-">: <cleaned message>; the lock is unchanged)`
     and exits 1, with no traceback. This covers an `OSError` writing
     `/out` and a wrong-typed `needs` entry (N6).
2. **B2 / security M-1, the pending-neo4j decision in Python.**
   `sbom_check.py lock-check ... --pending-neo4j` exits 3 exactly when the
   problem list is non-empty and every problem is a coverage miss for a
   `neo4j:` key. Otherwise it exits 1 on problems, or 0 when there are
   none. The decision uses the full list in memory; the 20-line print cut
   applies only to output. `sources_lock.sh` branches on that exit code
   alone and never parses lock-check's text. Without the flag, lock-check
   keeps U7a's exits 0, 1 and 2.
3. **N1 / security L-1, rules on every redirect hop.** Each `Location`
   target, once joined, is refused unless it passes all of these:
   - characters 0x21-0x7e only;
   - a lower-case `https://` scheme, compared literally;
   - no userinfo and no port;
   - no fragment;
   - a plain path (U7a round 2 item 1, with no `%` in the path);
   - a host in the allowlist of item 8.
   *Architect's precisions:*
   - A hop may carry a *query*. GitHub's release-asset redirects are
     signed URLs whose query is the signature, so a no-query rule would
     refuse every Temurin fetch. The query is never written to the lock,
     whose file URLs stay query-free (U7a).
   - The resolver's own first request URLs are fixed templates (the
     endpoint list). They pass the charset, scheme, userinfo, port and
     fragment rules. They are exempt from the path `%` rule, because they
     carry the endpoints' own encodings: GitLab's `alpine%2Faports`, and
     snapshot's `%3A`, `%2B` and `%7E` in a quoted Debian version.
   - If U8's real fetches find a needed redirect with a `%` in its path,
     the architect amends this rule; it is never loosened in code.
   - *Duplication, recorded:* `sbom_check.py` cannot be imported in the
     `sources-resolve` container (only the resolver is mounted), so
     `sources_resolve.py` carries a minimal copy of these checks. U7a's
     tests pin the lock side and U7b's tests pin the hop side, each with
     the same bad shapes (port, userinfo, fragment, `%2e%2e`, backslash,
     tab, `HTTPS://`).
4. **N2, tools first.** `sources_lock.sh` checks `jq`, `git` and `docker`
   with `command -v` before anything else. A missing tool fails with
   `sources_lock: FAIL (tools: <tool> not on PATH; the lock is
   unchanged)`.
5. **N3, temp file.** The EXIT trap removes
   `docker/.sources.lock.json.XXXXXXXX` on every failure path, alongside
   the work dir.
6. **N4, six images.** The script takes the image refs from the same list
   `bundle.sh` uses (one source, not a copy). It requires exactly those six
   names, each present locally, and fails naming any that is missing or
   extra. It derives the `ke-neo4j` tar path from that list rather than a
   literal.
7. **N5, whiteouts.** Recorded as failing closed, no change.
   `tar_file_text` ignores a top-layer `.wh.release`, but the resolver's
   SBOM cross-check (interface pins item 2) refuses any resulting
   mismatch.
8. **Security L-2, the pypi.org scope.** `pypi.org` is allowed only for the
   request `https://pypi.org/pypi/<name>/<ver>/json`, where `<name>` and
   `<ver>` come from a `pypi:` key. Every other request, and every
   redirect hop of every request including that one, uses the policy
   `hosts` alone. This narrows the endpoint list's "`hosts` ∪ {`pypi.org`}"
   to that one request.
9. **Security L-5, file mode.** `sources_lock.sh` runs `chmod 0644` on the
   temp lock before the `mv`. `mktemp` creates it 0600, and the gates
   container (uid 10001) must be able to read the committed file.
10. **Security I-1, error bodies.** The real opener reads a 3xx or 4xx
    response body only up to 1 MiB (1048576 bytes) and then discards it.
    It is never parsed or printed.
11. **Security I-3, keys first.** Before building any URL, the resolver
    checks each `needs` key against U7a's key grammar for its kind (U7a
    item 6 (c)). It carries the patterns in its minimal copy (item 3). A
    bad key is `ResolveError` `<key>: not a valid lock key`. No request is
    made for it, and the run ends (item 1's line).
12. **A34 finding, the sbom tmp dir (orchestrator, 2026-10-25;
    `u7b/windows-run.txt`).** The pinned `sbom` service sets
    `TMPDIR=/out/tmp`. `bundle.sh` creates that directory, but
    `sources_lock.sh` never creates `$work/sboms/tmp`, so a real run stops
    at step 2.
    - Rule: the script creates `$work/sboms/tmp` (with `mkdir` then
      `chmod`, the U3 Windows form) before the syft run.
    - A fake-docker happy-path test of the whole script is added. It runs
      every step in order: `docker save`, sbom, `lock-needs`, resolve,
      `lock-check` (`--pending-neo4j`), `chmod 0644`, `mv`, `git diff
      --stat`. It asserts exit 0 for a complete lock and exit 3 for
      neo4j-pending.
    - So a step-ordering or missing-directory defect turns `fast` red. It
      is no longer found only by a real run.
13. **`KE_IN_GATES` (orchestrator ruling, 2026-10-25).** `KE_IN_GATES` in
    the resolver's process environment comes from the gates image's own
    `ENV`. It is an image marker: not a secret, not a compose key, and not
    taken from the caller. Item 3's "no `KE_*` key" (and N4's) concerns the
    compose `environment:` block and any pass-through from the caller or
    `.env` only. Tests assert that the service's `environment:` block holds
    literals with no `KE_*` name and that the script passes no `-e` or
    `--env-file` value. They do not assert an empty process environment.
*O3 observation (orchestrator, 2026-10-25, from the A34 proof):* the fresh
`ke-neo4j` SBOM lists 72 packages under `neo4j:neo4j@5.26.32`, while the
fixture lists 73. The difference is `neo4j-genai-plugin`, which U4b
removed with `products/`. The key set is unchanged. U7d's drift check
(O3) therefore compares *key sets*, fresh against the fixtures. Any key
added or missing stops U7d and goes to the orchestrator. A different
package count inside a key that both share is reported as information
(key, fixture count, fresh count, the purls that differ) and does not stop
it. The committed-lock test still checks coverage against the fixtures.

## N6. The final SPDX document

`finish` keeps syft's packages, files and relationships and changes only:
- `name`: the `bundle.json` `ref`;
- `documentNamespace`: `urn:uuid:<uuid4>`, a fresh `uuid.uuid4()` per
  document, made by `finish` itself (U3, orchestrator ruling (b)). Why:
  SPDX 2.3 requires a unique absolute URI; RFC 3986 (scheme `urn`) with
  RFC 4122 (the `uuid` namespace) makes `urn:uuid:` one, with no host.
  PS-1.2 forbids hardcoded hosts in scripts, and any https base would
  invent a domain we do not own. Identity lives in the annotations below,
  not the namespace, so `bundle.sh` makes no uuid and passes none (its
  `od /dev/urandom` uuid and `finish --uuid` are dropped);
- `creationInfo.creators`: syft's `Tool: syft-<version>` kept, plus
  `Tool: knowledge-engine-bundle-<git_sha[:12]>`;
- three document `annotations` (`annotationType: OTHER`, annotator
  `Tool: knowledge-engine-bundle-...`): `ke:ref=<ref>`,
  `ke:image-config=sha256:<64 hex>` (the `Config` entry of the tar's
  `manifest.json`), `ke:arch=<amd64|arm64>`;

Then `finish` validates, and exits 1 naming the first failure:
`spdxVersion == "SPDX-2.3"`, `dataLicense == "CC0-1.0"`,
`SPDXID == "SPDXRef-DOCUMENT"`, non-empty `name`, `documentNamespace`
matching `^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`
(lower-case uuid4, as `str(uuid.uuid4())`), `creationInfo.created` an RFC 3339
UTC time, creators include a `Tool: syft-` entry; every package has a
unique `SPDXID` matching `^SPDXRef-[A-Za-z0-9.-]+$`, a `name` and a
`downloadLocation`; exactly one `DESCRIBES` from the document; every
relationship end resolves. This is the SPDX 2.3 required-field set PSC-13
tests, not the full JSON schema (rejected: a schema-validator dependency).
`validate` sees one document; that the namespaces differ across a
bundle's documents is a bundle-level check, by the PSC-13 tests over
`app/sboms/` and by N11's `verify`.

*Ruling 5, Neo4j jars (U3):* decided at the developer's GREEN `verify
full`, the first real syft run (the RED tests stub syft and cannot see
them). The developer lists, from the `neo4j` SBOM, every package whose
licence the N8 classifier marks GPL-family, with purl and licence, in the
GREEN evidence. None: recorded, ruling 5 closed. Any GPL-family jar comes
back to the architect before the commit gate (lock kind, N5/N9 mapping).

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
- There is no vendored-library injection and no vendored-library drift
  check (Q64), because there is no `psycopg_binary.libs`. libpq5 and its
  dependencies are dpkg packages, which syft's dpkg cataloguer reads from
  `/var/lib/dpkg/status`. U4's `full` test asserts that `ke-app`'s SBOM
  lists `pkg:deb/debian/libpq5@<pin>` (upstream `postgresql-15`) and
  `pkg:pypi/psycopg-c@3.3.6`, and has no `psycopg-binary`; and NOTICE's
  image-side drift check (N10, B3). Both run in the drift step of
  `offline_check.sh`, on the bundle's `app/sboms/ke-app.spdx.json` (N1
  amendment, U4).
- *Forked lock (U4, review N7).* `uv.lock` is read as a map from name to
  the **set** of its locked versions. An installed distribution passes if
  its version is in its name's set. A name locked at two versions is
  accepted, not refused: `uv sync --locked` installed one of them, and both
  are locked. Today the lock has no duplicate name.

## N8. The licence classifier (PSC-15 forms, PSC-22)

Input: a package's `licenseDeclared`; if that is missing, its
`licenseConcluded`; if both are, the list syft gives, joined with AND.
Missing means absent, empty, `NONE` or `NOASSERTION` (ruling 5, N8a: syft
writes `NOASSERTION` to `licenseDeclared` of jars it licenses from file
content, e.g. jna's concluded `Apache-2.0 AND LGPL-2.1-only`). If both
fields are set (none are in U3's SBOMs), it needs source if either does.
- Unlicensed: all three missing: reported per image with a count
  (PSC-22). U4: printed by `bundle.sh` (bundle output; the evidence keeps
  the run's output). U9: kept in the index (N9).
  - *Exact rule (U4, point 4; the tester's reading, confirmed).* A string
    field is *missing* when it is absent or `null`, or equals `""`,
    `"NONE"` or `"NOASSERTION"`. The match is exact and case-sensitive,
    as SPDX 2.3 spells the keywords, with no strip. A package is
    unlicensed when `licenseConcluded` and `licenseDeclared` are both
    missing **and** `licenseInfoFromFiles` is absent, `null`, `[]`, or a
    list whose every entry is missing. Any other value in any of the
    three makes the package licensed, and the classifier reads it in the
    input order above. "The list syft gives" is `licenseInfoFromFiles`,
    with its missing entries dropped and the rest joined with AND.
  - *Type rule (tightening).* A value of the wrong type is treated as
    missing: a non-string in either expression field, a non-list
    `licenseInfoFromFiles`, or a non-string entry. Such a package goes to
    the report, which security reviews, and it never crashes the report
    (e.g. an unhashable list in a set test). The DESCRIBES root is never
    reported.
  - *Hash-only ids (U4 rework, security H-1).* syft writes
    `LicenseRef-<64 lower-case hex>`, a hash of licence text it could not
    identify, as the only id on 59 rows (wget, the GCC runtime, gnutls,
    libgcrypt among them). Such a value is *missing* too: a string field
    whose licence ids, after splitting on whitespace and parentheses and
    dropping the operators `AND`/`OR`/`WITH` (any case) and the exception
    id after each `WITH`, are at least one and all match
    `^LicenseRef-[0-9a-f]{64}$` (exact, case-sensitive, as syft writes it).
    The rule applies to `licenseConcluded`, `licenseDeclared` and each
    `licenseInfoFromFiles` entry, so such a package is in the report.
    Security's expected counts: ke-app 19, ke-gateway 0, neo4j 28, phoenix
    35, postgres 25, valkey 1. Test rows: one hash alone; two hashes with
    `AND`; `MIT AND <hash>` is not reported (U5 still flags it, below).
    Security found no real row mixing a hash with a known id.
  - *Today:* syft v1.54.1 writes no `licenseInfoFromFiles` on any package
    of U3's valkey (25) or ke-gateway (71) documents. So the rule reduces
    to the two expression fields. The third field is read so that a
    generator which fills it is classified, not reported.
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
- Token rule (ruling 5, N8a): an id the pattern does not match is still
  GPL-family if any token of its lower-cased text, split on
  `[^a-z0-9]+`, matches `^(a|l)?gpl(v?\d+)?$`; it is then also listed
  as "unparsed". Syft folds a pom's licence URLs into one `LicenseRef-`
  id, so jaxb-api's `LicenseRef-https---glassfish.java.net-public-CDDL-GPL-1-1.html...`
  parses as a single id and the anchored pattern alone would pass it
  with no source (fail open). Every `LicenseRef-` id containing `http`
  is listed as "unparsed" too, flagged or not (43 in neo4j).
- Hash ids (U5; security H-1): `^LicenseRef-[0-9a-f]{64}$` is *unknown*,
  never "no source needed": `needs(id)` is true for it (as the token
  rule fails closed), and every package carrying one is listed as
  "unidentified" in the index (N9) for security. Only a reviewed `exempt`
  entry (N10), whose `reason` names the licence security read in the
  SBOM's `hasExtractedLicensingInfos`, clears it; otherwise U7 locks its
  source. So `<hash>` and `Apache-2.0 AND <hash>` need source, and
  `MIT OR <hash>` does not (MIT elected) but is still listed. *Not*
  reading `hasExtractedLicensingInfos` through the token rule: a GPL text
  that never spells `gpl` ("GNU General Public License") would pass.
- Unparseable text: needs source if it contains `gpl` as a word
  (case-insensitive), and is listed as "unparsed" in the index for
  security.
- The `always` list (N10) overrides: matching packages need source
  whatever `needs()` says.
Pure functions, no I/O: the first fast tests.

### N8a. Ruling 5 (U3 GREEN; architect, 2026-10-23)

Evidence: `u3/gpl-family-packages.md`, `u3/sboms/*.pkgs.tsv`, and each
jar's own metadata, read from `ke-vendor/neo4j:0a6e7aedf54a` by `docker
create`/`cp` (nothing run): `jna-5.15.0.jar` sha256
`a564158d28ab5127fc6a958028ed54279fe0999662c46425b6a3b09a2a52094d`,
`jaxb-api-2.2.12.jar`
`68a621ec18485f951d09ac76f43e57eee394dbe42cb8f2a4c59c93296fa9dcc6`,
`javassist-3.30.2-GA.jar`
`eba37290994b5e4868f3af98ff113f6244a6b099385d9ad46881307d3cb01aaf`.
Maven's POM reference: several `<license>` entries mean the user may
select any one of them.
1. **jna 5.15.0: OR, Apache-2.0 elected, no source.** Its
   `META-INF/LICENSE`: `SPDX-License-Identifier: Apache-2.0 OR LGPL-2.1`,
   "LGPL, version 2.1 or later, or ... the Apache License, version 2.0.
   You can freely decide". Syft's `Apache-2.0 AND LGPL-2.1-only` is the
   two texts in `META-INF` (`AL2.0`, `LGPL2.1`) joined with AND. Nothing
   rewrites syft's expression: the classifier stays literal (needs
   source) and a reviewed `exempt` entry (N10; image `neo4j`, purl
   `pkg:maven/com.sun.jna/jna@5.15.0`) carries the correction, its reason
   naming the LICENSE line, the elected branch and the jar sha256. *Not*
   a licence-override key: same versioned-purl, security-reviewed,
   void-on-bump effect, with no fourth policy key or classifier input, and
   the index keeps the generator's text verbatim. *Not* jna's sources
   jar: it has the Java only, not the C of the bundled `libjnidispatch`,
   so it is not complete source under the LGPL branch. U5 pins the
   literal result, U6 the entry and its security review.
2. **jaxb-api 2.2.12: OR, CDDL-1.1 elected, source shipped.** Pom:
   `CDDL 1.1` and `GPL2 w/ CPE`, both to `CDDL+GPL_1_1.html`, i.e.
   `CDDL-1.1 OR GPL-2.0-only WITH Classpath-exception-2.0`. CDDL 3.1
   still requires the Source Code form of covered files to be made
   available and recipients told how; the GPL branch needs it as well, so
   no branch removes it. Met by shipping the exact sources jar: U7 adds a
   `maven` kind (N5), key `maven:javax.xml.bind:jaxb-api@2.2.12`, file
   `jaxb-api-2.2.12-sources.jar` from `repo1.maven.org` (joins N4
   `hosts`), checked by Maven Central's published `.sha1` (as temurin's
   `.sha256.txt`). *Confirm at U7* the jar is published; if not, back to
   the architect (Q61 fails closed). *Not* an exemption with an "Upstream
   source" pointer: for an offline bundle that is the judgment PSC-15
   option 1 avoids. No special case: the N8 token rule makes it
   GPL-family and lists it unparsed. U5 (rule), U7 (lock), U9 (index).
3. **javassist 3.30.2-GA (found here):** syft's folded id holds
   `...gnu.org-licenses-lgpl-2.1.html...`; the developer's list missed it
   (its selection was case-sensitive). Pom: MPL 1.1, LGPL 2.1, Apache 2.0
   (OR). As jna: Apache-2.0 elected, `exempt` at U6. U5's ids are tested
   lower- and mixed-case.
4. **neo4j NOASSERTION: confirmed to the U4 report, by rule, not a list.**
   20 rows: 18 maven jars, `pkg:generic/oracle/openjdk` and the `pkg:oci`
   root. The report excludes only the package the document DESCRIBES (the
   image itself). openjdk is also an `always` (temurin) match, so it needs
   source anyway; `jrt-fs@21.0.12.1` is the JDK's jar. The six Neo4j-org
   jars at other versions (4 `org.neo4j.bolt`@12.0.0, `cypher-dsl`@2024.2.0,
   `com.neo4j` fleet-management@1.2.0) do not map to the `neo4j` entry
   (N9: the image's Neo4j version only); security reviews them as listed,
   with the 43 URL-folded ids (EE4J `EPL-2.0 OR GPL-2.0 WITH
   Classpath-exception-2.0`, Eclipse, Jetty) the token rule does not flag.
5. **ke-app NOASSERTION: to the U4 report; no cargo default.** The
   ke-app figures in `u3/gpl-family-packages.md` (700/83/505, 493
   `pkg:cargo`) came from a stale pre-U0 image (security, U3); the tester
   regenerates them. The ruling is conditional: it applies to
   whatever the regenerated ke-app SBOM shows: every unlicensed row, cargo
   or not, goes to the report. "Cargo means MIT/Apache" would hide a GPL
   crate, the case PSC-22 exists for; unknown stays unknown. To keep it reviewable,
   the report counts rows per purl type and names a row with no purl by
   SPDXID and name. How security checks crates is its call at U4; a
   finding that changes the outcome uses an `exempt` or source entry.
6. **Syft cache warning: set `XDG_CACHE_HOME: /tmp/cache`** (literal, in
   `sbom`'s environment; U4, a compose change, U3's file untouched). The
   N1 *confirm at GREEN* fallback triggers: syft tried `/.cache/syft`,
   outside `/out` and `/tmp`. I-2 allows it at or under `/tmp`; the value
   is ADR-KE-013 am. 1's for grype. *Not* `SYFT_CACHE_DIR`: a ninth
   `SYFT_*` key U2's pin does not know. The cache stays empty (lookups
   off) and dies with the tmpfs. A34 not needed (a container-side literal,
   no host path or argv); the orchestrator's call. *U4 review B1:* the key
   was inert, because the tmpfs took the image's 0755 `/tmp`; the tmpfs
   gains `mode=1777` (*N1 amendment, U4 rework*).

### N8 amendment, U5 (architect, 2026-10-24)

Records orchestrator rulings 1-7 for U5 (security U4 L-4, L-5, I-4; review
U4 R2; U4b review N6, N7; U4b security L-1, I-2). N8 and N8a stand except
where a bullet here says otherwise; the *precision* bullets are the
architect's and leave the rulings unchanged.

**1. Classifier input (L-4, both parts).**
- Two "missing" predicates, never mixed:
  - *Report* (U4, `_missing`, unchanged): absent, `null` or wrong type, or
    exactly `""`/`NONE`/`NOASSERTION`, or hash-only. `unlicensed_report`
    keeps it, so its membership and counts do not move.
  - *Classifier* (U5, a new predicate; `_missing` is not edited): absent,
    `null` or wrong type (N8 type rule), or exactly `""`/`NONE`/
    `NOASSERTION` (case-sensitive, no strip). A hash-only field is *set*;
    its ids are unknown. This supersedes N8 l.806-815 ("such a value is
    *missing* too") for the classifier only.
- Input selection reads N8 l.781-786 with the classifier predicate:
  declared; else concluded; else the set `licenseInfoFromFiles` entries.
  Both expression fields set: needs source if either does (N8 l.786).
- So declared `<hash>` + concluded `MIT`: needs = true, unidentified. It is
  not in the U4 report (concluded is set there): the L-4 gap, closed. A
  package whose fields are all hash-only is in the U4 report *and*
  classified needs = true, unidentified, `unlicensed` = false.
- `NONE` and `NOASSERTION` as a leaf inside an expression (`<hash> OR
  NOASSERTION`, `MIT AND NOASSERTION`, `(NOASSERTION)`): unknown id, exact
  and case-sensitive like the hash rule; needs = true for that leaf, and
  the package is unidentified. `MIT OR NOASSERTION`: needs = false (MIT
  elected), still unidentified.
- *Precision, WITH:* `needs(X WITH e) = needs(X)` for the leaf X (N8 says
  `gpl(X)`; an unknown X fails closed). The exception id is not read.
- *Precision, grammar:* SPDX 2.3 Annex D precedence, `WITH` > `AND` > `OR`;
  parentheses override. So `MIT OR GPL-2.0-only AND Apache-2.0` is
  `MIT OR (GPL-2.0-only AND Apache-2.0)`: needs = false. A leaf is a
  maximal run of characters other than whitespace and parentheses (no
  charset check; the token rule covers odd ids). Unparseable: empty,
  unbalanced parentheses, two leaves or two operators adjacent, an
  operator first or last, `WITH` not between a leaf and an exception id.
- *Precision, "gpl as a word":* the N8a token rule applied to the whole
  text (lower-case, split on `[^a-z0-9]+`, any token matches
  `^(a|l)?gpl(v?\d+)?$`). It catches every `\bgpl\b` hit and also `LGPL`,
  `GPLv2`, `gpl_2`: fail closed.

**2. API (fixed by the orchestrator; the tester's RED uses these names and
the developer keeps them).** All in `scripts/sbom_check.py`, standard
library, no I/O (N3). The `index` subcommand (U9) is the only caller.
- `licence_input(pkg: dict) -> str | None`: N8 input selection with the
  classifier predicate; None when all three are missing (unlicensed).
  *Precision, the string:* the selected parts joined with ` AND `, each in
  parentheses only when there are two or more: declared alone; or
  `(<declared>) AND (<concluded>)` when both are set and differ (equal: one
  copy); or the set `licenseInfoFromFiles` entries in list order.
- `is_gpl_id(id: str) -> bool`: lower-case, strip a leading `licenseref-`
  (a superset of stripping `LicenseRef-` first), then N8's anchored
  pattern, or else the N8a token rule.
- `needs_source(expr: str) -> tuple[bool, dict]`: parses (operators
  case-insensitive); `info` has at least `unparsed` (unparseable text, or a
  leaf only the token rule caught, or a `LicenseRef-` leaf containing
  `http`, case-insensitive) and `unidentified` (a hash leaf, by
  `fullmatch`, or a `NONE`/`NOASSERTION` leaf). Unparseable text needs
  source iff the token rule hits it; it is also `unidentified` if
  `HASH_ID_RE` is found in it (listing only).
  - *Correction (orchestrator ruling, 2026-10-24), supersedes "iff ...
    (listing only)" above:* unparseable text needs source if the token
    rule finds `gpl` **or** the text contains a `LicenseRef-[0-9a-f]{64}`
    id (search, case-sensitive); such text is both `unparsed` and
    `unidentified`. Fail closed: `Public Domain OR <hash>` needs source.
- `classify_package(pkg: dict) -> dict`: keys `needs`, `expression`
  (`licence_input`), `unlicensed`, `unparsed`, `unidentified`, `purl`
  (`_purl`), `spdxid`, `name` (raw values; cleaned only when printed, 7).
  *Precision:* `needs` is `any(needs_source(part))` over the parts
  `licence_input` joined, and the info flags are OR-ed over them. This
  equals `needs(AND)` when every part parses, and stops one unparseable
  part from hiding a hash or GPL part beside it. Unlicensed: `needs` false,
  `expression` None, both flags false.
- `classify_document(image: str, doc: dict, always: list[dict]) ->
  list[dict]`: one row per package in document order, DESCRIBES roots
  (`_roots`) excluded; rows whose SPDXID `always_matches(image, doc,
  always)` flags get `needs = True`; every row carries `always` (bool).
  `always_matches`' problems are not returned here; U9's `index` reports
  them (exit 1).

**3. Generator digest (I-4).** A bump of the syft image digest
(`docker-compose.sbom.yml`) is a PSC-22 re-review trigger: the hash rule is
case-sensitive to syft's spelling. The analyst amends PSC-22's wording with
U6.

**4. `tree` (U4b review N6).** `tree_listing` gives path -> (type, mode,
uid, gid, size, link target), size the member's for regular files, 0
otherwise. *Precision:* tar writes a hard link with size 0, so one
normalisation runs on both listings before the compare: a `hardlink`
becomes `file` with its target's size (target path through `_rel`); a
target absent or not a regular file leaves it `hardlink`, so it differs
(fail closed). Evidence-only subcommand.

**5. Scanner exemption (U4b review N7, security I-2).** The Dockerfile
exact-line exemption in `tests/hardcoded_scan.py` also requires the previous
physical line, right-stripped, not to end in `\` (the first line has none).
Security re-reviews it as PS-1.2.

**6. Smoke no-plugin step (U4b security L-1).** Drop `-xdev`; prune
`/proc`, `/sys` and `/dev` (`find / \( -path /proc -o -path /sys -o -path
/dev \) -prune -o \( <today's tests> \) -print`). Wanted output and
fail-closed handling unchanged (any other match, or a non-zero exit, FAILs).

**7. Escaping and anchors (security L-5, review R2).** Every SBOM-sourced
string printed outside `report_lines` goes through `_clean`: `validate`'s
SPDXID failures, `drift_problems`' Debian names (unquoted by `_named`) and
CPython version, `psycopg_problems`. Every regex anchored with `$`
(`SPDXID_RE`, `NAMESPACE_RE`, `RFC3339_UTC`, and `NAME_RE`/`SHA_RE` on argv)
is used with `fullmatch`. *Precision:* prefix patterns (`PURL_RE`,
`PURL_TYPE_RE`, the `CPython x.y.z:` header) keep `match`.

**Loop mode.** The classifier loop stays `fast` (N15). Items 5 and 6 touch
`tests/` and `scripts/smoke.sh`; the smoke step runs only in `full`, so
item 6's GREEN is a `full` run (the commit gate's run suffices).

**First failing tests (adds to N15's U5 table).**
- declared `<hash>`, concluded `MIT`: needs, unidentified, not unlicensed;
  all fields hash-only: same, and `unlicensed_report` still lists it;
- `<hash> OR NOASSERTION`, `MIT AND NOASSERTION`, `<hash> WITH
  Classpath-exception-2.0`: needs, unidentified; `MIT OR NOASSERTION`: no
  source, unidentified;
- precedence: `MIT OR GPL-2.0-only AND Apache-2.0` no source;
  `GPL-2.0-only OR LGPL-2.1-only` needs; `GPL v2` unparsed, needs;
- named LicenseRef: `LicenseRef-GPL-2.0-only` needs, not unparsed;
  `LicenseRef-Public-Domain` no source, not unparsed;
- `licence_input` strings above; a non-string declared falls to concluded;
- `classify_document` skips the root, and `always` forces needs;
- `validate` rejects SPDXID `"SPDXRef-a\n"` and prints it escaped; `tree`
  size and symmetric hard link; scanner continuation line; smoke text has
  no `-xdev` and prunes the three.

**Tester pins accepted (orchestrator, 2026-10-24).**
- Junk text is read by the token rule: `the LGPL, version 2.1` is
  unparseable and needs source (token `lgpl`), listed unparsed.
- `tree` (item 4): a hard link keeps its own mode (and uid, gid) and takes
  its target's size.
- Scanner (item 5): blanks after a trailing `\` still make a continuation
  line (the right-strip), so the next line is not exempt.
- `needs_source` never raises on any string: deeply nested parentheses must
  not raise (no `RecursionError` escapes).

**Rework round 1 (orchestrator rulings, 2026-10-24).** From U5 review B1-B3
(`u5/review.md`) and security L-1..L-4 (`u5/security.md`). Every rule fails
closed; no real row has these shapes today. Supersedes the bullets above
where they conflict.
1. *Unknown leaves, any case (B2, security L-2).* In the classifier a leaf
   equal to `NONE` or `NOASSERTION` under ASCII case-fold (`none`,
   `NoAssertion`) is unknown: needs = true, unidentified (item 1 said
   case-sensitive). In unparseable text, any run between whitespace or
   parentheses equal to either, case-insensitively, counts like a hash id:
   needs source, unidentified. The U4 report rule (`_missing`) and the
   classifier's whole-field predicate stay exact and case-sensitive, so a
   whole field `none` is *set* and its one leaf is unknown.
2. *Wider token rule (security L-1).* A hit is any lower-cased token
   (split on `[^a-z0-9]+`) *containing* `gpl` (`gplv2orlater`, `lgpl2`;
   it subsumes N8a's `^(a|l)?gpl(v?\d+)?$`), or the consecutive tokens
   `general public licen[cs]e` (optionally after `lesser`, which the
   match does not need), or the token `affero`. A hit only by the token
   rule is listed unparsed, as before. Applies in `is_gpl_id`, the leaf
   test and the unparseable-text fallback.
3. *Non-ASCII (security L-3, review N2).* An expression with any non-ASCII
   character (`not expr.isascii()`) needs source and is listed unparsed.
   `AND`/`OR`/`WITH` are recognised only as ASCII letters, compared by
   ASCII case-fold; never `str.upper()` on arbitrary text.
4. *Exception id read (security L-4, review N1).* In `X WITH e`, if `e` is
   GPL-family by the pattern or the token rule (`MIT WITH GPL-3.0-only`),
   the leaf needs source and is listed unparsed (malformed). Otherwise
   `needs(X WITH e) = needs(X)`, unchanged.
5. *Drift success line (B3, L-5a).* `drift`'s success line takes the
   CPython versions from the same non-namespaced `pkg:generic/python` set
   that `drift_problems` checks, through `_clean`.
6. *Per-part rule pinned (B1).* Tests: declared `Public Domain`, concluded
   `MIT AND NOASSERTION` gives needs, unidentified; the same with the two
   values as `licenseInfoFromFiles` entries. The tester's note calling
   the joined text "an equivalent mutant" is wrong; the controls gain the
   row.
7. *U9 (review N5).* `index` never re-derives `needs` from `expression`:
   `needs` is the per-part result `classify_package` returns, and
   `expression` is a record only.
8. *No change:* review N4 (a whitespace-only field is set; no strip, per
   SPDX), the heredoc half of I-2, review N8 (CI flake risk, noted for
   U11), I-2 `/dev/shm`.
9. *Plural (orchestrator, 2026-10-24):* rule 2's phrase matches `general public licen[cs]es?` (plural included).
10. *Unknown exception (orchestrator, 2026-10-24):* in `X WITH e`, an `e` that is a hash id or `NONE`/`NOASSERTION` (any case) is unknown: the leaf needs source and is unidentified.

**Rework round 2 (orchestrator rulings, 2026-10-24).** From U5 review
re-check R1-B1, R1-N1, R1-N2 (`u5/review-r1.md`; security PASS,
`u5/security-r1.md`). Fail closed. Effect on the 7572 real leaves: none
(all already fullmatch (a)).
1. *Leaf charset (R1-B1).* Every leaf, the exception id after `WITH`
   included, must fullmatch `(DocumentRef-[A-Za-z0-9.-]+:)?[A-Za-z0-9.-]+\+?`.
   Any other leaf (`MIT,NOASSERTION`, `MIT/NOASSERTION`, `"NOASSERTION"`,
   `LicenseRef-<hash>;`) makes the whole text unparseable, so it takes the
   token-or-unknown fallback. Supersedes item 1's "no charset check". Rule
   3 of round 1 (non-ASCII needs source) still applies first.
2. *Unknown-run split.* `_unknown_in_text` splits runs on any character
   outside `[A-Za-z0-9.+:-]`, as well as on whitespace and parentheses
   (so `MIT,NOASSERTION` yields `NOASSERTION`).
3. *DocumentRef prefix.* `_unknown_id` accepts an optional
   `DocumentRef-[A-Za-z0-9.-]+:` prefix on hash ids and on
   `NONE`/`NOASSERTION` (any case), in leaves and in fallback runs; e.g.
   `DocumentRef-x:LicenseRef-<hash>` parses as a leaf and is unknown.
4. *http exception (R1-N1).* A `LicenseRef-` exception id containing
   `http` is listed unparsed, like any http `LicenseRef-` leaf.
5. *Tests (R1-N2).* Non-ASCII test characters are written as `\u`
   escapes in the test source.

**Rework round 3 (orchestrator rulings, 2026-10-25).** From U5 review
re-check R2-B1, R2-B2 (`u5/review-r2.md`) and security R2-L1
(`u5/security-r2.md`): a trailing `+` or a `:`/`+` joiner hid an unknown
id. Fail closed. Real-row effect: none (reviewer and security simulated).
1. *Run split.* `RUN_SPLIT_RE` is `[^A-Za-z0-9.-]+`: `+` and `:` split
   runs too (supersedes round 2 item 2's `[A-Za-z0-9.+:-]`). So
   `MIT:NOASSERTION` and `MIT+NOASSERTION` (unparseable by round 2 item 1)
   yield the run `NOASSERTION`. A run therefore never carries a
   DocumentRef prefix; round 2 item 3 still applies to leaves.
2. *Trimmed bare id.* `_unknown_id` strips a `DocumentRef-...:` prefix,
   then trims leading and trailing `.`, `-` and `+`, and tests what is
   left (exact 64-hex hash id, or `NONE`/`NOASSERTION` in any case). So
   `NOASSERTION+`, `NOASSERTION.`, `-NONE` and `DocumentRef-x:NONE+` are
   unknown.
3. *Hash anywhere.* A leaf or run in which `HASH_ID_RE.search` finds a
   hash is unknown (`LicenseRef-<hash>.x`, `xLicenseRef-<hash>`,
   `LicenseRef-<hash>+`).
4. *Unchanged:* 65 hex digits are not a hash; the exact 64 rule holds.
5. *Pinned near-misses stay ordinary:* `see NONE.txt here`, `NOASSERTIONS
   apply`, `MIT-NOASSERTION` (one run; trimmed, still `MIT-NOASSERTION`)
   and `LicenseRef-NONE` (`NONE` is not the whole trimmed bare id).
6. *Rulings 3 and 4 reconciled (orchestrator, 2026-10-25):* leaves and runs use `HASH_IN_RE = LicenseRef-[0-9a-f]{64}(?![0-9a-f])`, so a 65-hex id stays ordinary; unparseable text keeps round 0's whole-text `HASH_ID_RE.search` (so `Public Domain <65 hex>` still needs source, fail closed); `HASH_ID_RE` and the U4 report are untouched.
7. *Listing of decorated unknowns (orchestrator, 2026-10-25):* decorated unknown leaves (`NOASSERTION+`, `<hash>.x`) are listed through "unidentified"; no additional "unparsed" flag is required.

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
 "unparsed": [...], "unidentified": [...]}
```
- `path` is relative to the installed root (`app/` in the bundle).
- `not-shipped` exists only when `set` is `sample`; a `full` bundle with
  any `not-shipped` component fails. Mapping SBOM package to key: deb by
  the purl's `upstream` qualifier (source name, and version when it
  differs) else the package name/version; apk by `upstream` (origin);
  `pkg:maven/org.neo4j/*` and `com.neo4j/*` at the image's Neo4j version
  to the `neo4j` entry; the JVM package, and `pkg:maven/jrt-fs/jrt-fs` (the
  JDK's own jar, security M-2), to `temurin`; pypi by name; any
  other `pkg:maven/<group>/<artifact>@<version>` to `maven:` (N8a).
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
  psycopg-c (ke-app); glibc (`upstream=glibc`, every Debian image); and
  in `ke-app`, libldap-2.5-0 (`upstream=openldap`) and libsasl2-2 and
  libsasl2-modules-db (`upstream=cyrus-sasl2`).
  - *U4 ruling 2.* This supersedes this note's earlier text, which called
    these three "ordinary dpkg packages under the classifier". PSC-22's
    last bullet requires them covered "whatever licence the generator
    reports", and that is `always`. libpq5's other dependencies stay
    under the classifier. libkeyutils1, for example, is LGPL by its
    copyright file.
  - *Flag (orchestrator).* `postgres` ships the same three binaries
    (U3 evidence). There, syft's AND expressions carry `GPL-2.0-only`,
    `GPL-3.0-or-later` and similar ids, so the classifier flags them. U7's
    one entry per source package (`openldap`, `cyrus-sasl2`) covers both
    images. `postgres` `always` entries for these three are optional
    belt-and-braces; that call is not the architect's.
  - *U4 rework (security M-1, M-2, L-1): new `always` entries.* Each was
    checked against the U3 SBOMs (`u3/sboms/*.pkgs.tsv`):
    | image | match | catalogued rows |
    |---|---|---|
    | ke-app, postgres | `upstream=gcc-12` | gcc-12-base, libgcc-s1, libstdc++6 (12.2.0-14+deb12u1) |
    | neo4j, phoenix | `upstream=gcc-14` | gcc-14-base, libgcc-s1, libstdc++6 (14.2.0-19), and libgomp1 in phoenix |
    | neo4j | `pkg:maven/jrt-fs/jrt-fs` | jrt-fs@21.0.12.1, the JDK's `/opt/java/openjdk/lib/jrt-fs.jar` |
    | valkey, ke-gateway | `upstream=busybox` | busybox-binsh, ssl_client |
    | valkey, ke-gateway | `upstream=apk-tools` | libapk |
    The exact-name busybox and apk-tools entries stay: those packages carry
    no `upstream` qualifier. After U4b every `neo4j` key reads `ke-neo4j`
    (N16).
  - *How each is met (U6/U7).*
    - **GCC runtime: ship the source, `deb` kind (U7).** Lock keys
      `deb:gcc-12@12.2.0-14+deb12u1` and `deb:gcc-14@14.2.0-19` by the
      normal snapshot route; no `exempt` entry. *Why not the GCC Runtime
      Library Exception:* it lets Target Code "formed by combining the
      Runtime Library with Independent Modules" be conveyed on any terms.
      The images carry the runtime itself (`libgcc_s.so.1`,
      `libstdc++.so.6`, `libgomp.so.1`) as stand-alone object code in
      Debian packages. Whether the exception reaches that is a legal
      reading. Shipping the source needs no such reading, as for jaxb-api
      (N8a 2). It also needs no new kind, host or review form: glibc,
      openldap and cyrus-sasl2 take the same route. *Cost:* each gcc
      `.orig.tar` is large (estimate 80-100 MB; U7 measures), in the full
      set only. The sample takes the smallest `deb`, so verify and CI are
      unchanged. U11's floor re-derivation counts it. If the human rules
      the size unacceptable, the fallback is one `exempt` entry per
      versioned purl and image, reviewed by security, with a reason that
      cites the exception. That is the human's call, not a default.
    - **jrt-fs: the Temurin entry (U9 mapping, N9).** No lock entry and
      no exemption: the `temurin:` jdk-sources archive is its source. N9
      maps `pkg:maven/jrt-fs/jrt-fs` to `temurin`. U9 checks that its
      version is the image's Temurin build, else it fails naming the purl.
    - **busybox-binsh, ssl_client, libapk: the existing apk entries.**
      The apk route keys by origin (`apk:busybox@<v>`,
      `apk:apk-tools@<v>`), and N9 maps by `upstream`, so no new lock
      entry is needed.
  - *Arrival (U4 ruling 1).* `always` arrives at U4, alone in the file,
    with entries shaped `{"image", "match", "why"}`. `match` is a
    versionless purl or `upstream=<source>`, the latter matched on the
    qualifier's name before any `@`. U6 adds `hosts` and `exempt` and the
    exactly-three-keys schema test below. An `always`
  entry with no matching package in its image fails ("expected component
  not catalogued"): the generator cannot hide one by missing it. An exemption
  names a versioned purl, so a version bump voids it and forces a new
  review. An exemption also carries a corrected licence: an OR the
  generator reported as AND, with the elected branch and the jar's own
  evidence in `reason` (jna, javassist; ruling 5, N8a). Schema test:
  exactly these three keys; `reason` non-blank; `reviewed` matches
  `^security \d{4}-\d{2}-\d{2}$`; purl has `@<version>`; no duplicates;
  hosts are lower-case DNS names with no wildcard; every lock URL host is
  in `hosts`.
- `NOTICE.md` (PSC-14) gains one section and one pointer:
  - "Base of `ke-app`":
    - the base reference, byte for byte from the `FROM` of
      `docker/app.Dockerfile`'s `runtime` stage (from U1 round 2; the last
      stage is `FROM scratch`, N10a);
    - CPython 3.12.x under `/usr/local`, SPDX `Python-2.0` (the stacked
      PSF/BeOpen/CNRI/CWI licence; `PSF-2.0` is only its top layer), ending
      with security's M-2 text: "`/usr/local/lib/python3.12/LICENSE.txt`
      inside the image holds that licence stack only. CPython also builds
      in third-party code under its own licences. CPython's own list of it
      (among them expat and libmpdec) is in
      `licenses/CPython-3.12-incorporated.txt`; the HACL* hash code (MIT)
      in `_md5`, `_sha1`, `_sha2` and `_sha3`, which that list omits, is in
      `licenses/CPython-3.12-HACL.txt`." (Round 3, L-9: the bullet names
      what each file holds and claims no complete set. This note's earlier
      "and the licences of the code CPython bundles" was wrong: M-2.);
    - the base's Debian 12 packages, plus libpq5 at `LIBPQ_VERSION` and
      the dependencies apt adds (N0), with their licences in
      `/usr/share/doc/*/copyright` and, where the bundle carries one, the
      image's SBOM (conditional wording until U3 ships SBOMs; L-1);
    - no pip: the shipped image carries neither the base's pip nor
      ensurepip's bundled pip wheel (human ruling 2026-10-23, superseding
      the keep-pip ruling; N10a). The pip bullet, its vendored-licence
      text and `licenses/Apache-2.0.txt`/`MPL-2.0.txt` go (L-2, L-2b, L-7,
      B4 are moot);
    - no uv.

    A static fast test pins the reference, the libpq pin, the CPython
    minor and the Debian release (parsed strictly from the reference, no
    default; review B1) to the Dockerfile. The image-side checks are U4's
    `full` SBOM test (review B3), on `ke-app`'s SBOM (`--scope
    all-layers`, so a pip file in any layer counts):
    - its dpkg names minus those in an SBOM of the pinned base (same `sbom`
      service, `--pull never`, on a `docker save` of the base that
      `offline_check.sh` pulls by digest first, outside the bundle: N1
      amendment, U4) equal the U1 test's `ADDED_PACKAGES` (read by `ast`,
      never imported);
    - it has no `pkg:pypi/pip` package, of any version (this replaces the
      pip-version check);
    - its CPython package version (syft's binary cataloguer; the exact
      purl is *confirm at GREEN*) equals the `X.Y.Z` on line 1 of
      `licenses/CPython-3.12-incorporated.txt` and of
      `licenses/CPython-3.12-HACL.txt`.
    A base, pin or apt change that moves any one fails U4 by name. A micro
    bump of the base between U1 and U4 is only caught at U4; N1 (no bundle
    before U3 and U9) means none ships meanwhile.
  - A pointer: "`THIRD_PARTY_NOTICES.md` says, in its "Source code"
    section, for each GPL-family component whether its source is in
    `sources/` of this bundle." The same block ends with security's L-6
    text (it replaces the M-1 sentence; true until U9 writes the section
    and after): "A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source
    code" section has no `sources/`, so it does not itself provide the
    source that a GPL-family licence requires." The committed file claims
    nothing per component, because the same file ships in sample and full
    bundles. U9 restates the paths per I-3 (N10a).
  - "Licence texts" drops the Apache-2.0/MPL-2.0 paragraph and gains one
    with no `docs/` path (L-8): "`licenses/CPython-3.12-incorporated.txt`
    is the "Licenses and Acknowledgements for Incorporated Software"
    section of CPython 3.12.15's `Doc/license.rst`, unmodified, fetched
    over HTTPS from
    https://raw.githubusercontent.com/python/cpython/v3.12.15/Doc/license.rst;
    its header gives the fetched file's sha256." Round 3 (L-9) adds:
    "`licenses/CPython-3.12-HACL.txt` is the MIT licence header of
    `Modules/_hacl/Hacl_Hash_SHA2.c` in CPython 3.12.15's release tarball
    https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz,
    unmodified; its header gives the tarball's sha256." (Facts fixed here;
    the analyst owns the wording.) Both files are git-added at commit (I-4).
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

### N10a. U1 round 2: `ke-app` ships no pip

Probe, 2026-10-22, pinned base, `--network none`, label `ke.scratch=u1r2`
(transcript for the orchestrator to file as `u1/r2-pip-probe.txt`: the
architect's report names it):
- `ensurepip/_bundled/` holds `pip-25.0.1-py3-none-any.whl`, 1,841,526 B:
  the same vendored code, so it goes too. Also present: `site-packages/pip`,
  `pip-25.0.1.dist-info`, `/usr/local/bin/pip`, `pip3`, `pip3.12`.
- `python -m pip uninstall -y pip` removes the package, dist-info and all
  three scripts (pip's RECORD); only the wheel is left.
- A scratch image doing both deletes in a layer on the base, then `docker
  save`: the base layer still holds 536 pip entries, the new layer only
  `.wh.` whiteouts. So a delete in any stage `FROM` the base still ships
  pip in the bundle tar, and syft (`--scope all-layers`) still finds it.
- The same, `FROM scratch` + `COPY --from=<stage> / /`: one layer, 0 pip
  entries; setuid/setgid set, hardlinks (4), `dpkg -l` (110 lines) and
  `/tmp` 1777 unchanged; `venv --with-pip` then fails (rc 2).

Decision:
- **Command:** `python -m pip uninstall -y pip`, not `rm -rf` globs:
  RECORD is the exact list (scripts and dist-info too), nothing hand-kept,
  and it fails the build if pip is gone, so a base that drops pip shows
  by name. The wheel: `rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl`
  with no `-f`, failing the same way. `ensurepip` and `venv --with-pip`
  stop working; the engine uses neither (uv builds the venv in `builder`).
  The `ensurepip` module itself stays (stdlib, under `Python-2.0`).
- **Separate RUN**, after the libpq5 RUN, in stage `runtime`: U0's
  apt-RUN rules keep their meaning, and layers inside `runtime` do not
  ship, because the last stage flattens it.
- **Shape** (`builder` and `uv` unchanged):
  ```
  FROM python:3.12-slim-bookworm@sha256:<builder's> AS runtime
  ARG LIBPQ_VERSION
  RUN apt-get update \
   && apt-get install -y --no-install-recommends libpq5=${LIBPQ_VERSION} \
   && rm -rf /var/lib/apt/lists/*
  RUN python -m pip uninstall -y pip \
   && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl

  FROM scratch
  COPY --from=runtime / /
  ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
      LANG=C.UTF-8 \
      PYTHONUNBUFFERED=1
  COPY --from=builder /opt/venv /opt/venv
  COPY --from=builder /app /app
  WORKDIR /app
  RUN useradd --no-create-home --uid 10001 ke
  USER ke
  CMD ["python", "-m", "engine.api"]
  ```
  `PATH` is spelled out (scratch has no `$PATH`). The base's `GPG_KEY`,
  `PYTHON_VERSION` and `PYTHON_SHA256` are build metadata; nothing in the
  repo reads them, so they are not re-set. Amends ADR-KE-013 am. 1 D10
  ("final FROM is the base"); D10's reason (venv interpreter paths) holds,
  as `runtime`'s FROM is the builder's byte for byte.
- **Existing static tests that must follow the shape** (tester, fast):
  `test_psycopg_c.app_runtime_problems` checks the stage the last stage
  copies `/` from, not `stages[-1]`, and the last stage has no apt RUN;
  `pin_base_problems` is unchanged (builder plus `runtime`). D10 test 1
  (`test_image_scan`): last stage `FROM scratch`, first instruction
  `COPY --from=runtime / /` (once), `runtime`'s FROM equals the builder's,
  other copies only `/opt/venv` and `/app` from `builder`.
  `test_dockerfiles_pin_base_images_by_digest` allows `scratch` (it pulls
  nothing). `test_notice_ke_app` reads the base from `runtime`.
- **New static test** (U1): `runtime` holds exactly that pip RUN after the
  libpq5 RUN; the last stage starts with `COPY --from=runtime / /`; its
  `PATH` starts `/opt/venv/bin:` and has `/usr/local/bin`; `LANG=C.UTF-8`.
- **Smoke `no pip`** (live `api`, after the psycopg step, M-1 pattern):
  ```
  pip_out="$(compose exec -T api /usr/local/bin/python3 -I -c 'import importlib.util as u, os, re
  h = sorted(os.path.join(d, n) for r in ("/usr", "/opt") for d, ds, fs in os.walk(r)
             for n in ds + fs if re.fullmatch(r"pip(3(\.[0-9]+)?)?|pip-.+\.(dist-info|whl)", n))
  if u.find_spec("pip") and not h:
      h = ["pip (importable)"]
  print(",".join(h).replace(" ", "_") or "-")')" || FAIL "the check in api failed"
  [ "$pip_out" = - ] || FAIL "pip in api: $pip_out"
  ```
  Round 3 (B6, I-6): the whole captured output is compared, with no
  `read` and no default. Empty output fails (orchestrator ruling
  2026-10-23; the old `${pip_hits:--}` was mutant S10), and so does `-`
  followed by any second line (I-6: `read -r` kept only line 1). `$(...)`
  strips trailing newlines only, so `-` plus a newline still passes.
  The base interpreter, because the venv's `sys.path` omits the system
  site-packages, so `find_spec` there misses the base pip. The walk
  covers `/usr/local/bin/pip*`, the dist-info and the wheel. As in M-1 the
  container output is one token compared as a string with `-`: no `$(( ))`,
  no `eval`, no unquoted expansion; it is printed only inside a quoted
  message. On the unmodified base it prints all six paths (probe).
- **I-5 (follow-up, not U1):** the 156 stdlib `.pyc` files pip's run
  writes in `runtime` ship (root 0644, harmless); `python -B -m pip
  uninstall -y pip` would drop them, a later plan item's call.
- **CPython incorporated licences** (`licenses/CPython-3.12-incorporated.txt`):
  - Fetch: `curl -q --proto '=https' --tlsv1.2 --fail -o <empty dir>/license.rst
    https://raw.githubusercontent.com/python/cpython/v3.12.15/Doc/license.rst`
    (the Valkey `COPYING` route). Architect's probe fetch, 2026-10-22:
    54,130 B, sha256
    `341832873fd316a37927e79385093fbbfd40a467428480835fe435a80cadf4e5`.
  - Extract: from the one line exactly `Licenses and Acknowledgements for
    Incorporated Software` (it must occur once, followed by its `=`
    underline) to the end of the file, bytes unchanged, reST kept
    (`sed -n '/^Licenses and Acknowledgements for Incorporated Software$/,$p'`).
    Probe: 808 lines, 38,036 B, sha256 `d4f3b214...40698a`; 20 subsections
    from Mersenne Twister to asyncio, with expat and libmpdec.
  - Header (four lines, then a blank line, then the extract):
    ```
    CPython 3.12.15: "Licenses and Acknowledgements for Incorporated Software"
    Source: https://raw.githubusercontent.com/python/cpython/v3.12.15/Doc/license.rst
    Source sha256: <64 hex of the fetched license.rst>
    Extract: from that heading line to the end of the file, unmodified.
    ```
    The fast test checks the shape, that the URL's tag equals line 1's
    version, the minor equals the base's `3.12`, and the extract starts
    with the heading and its underline. U4 checks the micro (N10).
  - Q48 form: no upstream checksum for the file, so the first fetch is
    trusted and recorded. Security's second fetch is
    `https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz`,
    whose sha256 must equal the pinned base's `PYTHON_SHA256`
    (`c2c43219...94fd5a`, read offline with `docker inspect` of the
    digest); `Python-3.12.15/Doc/license.rst` in it must match the
    header's sha256, and the re-extract must `cmp` equal. Recorded as
    "no upstream checksum; TOFU, confirmed by security from the release
    tarball anchored to the base's PYTHON_SHA256".
- **CPython HACL* notice** (`licenses/CPython-3.12-HACL.txt`; L-9, round
  3). v3.12.15's `license.rst` has 0 `HACL` hits, yet `_md5`, `_sha1`,
  `_sha2`, `_sha3` are built from `Modules/_hacl/` (MIT).
  - Source: member `Python-3.12.15/Modules/_hacl/Hacl_Hash_SHA2.c` of
    https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz, sha256
    `c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a`
    (equals the base's `PYTHON_SHA256`: Q48 anchor, no TOFU). Fetch and
    untar as in security's second fetch: HTTPS, one regular-file member
    into an empty directory, nothing executed. Probe, 2026-10-22: member
    36,131 B, LF only, sha256 `30638efb...201b31`.
  - Extract rule: from line 1 of that member to its first line that is
    exactly ` */` (space, `*`, `/`), bytes unchanged:
    `sed -n '1,/^ \*\/$/p'`. Checkable: line 1 is exactly `/* MIT License`,
    the extract holds `HACL* Contributors` and ends at the ` */` after
    ` * SOFTWARE.`. Probe: 23 lines, 1,207 B, sha256
    `998ce04fb8ad9dedb0bc1b44938f8c3dcf1089780fa105ce1c8c30fb5554d78c`;
    13 of the 20 `.c`/`.h` files under `Modules/_hacl/` carry this same
    block byte for byte.
  - Header (four lines, then a blank line, then the extract; `tail -n +6`
    must `cmp` equal the re-extract):
    ```
    CPython 3.12.15: HACL* licence header (MIT), Modules/_hacl/
    Source: Python-3.12.15/Modules/_hacl/Hacl_Hash_SHA2.c
    Tarball: https://www.python.org/ftp/python/3.12.15/Python-3.12.15.tar.xz
    Tarball sha256: c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a
    ```
    Fast test: this shape; line 1's version equals the incorporated
    file's line 1 and the `Source:`/`Tarball:` versions; minor `3.12`;
    sha256 is 64 lower-case hex; the extract's first line is
    `/* MIT License` and its last ` */`. U4 checks the micro (N10). Security
    re-fetches once at GREEN and `cmp`s.
  - Open for security (not designed here): the other 7 files differ. Five
    KaRaMeL headers under `Modules/_hacl/include/krml/` say "Licensed
    under the Apache 2.0 License" (INRIA and Microsoft); the probe did not
    settle which of their code is compiled in. NOTICE's wording above
    claims no complete set, so it stays true either way.
- **I-3 (U9):** `sources/` lives at `app/sources/`; the bundle root and
  `app/` both carry NOTICE.md and THIRD_PARTY_NOTICES.md, and install
  publishes `app/` as the install directory. One identical text in every
  copy: the Source code section, and NOTICE's pointer, say once "Paths
  here are relative to the bundle's `app/` directory, which install
  publishes as the install directory", then write `sources/`. U9's test
  resolves `<app root of each copy>/sources/index.json` for the root copy,
  the `app/` copy and the installed copy.

### N10 amendment, U6 (architect, 2026-10-25)

Orchestrator rulings for U6 (N15 row U6; N8a 1 and 3; review U5 r3
I-r3-1, security U5 r3 I-9), with the precision the developer needs.
Supersedes N8a 1's image name `neo4j` (it is `ke-neo4j` since U4b, N16)
and, for U6, N10's "every lock URL host is in `hosts`" (no lock until U7:
that check arrives with U7's lock test, not here).

**1. `exempt_matches` and `classify_document`.**
- `exempt_matches(image: str, doc: dict, exempt: list[dict]) ->
  tuple[list[str], list[str]]` in `scripts/sbom_check.py`: (flagged
  SPDXIDs, problems), the shape of `always_matches`; entries for other
  images are skipped.
- Match: the package's purl with its qualifiers (`?...`) and subpath
  (`#...`) removed equals the entry's `package` exactly, as a string
  (type, namespace, name and version; no percent-decoding, no case fold:
  the entry is written as syft writes the purl). A miss is a loud problem,
  never a silent pass, so literal comparison fails closed.
- Problems: an entry whose `package` is not a versioned purl without
  qualifiers or subpath (`PURL_RE` match, no `?`, no `#`) matches nothing
  and is `"<image>: exempt entry is not a versioned purl: <package>"`; an
  entry with no package at that purl is `"<image>: exempt entry matches
  nothing: <package>; the version moved or the package left: review
  again"` (void on bump). SBOM strings in problems go through `_clean`.
- `classify_document(image, doc, always, exempt=())`: every row gains
  `exempt` (bool). Choice: `always` wins inside the classifier and the
  conflict is U9's to refuse. A row flagged by both keeps
  `always: True, exempt: True, needs: True`; a row flagged by `exempt`
  only gets `needs = False`; `unparsed`, `unidentified` and `expression`
  are left as computed (the index keeps the generator's text verbatim,
  N8a 1). `classify_document` drops `exempt_matches`'s problems as it
  drops `always_matches`'s; U9's `index` calls both for problems and
  refuses a row with both flags ("`always` and `exempt` both match
  <purl>"). *Why not in `exempt_matches`:* it would need the always
  flags, coupling the two lists; one boolean pair on the row is enough.
- With the default `exempt=()` every U5 row is unchanged but for
  `exempt: False`.
- The ke-app libldap/libsasl2 rows (N15 notes, security u1 I-1) are
  `always` matches since U4 ruling 2, so an `exempt` entry for them would
  be the conflict above: none is written; U7's lock covers them.

**2. `hosts`: the N4 list, nine names.** `bundle_fetch.sh` (U8) refuses
any other host on any hop (N4).
- `snapshot.debian.org`: `deb`
- `gitlab.alpinelinux.org`: `apk` (APKBUILD and local patches at the commit)
- `distfiles.alpinelinux.org`: `apk` (upstream tarballs, Alpine's mirror)
- `github.com`: `neo4j` (tag tarball), `temurin` (release asset, first hop)
- `codeload.github.com`: `neo4j` (the tarball redirect target)
- `objects.githubusercontent.com`: `temurin` (release asset redirect target)
- `release-assets.githubusercontent.com`: `temurin` (release asset redirect target)
- `files.pythonhosted.org`: `pypi`
- `repo1.maven.org`: `maven` (N8a 2)

N4 names every kind's host; no new host is proposed. Two remarks. `apk`
upstream files come only from Alpine's mirror, never the upstream
project's own host, by N5's design (a file missing there fails closed,
Q61, and goes back to the architect at U7). The redirect targets stay
*confirm at GREEN* of U8 (N4); a host U8 finds is added by a design-note
amendment and a test change, never by the developer alone. The brief's
"github.com/adoptium" is the host `github.com`: `hosts` holds no paths.

**3. Schema test (U6, fast).** On `docker/source-policy.json`:
- exactly the keys `hosts`, `always`, `exempt`;
- `hosts`: a non-empty list of strings, no duplicates, each a full match
  of `[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}`
  (lower case, at least one dot, no scheme, port, path, wildcard or IP
  literal); and the set equals the nine of item 2 (a new host is a
  reviewed test change);
- `always`: unchanged (U4's `always_problems`);
- `exempt`: a list; each entry exactly the keys `image`, `package`,
  `reason`, `reviewed`; `image` a bundled image name (`bundled_names()`);
  `package` as in item 1; `reason` non-blank after strip and containing
  `sha256 ` followed by 64 lower-case hex, and the word `elected`;
  `reviewed` a full match of `security \d{4}-\d{2}-\d{2}` and a valid
  date (`date.fromisoformat`); no two entries with the same
  (`image`, `package`);
- fixture check: for each entry, `exempt_matches(image, ss.u3_doc(fixture),
  [entry])` flags at least one SPDXID and returns no problem. Fixture
  mapping: the reverse of `U4B_POLICY_NAME` (`tests/test_sbom_obligations.py`),
  so image `ke-neo4j` reads `tests/fixtures/sbom-u3/neo4j.pkgs.tsv`, every
  other image `<image>.pkgs.tsv`. The U3 neo4j list stands in for
  ke-neo4j (same rows, N16). jna and javassist sit in `var/lib/neo4j/lib`,
  not `products/` (`u4b/windows-tree-ke-neo4j.tvf.txt` l.7807, 7840), and
  `u4b/windows-ke-neo4j.pkgs.tsv` l.79, 113 hold the same purls;
- no fixture row is flagged by both `always` and `exempt` (the U9 conflict
  is caught at verify time on real data).

**4. The two entries (image `ke-neo4j`).**
- `pkg:maven/com.sun.jna/jna@5.15.0` (fixture l.113; syft: declared
  `NOASSERTION`, concluded `Apache-2.0 AND LGPL-2.1-only`). Reason facts:
  `META-INF/LICENSE` reads `SPDX-License-Identifier: Apache-2.0 OR
  LGPL-2.1`; Apache-2.0 elected; jar `jna-5.15.0.jar` sha256
  `a564158d28ab5127fc6a958028ed54279fe0999662c46425b6a3b09a2a52094d`.
- `pkg:maven/org.javassist/javassist@3.30.2-GA` (fixture l.79; syft's
  URL-folded MPL-1.1 / LGPL-2.1 / Apache-2.0 id). Reason facts: the pom's
  three `<license>` entries (MPL 1.1, LGPL 2.1, Apache 2.0) are an OR by
  Maven's POM reference; Apache-2.0 elected; jar `javassist-3.30.2-GA.jar`
  sha256 `eba37290994b5e4868f3af98ff113f6244a6b099385d9ad46881307d3cb01aaf`.
- Real-row test: `classify_document("ke-neo4j", <neo4j fixture>, always,
  exempt)` gives jna and javassist `exempt: True, needs: False`
  (javassist stays `unparsed: True`); every other row of every image
  equals its U5 value with `exempt: False`.
- *`reviewed` sequencing (flag).* The test checks the pattern, so the
  entries cannot go green before a value exists, and the value may only
  be written after security's review. So security's review of the two
  entries is a separate dispatch between the entries' RED and GREEN:
  security checks each `reason` against N8a's evidence and records PASS
  with its date in `docs/evidence/platform-sbom/u6/security-exempt.md`;
  the developer then writes `security <that date>` (expected
  `2026-10-25`). No placeholder value is committed or made to pass. The
  U6 gate audit by security still follows on the integrated diff.

**5. I-r3-1: separated keyword segments (U6's first test row).**
In `_unknown_id`, after the DocumentRef strip and round 3's trim of
`.`, `-`, `+`: if the trimmed bare id is ASCII and does not start with
`licenseref-` under ASCII case fold, it is unknown when any segment of
it split on `.` and `-` equals `NONE` or `NOASSERTION` under ASCII case
fold. The hash rule and the whole-id rule are unchanged. `+` cannot sit
inside a parsed leaf (`LEAF_RE`) and splits runs (`RUN_SPLIT_RE`), so
`.` and `-` are the only separators needed. The name in a
`DocumentRef-NONE:` prefix is not a licence and is ignored
(`DocumentRef-NONE:MIT` is bare `MIT`, ordinary). Because `_unknown_id`
also serves fallback runs and `WITH` exception ids, the rule applies
there too (fail closed).
- Unknown (needs, unparsed, unidentified): `NOASSERTION.NONE` (T,F,T),
  `NOASSERTION-2.0` (T,F,T), `MIT-NOASSERTION` (T,F,T), `MIT AND
  NONE.NONE` (T,F,T, security I-9), `none-mit` (T,F,T),
  `DocumentRef-x:NONE-1` (T,F,T).
- Ordinary: `LicenseRef-NONE`, `licenseref-none`, `LicenseRef-NOASSERTION`,
  `DocumentRef-x:LicenseRef-NONE` (F,F,F); `NOASSERTIONS`, `NONEX-1`
  (F,F,F); `NOASSERTIONS apply` (F,T,F).
- *Pins that flip (recorded):* `MIT-NOASSERTION` (round 3 item 5; the
  orchestrator's ruling) and also `see NONE.txt here`, which the ruling
  did not name: its run `NONE.txt` has the segment `NONE`, so it goes
  from (F,T,F) to (T,T,T). Both pins sit in `tests/test_sbom_classifier.py`
  (l.626 and l.959-960 at d8ffa2d). The architect recommends the flip
  (fail closed; one rule for leaves and runs). Keeping `see NONE.txt
  here` ordinary would need the rule scoped to parsed leaves only, a
  second code path; flagged for the orchestrator's ruling.
- Real-row effect: none. Architect's simulation at d8ffa2d (the rule
  patched over `_unknown_id`, `classify_document` on all six U3 fixtures
  with the real `always`): 1015 rows, 0 changed. The tester confirms it
  with the snapshot.

**6. Loop mode.** `fast` (N15 row U6). `scripts/sbom_check.py` is under
`scripts/`, so the developer runs `scripts/verify.sh full` before the
gate.

**Suggested TDD order.** (a) item 5's table, both flipped pins included;
(b) `exempt_matches` on synthetic docs: match with qualifiers ignored,
version moved, other image skipped, qualifier-bearing or versionless
entry; (c) `classify_document` with `exempt`: exempt only, both flags,
default `()` unchanged; (d) item 3's schema test on the committed file
(RED until `hosts` and `exempt` land; its `reviewed` part RED until
security's entry review); (e) item 4's real-row test. Pure functions and
a JSON file: no spans (no agent loop, model, retrieval or tool call).

**Open for the orchestrator (not U6 code).** The U5 amendment's "3.
Generator digest (I-4)" says the analyst amends PSC-22's wording with
U6; that is not in this brief.

**Correction (orchestrator, 2026-10-25; supersedes the `always`/`exempt`
choice in item 1 above).** The analyst found that PSC-22 bullet 1, its
"`always` additions", the libldap/libsasl2 bullet and N10's human-call
GCC fallback all let a reviewed exemption clear an `always` package.
Ruling: `always` overrides only the classifier; a reviewed `exempt` entry
at the exact versioned purl still clears the package.
- `classify_document(image, doc, always, exempt=())`: a row flagged by
  `exempt` gets `exempt: True` and `needs = False`, whether or not
  `always` also flags it. A row flagged by both is `always: True,
  exempt: True, needs: False`. A row flagged by `always` only keeps
  `needs = True`. `unparsed`, `unidentified` and `expression` are left
  as computed.
- U9's `index` does not refuse a row with both flags. It lists it as
  "always, cleared by exemption <reviewed>" (the entry's `reviewed`
  value), so the clearance is visible. Item 1's "refuses a row with both
  flags" and its "*Why not in `exempt_matches`*" sentence are withdrawn;
  `exempt_matches` still takes no `always` input.
- Item 3: the bullet "no fixture row is flagged by both `always` and
  `exempt`" is withdrawn (both is now a legal state). At U6 no entry hits
  an `always` package: jna and javassist match no ke-neo4j `always` entry.
- Item 1, last bullet: for the libldap/libsasl2 rows an `exempt` entry is
  now possible, not a conflict. None is written at U6, so U7's lock
  covers them (the default, fail closed; N15 notes).
- Item (c) of the TDD order becomes: exempt only (`needs` False), both
  flags (`needs` False, both True), always only (`needs` True), default
  `()` unchanged but for `exempt: False`.

**Contradiction with `docs/requirements.md` (flag, not resolved here).**
PSC-22's "*First test row (U5 review I-r3-1, orchestrator 2026-10-25)*"
bullet says an opaque idstring with a keyword joined by `.` or `-` "stays
ordinary, as `MIT-NOASSERTION` does", and names `NOASSERTION.NONE`,
`NOASSERTION-2.0` and `LicenseRef-NOASSERTION`. Item 5 (the orchestrator's
ruling 5) makes the first two and `MIT-NOASSERTION` unknown; only
`LicenseRef-NOASSERTION` stays ordinary. The analyst must amend that
bullet before the tester's RED. Its "*`always` and `exempt` (open)*"
bullet is settled by the correction above.
*Update (architect, 2026-10-25):* resolved while this was written. The
analyst's amended bullet (requirements l.3929 on) now matches item 5. It
does not name `see NONE.txt here`; that flip (item 5) is still for the
orchestrator to confirm.
*Ruled (orchestrator, 2026-10-25):* `see NONE.txt here` flips to (T,T,T) under item 5; one fail-closed rule for leaves, runs and exception ids, no second code path.

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
| U1 | PSC-14 NOTICE.md "Base of `ke-app`" section and pointer; round 2: no pip (`app.Dockerfile` `runtime` stage, `FROM scratch` flatten, N10a), smoke `no pip`, `licenses/CPython-3.12-incorporated.txt`; static tests, incl. the U0/D10/digest tests re-targeted at `runtime` | full | yes (Dockerfile) |
| U2 | PSC-20 `docker-compose.sbom.yml` `sbom`, pin and provenance, presence refusal in `bundle.sh` | full | yes (compose) |
| U3 | PSC-13 `bundle.sh` save -> syft -> `finish`; `sbom_check.py` N6 and runtime packages; Neo4j jars decided (ruling 5) | full | no |
| U4 | PSC-22: `ke-app` SBOM lists libpq5 (dpkg) and psycopg-c with no psycopg-binary; NOTICE's image-side checks (dpkg set of `ke-app` minus the base equals `ADDED_PACKAGES`; no `pkg:pypi/pip`; CPython version equals the incorporated-licences header; N10, B3); unlicensed report per image (by rule; minus the DESCRIBES root; counts per purl type; no-purl rows by SPDXID; N8a 4-5; exact rule N8); `sbom` env `XDG_CACHE_HOME: /tmp/cache` (N8a 6); `docker/source-policy.json` with `always` only (N10, incl. openldap and cyrus-sasl2 in ke-app); base pulled by digest in `offline_check.sh`, SBOM work dir beside `--out` (N1 amendment, U4); carry: review N1-N4, N6, N7 (N7 forked lock), N9. Rework round 1: hash-only `LicenseRef-<64 hex>` counts as missing (N8, H-1); `sbom` tmpfs `/tmp:mode=1777` and the floor also on `dirname(--out)` (N1 amendment, U4 rework); `always` gains gcc-12/gcc-14, jrt-fs, `upstream=busybox`/`apk-tools` (N10) | full | yes (compose tmpfs: re-run 2b and 3b) |
| U4b | Q67 (security M-3): first-party `ke-neo4j` without `products/` (N16): `docker/neo4j.Dockerfile` (flattened, config re-set), compose `neo4j` service, NOTICE vendor row replaced by "Base image of `ke-neo4j`", `source-policy.json` `neo4j` keys renamed `ke-neo4j`, smoke no-plugin step, first-party image lists in tests | full | yes (Dockerfile, compose) |
| U5 | PSC-15 classifier (N8), pure functions; ruling 5: NOASSERTION fall-through, token rule, URL-folded ids listed (N8a); hash ids unknown, needs source, listed "unidentified" (N8, H-1) | fast | no |
| U6 | `docker/source-policy.json` gains `hosts` and `exempt` (`always` is U4's) and the three-key schema test; `exempt` for jna and javassist, security-reviewed (N8a 1, 3) | fast | no |
| U7 | lock: `docker/sources.lock.json`, `scripts/sources_lock.sh`, provenance evidence (security's second fetch); `maven` kind, jaxb-api sources jar (N8a 2); `deb` gcc-12 and gcc-14 (N10) | full | no |
| U8 | PSC-23 `bundle_fetch.sh`, `sources-fetch` and client loop, wired into `offline_check.sh` (replaces the generator pull only; the base pull stays, N1 amendment, U4); README and header wording; CLAUDE.md text to the human (ruling 6) | full | yes (compose) |
| U9 | PSC-15/24 `index`, content-addressed copy, notices section (paths relative to `app/`, I-3, N10a), no-partial tests, install tamper tests (sh and ps1) | full | only if `install.ps1` changes |
| U10 | PSC-19 e2e `verify`, `/install` size and memory pre-check; follow-up security U3 L-1: `build.sh` stamps `org.opencontainers.image.revision=<git HEAD>` on each first-party `ke-*` image, and `bundle.sh` refuses, before any write, an image whose label is absent or differs from its `git_sha` (else the SBOM creator and `bundle.json` name the wrong commit; U3's stale ke-app SBOM is the case). First test: the refusal on a mismatched or missing label (fake docker) | full | yes (compose) |
| U11 | PSC-16 two CI runs, floor re-derivation, Q62 trigger, PS-3.4; full operator recorded run (Q63) | full (CI) | no |
| U12 | PSC-21 recorded arm64 run (Q51 form) | full (arm64) | no |

Dropped by Q64: U4's vendored injection and two-way drift check, and U1's
vendored table. First tests for U1, U2 and U5 are unchanged:
- U1: `test_notice_has_ke_app_base_paragraph` (it now also names libpq5);
  round 2: the N10a static test (pip RUN in `runtime`, `FROM scratch`
  flatten) and the CPython-incorporated header test; the smoke `no pip`
  step is red on today's image (six pip paths) before the Dockerfile
  change.
- U2: `test_sbom_generator_is_pinned`,
  `test_sbom_generator_runs_without_network_or_privileges` and
  `test_bundle_refuses_when_sbom_generator_absent` (`--out` stays empty).
- U5's classifier table:
  - `GPL-2+`, `MIT AND GPL-3.0-or-later` and
    `GPL-2.0-only WITH Classpath-exception-2.0` need source;
  - `LGPL-2.1-or-later OR Apache-2.0` does not;
  - `NOASSERTION` is unlicensed;
  - junk containing "GPL" needs source and is listed as unparsed;
  - ruling 5 (N8a): declared `NOASSERTION` with concluded
    `Apache-2.0 AND LGPL-2.1-only` needs source (fall-through; literal
    AND); jaxb-api's folded `LicenseRef-...CDDL-GPL-1-1.html...` and
    javassist's `...lgpl-2.1.html...` need source and are listed
    unparsed; `LicenseRef-...gnu.org-software-classpath-license.html`
    needs none but is listed.
- U5/U6 (security u1 I-1): the copyright files of libldap-2.5-0 (GPL-2+
  and GPL-3+ lines, mostly with Autoconf or Libtool exceptions),
  libsasl2-2 and libsasl2-modules-db (GPL-3 and GPL-3+ lines) make the
  classifier mark all three GPL-family. So U7's lock carries their deb
  sources (`openldap`, `cyrus-sasl2`, by the normal snapshot route; the
  default, fail closed), unless security records a reviewed `exempt`
  entry per versioned purl at U6. U5's table adds Debian's `GPL-3+` and
  `GPL-2+ with Autoconf exception`; both need source.

## N16. U4b: our own neo4j image, `ke-neo4j` (human ruling Q67, 2026-10-23)

Security M-3: `/var/lib/neo4j/products/` ships
`neo4j-fleet-management-plugin-1.2.0-v5.jar` (`com.neo4j`, "Use of this
Software without a proper commercial license with Neo4j, Inc. ... is
prohibited"). The human ruled that we build our own image without it.
Probe (2026-10-23, architect): `docker create` of the pinned image, then
`docker export | tar -tv`, so nothing ran. 8,028 entries.
- *What goes.* `products/` holds exactly two files, both `0777
  7474:7474`. The first is the fleet plugin, sha256 `e4c3250a...222faf`.
  The second is `neo4j-genai-plugin-5.26.32.jar` (`org.neo4j`, GPL-3.0
  by its own `META-INF/NOTICE.txt`; sha256 `f355e1e7...bdf8123`). No
  other path names fleet or the plugin; `lib/` and `labs/` hold neither.
  `/startup/neo4j-plugins.json` points at `products/*.jar` only when
  `NEO4J_PLUGINS` asks for a plugin. The stack never sets it, and without
  the file the entrypoint would try a download, which fails on the
  backend network. The whole directory goes, as the ruling says. The
  GenAI plugin is unused and its loss changes nothing at runtime. The
  entrypoint and `neo4j-plugins.json` are left untouched.
- *`docker/neo4j.Dockerfile`* (shape of `app.Dockerfile`'s flatten, N10a):
  ```
  # ke-neo4j: the official Neo4j Community image without products/ (Q67).
  # Config below re-set from `docker image inspect <ref> --format '{{json .Config}}'`;
  # re-read it on every digest bump.
  FROM neo4j:5-community@sha256:0a6e7aedf54a531f76286032d4365ead65b11cca05e4a15cdf23b8e53d6db02b AS runtime
  RUN rm -rf /var/lib/neo4j/products
  FROM scratch
  COPY --from=runtime / /
  ENV PATH=/var/lib/neo4j/bin:/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
      JAVA_HOME=/opt/java/openjdk \
      NEO4J_SHA256=d279ae6a9b38034280681a558b0cd222dce89f87cc3d9867f1f7bd28ef5ebc30 \
      NEO4J_TARBALL=neo4j-community-5.26.32-unix.tar.gz \
      NEO4J_EDITION=community \
      NEO4J_HOME=/var/lib/neo4j \
      LANG=C.UTF-8
  WORKDIR /var/lib/neo4j
  VOLUME ["/data", "/logs"]
  EXPOSE 7473 7474 7687
  ENTRYPOINT ["tini", "-g", "--", "/startup/docker-entrypoint.sh"]
  CMD ["neo4j"]
  ```
  *Why flatten:* a `RUN rm` layer over the official layers still ships
  the jar in the saved tar (`--scope all-layers` would list it, and the
  bytes would be redistributed). That is U1's pip finding.
- *The full config, from `docker image inspect`* (amd64 entry of the
  pinned digest):
  - `Entrypoint` `["tini","-g","--","/startup/docker-entrypoint.sh"]`
  - `Cmd` `["neo4j"]`
  - `Env`, in order: `PATH`, `JAVA_HOME`, `NEO4J_SHA256`,
    `NEO4J_TARBALL`, `NEO4J_EDITION`, `NEO4J_HOME`, `LANG`, values as above
  - `WorkingDir` `/var/lib/neo4j`
  - `ExposedPorts` 7473, 7474 and 7687/tcp
  - `Volumes` `/data` and `/logs`
  - `User` empty (root). This is not set, and it must stay unset: the
    entrypoint runs as root, chowns `NEO4J_HOME`, `/data` and `/logs` to
    7474, then drops privilege.
  - `Labels` null, `Healthcheck` null (compose has its own), `StopSignal`
    empty, `OnBuild` null, `Shell` null. None of these is set.

  A fast static test pins this list against the final stage. Every value
  is copied as is. The `NEO4J_*` keys are read by the entrypoint, which
  also uses `NEO4J_SHA256` and `NEO4J_TARBALL` in its exclusion list, so
  none is dropped.
- *Ownership and modes (probe).* The flatten keeps them.
  - `COPY --from=<stage> / /` with no `--chown` keeps uid/gid, mode bits
    (setuid, setgid, sticky), symlinks and hard links.
  - Key paths in the official image, to be reproduced:
    - `/var/lib/neo4j` and its subdirectories `0777 7474:7474`, except
      `bin/` at `0755 7474:7474`
    - `/data` and `/logs` `0777 7474:7474`
    - `var/lib/neo4j/data -> /data` and `logs -> /logs`, symlinks owned
      0:0
    - `/startup` `0755 0:0`; `/opt/java/openjdk` `0755 0:0`
    - `/tmp`, `/var/tmp` and `/run/lock` `1777`
    - 8 setuid-root binaries (su, passwd, mount ...), plus setgid shadow
      (gid 42) on chage and expiry
    - one hard link, `usr/bin/perl5.40.1`
  - The export carries no xattrs, so no file capability can be lost.
  - *Confirm at GREEN (evidence, not a gate step):* list both images with
    `docker create` + `docker export | tar -tv`. Compare type, mode,
    uid/gid, size and link target, by path. The only difference allowed is
    `var/lib/neo4j/products/` and its two files. A hard link written out
    as a regular file is recorded, not failed.
- *Name and tag:* `ke-neo4j:${KE_IMAGE_TAG:-local}`, like `ke-gateway`. In
  compose, service `neo4j` keeps its name, networks, env, volume and
  healthcheck. `image:` becomes that ref, plus `build: {context: .,
  dockerfile: docker/neo4j.Dockerfile}` (nothing is copied from the
  context, so BuildKit sends nothing). `build.sh`/`build.ps1` need no
  logic change: `compose build` builds it, and `pull --ignore-buildable`
  no longer pulls neo4j (BuildKit fetches the base by digest). Each
  header comment gains `ke-neo4j`. `verify.sh` builds it under
  `wt-<12 hex>`, as the other first-party images.
- *Bundle and install, first-party like `ke-gateway`.* The ref has no
  digest and matches `^ke-`, so `bundle.sh` saves it as
  `ke-neo4j:bundle-<sha12>`, in `images/ke-neo4j.tar`, with the SBOM at
  `app/sboms/ke-neo4j.spdx.json` (`ke:ref` the `wt-` ref). Install
  (sh and ps1) already accepts `ke-[a-z0-9._-]+:bundle-<12 hex>`, checks
  the header `git_sha`, and writes the `neo4j` override. **No install
  change.** U10's revision label covers it with the other `ke-*` images.
  The `neo4j-data` volume is compatible (same uid 7474, same paths).
- *NOTICE.md (analyst owns wording).*
  - The `neo4j` row leaves "Vendor images". `bundle.sh` checks rows only
    for digest-pinned stack refs, and `ke-neo4j` is not one.
  - A new "Base image of `ke-neo4j`" section, as for `ke-gateway`, carries
    these facts: the base ref byte for byte from the Dockerfile `FROM`;
    Neo4j Community 5.26.32, GPL-3.0 (`/var/lib/neo4j/LICENSE.txt`,
    `licenses/GPL-3.0.txt`); upstream source https://github.com/neo4j/neo4j
    tag 5.26.32; and that `ke-neo4j` omits `/var/lib/neo4j/products/` (the
    fleet-management plugin under a commercial licence, and the GenAI
    plugin). It also says no Neo4j file is changed and the filesystem is
    otherwise the official one, flattened.
  - A fast test ties that ref to the Dockerfile, as U1's does for
    `ke-app`.
- *SBOM, policy, scan.*
  - The SBOM now has one layer, and neither plugin, nor anything syft
    catalogued inside them, is in it. GREEN evidence diffs its package
    list against U4's neo4j SBOM: the plugin rows go, and nothing else
    changes.
  - The unlicensed report loses the fleet row.
  - The `neo4j` keys in `docker/source-policy.json` become `ke-neo4j`;
    the `always` matches are unchanged.
  - N9's `com.neo4j/*` mapping then has no member (kept; harmless).
  - The scan is unchanged: `scan.sh` scans `ke-app` only (ADR-KE-013),
    and neo4j was never scanned.
  - The lock's `neo4j:` and `temurin:` entries and the N5 route for them
    are unchanged.
- *Smoke (live stack).* In the running `neo4j` service, `/var/lib/neo4j/products` is absent and no
  file under `/` (`-xdev`) is named `*fleet-management*`. This holds on
  every image; whole-output compare, failing closed (U1 form).
  - *Note (architect, 2026-10-24):* `-xdev` is superseded by the N8
    amendment, U5, item 6: the step prunes `/proc`, `/sys` and `/dev`
    instead (security U4b L-1).
- *First failing tests (fast):*
  - compose `neo4j` image is `ke-neo4j:${KE_IMAGE_TAG:-local}` with
    `build.dockerfile` `docker/neo4j.Dockerfile`;
  - the Dockerfile's `runtime` stage removes `/var/lib/neo4j/products`,
    and its last stage is `FROM scratch` + `COPY --from=runtime / /` with
    exactly the config list above;
  - NOTICE has no neo4j vendor row and has the base section with the
    Dockerfile's ref;
  - no `"image": "neo4j"` key remains in `source-policy.json`;
  - the first-party lists in `tests/test_stack_compose.py`
    (`FIRST_PARTY_REPOS`) and `tests/test_offline_check.py`
    (`FIRST_PARTY`) gain `ke-neo4j`.

  Then `full`: smoke step red on today's image, green after.
- *A34 (yes).* A Dockerfile and a compose change. The Windows proof:
  `build.ps1` builds `ke-neo4j`; `launch.ps1` brings `neo4j` healthy on
  it; Git Bash `bundle.sh` writes `images/ke-neo4j.tar` and its SBOM
  (with no plugin rows); `install.ps1` loads it as `ke-neo4j:bundle-<sha12>`
  and writes the override; the ownership diff above on Docker Desktop's
  containerd store; `teardown.ps1` leaves nothing.
- *Size:* about 380 KB less, plus anything the official layers deleted
  above themselves. Build adds one rootfs copy (about 590 MB, once per
  base digest; cached).
