"""A fake `docker` CLI for the script tests (not a test module).

`install(bin_dir)` writes an executable `docker` into `bin_dir`. It is a Python
script run by this interpreter, so bash and pwsh can both find it on PATH. It
never touches a real daemon. What it does:

- Logs each call. `FAKE_DOCKER_LOG` gets one plain line (`$*`). If
  `FAKE_DOCKER_JSON` is set, that file also gets one JSON line per call:
  argv, cwd, the compose project directory, whether a `.env` sits there, and
  the COMPOSE_*/KE_* environment.
- `FAKE_DOCKER_FAIL` is a list of substrings separated by `|`. A call whose
  joined argv contains one of them exits 1 after logging.
- `compose version [--short]` reports 2.29.7.
- `compose ... config` resolves the way compose does for the keys the scripts
  care about (KE_ENV, KE_BIND_ADDRESS and the published ports).
  - Inputs: every `--env-file` (a later one wins), or else `.env` in the
    project directory. The dotenv forms `KEY=v`, `export KEY=v`, `KEY = v` and
    `KEY: v` are understood, with quotes and ` #` comments.
  - The process environment wins over the files (compose interpolation order).
  - `KE_ENV` is `${KE_ENV}`: unset gives "". `KE_BIND_ADDRESS` is
    `${KE_BIND_ADDRESS:-127.0.0.1}`.
  - `FAKE_COMPOSE_RESOLVED` (JSON object) overrides the resolved values. A
    test uses it to prove that a script trusts compose rather than its own
    parser.
  - Output: `--format json` gives the JSON model, `--environment` gives
    KEY=VALUE lines, `--services` gives names, and anything else gives YAML in
    compose's shape.
  - `FAKE_COMPOSE_PORTS` (JSON list) replaces the gateway's published ports
    in the model, so a test can drop `host_ip` (review N-3).
  - The JSON model also carries `networks` (`<project>_backend`,
    `<project>_edge`), the project being COMPOSE_PROJECT_NAME or
    `knowledge-engine`.
- `compose ps --format {{.Health}} <svc>` prints `healthy`.
- A `compose exec` naming KE_GATEWAY_API_LISTEN prints `{"status":"ok"}`.
- `docker version` and `docker info` (rework 2, review R1-B2, security L-6):
  - The server (Engine) version is `FAKE_DOCKER_ENGINE`, printed verbatim
    (a leading space is kept). Unset or empty prints an empty line, as an odd
    engine or shim would. `--format` with `.Server.Version` (version) or
    `.ServerVersion` (info) prints it; no `--format` prints compose-like text
    with a Client and a Server section.
  - The client version is always 27.0.0 (below 28), so a script that reads
    the client instead of the server fails the accepting cases.
  - `FAKE_DOCKER_ENGINE_EXIT` (an integer): after printing, write a daemon
    error to stderr and exit with that code (a daemon error).
- `docker network inspect NAME` (rework 2, review R1-B1, security M-4):
  - Only `<project>_backend` exists (project as above); any other name exits
    1 with "No such network".
  - Its Options are `FAKE_DOCKER_BACKEND_OPTIONS` (JSON object), by default
    `{"com.docker.network.bridge.gateway_mode_ipv4": "isolated"}`.
  - Output: no `--format` gives docker's JSON array. `--format` (or `-f`)
    understands `{{json .}}`, `{{json .Options}}`, `{{.Options}}` and
    `{{index .Options "KEY"}}`; any other template exits 2 naming it.
- platform-stack-ready (2b) additions:
  - `compose ... config`: the gateway environment also carries
    KE_MODEL_UPSTREAM and KE_EGRESS_ALLOWLIST as compose resolves them
    (`${VAR:-}`; process env over env file), overridable through
    FAKE_COMPOSE_RESOLVED (PS-2.21, env_value.sh reads them).
  - `network inspect`: `"Internal"` is false when FAKE_DOCKER_BACKEND_INTERNAL
    is `false` (review R2-N4).
  - `compose ps -q` / `--quiet` prints FAKE_DOCKER_RUNNING (container ids,
    empty by default: nothing of the project runs); `compose ps --services`
    prints the stack names only when FAKE_DOCKER_RUNNING is non-empty. Plain
    `docker ps -q` (no --format) prints FAKE_DOCKER_RUNNING too. Smoke uses
    this to know whether it launched the project (ruling S1, Q37).
  - Leftover listings (security L-9, teardown): `docker ps -a ... --format`
    (or `container ls`), `docker network ls` and `docker volume ls`, each
    with `--filter label=com.docker.compose.project=<p>`, print the names in
    FAKE_DOCKER_LEFTOVERS, a JSON object `{"<p>": {"containers": [...],
    "networks": [...], "volumes": [...]}}`, for the project the filter names.
    FAKE_DOCKER_LEFTOVER_CONTAINERS / _NETWORKS / _VOLUMES (newline-
    separated) answer for any project. The filter is in the call log.
  - FAKE_DOCKER_FAIL_NTH: `|`-separated `<regex>#<n>` items. The n-th call
    (1-based, counted from FAKE_DOCKER_JSON, which must be set) whose joined
    argv matches the regex exits 1 after logging. Records whose argv starts
    with "STUB" (stub scripts logging into the same file) are not counted.
- platform-offline (PS-3.1, bundle and install) additions. Each is inert
  unless its variable is set, so the earlier tests see the old behaviour:
  - FAKE_COMPOSE_IMAGES (JSON object, service -> image reference): the
    stack services `compose ... config` reports. `--services` prints its
    keys, `--images [svc...]` prints the distinct images (of the named
    services, or of all), `--format json` gives each service an `image`
    and drops services not in it. FAKE_COMPOSE_PROFILE_IMAGES (same shape)
    is added only when the call passes a `--profile`, so a script that
    activates profiles picks up the verification images.
  - FAKE_DOCKER_IMAGES (JSON object, reference -> {"Id", "Os",
    "Architecture", ...}): the images present on the daemon. `image
    inspect` / `inspect` of a reference not in it (and not given by an
    earlier logged `tag <known> <ref>`) exits 1 with "No such image";
    `tag` from an unknown source exits 1 too. `--format` understands
    `{{.Field}}`, `{{json .}}` and `{{json .Field}}`.
  - `save -o|--output <path> <ref>...` writes a small file at <path> (its
    directory must exist), so manifests can hash it. platform-sbom U4: with
    FAKE_DOCKER_IMAGES set, a <ref> not in it (nor tagged from it) exits 1,
    as the daemon does; save never pulls. A `pull <ref>` (last argument)
    logged earlier with FAKE_DOCKER_PULL_OK=1 makes <ref> known (inspect,
    tag, save), as a real pull does.
  - `load -i|--input <file>` prints FAKE_DOCKER_LOAD[<basename>] when that
    JSON object names the file (any text: none, one or two lines), else
    `Loaded image ID: sha256:<sha256 of the file>`. A missing file exits 1.
  - `install_df(bin_dir)` writes a fake `df` printing POSIX `-Pk` output
    with FAKE_DF_AVAIL_KB available (default 50 GiB) for each path argument,
    logging its argv to FAKE_DF_LOG.
- platform-offline unit-2 rework 1 (review B1/N6, security M-1/L-2/L-3/L-6):
  - FAKE_DOCKER_HOOKS (JSON list of {"on": <regex>, "write": {path: text},
    "symlink": [link, to]}): on a call whose joined argv matches `on`, after
    logging, overwrite each `write` path in place (a hardlink's other name
    sees it), and create `link -> to` unless `link` already exists. Tests use
    it to change the bundle after `info` or plant a target link during `load`.
    More actions: "list": [dir, outfile, prefix] appends one JSON line listing
    the entries of dir whose names start with prefix ({name, mode, dir},
    lstat); "touch": path creates a marker; "sleep": seconds, last.
- platform-offline unit-2 rework 2 (security H-1, M-4, L-8):
  - hook "once": path -- the hook runs only on its first match (the path
    is created as the marker).
  - hook "append": {path: text} appends to a file (a script changed while
    it runs).
  - hook "swap": [parent, prefix, lookalike, log?] renames each entry of
    parent starting with prefix to `<name>.swapped` and copies lookalike to
    the old name (a staging dir swapped after verification); appends
    `swapped <name>` or `refused <error>` to log.
  - hook "replace": [path, "dir"|"symlink", to, log?] removes whatever is
    at path and plants an empty directory or a symlink to `to` (a claimed
    target replaced during load); appends `replaced` or `refused <error>`.
  - FAKE_DOCKER_LOADED_LOG: each `load -i` appends `<tar basename> <sha256
    of the bytes read>`, so a test sees which bytes were loaded.
  - FAKE_DOCKER_EXIT_AFTER (`|`-separated substrings): a matching call prints
    its normal output and then exits 3 (a compose that lists and fails).
  - Fake df: FAKE_DF_TOTAL_KB sets the size column; FAKE_DF_FILESYSTEM sets
    the first column (it may hold spaces, as real `df -P` prints them).
- platform-offline per-arch bundles (PS-3.1, architecture §2.5 Arch):
  - FAKE_DOCKER_ARCH: the daemon's `docker info` Architecture, printed
    verbatim (`x86_64`, `aarch64`, `arm64`, `amd64` or any other value).
    Unset gives `x86_64`, so earlier tests see an amd64 daemon. `info
    --format` renders `{{.Architecture}}`, `{{.ServerVersion}}`,
    `{{.OSType}}`, `{{json .Field}}` and `{{json .}}` from one record; an
    unknown field renders empty. Plain `info` adds an ` Architecture:` line.
  - Per-image arch comes from the FAKE_DOCKER_IMAGES records (`Os`,
    `Architecture`), which `image inspect --format` renders.
- platform-offline unit-2 rework 3 (review RB5b, security L-12):
  - FAKE_COMPOSE_VERSION: what `compose version --short` prints (and, after
    `v`, plain `compose version`); unset gives 2.29.7.
  - hook "remove": [dir, prefix, log?] deletes each non-directory entry of
    dir whose name starts with prefix (a claim marker deleted before
    publish); appends `removed <name>` to log.
- platform-offline unit-2 rework 5 (security M-7):
  - hook "rename": [parent, prefix, source, log?] renames the first entry
    of parent starting with prefix to `<name>.swapped` and renames source
    (a non-empty operator directory) to the old name; appends `renamed
    <name>` or `refused <error>` to log.
- platform-offline smoke-gate loop 1 (defect D1, recorded-runs.md): Compose
  5.x behaviour, inert unless FAKE_COMPOSE_DEPENDS is set (the bundle.sh
  tests set it by default from docker-compose.yml):
  - FAKE_COMPOSE_DEPENDS (JSON object, service -> list of the services it
    depends_on): `config --images <svc>...` prints the images of the named
    services AND of their depends_on services (transitively), distinct, in a
    shuffled order (Compose 5.1.4/5.2.0 print worker as ke-app + valkey, in
    varying order). A named service not in FAKE_COMPOSE_IMAGES exits 1.
  - FAKE_COMPOSE_SEED seeds that shuffle (unset: a fresh random order).
  - `config --format json [<svc>...]` gives every service its `image` and a
    long-form `depends_on`; with service names it holds those services and
    their dependencies only, as Compose does.
- platform-offline offline check (PS-3.2, PS-3.3; architecture §2.5
  `ci/offline` and `ci/deployable-offline`, §2.6 items 11 and 12). Inert for
  the earlier tests unless noted:
  - `compose ... config`: without FAKE_COMPOSE_IMAGES, gateway/api/worker
    carry `image` `ke-gateway|ke-app:<KE_IMAGE_TAG or local>`; the gateway
    environment carries KE_GATEWAY_API_LISTEN (resolved, default 8100), which
    is also its first port's `target` (FAKE_COMPOSE_RESOLVED may override it).
  - `compose ps -q|--quiet <svc>...` (a service named) prints that
    service's container id: FAKE_DOCKER_SERVICE_IDS[svc] (JSON object), else
    `fake<svc>000000`. Without a service name it is unchanged.
  - `inspect` / `container inspect` of such an id gives a container record
    whose NetworkSettings.Networks holds `<project>_backend` and, for the
    gateway only, `<project>_edge` with IPAddress FAKE_GATEWAY_EDGE_IP
    (default 172.30.0.2, printed verbatim). `--format` understands
    `{{json .}}`, `{{json .NetworkSettings.Networks}}`,
    `{{(index .NetworkSettings.Networks "NAME").IPAddress}}`,
    `{{with index .NetworkSettings.Networks "NAME"}}{{.IPAddress}}{{end}}`
    and plain `{{.A.B}}` paths; anything else exits 2 naming it.
  - `run ... engine.netprobe ...` (the ci/offline control) prints
    FAKE_NETPROBE_CONTROL (default `connected`); `compose ... exec ... <svc>
    ... engine.netprobe ...` prints FAKE_NETPROBE[svc] (JSON object, default
    `no_route`). Both exit 0 only for `connected`, as engine.netprobe does.
  - `pull` / `image pull` FAILS by default (no egress: a registry DNS
    error); FAKE_DOCKER_PULL_OK=1 makes it succeed.
  - `images` / `image ls|list`: the daemon's `repository:tag` names are
    FAKE_DOCKER_LS_BEFORE (JSON list, default empty) until the call log holds
    a `STUB install.sh` record, then FAKE_DOCKER_LS_AFTER. `<none>:<none>` is
    a dangling entry. `-q` prints one id per row; `--filter
    dangling=true|false` (or `-f`) filters; `--format` renders
    `{{.Repository}}`, `{{.Tag}}`, `{{.ID}}` and `{{json .}}`, anything else
    exits 2 naming it.
  - `info`: the record also has `Driver` (FAKE_DOCKER_STORAGE_DRIVER,
    default `overlayfs`), `DriverStatus` (FAKE_DOCKER_DRIVER_STATUS, JSON list
    of pairs, default the containerd store's `[["driver-type",
    "io.containerd.snapshotter.v1"]]`) and `DockerRootDir`
    (FAKE_DOCKER_ROOT_DIR, default /var/lib/docker). Lists render Go-style
    (`[[a b] [c d]]`); plain `info` prints ` Storage Driver:` and the
    DriverStatus pairs.
  - Fake df: FAKE_DF_AVAIL_BY_PATH (JSON object, path -> KiB) overrides the
    available figure for an exact path argument; FAKE_DF_JSON (a path, set to
    the FAKE_DOCKER_JSON file) appends one `{"argv": ["DF", ...]}` record per
    call so df calls sit in the same ordered call log.
- platform-offline licence notices (PS-3.8, architecture §2.5 Licence
  notices): `run ... engine.notices [args]` models the `ke-app` image. It runs
  the real `engine/notices.py` from FAKE_NOTICES_APP_ROOT (a directory that
  holds `engine/`) under this interpreter with `-S -E -B`, so the only
  distributions importlib.metadata sees are those in FAKE_NOTICES_SITE (a
  test-built site-packages directory standing in for the image's venv).
  Arguments after `engine.notices` are passed on; stdout, stderr and the exit
  status are the generator's. Either variable unset: exit 125 naming it.
- platform-supply-chain U2 rework 1 (review B1, security M-1, L-3). Each is
  inert unless its variable is set:
  - FAKE_DOCKER_RECORD_ENV (comma-separated names): those variables are
    also copied into each call record's `env` when set in the process.
  - FAKE_DOCKER_SAVE_MODE (octal, e.g. `600`): `save -o` chmods the tar it
    writes to that mode (docker/cli's atomicwriter writes 0600 on Linux).
  - hook "stat": [glob, outfile] appends one JSON object {path: mode} of the
    files matching glob (a script's file modes at the time of that call).
  - FAKE_DOCKER_CONTAINERS (JSON list of {"ID", "Names", "Labels",
    "State"}): the daemon's containers. `{run_project}` in any string is the
    project of the first logged `compose ... run` call (`-p`, else its
    COMPOSE_PROJECT_NAME); an entry naming it does not exist before that
    call. `ps` / `container ls|list|ps` list them: running only unless
    `-a`/`--all`; `--filter`/`-f` `label=K=V`, `label=K`, `name=RX`,
    `status=S`, `id=PREFIX` (any other filter exits 2); `-q` prints IDs;
    `--format` renders `{{.ID}}`, `{{.Names}}`, `{{.State}}`, `{{.Labels}}`,
    `{{.Label "K"}}` and `{{json .}}` (anything else exits 2). `rm` /
    `container rm` of a running container needs `-f`/`--force`; an unknown
    target exits 1 "No such container"; no target exits 1. A container
    named (ID, ID prefix of 4+ or name) by an earlier forced `rm` is gone.
- platform-supply-chain unit 3 (PSC-4). Inert unless a hook sets them:
  - hook "stdout": text -- written to stdout after the other actions (a
    fake `compose run ... scan` prints a grype-like table).
  - hook "exit": n -- then exit n at once (grype's exit status), before
    FAKE_DOCKER_FAIL / FAIL_NTH and any modelled reply.
- platform-sbom U0 (PSC-25, ADR-KE-016 point 0, design-notes N0): the
  api's psycopg, libpq and dpkg inside `compose ... exec [opts] <svc> CMD`.
  The defaults model a correct image (psycopg-c on Debian's libpq at the
  `LIBPQ_VERSION` pin read from docker/app.Dockerfile when the fake is
  installed, else 15.14-0+deb12u1), so earlier smoke tests stay green when
  smoke gains the psycopg step. CMD is matched on its first word:
  - `python|python3 [flags] -c CODE [args]`: CODE runs under this
    interpreter with `-I -S -B` and a stub site holding `psycopg`
    (`psycopg.pq.__impl__`, `pq.version()`, `pq.__build_version__`,
    `pq.PGconn`) and the impl package: `psycopg_c` for `c`, `psycopg_binary`
    for `binary`, neither for `python`. The impl package's `pq` and
    `_psycopg` modules report `__file__` (and `__spec__.origin`) as
    `<stub>/<pkg>/<mod>.cpython-312-<FAKE_PQ_TRIPLET>.so`; that file does not
    exist. stdout, stderr and the exit status are CODE's. Variables:
    FAKE_PQ_IMPL (`c`), FAKE_PQ_VERSION (the pin's number, 15.N ->
    150000+N), FAKE_PQ_BUILD_VERSION (FAKE_PQ_VERSION), FAKE_PQ_TRIPLET
    (`x86_64-linux-gnu`). The stub site is
    `<tmp>/opt/venv/lib/python3.12/site-packages` and CODE sees
    `sys.prefix`/`sys.exec_prefix` as `<tmp>/opt/venv` (the literal path
    `/opt/venv` is the host's, not the api's). FAKE_PQ_VENV_EXTRA
    (U0 rework, review B1): comma-separated entries also installed in that
    site beside the impl package: `psycopg_binary` (an importable package),
    `psycopg_binary.libs` (a directory holding a vendored libpq) and
    `<name>-<ver>.dist-info` (METADATA and RECORD); each is a directory.
  - `ldd PATH...`: prints ldd lines for an extension linked to libpq;
    `libpq.so.5 => FAKE_LDD_LIBPQ` (default `/lib/<triplet>/libpq.so.5`, as
    bookworm's ld.so.cache gives it; `not found` prints `=> not found`),
    plus FAKE_LDD_EXTRA lines verbatim. The path is not read.
  - `dpkg-query -W [-f|--showformat FMT] libpq5`, `dpkg -s libpq5`: libpq5
    installed at FAKE_LIBPQ5_VERSION (default the pin; set but empty prints
    an empty version; any other value verbatim). FMT understands
    `${Version}`, `${Package}`, `${binary:Package}`, `${Status}`,
    `${db:Status-Abbrev}` and `\\n`. FAKE_LIBPQ5_ABSENT=1: libpq5 is not
    installed; both exit 1, "dpkg-query: no packages found matching libpq5".
  - `dpkg -S|dpkg-query -S PATH`: `<owner>: PATH` only for
    `/usr/lib/<triplet>/libpq.so.5*` (merged-usr: dpkg does not own the
    `/lib/...` alias); anything else exits 1, "no path found". The owner is
    FAKE_LIBPQ_OWNER (default `libpq5:<arch>`; set but empty: no owner).
  - `realpath|readlink -f PATH`: `/lib/<t>/` becomes `/usr/lib/<t>/`, and
    a path ending `libpq.so.5` gains `.15`; FAKE_LIBPQ_REALPATH, if set, is
    printed instead for a path ending `libpq.so.5`.
  - `find PATH... [-name PAT [-o -name PAT]...]` (U0 rework, review B1):
    for a PATH that is `/opt/venv`, `/`, or any directory on the way to or
    equal to the site, prints `/opt/venv/lib/python3.12/site-packages/<e>`
    for each FAKE_PQ_VENV_EXTRA entry whose name matches a `-name`/`-iname`
    PAT (every entry with no PAT); exit 0.
- platform-sbom U1 round 2 (PSC-14, design-notes N10a; smoke `no pip`):
  inside the `python|python3 [flags] -c CODE` model above, `os.walk` of
  `/usr`, `/opt` or a path below them walks a model of the api's files and
  yields the api's absolute paths; any other path is walked as is. The
  model is a clean shipped image: `/usr/local/bin/python`, `python3`,
  `python3.12`, `/usr/local/lib/python3.12/{LICENSE.txt,pipes.py}`,
  `ensurepip/{__init__,__main__}.py` and an empty `ensurepip/_bundled/`,
  `site-packages/README.txt`, `/usr/lib/<triplet>/libpipeline.so.1` and
  `libpq.so.5.15`, `/usr/share/doc/libpipeline1/copyright`,
  `/opt/venv/bin/python`, psycopg and psycopg_c in the venv site, and
  each FAKE_PQ_VENV_EXTRA entry there. FAKE_API_FILES adds
  comma-separated absolute paths (a trailing `/` makes a directory, else
  an empty file). FAKE_API_PIP_IMPORTABLE=1 puts a `pip` package on CODE's
  sys.path that the walk does not see (importable only).
- platform-sbom U4b (PSC-26, Q67, design-notes N16; smoke `no fleet
  plugin`): `compose exec [opts] neo4j find ROOT... EXPR` evaluates EXPR
  (`-xdev`/`-mount`, `-path`, `-name`, `-iname`, `-type f|d|l`, `-print`,
  `-prune`, `!`/`-not`, `-a`/`-and`, `-o`/`-or`, `(`/`)`; no action means
  `-print`) over a model of the neo4j container, walked depth first in
  sorted order. The model is a clean ke-neo4j: `/var/lib/neo4j` with
  `LICENSE.txt`, `bin/neo4j`, `lib/neo4j-kernel-5.26.32.jar`,
  `labs/apoc-5.26.32-core.jar`, the `data -> /data` and `logs -> /logs`
  links, `/startup/docker-entrypoint.sh` and `neo4j-plugins.json`,
  `/opt/java/openjdk/lib/jrt-fs.jar`, `/data/databases/` and `/logs/`.
  FAKE_NEO4J_FILES adds comma-separated absolute paths (a trailing `/`
  makes a directory), FAKE_NEO4J_DROP removes paths (and what is below
  them), and FAKE_NEO4J_OTHER_FS adds paths on another filesystem (under
  `/proc`, `/data` or `/logs`), which `-xdev` does not enter. Any other
  token exits 1 ("unknown predicate").
  - FAKE_IMAGE_CONFIGS (JSON object, reference -> image `Config`): `image
    inspect [--format T] REF...` for references it names renders T against
    {"Config": <that object>} (no T: a JSON list of those records); a
    reference it does not name exits 1, "No such image". Inert when unset,
    and checked before FAKE_DOCKER_IMAGES.
- platform-sbom U2 (PSC-20, ADR-KE-016 point 1, design-notes N1). Inert
  unless FAKE_COMPOSE_FILE_IMAGES is set (the bundle.sh tests set it):
  - FAKE_COMPOSE_FILE_IMAGES (JSON object, compose file basename ->
    {service: image}): a `compose ... config` call whose `-f`/`--file`
    (else COMPOSE_FILE) names such a file answers from that entry in place
    of FAKE_COMPOSE_IMAGES: `--images [svc...]`, `--services` and `--format
    json` as above, with no depends_on and no profile images.
  - FAKE_COMPOSE_FILE_REQUIRED (JSON object, basename -> variable names):
    each must be set and non-empty in the interpolation environment (process
    KE_* or the env file), else exit 1 "required variable X is missing a
    value", as compose does for `${X:?}`; `--no-interpolate` skips it.
- platform-sbom U3 (PSC-13; ADR-KE-016 points 1, 2 and 6; design-notes N1,
  N3, N6, N7). Each is inert unless its variable is set (the bundle.sh tests
  set FAKE_DOCKER_SAVE_TAR and FAKE_IMAGE_PATHS):
  - FAKE_DOCKER_SAVE_TAR (`oci`, `legacy` or `two`): `save -o` writes a real
    image tar. `oci` is the docker 25+ layout (manifest.json `Config` is
    `blobs/sha256/<hex>`, plus index.json and oci-layout), `legacy` the older
    one (`Config` is `<hex>.json`), `two` an `oci` tar whose manifest.json
    has two entries. U7c (A1): FAKE_IMAGE_TAR_FILES (JSON image name ->
    {member: text}) adds files to the layer of `<name>.tar`. The config blob
    is JSON naming the saved references, so
    its digest differs per image and from the FAKE_DOCKER_IMAGES `Id`.
  - `compose ... -f <file> ...` for a file in FAKE_COMPOSE_FILE_IMAGES: the
    FAKE_COMPOSE_FILE_REQUIRED check applies to every command that loads the
    file (`run` and `down` too), not only `config`.
  - `compose ... run [opts] sbom docker-archive:/in/<name>.tar ... -o
    spdx-json=/out/<file>` models syft: `/in` is KE_SBOM_IN and `/out` is
    KE_SBOM_OUT, from the interpolation environment. It exits 1 when the tar
    is missing or `<KE_SBOM_OUT>/tmp` is not a directory (TMPDIR=/out/tmp; Go's
    MkdirTemp needs it). Otherwise it writes an unpack scratch file under
    `<KE_SBOM_OUT>/tmp/` and a syft-shaped SPDX 2.3 JSON document at
    `/out/<file>`: creators `Organization: Anchore, Inc` and `Tool:
    syft-<version of the sbom image's tag>`; a DocumentRoot package for the
    image, which the document DESCRIBES and which CONTAINS every package;
    dpkg packages (base-files, libc6, plus libpq5 at the pin for ke-app),
    each OTHER-related to a /var/lib/dpkg/status file; and, for `ke-app`, one
    `pkg:pypi/<METADATA Name>@<Version>` package per `*.dist-info` in
    `<FAKE_IMAGE_PATHS["/opt/venv"]>/lib/python3.12/site-packages`
    (knowledge-engine included, as syft lists it). Purl versions are
    percent-encoded (`+` is `%2B`), as syft writes them. Knobs:
    FAKE_SYFT_DROP (comma-separated pypi names left out, PEP 503 compared),
    FAKE_SYFT_PYPI_VERSIONS (JSON name -> version reported instead),
    FAKE_SYFT_RAW (JSON image name -> document text written verbatim),
    FAKE_SYFT_LOG (one JSON line per run: name, in, out, user, and the
    entries of KE_SBOM_OUT and of its tmp/ before the run; platform-sbom U4,
    review N4: also `out_mode` and `tmp_mode`, their permission bits).
    U4 rework 1 (review B1): syft's cache is modelled from the compose
    file's `sbom` service (`_syft_cache_warning`): a non-root user whose
    cache dir sits on a tmpfs without an o+w `mode=` (the image's /tmp is
    0755 root), or on the read-only root, gets syft's `WARN unable to get
    filesystem cache at ...` line on stderr; the run still succeeds.
  - `run ... <image> [args] <dir>/sbom_check.py ARGS` (the N3 checker): runs
    the real script, read from the host source of its `-v`/`--volume`/
    `--mount` bind, under this interpreter with `-I -S -B`, the venv site of
    FAKE_IMAGE_PATHS["/opt/venv"] appended to sys.path. Each argument after
    the script that is a container path (or `--opt=<path>`, or, from U7b
    rework round 1, `IMAGE=<path>` as --sbom and --tar take) is rewritten to
    the host: under a mount target by its bind source, else under a
    FAKE_IMAGE_PATHS prefix (JSON, container prefix -> host dir; the tests
    map `/opt/venv` and `/app`), longest prefix first. stdout, stderr and the
    exit status are the script's; a script that is not there exits 2.
- platform-sbom U7b rework round 1 (design-notes "U7b rework round 1", item
  12): `compose ... -f docker-compose.sources.yml run [opts] sources-resolve
  ARGS`, when that file is in FAKE_COMPOSE_FILE_IMAGES, runs the real
  resolver: the service's entrypoint (`python3 -I <script> ...`) and ARGS,
  each container path rewritten by the service's long-form binds (sources
  interpolated from the interpolation environment, relative ones against
  the compose file's directory; a `${X:?}` with no value, or a bind source
  that does not exist, exits 1 as compose and the daemon do). The module's
  OPENER is replaced by FAKE_RESOLVE_NET (JSON url -> [status, headers,
  body text]; any other url is a 404); FAKE_RESOLVE_LOG gets one requested
  url per line. stdout, stderr and the exit status are the resolver's.
- platform-sbom U8b (design-notes "N4 amendment, U8" item 12; tester, U8b
  RED): `run [opts] sources-fetch ARGS` on the same file is modelled the
  same way: the real scripts/sources_fetch.py from its bind, every container
  path rewritten by the service's long-form binds, and the client's
  `R.OPENER` (its loaded sources_resolve.py, U7b interface pin 1) replaced
  by FAKE_RESOLVE_NET; FAKE_RESOLVE_LOG gets one requested url per line.
  stdout, stderr and the exit status are the client's.
- platform-sbom U9d (A82a; design-notes "N9 amendment, U9d" item 13; tester,
  U9d RED). Each is inert unless its variable is set:
  - FAKE_DOCKER_CONTAINERS entries may give `State` as an object {"Status",
    "ExitCode", "OOMKilled", optional "Health": {"Status", "Log": [{"End",
    "ExitCode", "Output"}]}} and optional `Config` (e.g. {"Env": [...]}),
    `Args`, `Path`, `Mounts`. The listing reads `State.Status` where it read
    the `State` string. `inspect` / `container inspect` of such a container
    (ID, ID prefix of 4+ or name) renders `--format DIAG_TEMPLATE` (this
    module's constant, matched exactly) as Docker would; any other template
    exits 2; no `--format` prints the whole record (Config.Env included).
  - FAKE_COMPOSE_LOGS (JSON object, service -> list of lines): `compose ...
    logs [opts] <svc>...` prints each named service's lines, the last N with
    `--tail N`/`-n N`; a service not in it exits 1 "no such service".
  - `system df`: `--format` renders `{{.Type}}`, `{{.TotalCount}}`,
    `{{.Active}}`, `{{.Size}}`, `{{.Reclaimable}}` (and `{{json .}}`) per row
    of FAKE_DOCKER_SYSTEM_DF (JSON list of such objects; default four rows:
    Images, Containers, Local Volumes, Build Cache); an unknown field exits
    2. `-v`/`--verbose` adds a per-object section (the call record shows it).
  - Fake df: FAKE_DF_FAIL (`1`: every call; else `|`-separated path
    arguments) logs the call, then exits 1 with a df error on stderr.
- platform-sbom U9d rework 1 (ruling O-23; design-notes "Amendment, rework 1
  (O-23)" A1, A9; tester, U9d rework-1 RED). Each is inert unless set:
  - DIAG_TEMPLATE gains `RestartCount`, `State.StartedAt`, `State.FinishedAt`
    and `State.Error` (A1). The render reads `RestartCount` from the
    container record's top level (0 when missing), the two timestamps and
    `Error` from `State`: a timestamp that is missing, "" or Docker's zero
    value `0001-01-01T00:00:00Z` prints `<absent>`; an Error that is missing
    or "" prints `<absent>`, else JSON-quoted. The no-`--format` record gains
    `RestartCount`.
  - EVENTS_FORMAT (module constant, written into the fake by install()):
    the one `docker events --format` the client may use (A2's `events_fmt`).
  - FAKE_DOCKER_EVENTS (JSON list of {"Time", "Action", "Actor":
    {"Attributes": {...}}}): `events ...` requires `--format` EVENTS_FORMAT
    (else exit 2), prints each event as `<Time> <Action> <name> exitCode=<x>
    signal=<s>` (a missing name `<no value>`, a missing exitCode or signal
    empty), flushes, installs a SIGTERM handler that appends the record
    {"argv": ["EVENTS", "stopped"]} to FAKE_DOCKER_JSON and exits 143,
    appends {"argv": ["EVENTS", "ready"]}, then sleeps up to 60 s and exits 0
    (no `stopped` record: a stream nobody killed). Unset: `events` exits 0 at
    once with no output, as before.
- Every other call exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

VERSION = "2.29.7"

# platform-sbom U9d (design-notes "N9 amendment, U9d" item 7): the one
# `container inspect --format` template the launch diagnostic may use. The
# fake renders exactly this text (tests/test_offline_check.py compares the
# script's template with it); any other template exits 2.
DIAG_TEMPLATE = "\n".join((
    "State.Status: {{.State.Status}}",
    "State.ExitCode: {{.State.ExitCode}}",
    "State.OOMKilled: {{.State.OOMKilled}}",
    "RestartCount: {{.RestartCount}}",
    "State.StartedAt: {{if or (eq .State.StartedAt \"\") (eq .State.StartedAt \"0001-01-01T00:00:00Z\")}}<absent>"
    "{{else}}{{.State.StartedAt}}{{end}}",
    "State.FinishedAt: {{if or (eq .State.FinishedAt \"\") (eq .State.FinishedAt \"0001-01-01T00:00:00Z\")}}"
    "<absent>{{else}}{{.State.FinishedAt}}{{end}}",
    "State.Error: {{if .State.Error}}{{json .State.Error}}{{else}}<absent>{{end}}",
    "{{if .State.Health}}State.Health.Status: {{.State.Health.Status}}",
    "{{range $i, $e := .State.Health.Log}}State.Health.Log[{{$i}}]: end {{$e.End}} exit {{$e.ExitCode}}"
    " output {{json $e.Output}}",
    "{{else}}State.Health.Log: <absent>",
    "{{end}}{{else}}State.Health.Status: <absent>",
    "State.Health.Log: <absent>",
    "{{end}}",
))

# platform-sbom U9d rework 1 (O-23; design-notes "Amendment, rework 1 (O-23)"
# A2, A9): the one `docker events --format` the client's event stream may use.
# The fake renders exactly this format (FAKE_DOCKER_EVENTS); any other exits 2.
EVENTS_FORMAT = ('{{.Time}} {{.Action}} {{.Actor.Attributes.name}} exitCode={{index .Actor.Attributes "exitCode"}}'
                 ' signal={{index .Actor.Attributes "signal"}}')

_SCRIPT = r'''
import json, os, sys

argv = sys.argv[1:]
joined = " ".join(argv)

def opt_values(name):
    out, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == name and i + 1 < len(argv):
            out.append(argv[i + 1]); i += 2; continue
        if a.startswith(name + "="):
            out.append(a.split("=", 1)[1])
        i += 1
    return out

def project_dir():
    pd = opt_values("--project-directory")
    if pd:
        return os.path.abspath(pd[-1])
    files = opt_values("-f") + opt_values("--file")
    if files:
        return os.path.dirname(os.path.abspath(files[0]))
    return os.getcwd()

pdir = project_dir()
record = {
    "argv": argv, "cwd": os.getcwd(), "project_dir": pdir,
    "dotenv_present": os.path.isfile(os.path.join(pdir, ".env")),
    "env": {k: v for k, v in os.environ.items()
            if k.startswith(("COMPOSE_", "KE_")) and k != "KE_FAKE"},
}
for _extra in filter(None, os.environ.get("FAKE_DOCKER_RECORD_ENV", "").split(",")):
    if _extra in os.environ:
        record["env"][_extra] = os.environ[_extra]
log = os.environ.get("FAKE_DOCKER_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(joined + "\n")
jlog = os.environ.get("FAKE_DOCKER_JSON")
if jlog:
    with open(jlog, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

for hook in json.loads(os.environ.get("FAKE_DOCKER_HOOKS") or "[]"):
    import re as _re
    if not _re.search(hook["on"], joined):
        continue
    if hook.get("once"):
        if os.path.lexists(hook["once"]):
            continue
        with open(hook["once"], "a", encoding="utf-8"):
            pass
    for hpath, htext in (hook.get("append") or {}).items():
        with open(hpath, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(htext)
    swap = hook.get("swap")
    if swap:
        import shutil as _shutil
        for name in sorted(os.listdir(swap[0])):
            if not name.startswith(swap[1]) or name.endswith(".swapped"):
                continue
            here = os.path.join(swap[0], name)
            try:
                os.rename(here, here + ".swapped")
                _shutil.copytree(swap[2], here, symlinks=True)
                outcome = "swapped"
            except OSError as exc:
                outcome = "refused %s" % type(exc).__name__
            if len(swap) > 3:
                with open(swap[3], "a", encoding="utf-8") as fh:
                    fh.write("%s %s\n" % (outcome, name))
    rename = hook.get("rename")
    if rename:
        for name in sorted(os.listdir(rename[0])):
            if not name.startswith(rename[1]) or name.endswith(".swapped"):
                continue
            here = os.path.join(rename[0], name)
            try:
                os.rename(here, here + ".swapped")
                os.rename(rename[2], here)
                outcome = "renamed"
            except OSError as exc:
                outcome = "refused %s" % type(exc).__name__
            if len(rename) > 3:
                with open(rename[3], "a", encoding="utf-8") as fh:
                    fh.write("%s %s\n" % (outcome, name))
            break
    replace = hook.get("replace")
    if replace:
        import shutil as _shutil
        rpath, kind = replace[0], replace[1]
        try:
            if os.path.islink(rpath) or os.path.isfile(rpath):
                os.unlink(rpath)
            elif os.path.isdir(rpath):
                _shutil.rmtree(rpath)
            if kind == "dir":
                os.mkdir(rpath)
            else:
                os.symlink(replace[2], rpath)
            outcome = "replaced"
        except OSError as exc:
            outcome = "refused %s" % type(exc).__name__
        if len(replace) > 3:
            with open(replace[3], "a", encoding="utf-8") as fh:
                fh.write(outcome + "\n")
    remove = hook.get("remove")
    if remove:
        for name in sorted(os.listdir(remove[0])):
            here = os.path.join(remove[0], name)
            if name.startswith(remove[1]) and not os.path.isdir(here):
                os.unlink(here)
                if len(remove) > 2:
                    with open(remove[2], "a", encoding="utf-8") as fh:
                        fh.write("removed %s\n" % name)
    for hpath, htext in (hook.get("write") or {}).items():
        with open(hpath, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(htext)
    link = hook.get("symlink")
    if link and not os.path.lexists(link[0]):
        os.symlink(link[1], link[0])
    snap = hook.get("list")
    if snap:
        import stat as _stat
        found = []
        for name in sorted(os.listdir(snap[0])):
            if name.startswith(snap[2] if len(snap) > 2 else ""):
                st = os.lstat(os.path.join(snap[0], name))
                found.append({"name": name, "mode": _stat.S_IMODE(st.st_mode),
                              "dir": _stat.S_ISDIR(st.st_mode)})
        with open(snap[1], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(found) + "\n")
    st = hook.get("stat")
    if st:
        import glob as _glob, stat as _stat
        modes = {p: _stat.S_IMODE(os.stat(p).st_mode) for p in sorted(_glob.glob(st[0]))}
        with open(st[1], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(modes) + "\n")
    if hook.get("touch"):
        with open(hook["touch"], "a", encoding="utf-8"):
            pass
    if hook.get("sleep"):
        import time as _time
        _time.sleep(float(hook["sleep"]))
    if hook.get("stdout") is not None:
        sys.stdout.write(hook["stdout"])
        sys.stdout.flush()
    if hook.get("exit") is not None:
        sys.exit(int(hook["exit"]))

for needle in filter(None, os.environ.get("FAKE_DOCKER_EXIT_AFTER", "").split("|")):
    if needle in joined:
        _real_exit = sys.exit
        def _exit_late(code=0, _real_exit=_real_exit):
            sys.stdout.flush()
            _real_exit(code if code else 3)
        sys.exit = _exit_late
        break

for needle in filter(None, os.environ.get("FAKE_DOCKER_FAIL", "").split("|")):
    if needle in joined:
        sys.stderr.write("fake docker: failing on %r\n" % needle)
        sys.exit(1)

def _calls_matching(rx):
    import re as _re
    if not jlog or not os.path.isfile(jlog):
        return 0
    n = 0
    with open(jlog, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("argv", [None])[:1] == ["STUB"]:
                continue
            if _re.search(rx, " ".join(rec.get("argv", []))):
                n += 1
    return n

for item in filter(None, os.environ.get("FAKE_DOCKER_FAIL_NTH", "").split("|")):
    import re as _re
    rx, _, nth = item.rpartition("#")
    if _re.search(rx, joined) and _calls_matching(rx) == int(nth):
        sys.stderr.write("fake docker: failing call %s matching %r\n" % (nth, rx))
        sys.exit(1)

ISOLATED = {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"}
CLIENT_VERSION = "27.0.0"
project = os.environ.get("COMPOSE_PROJECT_NAME") or "knowledge-engine"

# --- platform-sbom U9d (A82a; design-notes "N9 amendment, U9d" item 13) -----
# Each is inert unless its variable is set (system df prints default rows, but
# no earlier caller runs it).
def _u9d_state(c):
    st = c.get("State", "running")
    return st.get("Status", "running") if isinstance(st, dict) else st

def _u9d_render(c):
    st = c["State"]
    def word(v):
        return ("true" if v else "false") if isinstance(v, bool) else str(v)
    lines = ["State.Status: %s" % st.get("Status", ""), "State.ExitCode: %s" % word(st.get("ExitCode", 0)),
             "State.OOMKilled: %s" % word(st.get("OOMKilled", False))]

    def stamp(v):  # rework 1 (O-23, A1): Docker's zero time and "" are absent
        return "<absent>" if v in (None, "", "0001-01-01T00:00:00Z") else str(v)
    err = st.get("Error")
    lines += ["RestartCount: %s" % word(c.get("RestartCount", 0)),
              "State.StartedAt: %s" % stamp(st.get("StartedAt")),
              "State.FinishedAt: %s" % stamp(st.get("FinishedAt")),
              "State.Error: %s" % (json.dumps(err, ensure_ascii=False) if err else "<absent>")]
    health = st.get("Health")
    if health is not None:
        lines.append("State.Health.Status: %s" % health.get("Status", ""))
        log_entries = health.get("Log") or []
        for i, e in enumerate(log_entries):
            lines.append("State.Health.Log[%d]: end %s exit %s output %s"
                         % (i, e.get("End", ""), word(e.get("ExitCode", 0)),
                            json.dumps(e.get("Output", ""), ensure_ascii=False)))
        if not log_entries:
            lines.append("State.Health.Log: <absent>")
    else:
        lines += ["State.Health.Status: <absent>", "State.Health.Log: <absent>"]
    return "\n".join(lines) + "\n"  # the template ends in a newline; inspect adds one more

if (os.environ.get("FAKE_DOCKER_CONTAINERS") is not None
        and (argv[:1] == ["inspect"] or argv[:2] == ["container", "inspect"])):
    _u9d_cts = [c for c in json.loads(os.environ["FAKE_DOCKER_CONTAINERS"]) if isinstance(c.get("State"), dict)]
    _u9d_rest = argv[1:] if argv[0] == "inspect" else argv[2:]
    _u9d_fmt = opt_values("--format") + opt_values("-f")
    _u9d_skip = set(_u9d_fmt) | set(opt_values("--type"))
    _u9d_names = [a for a in _u9d_rest if not a.startswith("-") and a not in _u9d_skip]

    def _u9d_hit(n):
        return next((c for c in _u9d_cts if n in (c.get("ID"), c.get("Names"))
                     or (len(n) >= 4 and str(c.get("ID", "")).startswith(n))), None)

    if _u9d_names and all(_u9d_hit(n) for n in _u9d_names):
        _u9d_found = [_u9d_hit(n) for n in _u9d_names]
        if not _u9d_fmt:
            print(json.dumps([{"Id": c["ID"], "Name": "/" + c.get("Names", ""), "Path": c.get("Path", ""),
                               "Args": c.get("Args", []), "State": c["State"], "Mounts": c.get("Mounts", []),
                               "RestartCount": c.get("RestartCount", 0),
                               "Config": dict(c.get("Config") or {}, Labels=c.get("Labels", {}))}
                              for c in _u9d_found], indent=4))
            sys.exit(0)
        if _u9d_fmt[-1] != DIAG_TEMPLATE:
            sys.stderr.write("fake docker: unsupported container inspect --format %r\n" % _u9d_fmt[-1])
            sys.exit(2)
        for c in _u9d_found:
            print(_u9d_render(c))
        sys.exit(0)

if argv[:1] == ["compose"] and "logs" in argv and os.environ.get("FAKE_COMPOSE_LOGS") is not None:
    _u9d_table = json.loads(os.environ["FAKE_COMPOSE_LOGS"])
    _u9d_tail, _u9d_svcs, _i = None, [], argv.index("logs") + 1
    while _i < len(argv):
        _a = argv[_i]
        if _a in ("--tail", "-n", "--since", "--until", "--index") and _i + 1 < len(argv):
            if _a in ("--tail", "-n"):
                _u9d_tail = argv[_i + 1]
            _i += 2
            continue
        if _a.startswith("--tail="):
            _u9d_tail = _a.split("=", 1)[1]
        elif not _a.startswith("-"):
            _u9d_svcs.append(_a)
        _i += 1
    for _s in _u9d_svcs:
        if _s not in _u9d_table:
            sys.stderr.write("no such service: %s\n" % _s)
            sys.exit(1)
    for _s in _u9d_svcs or list(_u9d_table):
        _lines = list(_u9d_table[_s])
        if _u9d_tail not in (None, "all"):
            _lines = _lines[len(_lines) - int(_u9d_tail):] if int(_u9d_tail) > 0 else []
        for _l in _lines:
            print(_l)
    sys.exit(0)

if argv[:2] == ["system", "df"]:
    import re as _re
    _u9d_rows = json.loads(os.environ.get("FAKE_DOCKER_SYSTEM_DF") or "null") or [
        {"Type": "Images", "TotalCount": "5", "Active": "0", "Size": "3.2GB", "Reclaimable": "3.2GB (100%)"},
        {"Type": "Containers", "TotalCount": "0", "Active": "0", "Size": "0B", "Reclaimable": "0B"},
        {"Type": "Local Volumes", "TotalCount": "0", "Active": "0", "Size": "0B", "Reclaimable": "0B"},
        {"Type": "Build Cache", "TotalCount": "0", "Active": "0", "Size": "0B", "Reclaimable": "0B"}]
    _u9d_fmt = opt_values("--format")
    if _u9d_fmt:
        for _r in _u9d_rows:
            def _u9d_sub(m, _r=_r):
                if m.group(1) is None:
                    return json.dumps(_r)
                if m.group(1) not in _r:
                    sys.stderr.write("fake docker: unsupported system df field %r\n" % m.group(1))
                    sys.exit(2)
                return str(_r[m.group(1)])
            print(_re.sub(r"\{\{\s*(?:json\s+\.|\.([A-Za-z]+))\s*\}\}", _u9d_sub, _u9d_fmt[-1]))
    else:
        print("TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE")
        for _r in _u9d_rows:
            print("%-15s %-9s %-9s %-9s %s" % (_r["Type"], _r["TotalCount"], _r["Active"], _r["Size"],
                                               _r["Reclaimable"]))
    if "-v" in argv or "--verbose" in argv:
        print("\nImages space usage:\n\nREPOSITORY   TAG   IMAGE ID   SIZE   (verbose: per object)")
    sys.exit(0)

# --- platform-sbom U9d rework 1 (O-23, A9): the client's event stream --------
if argv[:1] == ["events"] and os.environ.get("FAKE_DOCKER_EVENTS") is not None:
    _ev_fmt = opt_values("--format")
    if not _ev_fmt or _ev_fmt[-1] != EVENTS_FORMAT:
        sys.stderr.write("fake docker: unsupported events --format %r\n" % (_ev_fmt[-1] if _ev_fmt else None))
        sys.exit(2)
    for _ev in json.loads(os.environ["FAKE_DOCKER_EVENTS"]):
        _at = (_ev.get("Actor") or {}).get("Attributes") or {}
        sys.stdout.write("%s %s %s exitCode=%s signal=%s\n" % (_ev.get("Time", ""), _ev.get("Action", ""),
                                                              _at.get("name", "<no value>"),
                                                              _at.get("exitCode", ""), _at.get("signal", "")))
    sys.stdout.flush()

    def _ev_record(word):
        if jlog:
            with open(jlog, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"argv": ["EVENTS", word], "env": {}, "cwd": os.getcwd(),
                                     "project_dir": "", "dotenv_present": False}) + "\n")

    def _ev_term(signum, frame):
        _ev_record("stopped")
        os._exit(143)

    import signal as _signal, time as _time
    _signal.signal(_signal.SIGTERM, _ev_term)
    _ev_record("ready")
    _time.sleep(60)
    sys.exit(0)

# --- platform-sbom U0 (PSC-25): psycopg, libpq and dpkg inside the api ------
def _pq_number(debver):
    import re as _re
    m = _re.match(r"^(\d+)\.(\d+)", debver or "")
    return int(m.group(1)) * 10000 + int(m.group(2)) if m else 0

def _exec_split():
    _at = argv.index("exec")
    _takes = {"-e", "--env", "-u", "--user", "-w", "--workdir", "--index"}
    _i = _at + 1
    while _i < len(argv):
        if argv[_i] in _takes:
            _i += 2
            continue
        if argv[_i].startswith("-"):
            _i += 1
            continue
        return argv[_i], argv[_i + 1:]
    return None, []

if argv[:1] == ["compose"] and "exec" in argv:
    _psvc, _pcmd = _exec_split()
    _pword = os.path.basename(_pcmd[0]) if _pcmd else ""
    _triplet = os.environ.get("FAKE_PQ_TRIPLET") or "x86_64-linux-gnu"
    _darch = "arm64" if _triplet.startswith("aarch64") else "amd64"
    _deb = os.environ["FAKE_LIBPQ5_VERSION"] if "FAKE_LIBPQ5_VERSION" in os.environ else LIBPQ_PIN
    _venv_extra = [e for e in (os.environ.get("FAKE_PQ_VENV_EXTRA") or "").split(",") if e]
    _venv_site = "/opt/venv/lib/python3.12/site-packages"
    if _pword in ("python", "python3") and "-c" in _pcmd:
        import shutil as _shutil, subprocess as _subprocess, tempfile as _tempfile
        _ci = _pcmd.index("-c")
        _code = _pcmd[_ci + 1] if _ci + 1 < len(_pcmd) else ""
        _rest = _pcmd[_ci + 2:]
        _impl = os.environ.get("FAKE_PQ_IMPL", "c")
        _ver = int(os.environ.get("FAKE_PQ_VERSION") or _pq_number(LIBPQ_PIN))
        _build = int(os.environ.get("FAKE_PQ_BUILD_VERSION") or _ver)
        _root = _tempfile.mkdtemp(prefix="fake-pq-site-")
        _prefix = os.path.join(_root, "opt", "venv")
        _site = os.path.join(_prefix, "lib", "python3.12", "site-packages")
        try:
            os.makedirs(os.path.join(_site, "psycopg", "pq"))
            with open(os.path.join(_site, "psycopg", "__init__.py"), "w", encoding="utf-8") as fh:
                fh.write("__version__ = '3.3.6'\nfrom . import pq\n")
            _impl_pkg = {"c": "psycopg_c", "binary": "psycopg_binary"}.get(_impl)
            with open(os.path.join(_site, "psycopg", "pq", "__init__.py"), "w", encoding="utf-8") as fh:
                fh.write("__impl__ = %r\n__build_version__ = %d\n" % (_impl, _build))
                fh.write("def version():\n    return %d\n" % _ver)
                if _impl_pkg:
                    fh.write("from %s import pq as _pq\nPGconn = _pq.PGconn\n" % _impl_pkg)
                else:
                    fh.write("class PGconn:\n    pass\n")
            if _impl_pkg:
                _pkg = os.path.join(_site, _impl_pkg)
                os.makedirs(_pkg)
                with open(os.path.join(_pkg, "__init__.py"), "w", encoding="utf-8") as fh:
                    fh.write("__version__ = '3.3.6'\n")
                for _mod in ("pq", "_psycopg"):
                    _so = os.path.join(_pkg, "%s.cpython-312-%s.so" % (_mod, _triplet)).replace(os.sep, "/")
                    with open(os.path.join(_pkg, _mod + ".py"), "w", encoding="utf-8") as fh:
                        fh.write("__file__ = %r\n__spec__.origin = __file__\nclass PGconn:\n    pass\n" % _so)
            for _e in _venv_extra:
                _d = os.path.join(_site, _e)
                os.makedirs(_d, exist_ok=True)
                if _e.endswith(".dist-info"):
                    with open(os.path.join(_d, "METADATA"), "w", encoding="utf-8") as fh:
                        fh.write("Metadata-Version: 2.4\nName: %s\nVersion: 3.3.6\n" % _e.split("-")[0])
                    with open(os.path.join(_d, "RECORD"), "w", encoding="utf-8") as fh:
                        fh.write("%s/METADATA,,\n" % _e)
                elif _e.endswith(".libs"):
                    open(os.path.join(_d, "libpq-9f3e2a1b.so.5.18"), "w").close()
                elif not os.path.exists(os.path.join(_d, "__init__.py")):
                    with open(os.path.join(_d, "__init__.py"), "w", encoding="utf-8") as fh:
                        fh.write("__version__ = '3.3.6'\n")
            # platform-sbom U1 round 2 (N10a): the api's /usr and /opt, for
            # os.walk, and pip importable by the system interpreter.
            _fs = os.path.join(_root, "apifs")
            _api = ["/usr/local/bin/python", "/usr/local/bin/python3", "/usr/local/bin/python3.12",
                    "/usr/local/lib/python3.12/LICENSE.txt", "/usr/local/lib/python3.12/pipes.py",
                    "/usr/local/lib/python3.12/ensurepip/__init__.py",
                    "/usr/local/lib/python3.12/ensurepip/__main__.py",
                    "/usr/local/lib/python3.12/ensurepip/_bundled/",
                    "/usr/local/lib/python3.12/site-packages/README.txt",
                    "/usr/lib/%s/libpipeline.so.1" % _triplet, "/usr/lib/%s/libpq.so.5.15" % _triplet,
                    "/usr/share/doc/libpipeline1/copyright", "/opt/venv/bin/python",
                    _venv_site + "/psycopg/__init__.py", _venv_site + "/psycopg_c/__init__.py"]
            _api += [_venv_site + "/" + _e + "/" for _e in _venv_extra]
            _api += [e.strip() for e in (os.environ.get("FAKE_API_FILES") or "").split(",") if e.strip()]
            for _a in _api:
                _here = os.path.join(_fs, *[p for p in _a.split("/") if p])
                if _a.endswith("/"):
                    os.makedirs(_here, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(_here), exist_ok=True)
                    open(_here, "a").close()
            if os.environ.get("FAKE_API_PIP_IMPORTABLE") == "1":
                os.makedirs(os.path.join(_site, "pip"), exist_ok=True)
                with open(os.path.join(_site, "pip", "__init__.py"), "w", encoding="utf-8") as fh:
                    fh.write("__version__ = '25.0.1'\n")
            _boot = ("import os, sys\n"
                     "_prefix, _site, _code = sys.argv[1], sys.argv[2], sys.argv[3]\n"
                     "sys.argv = ['-c'] + sys.argv[4:]\n"
                     "sys.prefix = sys.exec_prefix = _prefix\n"
                     "sys.path.insert(0, _site)\n"
                     "_fs, _walk = os.environ.get('FAKE_API_FS', ''), os.walk\n"
                     "def _api_walk(top, *a, **k):\n"
                     "    t = os.fspath(top)\n"
                     "    if _fs and isinstance(t, str) and (t in ('/usr', '/opt') or t.startswith(('/usr/', '/opt/'))):\n"
                     "        for d, ds, fs in _walk(_fs + t, *a, **k):\n"
                     "            yield '/' + os.path.relpath(d, _fs).replace(os.sep, '/'), ds, fs\n"
                     "    else:\n"
                     "        yield from _walk(top, *a, **k)\n"
                     "os.walk = _api_walk\n"
                     "exec(compile(_code, '<string>', 'exec'), {'__name__': '__main__'})\n")
            sys.stdout.flush()
            _done = _subprocess.run([sys.executable, "-I", "-S", "-B", "-c", _boot, _prefix, _site, _code, *_rest],
                                    env=dict(os.environ, FAKE_API_FS=_fs))
        finally:
            _shutil.rmtree(_root, ignore_errors=True)
        sys.exit(_done.returncode)
    if _pword == "ldd":
        _lib = os.environ.get("FAKE_LDD_LIBPQ") or "/lib/%s/libpq.so.5" % _triplet
        _out = ["\tlinux-vdso.so.1 (0x00007ffc5e3f1000)"]
        _out.append("\tlibpq.so.5 => not found" if _lib == "not found"
                    else "\tlibpq.so.5 => %s (0x00007f3a1c600000)" % _lib)
        _out += ["\tlibc.so.6 => /lib/%s/libc.so.6 (0x00007f3a1c200000)" % _triplet,
                 "\tlibssl.so.3 => /lib/%s/libssl.so.3 (0x00007f3a1c100000)" % _triplet,
                 "\tlibgssapi_krb5.so.2 => /lib/%s/libgssapi_krb5.so.2 (0x00007f3a1c000000)" % _triplet]
        _out += [l for l in (os.environ.get("FAKE_LDD_EXTRA") or "").split("\n") if l]
        print("\n".join(_out))
        sys.exit(0)
    if _pword in ("dpkg", "dpkg-query") and ("-S" in _pcmd or "--search" in _pcmd):
        import re as _re
        _paths = [a for a in _pcmd[1:] if not a.startswith("-")]
        _rc = 0
        for _p in _paths:
            _owner = os.environ.get("FAKE_LIBPQ_OWNER", "libpq5:" + _darch)
            if os.environ.get("FAKE_LIBPQ5_ABSENT") == "1":
                _owner = ""
            if _owner and _re.fullmatch(r"/usr/lib/%s/libpq\.so\.5(\.\d+)*" % _re.escape(_triplet), _p):
                print("%s: %s" % (_owner, _p))
            else:
                sys.stderr.write("dpkg-query: no path found matching pattern %s\n" % _p)
                _rc = 1
        sys.exit(_rc if _paths else 2)
    if _pword in ("dpkg-query", "dpkg") and ("-W" in _pcmd or "--show" in _pcmd or "-s" in _pcmd
                                             or "--status" in _pcmd):
        _fmt = None
        _skip = set()
        for _j, _a in enumerate(_pcmd):
            if _a in ("-f", "--showformat") and _j + 1 < len(_pcmd):
                _fmt = _pcmd[_j + 1]
                _skip.add(_j + 1)
            elif _a.startswith("--showformat=") or _a.startswith("-f="):
                _fmt = _a.split("=", 1)[1]
        _names = [a for j, a in enumerate(_pcmd) if j > 0 and j not in _skip and not a.startswith("-")]
        if [n for n in _names if n.split(":")[0] != "libpq5"] or os.environ.get("FAKE_LIBPQ5_ABSENT") == "1":
            sys.stderr.write("dpkg-query: no packages found matching %s\n" % " ".join(_names))
            sys.exit(1)
        if "-s" in _pcmd or "--status" in _pcmd:
            print("Package: libpq5\nStatus: install ok installed\nArchitecture: %s\nVersion: %s" % (_darch, _deb))
            sys.exit(0)
        if _fmt is None:
            print("libpq5:%s\t%s" % (_darch, _deb))
            sys.exit(0)
        _txt = (_fmt.replace("${Version}", _deb).replace("${binary:Package}", "libpq5:" + _darch)
                .replace("${Package}", "libpq5").replace("${Status}", "install ok installed")
                .replace("${db:Status-Abbrev}", "ii ").replace("\\n", "\n"))
        sys.stdout.write(_txt)
        sys.exit(0)
    if _pword in ("realpath", "readlink"):
        _real = os.environ.get("FAKE_LIBPQ_REALPATH")
        for _p in [a for a in _pcmd[1:] if not a.startswith("-")]:
            if _real and _p.endswith("libpq.so.5"):
                print(_real)
                continue
            if _p.startswith("/lib/"):
                _p = "/usr" + _p
            print(_p + ".15" if _p.endswith("libpq.so.5") else _p)
        sys.exit(0)
    if _psvc == "neo4j" and _pword == "find":
        # platform-sbom U4b (PSC-26, N16): a model of the ke-neo4j filesystem.
        import fnmatch as _fnmatch
        _nfs = {"/": "d", "/var": "d", "/var/lib": "d", "/var/lib/neo4j": "d",
                "/var/lib/neo4j/LICENSE.txt": "f", "/var/lib/neo4j/bin": "d", "/var/lib/neo4j/bin/neo4j": "f",
                "/var/lib/neo4j/lib": "d", "/var/lib/neo4j/lib/neo4j-kernel-5.26.32.jar": "f",
                "/var/lib/neo4j/labs": "d", "/var/lib/neo4j/labs/apoc-5.26.32-core.jar": "f",
                "/var/lib/neo4j/data": "l", "/var/lib/neo4j/logs": "l", "/startup": "d",
                "/startup/docker-entrypoint.sh": "f", "/startup/neo4j-plugins.json": "f", "/opt": "d",
                "/opt/java": "d", "/opt/java/openjdk": "d", "/opt/java/openjdk/lib": "d",
                "/opt/java/openjdk/lib/jrt-fs.jar": "f", "/data": "d", "/data/databases": "d", "/logs": "d",
                "/proc": "d"}

        def _nadd(_spec):
            for _a in [e.strip() for e in (_spec or "").split(",") if e.strip()]:
                _dir = _a.endswith("/")
                _a = _a.rstrip("/") or "/"
                _parts = [x for x in _a.split("/") if x]
                for _k in range(1, len(_parts)):
                    _nfs.setdefault("/" + "/".join(_parts[:_k]), "d")
                _nfs[_a] = "d" if _dir else "f"
        _nadd(os.environ.get("FAKE_NEO4J_FILES"))
        _nadd(os.environ.get("FAKE_NEO4J_OTHER_FS"))
        for _d in [e.strip().rstrip("/") for e in (os.environ.get("FAKE_NEO4J_DROP") or "").split(",") if e.strip()]:
            for _k in [k for k in _nfs if k == _d or k.startswith(_d + "/")]:
                del _nfs[_k]
        _toks = _pcmd[1:]
        _roots = []
        while _toks and not _toks[0].startswith(("-", "(", ")", "!")):
            _roots.append(_toks.pop(0).rstrip("/") or "/")
        _xdev = any(t in ("-xdev", "-mount") for t in _toks)
        _toks = [t for t in _toks if t not in ("-xdev", "-mount")]
        _has_action = any(t in ("-print", "-prune") for t in _toks)
        _out = []

        def _nfail(msg):
            sys.stderr.write("find: %s\n" % msg)
            sys.exit(1)

        def _parse_or(i):
            node, i = _parse_and(i)
            while i < len(_toks) and _toks[i] in ("-o", "-or"):
                rhs, i = _parse_and(i + 1)
                node = ("or", node, rhs)
            return node, i

        def _parse_and(i):
            node, i = _parse_not(i)
            while i < len(_toks) and _toks[i] not in ("-o", "-or", ")"):
                if _toks[i] in ("-a", "-and"):
                    i += 1
                rhs, i = _parse_not(i)
                node = ("and", node, rhs)
            return node, i

        def _parse_not(i):
            if i < len(_toks) and _toks[i] in ("!", "-not"):
                node, i = _parse_not(i + 1)
                return ("not", node), i
            return _parse_prim(i)

        def _parse_prim(i):
            if i >= len(_toks):
                _nfail("expected an expression")
            t = _toks[i]
            if t == "(":
                node, i = _parse_or(i + 1)
                if i >= len(_toks) or _toks[i] != ")":
                    _nfail("missing )")
                return node, i + 1
            if t in ("-path", "-name", "-iname", "-type"):
                if i + 1 >= len(_toks):
                    _nfail("missing argument to %s" % t)
                return (t, _toks[i + 1]), i + 2
            if t in ("-print", "-prune"):
                return (t,), i + 1
            _nfail("unknown predicate `%s'" % t)

        _tree = _parse_or(0)[0] if _toks else ("true",)
        _pruned = set()

        def _ev(node, path):
            kind = node[0]
            if kind == "or":
                return _ev(node[1], path) or _ev(node[2], path)
            if kind == "and":
                return _ev(node[1], path) and _ev(node[2], path)
            if kind == "not":
                return not _ev(node[1], path)
            if kind == "true":
                return True
            if kind == "-print":
                _out.append(path)
                return True
            if kind == "-prune":
                _pruned.add(path)
                return True
            if kind == "-path":
                return _fnmatch.fnmatchcase(path, node[1])
            base = path.rsplit("/", 1)[-1] or "/"
            if kind == "-name":
                return _fnmatch.fnmatchcase(base, node[1])
            if kind == "-iname":
                return _fnmatch.fnmatchcase(base.lower(), node[1].lower())
            if kind == "-type":
                return _nfs.get(path) == node[1]
            return False

        def _children(path):
            pre = "/" if path == "/" else path + "/"
            return sorted(k for k in _nfs if k != path and k.startswith(pre) and "/" not in k[len(pre):])

        def _walk(path, dev_root):
            if path not in _nfs:
                _nfail("'%s': No such file or directory" % path)
            if _ev(_tree, path) and not _has_action:
                _out.append(path)
            if _nfs.get(path) != "d" or path in _pruned:
                return
            for c in _children(path):
                if _xdev and c in ("/proc", "/data", "/logs") and c != dev_root:
                    # another filesystem: find tests the mount point, never enters it
                    if _ev(_tree, c) and not _has_action:
                        _out.append(c)
                    continue
                _walk(c, dev_root)
        for _r in _roots or ["."]:
            _walk(_r, _r)
        if _out:
            print("\n".join(_out))
        sys.exit(0)
    if _pword == "find":
        import fnmatch as _fnmatch
        _pats, _roots, _j = [], [], 1
        while _j < len(_pcmd) and not _pcmd[_j].startswith(("-", "(", ")", "!")):
            _roots.append(_pcmd[_j].rstrip("/") or "/")
            _j += 1
        while _j < len(_pcmd):
            if _pcmd[_j] in ("-name", "-iname") and _j + 1 < len(_pcmd):
                _pats.append((_pcmd[_j + 1], _pcmd[_j] == "-iname"))
                _j += 2
                continue
            _j += 1

        def _under(_r):
            return _r == "/" or _venv_site == _r or _venv_site.startswith(_r + "/")
        for _e in _venv_extra:
            _hit = not _pats or any(_fnmatch.fnmatchcase(_e.lower() if _ci else _e, _pt.lower() if _ci else _pt)
                                    for _pt, _ci in _pats)
            if _hit and any(_under(_r) for _r in _roots):
                print("%s/%s" % (_venv_site, _e))
        sys.exit(0)

def _go(val):
    # Go's default rendering of a template value: lists as [a b], nested.
    if isinstance(val, list):
        return "[" + " ".join(_go(v) for v in val) + "]"
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)

# --- platform-offline: ci/offline target and probes (architecture §2.5) ----
STACK_NAMES = ["gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix"]

def _service_ids():
    ids = {s: "fake%s000000" % s for s in STACK_NAMES}
    ids.update(json.loads(os.environ.get("FAKE_DOCKER_SERVICE_IDS") or "{}"))
    return ids

def _container(svc, cid):
    nets = {project + "_backend": {"IPAddress": "172.31.0.%d" % (2 + STACK_NAMES.index(svc))
                                   if svc in STACK_NAMES else "172.31.0.99"}}
    if svc == "gateway":
        nets[project + "_edge"] = {"IPAddress": os.environ.get("FAKE_GATEWAY_EDGE_IP", "172.30.0.2")}
    return {"Id": cid, "Name": "/%s-%s-1" % (project, svc),
            "Config": {"Labels": {"com.docker.compose.project": project,
                                  "com.docker.compose.service": svc}},
            "NetworkSettings": {"Networks": nets}}

def _netprobe_reply(word):
    if word:
        print(word)
    sys.exit(0 if word == "connected" else 1)

def format_values():
    return opt_values("--format") + opt_values("-f")

def engine_reply(server_template):
    engine = os.environ.get("FAKE_DOCKER_ENGINE", "")
    fmt = format_values()
    if fmt:
        t = fmt[-1]
        if server_template in t:
            print(engine)
        elif "Client" in t:
            print(CLIENT_VERSION)
        else:
            print("")
    else:
        print("Client:\n Version:           %s\n\nServer:\n Engine:\n  Version:          %s"
              % (CLIENT_VERSION, engine))
    code = int(os.environ.get("FAKE_DOCKER_ENGINE_EXIT") or "0")
    if code:
        sys.stderr.write("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
                         "Is the docker daemon running?\n")
        sys.exit(code)
    sys.exit(0)

if argv[:1] == ["version"]:
    engine_reply(".Server.Version")

def _label_project():
    for f in opt_values("--filter"):
        if f.startswith("label=com.docker.compose.project="):
            return f.split("=", 2)[2]
    return None

def _leftovers(kind):
    names = [n for n in os.environ.get("FAKE_DOCKER_LEFTOVER_" + kind.upper(), "").splitlines() if n]
    p = _label_project()
    table = json.loads(os.environ.get("FAKE_DOCKER_LEFTOVERS") or "{}")
    if p is not None:
        names += list((table.get(p) or {}).get(kind, []))
    return names

def _listing(kind):
    out = _leftovers(kind)
    if out:
        print("\n".join(out))
    sys.exit(0)

_CT_LIST = argv[:1] == ["ps"] or argv[:2] in (["container", "ls"], ["container", "list"], ["container", "ps"])
_CT_RM = argv[:1] == ["rm"] or argv[:2] == ["container", "rm"]
if os.environ.get("FAKE_DOCKER_CONTAINERS") is not None and (_CT_LIST or _CT_RM):
    import re as _re

    def _short_flags(words):
        found = set()
        for w in words:
            if w.startswith("-") and not w.startswith("--"):
                found.update(w[1:])
        return found

    def _is_forced_rm(words):
        return "--force" in words or "f" in _short_flags(words)

    def _rm_targets(words):
        start = 1 if words[:1] == ["rm"] else 2
        return [w for w in words[start:] if not w.startswith("-")]

    def _prior_records():
        if not jlog or not os.path.isfile(jlog):
            return []
        with open(jlog, encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        return lines[:-1]  # this call is the last record

    def _run_project(prior):
        for rec in prior:
            a = rec.get("argv", [])
            if a[:1] != ["compose"] or "run" not in a:
                continue
            for i, w in enumerate(a):
                if w in ("-p", "--project-name") and i + 1 < len(a):
                    return a[i + 1]
                if w.startswith("--project-name="):
                    return w.split("=", 1)[1]
            return rec.get("env", {}).get("COMPOSE_PROJECT_NAME")
        return None

    def _matches(c, token):
        return token == c["Names"] or token == c["ID"] or (len(token) >= 4 and c["ID"].startswith(token))

    prior = _prior_records()
    rp = _run_project(prior)
    containers = []
    for raw in json.loads(os.environ["FAKE_DOCKER_CONTAINERS"]):
        text = json.dumps(raw)
        if "{run_project}" in text:
            if rp is None:
                continue
            text = text.replace("{run_project}", rp)
        c = json.loads(text)
        c.setdefault("State", "running")
        c.setdefault("Labels", {})
        containers.append(c)
    gone = set()
    for rec in prior:
        a = rec.get("argv", [])
        if (a[:1] == ["rm"] or a[:2] == ["container", "rm"]) and _is_forced_rm(a):
            gone.update(_rm_targets(a))
    containers = [c for c in containers if not any(_matches(c, t) for t in gone)]

    if _CT_RM:
        targets = _rm_targets(argv)
        if not targets:
            sys.stderr.write('"docker rm" requires at least 1 argument.\n')
            sys.exit(1)
        rc = 0
        for t in targets:
            hit = [c for c in containers if _matches(c, t)]
            if not hit:
                sys.stderr.write("Error response from daemon: No such container: %s\n" % t)
                rc = 1
            elif _u9d_state(hit[0]) == "running" and not _is_forced_rm(argv):
                sys.stderr.write("Error response from daemon: cannot remove container \"/%s\": container is "
                                 "running: stop the container before removing or force remove\n" % hit[0]["Names"])
                rc = 1
            else:
                print(t)
        sys.exit(rc)

    flags = _short_flags([w for w in argv if w not in opt_values("--filter") + opt_values("-f")
                          + opt_values("--format")])
    show_all = "--all" in argv or "a" in flags
    quiet = "--quiet" in argv or "q" in flags
    rows = [c for c in containers if show_all or _u9d_state(c) == "running"]
    for f in opt_values("--filter") + opt_values("-f"):
        key, _, val = f.partition("=")
        if key == "label":
            k, sep, v = val.partition("=")
            rows = [c for c in rows if (c["Labels"].get(k) == v if sep else k in c["Labels"])]
        elif key == "name":
            rows = [c for c in rows if _re.search(val, c["Names"])]
        elif key == "status":
            rows = [c for c in rows if _u9d_state(c) == val]
        elif key == "id":
            rows = [c for c in rows if c["ID"].startswith(val)]
        else:
            sys.stderr.write("fake docker: ps filter %r is not modelled\n" % f)
            sys.exit(2)
    fmt = opt_values("--format")
    if fmt:
        t = fmt[-1]
        if t.startswith("table "):
            t = t[len("table "):]
        for c in rows:
            line = t.replace("{{json .}}", json.dumps(c))
            line = _re.sub(r'\{\{\s*\.Label\s+"([^"]*)"\s*\}\}', lambda m: c["Labels"].get(m.group(1), ""), line)
            line = line.replace("{{.ID}}", c["ID"]).replace("{{.Names}}", c["Names"])
            line = line.replace("{{.State}}", _u9d_state(c))
            line = line.replace("{{.Labels}}", ",".join("%s=%s" % kv for kv in c["Labels"].items()))
            if "{{" in line:
                sys.stderr.write("fake docker: ps template %r is not modelled\n" % fmt[-1])
                sys.exit(2)
            print(line)
        sys.exit(0)
    if quiet:
        for c in rows:
            print(c["ID"])
        sys.exit(0)
    print("CONTAINER ID   NAMES")
    for c in rows:
        print("%s   %s" % (c["ID"], c["Names"]))
    sys.exit(0)

if argv[:1] == ["ps"] or argv[:2] in (["container", "ls"], ["container", "list"], ["container", "ps"]):
    if ("-q" in argv or "--quiet" in argv) and not opt_values("--format"):
        running = os.environ.get("FAKE_DOCKER_RUNNING", "")
        if running:
            print(running)
        sys.exit(0)
    _listing("containers")
if argv[:2] in (["network", "ls"], ["network", "list"]):
    _listing("networks")
if argv[:2] in (["volume", "ls"], ["volume", "list"]):
    _listing("volumes")
def info_reply():
    import re as _re
    arch = os.environ.get("FAKE_DOCKER_ARCH")
    arch = "x86_64" if arch is None else arch
    rec = {"ServerVersion": os.environ.get("FAKE_DOCKER_ENGINE", ""), "Architecture": arch,
           "OSType": "linux",
           "Driver": os.environ.get("FAKE_DOCKER_STORAGE_DRIVER", "overlayfs"),
           "DriverStatus": json.loads(os.environ.get("FAKE_DOCKER_DRIVER_STATUS")
                                      or '[["driver-type", "io.containerd.snapshotter.v1"]]'),
           "DockerRootDir": os.environ.get("FAKE_DOCKER_ROOT_DIR", "/var/lib/docker")}
    fmt = format_values()
    if fmt and "Client" not in fmt[-1]:
        def sub(m):
            if m.group(2) == "":
                return json.dumps(rec) if m.group(1) else str(rec)
            val = rec.get(m.group(2), "")
            return json.dumps(val) if m.group(1) else _go(val)
        print(_re.sub(r"\{\{\s*(json\s+)?\.([A-Za-z0-9_]*)\s*\}\}", sub, fmt[-1]))
    elif fmt:
        print(CLIENT_VERSION)
    else:
        status = "".join("\n  %s: %s" % tuple(p) for p in rec["DriverStatus"])
        print("Client:\n Version:           %s\n\nServer:\n Engine:\n  Version:          %s\n"
              " Architecture: %s\n Storage Driver: %s%s\n Docker Root Dir: %s"
              % (CLIENT_VERSION, rec["ServerVersion"], arch, rec["Driver"], status,
                 rec["DockerRootDir"]))
    code = int(os.environ.get("FAKE_DOCKER_ENGINE_EXIT") or "0")
    if code:
        sys.stderr.write("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
                         "Is the docker daemon running?\n")
        sys.exit(code)
    sys.exit(0)

if argv[:1] == ["info"]:
    info_reply()

if argv[:1] == ["inspect"] or argv[:2] == ["container", "inspect"]:
    import re as _re
    by_id = {v: k for k, v in _service_ids().items() if v}
    rest = argv[1:] if argv[0] == "inspect" else argv[2:]
    skip = set(format_values()) | set(opt_values("--type"))
    names = [a for a in rest if not a.startswith("-") and a not in skip]
    if names and all(n in by_id for n in names):
        recs = [_container(by_id[n], n) for n in names]
        fmt = format_values()
        if not fmt:
            print(json.dumps(recs, indent=4))
            sys.exit(0)
        t = fmt[-1].strip()
        for rec in recs:
            nets = rec["NetworkSettings"]["Networks"]
            m1 = _re.fullmatch(r'\{\{\s*\(\s*index\s+\.NetworkSettings\.Networks\s+"([^"]+)"\s*\)'
                               r'\.IPAddress\s*\}\}', t)
            m2 = _re.fullmatch(r'\{\{\s*with\s+index\s+\.NetworkSettings\.Networks\s+"([^"]+)"\s*\}\}'
                               r'\{\{\s*\.IPAddress\s*\}\}\{\{\s*end\s*\}\}', t)
            if m1 or m2:
                print((nets.get((m1 or m2).group(1)) or {}).get("IPAddress", ""))
            elif _re.fullmatch(r"\{\{\s*json\s+\.\s*\}\}", t):
                print(json.dumps(rec))
            elif _re.fullmatch(r"\{\{\s*json\s+\.NetworkSettings\.Networks\s*\}\}", t):
                print(json.dumps(nets))
            elif _re.fullmatch(r"\{\{\s*(?:json\s+)?(?:\.[A-Za-z0-9_]+)+\s*\}\}", t):
                cur = rec
                for part in _re.findall(r"\.([A-Za-z0-9_]+)", t):
                    if not isinstance(cur, dict) or part not in cur:
                        sys.stderr.write("fake docker: template field %r not supported\n" % t)
                        sys.exit(2)
                    cur = cur[part]
                print(json.dumps(cur) if "json" in t else _go(cur))
            else:
                sys.stderr.write("fake docker: unsupported container inspect --format %r\n" % t)
                sys.exit(2)
        sys.exit(0)

if argv[:1] == ["run"] or argv[:2] == ["container", "run"]:
    # platform-sbom U3 (N3): `run ... <image> ... sbom_check.py ARGS`.
    _rv = {"-v", "--volume", "--mount", "-e", "--env", "--env-file", "-l", "--label", "--label-file",
           "--entrypoint", "--network", "--net", "--security-opt", "--cap-drop", "--cap-add", "-u",
           "--user", "--pull", "--name", "-w", "--workdir", "--tmpfs", "--platform", "-m", "--memory",
           "--cpus", "--ulimit", "--log-driver", "--log-opt", "-h", "--hostname", "--add-host", "--dns",
           "--device", "--stop-signal", "--pids-limit", "--userns", "--ipc", "--pid", "--uts",
           "--cgroupns", "--restart", "--shm-size", "--gpus"}
    _rs = 1 if argv[0] == "run" else 2
    _ri, _rimg = _rs, None
    while _ri < len(argv):
        if argv[_ri] in _rv:
            _ri += 2
            continue
        if argv[_ri].startswith("-"):
            _ri += 1
            continue
        _rimg = _ri
        break
    _rtail = argv[_rimg + 1:] if _rimg is not None else []
    _rck = [k for k, a in enumerate(_rtail) if a.replace("\\", "/").rsplit("/", 1)[-1] == "sbom_check.py"]
    if _rck:
        import subprocess as _subprocess
        _pairs = []
        _ro = argv[_rs:_rimg]
        for _k, _a in enumerate(_ro):
            _val = None
            if _a in ("-v", "--volume", "--mount") and _k + 1 < len(_ro):
                _val, _kind = _ro[_k + 1], _a
            elif _a.startswith(("--volume=", "--mount=", "-v=")):
                _kind, _val = _a.split("=", 1)
            if _val is None:
                continue
            if _kind == "--mount":
                _kv = dict(p.split("=", 1) if "=" in p else (p, "") for p in _val.split(","))
                _src = _kv.get("source") or _kv.get("src") or ""
                _dst = _kv.get("target") or _kv.get("destination") or _kv.get("dst") or ""
            else:
                _parts = _val.split(":")
                if len(_parts) >= 2 and len(_parts[0]) == 1 and _parts[0].isalpha():
                    _parts = [_parts[0] + ":" + _parts[1]] + _parts[2:]
                _src, _dst = _parts[0], (_parts[1] if len(_parts) > 1 else "")
            if _src and _dst:
                _pairs.append((_dst, _src))
        _imgpaths = json.loads(os.environ.get("FAKE_IMAGE_PATHS") or "{}")
        _pairs += list(_imgpaths.items())

        def _remap(t):
            if t.startswith("--") and "=" in t:
                _k2, _v2 = t.split("=", 1)
                return _k2 + "=" + _remap(_v2)
            if "=" in t and not t.startswith("/") and t.split("=", 1)[1].startswith("/"):
                # platform-sbom U7b rework round 1: IMAGE=<container path> (--sbom, --tar)
                _k2, _v2 = t.split("=", 1)
                return _k2 + "=" + _remap(_v2)
            best = None
            for c, h in _pairs:
                c2 = c.rstrip("/") or "/"
                if t == c2 or t.startswith(c2.rstrip("/") + "/"):
                    if best is None or len(c2) > len(best[0]):
                        best = (c2, h)
            if best is None:
                return t
            return best[1].rstrip("/\\") + t[len(best[0].rstrip("/")):]

        _script = _remap(_rtail[_rck[0]])
        if not os.path.isfile(_script):
            sys.stderr.write("python: can't open file %r: [Errno 2] No such file or directory\n" % _rtail[_rck[0]])
            sys.exit(2)
        _venv = _imgpaths.get("/opt/venv")
        _site = os.path.join(_venv, "lib", "python3.12", "site-packages") if _venv else ""
        _boot = ("import runpy, sys; s, site = sys.argv[1], sys.argv[2]; "
                 "sys.path.append(site) if site else None; sys.argv = [s] + sys.argv[3:]; "
                 "runpy.run_path(s, run_name='__main__')")
        sys.stdout.flush()
        _done = _subprocess.run([sys.executable, "-I", "-S", "-B", "-c", _boot, _script, _site,
                                 *[_remap(a) for a in _rtail[_rck[0] + 1:]]])
        sys.exit(_done.returncode)
    if "engine.notices" in argv:
        import subprocess as _subprocess
        _site = os.environ.get("FAKE_NOTICES_SITE")
        _app = os.environ.get("FAKE_NOTICES_APP_ROOT")
        if not _site or not _app:
            sys.stderr.write("fake docker: FAKE_NOTICES_SITE and FAKE_NOTICES_APP_ROOT must be set "
                             "for `run ... engine.notices`\n")
            sys.exit(125)
        _boot = ("import runpy, sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; del sys.argv[1:3]; "
                 "runpy.run_module('engine.notices', run_name='__main__', alter_sys=True)")
        _extra = argv[argv.index("engine.notices") + 1:]
        sys.stdout.flush()
        _done = _subprocess.run([sys.executable, "-S", "-E", "-B", "-c", _boot, _site, _app, *_extra],
                                cwd=_site)
        sys.exit(_done.returncode)
    if "engine.netprobe" in joined:
        _netprobe_reply(os.environ.get("FAKE_NETPROBE_CONTROL", "connected"))
    sys.exit(0)

if argv[:1] == ["pull"] or argv[:2] == ["image", "pull"]:
    if os.environ.get("FAKE_DOCKER_PULL_OK") == "1":
        print("Status: Downloaded newer image")
        sys.exit(0)
    sys.stderr.write('Error response from daemon: Get "https://registry-1.docker.io/v2/": dial tcp: '
                     "lookup registry-1.docker.io: no such host\n")
    sys.exit(1)

if argv[:1] == ["images"] or argv[:2] in (["image", "ls"], ["image", "list"]):
    import hashlib as _hashlib, re as _re
    installed = False
    if jlog and os.path.isfile(jlog):
        with open(jlog, encoding="utf-8") as fh:
            installed = any(json.loads(l).get("argv", [])[:2] == ["STUB", "install.sh"]
                            for l in fh if l.strip())
    names = json.loads(os.environ.get("FAKE_DOCKER_LS_AFTER" if installed else "FAKE_DOCKER_LS_BEFORE")
                       or "[]")
    rows = []
    for i, n in enumerate(names):
        last = n.rsplit("/", 1)[-1]
        repo, tag = (n.rsplit(":", 1) if ":" in last else (n, "latest"))
        rows.append({"Repository": repo, "Tag": tag,
                     "ID": _hashlib.sha256(("%d %s" % (i, n)).encode()).hexdigest()[:12]})
    for f in opt_values("--filter") + opt_values("-f"):
        if f == "dangling=true":
            rows = [r for r in rows if r["Repository"] == "<none>"]
        elif f == "dangling=false":
            rows = [r for r in rows if r["Repository"] != "<none>"]
    fmt = opt_values("--format")
    if "-q" in argv or "--quiet" in argv:
        for r in rows:
            print(r["ID"])
        sys.exit(0)
    if fmt:
        t = fmt[-1]
        for r in rows:
            def sub(m):
                if m.group(2) == "":
                    return json.dumps(r)
                if m.group(2) not in r:
                    sys.stderr.write("fake docker: unsupported image ls field %r\n" % m.group(2))
                    sys.exit(2)
                return json.dumps(r[m.group(2)]) if m.group(1) else r[m.group(2)]
            print(_re.sub(r"\{\{\s*(json\s+)?\.([A-Za-z0-9_]*)\s*\}\}", sub, t))
        sys.exit(0)
    print("REPOSITORY   TAG   IMAGE ID")
    for r in rows:
        print("%s   %s   %s" % (r["Repository"], r["Tag"], r["ID"]))
    sys.exit(0)

if argv[:2] == ["network", "inspect"]:
    import re
    names = [a for a in argv[2:] if not a.startswith("-") and a not in format_values()]
    backend = project + "_backend"
    options = json.loads(os.environ.get("FAKE_DOCKER_BACKEND_OPTIONS") or json.dumps(ISOLATED))
    nets = []
    for n in names:
        if n != backend:
            sys.stderr.write("Error response from daemon: network %s not found\n"
                             "Error: No such network: %s\n" % (n, n))
            sys.exit(1)
        internal = os.environ.get("FAKE_DOCKER_BACKEND_INTERNAL", "true").lower() != "false"
        nets.append({"Name": n, "Driver": "bridge", "Internal": internal, "Options": options,
                     "Labels": {"com.docker.compose.network": "backend",
                                "com.docker.compose.project": project}})
    if not nets:
        sys.stderr.write("fake docker: network inspect needs a name\n")
        sys.exit(1)
    fmt = format_values()
    if not fmt:
        print(json.dumps(nets, indent=4))
        sys.exit(0)
    t = fmt[-1].strip()
    for net in nets:
        if re.fullmatch(r"\{\{\s*json\s+\.\s*\}\}", t):
            print(json.dumps(net))
        elif re.fullmatch(r"\{\{\s*json\s+\.Options\s*\}\}", t):
            print(json.dumps(net["Options"]))
        elif re.fullmatch(r"\{\{\s*\.Options\s*\}\}", t):
            print("map[" + " ".join("%s:%s" % kv for kv in sorted(net["Options"].items())) + "]")
        else:
            m = re.fullmatch(r"\{\{\s*index\s+\.Options\s+\"([^\"]+)\"\s*\}\}", t)
            if not m:
                sys.stderr.write("fake docker: unsupported network inspect --format %r\n" % t)
                sys.exit(2)
            print(net["Options"].get(m.group(1), ""))
    sys.exit(0)

def _image_table():
    raw = os.environ.get("FAKE_DOCKER_IMAGES")
    return None if raw is None else json.loads(raw)

def _known_image(name, table):
    if name in table:
        return table[name]
    if jlog and os.path.isfile(jlog):
        with open(jlog, encoding="utf-8") as fh:
            recs = [json.loads(l) for l in fh if l.strip()]
        for rec in recs[:-1]:  # the last record is this call
            a = rec.get("argv", [])
            if a[:1] == ["tag"] and len(a) >= 3 and a[-1] == name and a[-2] != name:
                src = _known_image(a[-2], table)
                if src is not None:
                    return src
            # platform-sbom U4: a successful `pull <name>` puts it on the daemon.
            if ((a[:1] == ["pull"] or a[:2] == ["image", "pull"]) and a[-1:] == [name]
                    and os.environ.get("FAKE_DOCKER_PULL_OK") == "1"):
                return {"Id": "sha256:" + "2" * 64, "Os": "linux", "Architecture": "amd64", "RepoDigests": [name]}
    return None

def _render(template, obj):
    import re as _re
    def field(path):
        cur = obj
        for part in [p for p in path.split(".") if p]:
            if not isinstance(cur, dict) or part not in cur:
                sys.stderr.write("fake docker: template field %r not supported\n" % path)
                sys.exit(2)
            cur = cur[part]
        return cur
    def sub(m):
        val = field(m.group(2))
        if m.group(1):
            return json.dumps(val)
        if isinstance(val, list):
            return "[" + " ".join(str(v) for v in val) + "]"
        return str(val)
    return _re.sub(r"\{\{\s*(json\s+)?\.([A-Za-z0-9_.]*)\s*\}\}", sub, template)

if argv[:2] == ["image", "inspect"] and os.environ.get("FAKE_IMAGE_CONFIGS"):
    # platform-sbom U4b (PSC-26): the ke-neo4j config check.
    _cfgs = json.loads(os.environ["FAKE_IMAGE_CONFIGS"])
    _skip = set(format_values())
    _names = [a for a in argv[2:] if not a.startswith("-") and a not in _skip]
    for _n in _names:
        if _n not in _cfgs:
            sys.stderr.write("Error response from daemon: No such image: %s\n" % _n)
            sys.exit(1)
    _fmt = format_values()
    for _n in _names:
        print(_render(_fmt[-1], {"Config": _cfgs[_n]}) if _fmt else json.dumps([{"Config": _cfgs[_n]}]))
    sys.exit(0)

if argv[:2] == ["image", "inspect"] or argv[:1] == ["inspect"]:
    table = _image_table()
    if table is not None:
        rest = argv[2:] if argv[0] == "image" else argv[1:]
        skip = set(format_values()) | set(opt_values("--type"))
        names = [a for a in rest if not a.startswith("-") and a not in skip]
        found = []
        for n in names:
            img = _known_image(n, table)
            if img is None:
                sys.stderr.write("Error response from daemon: No such image: %s\n" % n)
                sys.exit(1)
            found.append(img)
        fmt = format_values()
        if fmt:
            for img in found:
                print(_render(fmt[-1], img))
        else:
            print(json.dumps(found, indent=4))
        sys.exit(0)

if argv[:1] == ["tag"] or argv[:2] == ["image", "tag"]:
    table = _image_table()
    if table is not None:
        src = [a for a in argv[1 if argv[0] == "tag" else 2:] if not a.startswith("-")][0]
        if _known_image(src, table) is None:
            sys.stderr.write("Error response from daemon: No such image: %s\n" % src)
            sys.exit(1)
    sys.exit(0)

def _write_image_tar(target, refs, form):
    """platform-sbom U3: a real image tar (FAKE_DOCKER_SAVE_TAR)."""
    import hashlib as _h, io as _io, tarfile as _tf
    def _add(tar, name, data):
        info = _tf.TarInfo(name)
        info.size = len(data)
        info.mtime = 0
        tar.addfile(info, _io.BytesIO(data))
    buf = _io.BytesIO()
    with _tf.open(fileobj=buf, mode="w") as lt:
        _add(lt, "etc/fake-release", ("layer of %s\n" % " ".join(refs)).encode("utf-8"))
        # platform-sbom U7c (A1): FAKE_IMAGE_TAR_FILES (JSON image name -> {member: text})
        # adds files to the layer of `<name>.tar` (lib/apk/db/installed, etc/alpine-release).
        _stem = os.path.basename(target)
        _stem = _stem[:-4] if _stem.endswith(".tar") else _stem
        for _mem, _txt in sorted(json.loads(os.environ.get("FAKE_IMAGE_TAR_FILES") or "{}").get(_stem, {}).items()):
            _add(lt, _mem, _txt.encode("utf-8"))
    layer = buf.getvalue()
    layer_hex = _h.sha256(layer).hexdigest()
    config = json.dumps({"architecture": "fake", "os": "linux",
                         "config": {"Labels": {"ke.fake.refs": " ".join(refs)}},
                         "rootfs": {"type": "layers", "diff_ids": ["sha256:" + layer_hex]}},
                        sort_keys=True).encode("utf-8")
    cfg_hex = _h.sha256(config).hexdigest()
    if form == "legacy":
        cfg_name, layer_name = cfg_hex + ".json", layer_hex + "/layer.tar"
    else:
        cfg_name, layer_name = "blobs/sha256/" + cfg_hex, "blobs/sha256/" + layer_hex
    entry = {"Config": cfg_name, "RepoTags": refs, "Layers": [layer_name]}
    manifest = [entry, dict(entry, RepoTags=["fake-second:entry"])] if form == "two" else [entry]
    with _tf.open(target, "w") as tar:
        _add(tar, cfg_name, config)
        _add(tar, layer_name, layer)
        if form != "legacy":
            _add(tar, "oci-layout", b'{"imageLayoutVersion": "1.0.0"}')
            _add(tar, "index.json", json.dumps({"schemaVersion": 2, "manifests": []}).encode("utf-8"))
        _add(tar, "manifest.json", json.dumps(manifest).encode("utf-8"))

if argv[:1] == ["save"] or argv[:2] == ["image", "save"]:
    out = opt_values("-o") + opt_values("--output")
    if out:
        target = out[-1]
        if not os.path.isdir(os.path.dirname(os.path.abspath(target))):
            sys.stderr.write("fake docker: save: no such directory for %s\n" % target)
            sys.exit(1)
        refs = [a for a in argv[1:] if not a.startswith("-") and a not in out
                and a not in opt_values("--platform") and a != "save"]
        # platform-sbom U4: as the real daemon, `save` of an image it does not
        # hold fails (it never pulls), when FAKE_DOCKER_IMAGES models the store.
        _stable = _image_table()
        for _sref in refs if _stable is not None else []:
            if _known_image(_sref, _stable) is None:
                sys.stderr.write("Error response from daemon: reference does not exist: %s\n" % _sref)
                sys.exit(1)
        if os.environ.get("FAKE_DOCKER_SAVE_TAR"):
            _write_image_tar(target, refs, os.environ["FAKE_DOCKER_SAVE_TAR"])
        else:
            with open(target, "wb") as fh:
                fh.write(("fake image tar for %s\n" % " ".join(refs)).encode("utf-8"))
        if os.environ.get("FAKE_DOCKER_SAVE_MODE"):
            os.chmod(target, int(os.environ["FAKE_DOCKER_SAVE_MODE"], 8))
    sys.exit(0)

if argv[:1] == ["load"] or argv[:2] == ["image", "load"]:
    src = opt_values("-i") + opt_values("--input")
    if src:
        path = src[-1]
        if not os.path.isfile(path):
            sys.stderr.write("open %s: no such file or directory\n" % path)
            sys.exit(1)
        table = json.loads(os.environ.get("FAKE_DOCKER_LOAD") or "{}")
        base = os.path.basename(path.replace("\\", "/"))
        loaded_log = os.environ.get("FAKE_DOCKER_LOADED_LOG")
        if loaded_log:
            import hashlib
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            with open(loaded_log, "a", encoding="utf-8") as fh:
                fh.write("%s %s\n" % (base, digest))
        if base in table:
            text = table[base]
            if text:
                sys.stdout.write(text if text.endswith("\n") else text + "\n")
        else:
            import hashlib
            with open(path, "rb") as fh:
                print("Loaded image ID: sha256:" + hashlib.sha256(fh.read()).hexdigest())
    sys.exit(0)

if not argv or argv[0] != "compose":
    sys.exit(0)

if "version" in argv:
    _v = os.environ.get("FAKE_COMPOSE_VERSION") or VERSION
    print(_v if "--short" in argv else "Docker Compose version v" + _v)
    sys.exit(0)

def parse_dotenv(path):
    values = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh.read().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            cut = [i for i in (line.find("="), line.find(":")) if i > 0]
            if not cut:
                continue
            i = min(cut)
            key, value = line[:i].strip(), line[i + 1:].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            else:
                hash_at = value.find(" #")
                if hash_at >= 0:
                    value = value[:hash_at].rstrip()
            values[key] = value
    return values

def interpolation_env():
    files = opt_values("--env-file")
    merged = {}
    if files:
        for f in files:
            if not os.path.isfile(f):
                sys.stderr.write("fake docker: env file %s not found\n" % f)
                sys.exit(1)
            merged.update(parse_dotenv(f))
    elif os.path.isfile(os.path.join(pdir, ".env")):
        merged.update(parse_dotenv(os.path.join(pdir, ".env")))
    for k, v in os.environ.items():
        if k.startswith("KE_") or k.startswith("PHOENIX_"):
            merged[k] = v
    return merged

# platform-sbom U3 (PSC-13, N1): a file of its own (FAKE_COMPOSE_FILE_IMAGES)
# is loaded by every command, so its ${VAR:?} check applies to run and down
# too; `run ... sbom docker-archive:/in/<name>.tar ...` models syft.
_u3_images = json.loads(os.environ.get("FAKE_COMPOSE_FILE_IMAGES") or "{}")
_u3_files = opt_values("-f") + opt_values("--file")
if not _u3_files and os.environ.get("COMPOSE_FILE"):
    _u3_files = os.environ["COMPOSE_FILE"].split(os.environ.get("COMPOSE_PATH_SEPARATOR") or os.pathsep)
_u3_own = [os.path.basename(f) for f in _u3_files if os.path.basename(f) in _u3_images]
if _u3_own and "config" not in argv and "--no-interpolate" not in argv:
    _u3_env = interpolation_env()
    for _var in json.loads(os.environ.get("FAKE_COMPOSE_FILE_REQUIRED") or "{}").get(_u3_own[0], []):
        if not _u3_env.get(_var):
            sys.stderr.write("error while interpolating %s: required variable %s is missing a value\n"
                             % (_u3_own[0], _var))
            sys.exit(1)

def _pep503(n):
    import re as _re
    return _re.sub(r"[-_.]+", "-", n).lower()

def _syft_doc(name, ver):
    import hashlib as _h, re as _re, time as _time, uuid as _uuid
    from urllib.parse import quote as _quote
    def _id(prefix, *parts):
        stem = _re.sub(r"[^A-Za-z0-9.-]", "-", parts[0])
        return "SPDXRef-%s-%s-%s" % (prefix, stem, _h.sha256("|".join(parts).encode()).hexdigest()[:16])
    root = {"name": "/in/%s.tar" % name, "SPDXID": "SPDXRef-DocumentRoot-Image-" + _re.sub(r"[^A-Za-z0-9.-]", "-", name),
            "versionInfo": "sha256:" + _h.sha256(name.encode()).hexdigest(), "supplier": "NOASSERTION",
            "downloadLocation": "NOASSERTION", "filesAnalyzed": False, "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION", "copyrightText": "NOASSERTION", "primaryPackagePurpose": "CONTAINER"}
    status = {"fileName": "/var/lib/dpkg/status", "SPDXID": _id("File", "var-lib-dpkg-status", name),
              "checksums": [{"algorithm": "SHA1", "checksumValue": "0" * 40}],
              "licenseConcluded": "NOASSERTION", "copyrightText": ""}
    pkgs, rels = [], [{"spdxElementId": "SPDXRef-DOCUMENT", "relatedSpdxElement": root["SPDXID"],
                       "relationshipType": "DESCRIBES"}]
    debs = [("base-files", "12.4+deb12u13", "GPL-2.0-or-later"),
            ("libc6", "2.36-9+deb12u13", "GPL-2.0-only AND LGPL-2.1-only")]
    if name == "ke-app":
        debs.append(("libpq5", LIBPQ_PIN, "PostgreSQL"))
    for n, v, lic in debs:
        p = {"name": n, "SPDXID": _id("Package-deb", n, v), "versionInfo": v, "supplier": "Person: Debian",
             "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
             "sourceInfo": "acquired package info from DPKG DB: /var/lib/dpkg/status",
             "licenseConcluded": "NOASSERTION", "licenseDeclared": lic, "copyrightText": "NOASSERTION",
             "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                               "referenceLocator": "pkg:deb/debian/%s@%s?arch=amd64&distro=debian-12"
                               % (n, _quote(v, safe=""))}]}
        pkgs.append(p)
        rels.append({"spdxElementId": p["SPDXID"], "relatedSpdxElement": status["SPDXID"],
                     "relationshipType": "OTHER",
                     "comment": "evident-by: indicates the package's existence is evident by the given file"})
    if name == "ke-app":
        venv = json.loads(os.environ.get("FAKE_IMAGE_PATHS") or "{}").get("/opt/venv")
        site = os.path.join(venv, "lib", "python3.12", "site-packages") if venv else ""
        drop = {_pep503(d) for d in os.environ.get("FAKE_SYFT_DROP", "").split(",") if d}
        versions = {_pep503(k): v for k, v in json.loads(os.environ.get("FAKE_SYFT_PYPI_VERSIONS") or "{}").items()}
        for dist in sorted(os.listdir(site)) if site and os.path.isdir(site) else []:
            if not dist.endswith(".dist-info"):
                continue
            meta = {}
            with open(os.path.join(site, dist, "METADATA"), encoding="utf-8") as fh:
                for line in fh.read().split("\n\n", 1)[0].splitlines():
                    k, _, v = line.partition(": ")
                    meta.setdefault(k, v)
            n, v = meta.get("Name", ""), meta.get("Version", "")
            if not n or _pep503(n) in drop:
                continue
            v = versions.get(_pep503(n), v)
            pkgs.append({"name": n, "SPDXID": _id("Package-python", n, v), "versionInfo": v,
                         "supplier": "NOASSERTION", "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                         "sourceInfo": "acquired package info from installed python package manifest file: "
                                       "/opt/venv/lib/python3.12/site-packages/%s/METADATA" % dist,
                         "licenseConcluded": "NOASSERTION",
                         "licenseDeclared": meta.get("License-Expression", "NOASSERTION"),
                         "copyrightText": "NOASSERTION",
                         "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                                           "referenceLocator": "pkg:pypi/%s@%s" % (n, _quote(v, safe=""))}]})
    for p in pkgs:
        rels.append({"spdxElementId": root["SPDXID"], "relatedSpdxElement": p["SPDXID"],
                     "relationshipType": "CONTAINS"})
    return {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": "/in/%s.tar" % name,
            "documentNamespace": "https://anchore.com/syft/file/in/%s.tar-%s" % (name, _uuid.uuid4()),
            "creationInfo": {"licenseListVersion": "3.27",
                             "creators": ["Organization: Anchore, Inc", "Tool: syft-" + ver],
                             "created": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())},
            "packages": [root] + pkgs, "files": [status], "relationships": rels}

def _syft_cache_warning(files, own, env):
    """platform-sbom U4 rework 1 (review B1, security L-2; u4/windows-run.txt
    3c, u4/security-probes.txt 5): syft's filesystem cache, modelled from the
    compose file's `sbom` service. The cache is $XDG_CACHE_HOME/syft (else
    $HOME/.cache/syft, HOME "/" in the syft image). The syft image's own
    directories are 0755 root and a tmpfs over one takes that mode unless its
    entry sets mode=; the root is read-only. A non-root user that cannot
    create the cache gets syft's warning line, returned here ("" if none)."""
    import posixpath as _pp, re as _re
    path = next(f for f in files if os.path.basename(f) == own)
    try:
        import yaml as _yaml
        with open(path, encoding="utf-8") as fh:
            svc = (_yaml.safe_load(fh) or {})["services"]["sbom"]
    except Exception as exc:  # the model must never pass silently
        sys.stderr.write("fake syft: cannot model the cache from %s: %r\n" % (path, exc))
        sys.exit(1)

    def interp(value):
        return _re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}", lambda m: env.get(m.group(1), ""), str(value))
    senv = svc.get("environment") or {}
    if isinstance(senv, list):
        senv = dict(str(e).split("=", 1) if "=" in str(e) else (str(e), "") for e in senv)
    senv = {k: interp(v) for k, v in senv.items()}
    cache = _pp.join(_pp.normpath(senv.get("XDG_CACHE_HOME") or _pp.join(senv.get("HOME") or "/", ".cache")),
                     "syft")
    user = interp(svc.get("user", "")).strip()
    root_user = user in ("", "0", "root") or user.startswith(("0:", "root:"))
    mounts = [("/", "root", None)]
    raw = svc.get("tmpfs") or []
    for entry in [raw] if isinstance(raw, str) else raw:
        target, _, opts = str(entry).partition(":")
        mode = 0o755
        for opt in opts.split(","):
            if opt.startswith("mode="):
                mode = int(opt[len("mode="):], 8)
        mounts.append((_pp.normpath(target), "tmpfs", mode))
    for vol in svc.get("volumes") or []:
        if isinstance(vol, dict):
            target, ro = str(vol.get("target", "")), bool(vol.get("read_only"))
        else:
            parts = str(vol).split(":")
            target, ro = parts[1] if len(parts) > 1 else parts[0], len(parts) > 2 and "ro" in parts[2].split(",")
        mounts.append((_pp.normpath(target), "bind", ro))
    target, kind, attr = max((m for m in mounts if m[0] == "/" or cache == m[0] or cache.startswith(m[0] + "/")),
                             key=lambda m: len(m[0]))
    if kind == "tmpfs":
        reason = None if root_user or attr & 0o002 else "permission denied"
    elif kind == "bind":
        reason = "read-only file system" if attr else None
    else:
        reason = "read-only file system" if svc.get("read_only") else (None if root_user else "permission denied")
    if reason is None:
        return ""
    first = _pp.join(target, cache[len(target):].lstrip("/").split("/")[0])
    return ("[0000]  WARN unable to get filesystem cache at %s: unable to create directory at '%s': mkdir %s: %s"
            % (cache, cache, first, reason))

