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
    directory must exist), so manifests can hash it.
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
- Every other call exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

VERSION = "2.29.7"

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
    if hook.get("touch"):
        with open(hook["touch"], "a", encoding="utf-8"):
            pass
    if hook.get("sleep"):
        import time as _time
        _time.sleep(float(hook["sleep"]))

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
           "OSType": "linux"}
    fmt = format_values()
    if fmt and "Client" not in fmt[-1]:
        def sub(m):
            if m.group(2) == "":
                return json.dumps(rec) if m.group(1) else str(rec)
            val = rec.get(m.group(2), "")
            return json.dumps(val) if m.group(1) else str(val)
        print(_re.sub(r"\{\{\s*(json\s+)?\.([A-Za-z0-9_]*)\s*\}\}", sub, fmt[-1]))
    elif fmt:
        print(CLIENT_VERSION)
    else:
        print("Client:\n Version:           %s\n\nServer:\n Engine:\n  Version:          %s\n"
              " Architecture: %s" % (CLIENT_VERSION, rec["ServerVersion"], arch))
    code = int(os.environ.get("FAKE_DOCKER_ENGINE_EXIT") or "0")
    if code:
        sys.stderr.write("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
                         "Is the docker daemon running?\n")
        sys.exit(code)
    sys.exit(0)

if argv[:1] == ["info"]:
    info_reply()

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

if argv[:1] == ["save"] or argv[:2] == ["image", "save"]:
    out = opt_values("-o") + opt_values("--output")
    if out:
        target = out[-1]
        if not os.path.isdir(os.path.dirname(os.path.abspath(target))):
            sys.stderr.write("fake docker: save: no such directory for %s\n" % target)
            sys.exit(1)
        refs = [a for a in argv[1:] if not a.startswith("-") and a not in out
                and a not in opt_values("--platform") and a != "save"]
        with open(target, "wb") as fh:
            fh.write(("fake image tar for %s\n" % " ".join(refs)).encode("utf-8"))
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

if "config" in argv:
    env = interpolation_env()
    resolved = {
        "KE_ENV": env.get("KE_ENV", ""),
        "KE_BIND_ADDRESS": env.get("KE_BIND_ADDRESS") or "127.0.0.1",
        "KE_API_PORT": env.get("KE_API_PORT") or "47100",
        "KE_PHOENIX_PORT": env.get("KE_PHOENIX_PORT") or "47101",
        "KE_MODEL_UPSTREAM": env.get("KE_MODEL_UPSTREAM", ""),
        "KE_EGRESS_ALLOWLIST": env.get("KE_EGRESS_ALLOWLIST", ""),
    }
    resolved.update(json.loads(os.environ.get("FAKE_COMPOSE_RESOLVED") or "{}"))
    stack_images = os.environ.get("FAKE_COMPOSE_IMAGES")
    images = None
    depends = json.loads(os.environ.get("FAKE_COMPOSE_DEPENDS") or "null")
    wanted = []
    if stack_images is not None:
        images = dict(json.loads(stack_images))
        if opt_values("--profile"):
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
        {"mode": "ingress", "host_ip": resolved["KE_BIND_ADDRESS"], "target": 8100,
         "published": resolved["KE_API_PORT"], "protocol": "tcp"},
        {"mode": "ingress", "host_ip": resolved["KE_BIND_ADDRESS"], "target": 8101,
         "published": resolved["KE_PHOENIX_PORT"], "protocol": "tcp"},
    ]
    if os.environ.get("FAKE_COMPOSE_PORTS"):
        ports = json.loads(os.environ["FAKE_COMPOSE_PORTS"])
    model = {"name": project, "services": {
        "gateway": {"environment": dict(app_env, KE_MODEL_UPSTREAM=resolved["KE_MODEL_UPSTREAM"],
                                        KE_EGRESS_ALLOWLIST=resolved["KE_EGRESS_ALLOWLIST"]),
                    "networks": {"backend": None, "edge": None},
                    "ports": ports},
        "api": {"environment": dict(app_env), "networks": {"backend": None}},
        "worker": {"environment": dict(app_env), "networks": {"backend": None}},
    }}
    if images is None:
        for extra in names[3:]:
            model["services"][extra] = {"networks": {"backend": None}}
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

if "exec" in argv and "KE_GATEWAY_API_LISTEN" in joined:
    print('{"status":"ok"}')
    sys.exit(0)

sys.exit(0)
'''


def install(bin_dir: Path) -> Path:
    """Write the fake `docker` into `bin_dir` and return its path."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "docker"
    fake.write_text(f"#!{sys.executable}\nVERSION = {VERSION!r}\n{_SCRIPT}",
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
avail = int(os.environ.get("FAKE_DF_AVAIL_KB") or str(50 * 1024 * 1024))
total = int(os.environ.get("FAKE_DF_TOTAL_KB") or str(max(avail * 2, 1)))
used = total - avail
fs = os.environ.get("FAKE_DF_FILESYSTEM") or "/dev/fake"
paths = [a for a in argv if not a.startswith("-")] or ["/"]
print("Filesystem     1024-blocks      Used Available Capacity Mounted on")
for _ in paths:
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