if _u3_own and "run" in argv:
    _at3 = argv.index("run")
    _takes3 = {"-e", "--env", "-u", "--user", "-v", "--volume", "--name", "--entrypoint", "-w",
               "--workdir", "-l", "--label", "-p", "--publish", "--pull", "--cap-add", "--cap-drop"}
    _i3, _svc3 = _at3 + 1, None
    while _i3 < len(argv):
        if argv[_i3] in _takes3:
            _i3 += 2
            continue
        if argv[_i3].startswith("-"):
            _i3 += 1
            continue
        _svc3 = argv[_i3]
        break
    if _svc3 == "sbom":
        import re as _re3
        _args3 = argv[_i3 + 1:]
        _env3 = interpolation_env()
        _src3 = _args3[0] if _args3 else ""
        if not _src3.startswith("docker-archive:/in/"):
            sys.stderr.write("fake syft: want docker-archive:/in/<name>.tar first, got %r\n" % _src3)
            sys.exit(1)
        _tar3 = os.path.join(_env3.get("KE_SBOM_IN", ""), _src3[len("docker-archive:/in/"):])
        _outs3, _j3 = [], 0
        while _j3 < len(_args3):
            if _args3[_j3] in ("-o", "--output") and _j3 + 1 < len(_args3):
                _outs3.append(_args3[_j3 + 1])
                _j3 += 2
                continue
            if _args3[_j3].startswith(("-o=", "--output=")):
                _outs3.append(_args3[_j3].split("=", 1)[1])
            _j3 += 1
        _spdx3 = [o.split("=", 1)[1] for o in _outs3 if o.startswith("spdx-json=")]
        if not _spdx3 or not _spdx3[-1].startswith("/out/"):
            sys.stderr.write("fake syft: want -o spdx-json=/out/<file>\n")
            sys.exit(1)
        _cache3 = _syft_cache_warning(_u3_files, _u3_own[0], _env3)
        if _cache3:
            sys.stderr.write(_cache3 + "\n")
        _work3 = _env3.get("KE_SBOM_OUT", "")
        _name3 = os.path.basename(_tar3)
        _name3 = _name3[:-4] if _name3.endswith(".tar") else _name3
        if os.environ.get("FAKE_SYFT_LOG"):
            _tmp3 = os.path.join(_work3, "tmp")
            with open(os.environ["FAKE_SYFT_LOG"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "name": _name3, "in": _env3.get("KE_SBOM_IN", ""), "out": _work3,
                    "user": _env3.get("KE_SBOM_USER"),
                    "out_entries": sorted(os.listdir(_work3)) if os.path.isdir(_work3) else None,
                    "tmp_entries": sorted(os.listdir(_tmp3)) if os.path.isdir(_tmp3) else None,
                    "out_mode": (os.stat(_work3).st_mode & 0o7777) if os.path.isdir(_work3) else None,
                    "tmp_mode": (os.stat(_tmp3).st_mode & 0o7777) if os.path.isdir(_tmp3) else None}) + "\n")
        if not os.path.isfile(_tar3):
            sys.stderr.write("1 error occurred:\n\t* could not open docker-archive:/in/%s.tar\n" % _name3)
            sys.exit(1)
        if not os.path.isdir(os.path.join(_work3, "tmp")):
            sys.stderr.write("mkdir /out/tmp/stereoscope-1: no such file or directory\n")
            sys.exit(1)
        os.makedirs(os.path.join(_work3, "tmp", "stereoscope-fake"), exist_ok=True)
        with open(os.path.join(_work3, "tmp", "stereoscope-fake", "layer.tar"), "wb") as fh:
            fh.write(b"unpacked layer (fake)\n")
        _raw3 = json.loads(os.environ.get("FAKE_SYFT_RAW") or "{}").get(_name3)
        if _raw3 is None:
            _m3 = _re3.search(r":v(\d+\.\d+\.\d+)", str(_u3_images[_u3_own[0]].get("sbom", "")))
            _raw3 = json.dumps(_syft_doc(_name3, _m3.group(1) if _m3 else "0.0.0"), indent=1)
        with open(os.path.join(_work3, _spdx3[-1][len("/out/"):]), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_raw3)
        sys.exit(0)
    if _svc3 in ("sources-resolve", "sources-fetch"):
        # platform-sbom U7b rework round 1 (design-notes, U7b rework round 1,
        # item 12): the real scripts/sources_resolve.py, read from its bind in
        # the compose file, under this interpreter; every bind of the service
        # maps its target to its source; OPENER is FAKE_RESOLVE_NET.
        # U8b (N4 amendment U8 item 12): `sources-fetch` runs the real
        # scripts/sources_fetch.py the same way; its hook is `R.OPENER`.
        import subprocess as _subprocess
        _env4 = interpolation_env()
        _path4 = next(f for f in _u3_files if os.path.basename(f) == _u3_own[0])
        try:
            import yaml as _yaml4
            with open(_path4, encoding="utf-8") as fh:
                _svc4 = (_yaml4.safe_load(fh) or {})["services"][_svc3]
        except Exception as exc:  # the model must never pass silently
            sys.stderr.write("fake %s: cannot read %s: %r" % (_svc3, _path4, exc) + chr(10))
            sys.exit(1)

        def _interp4(value):
            text, out = str(value), ""
            while "${" in text:
                head, _, rest = text.partition("${")
                body, _, text = rest.partition("}")
                name, op, word = body, "", ""
                for sep in (":?", ":-"):
                    if sep in body:
                        name, _, word = body.partition(sep)
                        op = sep
                        break
                val = _env4.get(name, "")
                if op == ":?" and not val:
                    sys.stderr.write("error while interpolating %s: required variable %s is missing a value: %s"
                                     % (os.path.basename(_path4), name, word) + chr(10))
                    sys.exit(1)
                out += head + (word if op == ":-" and not val else val)
            return out + text

        _interp4(_svc4.get("user", ""))
        _base4 = os.path.dirname(os.path.abspath(_path4))
        _pairs4 = []
        for _vol4 in _svc4.get("volumes") or []:
            if not isinstance(_vol4, dict) or _vol4.get("type") != "bind":
                sys.stderr.write("fake %s: only long-form binds are modelled" % _svc3 + chr(10))
                sys.exit(1)
            _s4 = _interp4(_vol4["source"])
            if not os.path.isabs(_s4):
                _s4 = os.path.normpath(os.path.join(_base4, _s4))
            if not os.path.exists(_s4):
                sys.stderr.write("Error response from daemon: invalid mount config: bind source path does not "
                                 "exist: %s" % _s4 + chr(10))
                sys.exit(1)
            _pairs4.append((_vol4["target"], _s4))

        def _remap4(t):
            best = None
            for c, h in _pairs4:
                if t == c or t.startswith(c.rstrip("/") + "/"):
                    if best is None or len(c) > len(best[0]):
                        best = (c, h)
            return t if best is None else best[1] + t[len(best[0]):]

        _entry4 = [str(x) for x in _svc4.get("entrypoint") or []]
        if _entry4[:2] != ["python3", "-I"] or len(_entry4) < 3:
            sys.stderr.write("fake %s: want an entrypoint python3 -I <script> ..., got %r" % (_svc3, _entry4)
                             + chr(10))
            sys.exit(1)
        _script4 = _remap4(_entry4[2])
        if not os.path.isfile(_script4):
            sys.stderr.write("python3: can't open file %r: [Errno 2] No such file or directory" % _entry4[2] + chr(10))
            sys.exit(2)
        _boot4 = chr(10).join([
            "import importlib.util, json, os, sys, types",
            "name = 'sources_fetch' if sys.argv[2] == 'sources-fetch' else 'sources_resolve'",
            "spec = importlib.util.spec_from_file_location(name, sys.argv[1])",
            "mod = importlib.util.module_from_spec(spec)",
            "sys.modules[name] = mod",
            "spec.loader.exec_module(mod)",
            "hook = mod.R if name == 'sources_fetch' else mod",
            "net = json.loads(os.environ.get('FAKE_RESOLVE_NET') or '{}')",
            "log = os.environ.get('FAKE_RESOLVE_LOG')",
            "def opener(url, timeout):",
            "    if log:",
            "        with open(log, 'a', encoding='utf-8') as fh:",
            "            fh.write(url + chr(10))",
            "    st, hd, body = net.get(url, [404, {}, 'not found'])",
            "    return types.SimpleNamespace(status=st, headers={k.lower(): v for k, v in hd.items()},",
            "                                 body=[body.encode('utf-8')])",
            "hook.OPENER = opener",
            "sys.exit(mod.main(sys.argv[3:]))",
            ""])
        sys.stdout.flush()
        _done4 = _subprocess.run([sys.executable, "-I", "-S", "-B", "-c", _boot4, _script4, _svc3,
                                  *[_remap4(a) for a in _entry4[3:] + argv[_i3 + 1:]]])
        sys.exit(_done4.returncode)

if "config" in argv:
    env = interpolation_env()
    resolved = {
        "KE_ENV": env.get("KE_ENV", ""),
        "KE_BIND_ADDRESS": env.get("KE_BIND_ADDRESS") or "127.0.0.1",
        "KE_API_PORT": env.get("KE_API_PORT") or "47100",
        "KE_PHOENIX_PORT": env.get("KE_PHOENIX_PORT") or "47101",
        "KE_MODEL_UPSTREAM": env.get("KE_MODEL_UPSTREAM", ""),
        "KE_EGRESS_ALLOWLIST": env.get("KE_EGRESS_ALLOWLIST", ""),
        "KE_GATEWAY_API_LISTEN": env.get("KE_GATEWAY_API_LISTEN") or "8100",
        "KE_IMAGE_TAG": env.get("KE_IMAGE_TAG") or "local",
    }
    resolved.update(json.loads(os.environ.get("FAKE_COMPOSE_RESOLVED") or "{}"))
    stack_images = os.environ.get("FAKE_COMPOSE_IMAGES")
    images = None
    depends = json.loads(os.environ.get("FAKE_COMPOSE_DEPENDS") or "null")
    wanted = []
    # platform-sbom U2 (PSC-20): a compose file of its own, named by -f/--file
    # (else COMPOSE_FILE) and listed in FAKE_COMPOSE_FILE_IMAGES, answers from
    # that entry instead of the stack's, with no depends_on and no profile
    # images; its FAKE_COMPOSE_FILE_REQUIRED variables must be set and
    # non-empty unless --no-interpolate is given, as real compose requires.
    _file_images = json.loads(os.environ.get("FAKE_COMPOSE_FILE_IMAGES") or "{}")
    _cfiles = opt_values("-f") + opt_values("--file")
    if not _cfiles and os.environ.get("COMPOSE_FILE"):
        _cfiles = os.environ["COMPOSE_FILE"].split(os.environ.get("COMPOSE_PATH_SEPARATOR") or os.pathsep)
    _own = [os.path.basename(f) for f in _cfiles if os.path.basename(f) in _file_images]
    if _own:
        if "--no-interpolate" not in argv:
            _required = json.loads(os.environ.get("FAKE_COMPOSE_FILE_REQUIRED") or "{}").get(_own[0], [])
            for _var in _required:
                if not env.get(_var):
                    sys.stderr.write("error while interpolating %s: required variable %s is missing a value\n"
                                     % (_own[0], _var))
                    sys.exit(1)
        stack_images = json.dumps(_file_images[_own[0]])
        depends = None
    if stack_images is not None:
        images = dict(json.loads(stack_images))
        if opt_values("--profile") and not _own:
            images.update(json.loads(os.environ.get("FAKE_COMPOSE_PROFILE_IMAGES") or "{}"))
        at = argv.index("config")
        skip = (set(opt_values("--format")) | set(opt_values("-o")) | set(opt_values("--output"))
                | set(opt_values("--profile")))
        wanted = [a for a in argv[at + 1:] if not a.startswith("-") and a not in skip]
        if depends is not None:
            unknown = [w for w in wanted if w not in images]
            if unknown:
                sys.stderr.write("no such service: %s\n" % unknown[0])
                sys.exit(1)
        def with_deps(names):
            # The named services and, transitively, their depends_on services
            # (only those that exist in this project's model).
            seen, todo = [], list(names)
            while todo:
                svc = todo.pop(0)
                if svc in seen or svc not in images:
                    continue
                seen.append(svc)
                todo.extend((depends or {}).get(svc, []))
            return seen
        if "--images" in argv:
            out = []
            if depends is None:
                for svc, img in images.items():
                    if (not wanted or svc in wanted) and img not in out:
                        out.append(img)
            else:
                import random as _random
                for svc in with_deps(wanted or list(images)):
                    if images[svc] not in out:
                        out.append(images[svc])
                _random.Random(os.environ.get("FAKE_COMPOSE_SEED")).shuffle(out)
            if out:
                print("\n".join(out))
            sys.exit(0)
    if "--environment" in argv:
        env.update(resolved)
        for k in sorted(env):
            print("%s=%s" % (k, env[k]))
        sys.exit(0)
    names = ["gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix"]
    if images is not None:
        names = list(images)
    if "--services" in argv:
        print("\n".join(names))
        sys.exit(0)
    app_env = {"KE_ENV": resolved["KE_ENV"], "KE_BIND_ADDRESS": resolved["KE_BIND_ADDRESS"]}
    ports = [
        {"mode": "ingress", "host_ip": resolved["KE_BIND_ADDRESS"],
         "target": int(resolved["KE_GATEWAY_API_LISTEN"])
         if str(resolved["KE_GATEWAY_API_LISTEN"]).isdigit() else resolved["KE_GATEWAY_API_LISTEN"],
         "published": resolved["KE_API_PORT"], "protocol": "tcp"},
        {"mode": "ingress", "host_ip": resolved["KE_BIND_ADDRESS"], "target": 8101,
         "published": resolved["KE_PHOENIX_PORT"], "protocol": "tcp"},
    ]
    if os.environ.get("FAKE_COMPOSE_PORTS"):
        ports = json.loads(os.environ["FAKE_COMPOSE_PORTS"])
    model = {"name": project, "services": {
        "gateway": {"environment": dict(app_env, KE_MODEL_UPSTREAM=resolved["KE_MODEL_UPSTREAM"],
                                        KE_EGRESS_ALLOWLIST=resolved["KE_EGRESS_ALLOWLIST"],
                                        KE_GATEWAY_API_LISTEN=str(resolved["KE_GATEWAY_API_LISTEN"])),
                    "networks": {"backend": None, "edge": None},
                    "ports": ports},
        "api": {"environment": dict(app_env), "networks": {"backend": None}},
        "worker": {"environment": dict(app_env), "networks": {"backend": None}},
    }}
    if images is None:
        for extra in names[3:]:
            model["services"][extra] = {"networks": {"backend": None}}
        # platform-offline (ci/offline): the first-party images, as compose
        # resolves ${KE_IMAGE_TAG:-local}.
        model["services"]["gateway"]["image"] = "ke-gateway:" + resolved["KE_IMAGE_TAG"]
        for svc in ("api", "worker"):
            model["services"][svc]["image"] = "ke-app:" + resolved["KE_IMAGE_TAG"]
    else:
        for svc in list(model["services"]):
            if svc not in images:
                del model["services"][svc]
        for svc, img in images.items():
            model["services"].setdefault(svc, {"networks": {"backend": None}})["image"] = img
        if depends is not None:
            for svc, entry in model["services"].items():
                deps = [d for d in depends.get(svc, []) if d in images]
                if deps:
                    entry["depends_on"] = {d: {"condition": "service_healthy", "required": True}
                                           for d in deps}
            if wanted:
                keep = with_deps(wanted)
                model["services"] = {s: e for s, e in model["services"].items() if s in keep}
    model["networks"] = {
        "backend": {"name": project + "_backend", "internal": True,
                    "driver_opts": dict(ISOLATED)},
        "edge": {"name": project + "_edge"},
    }
    if "json" in opt_values("--format"):
        print(json.dumps(model, indent=2))
        sys.exit(0)
    def q(v):
        return json.dumps(v) if (v == "" or v.isdigit()) else v
    out = ["name: " + model["name"], "services:"]
    for name, svc in model["services"].items():  # YAML: services only
        out.append("  %s:" % name)
        if "image" in svc:
            out.append("    image: %s" % svc["image"])
        if "environment" in svc:
            out.append("    environment:")
            for k, v in svc["environment"].items():
                out.append("      %s: %s" % (k, q(v)))
        out.append("    networks:")
        for n in svc["networks"]:
            out.append("      %s: null" % n)
        if "ports" in svc:
            out.append("    ports:")
            for p in svc["ports"]:
                out.append("      - mode: ingress")
                if "host_ip" in p:
                    out.append("        host_ip: %s" % p["host_ip"])
                out.append("        target: %s" % p["target"])
                out.append("        published: %s" % json.dumps(p["published"]))
                out.append("        protocol: tcp")
    print("\n".join(out))
    sys.exit(0)

if "ps" in argv:
    running = os.environ.get("FAKE_DOCKER_RUNNING", "")
    _at = argv.index("ps")
    _vals = set(opt_values("--format")) | set(opt_values("--filter")) | set(opt_values("--status"))
    _named = [a for a in argv[_at + 1:] if not a.startswith("-") and a not in _vals]
    if ("-q" in argv or "--quiet" in argv) and _named:
        _ids = _service_ids()
        for _svc in _named:
            if _ids.get(_svc, "fake%s000000" % _svc):
                print(_ids.get(_svc, "fake%s000000" % _svc))
        sys.exit(0)
    if "-q" in argv or "--quiet" in argv:
        if running:
            print(running)
        sys.exit(0)
    if "--services" in argv:
        if running:
            print("\n".join(["gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix"]))
        sys.exit(0)
    print(os.environ.get("FAKE_DOCKER_HEALTH", "healthy"))
    sys.exit(0)

if "exec" in argv and "engine.netprobe" in joined:
    _at = argv.index("exec")
    _takes = {"-e", "--env", "-u", "--user", "-w", "--workdir", "--index"}
    _svc, _i = None, _at + 1
    while _i < len(argv):
        if argv[_i] in _takes:
            _i += 2
            continue
        if argv[_i].startswith("-"):
            _i += 1
            continue
        _svc = argv[_i]
        break
    _netprobe_reply(json.loads(os.environ.get("FAKE_NETPROBE") or "{}").get(_svc, "no_route"))

if "exec" in argv and "KE_GATEWAY_API_LISTEN" in joined:
    print('{"status":"ok"}')
    sys.exit(0)

sys.exit(0)
'''


def _libpq_pin() -> str:
    """The `ARG LIBPQ_VERSION=` pin of docker/app.Dockerfile (platform-sbom U0),
    or a bookworm-shaped stand-in while the Dockerfile has none."""
    import re

    path = Path(__file__).resolve().parent.parent / "docker" / "app.Dockerfile"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    m = re.search(r"(?m)^\s*ARG\s+LIBPQ_VERSION=(\S+)\s*$", text)
    return m.group(1).strip("\"'") if m else "15.14-0+deb12u1"


def install(bin_dir: Path) -> Path:
    """Write the fake `docker` into `bin_dir` and return its path."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "docker"
    fake.write_text(f"#!{sys.executable}\nVERSION = {VERSION!r}\nLIBPQ_PIN = {_libpq_pin()!r}\n"
                    f"DIAG_TEMPLATE = {DIAG_TEMPLATE!r}\nEVENTS_FORMAT = {EVENTS_FORMAT!r}\n{_SCRIPT}",
                    encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    return fake


_DF_SCRIPT = r'''
import os, sys
argv = sys.argv[1:]
log = os.environ.get("FAKE_DF_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(" ".join(argv) + "\n")
import json
jlog = os.environ.get("FAKE_DF_JSON")
if jlog:
    with open(jlog, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": ["DF"] + argv, "env": {}, "cwd": os.getcwd(),
                             "project_dir": "", "dotenv_present": False}) + "\n")
_fail = os.environ.get("FAKE_DF_FAIL") or ""
if _fail and (_fail == "1" or set(a for a in argv if not a.startswith("-")) & set(_fail.split("|"))):
    sys.stderr.write("df: cannot read table of mounted file systems: fake failure\n")
    sys.exit(1)
by_path = json.loads(os.environ.get("FAKE_DF_AVAIL_BY_PATH") or "{}")
default_avail = int(os.environ.get("FAKE_DF_AVAIL_KB") or str(50 * 1024 * 1024))
fs = os.environ.get("FAKE_DF_FILESYSTEM") or "/dev/fake"
paths = [a for a in argv if not a.startswith("-")] or ["/"]
print("Filesystem     1024-blocks      Used Available Capacity Mounted on")
for path in paths:
    avail = int(by_path.get(path, default_avail))
    total = int(os.environ.get("FAKE_DF_TOTAL_KB") or str(max(avail * 2, 1)))
    used = total - avail
    print("%s %15d %9d %9d %7d%% /" % (fs, total, used, avail, used * 100 // total))
'''


def install_df(bin_dir: Path) -> Path:
    """Write a fake `df` into `bin_dir` (FAKE_DF_AVAIL_KB, FAKE_DF_LOG) and return its path."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "df"
    fake.write_text(f"#!{sys.executable}\n{_DF_SCRIPT}", encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    return fake


def records(path: Path) -> list[dict]:
    """The JSON call records written to FAKE_DOCKER_JSON."""
    import json

    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
