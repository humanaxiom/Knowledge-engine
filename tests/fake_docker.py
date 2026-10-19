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
if argv[:1] == ["info"]:
    engine_reply(".ServerVersion")

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

if not argv or argv[0] != "compose":
    sys.exit(0)

if "version" in argv:
    print(VERSION if "--short" in argv else "Docker Compose version v" + VERSION)
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
    if "--environment" in argv:
        env.update(resolved)
        for k in sorted(env):
            print("%s=%s" % (k, env[k]))
        sys.exit(0)
    names = ["gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix"]
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
    for extra in names[3:]:
        model["services"][extra] = {"networks": {"backend": None}}
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


def records(path: Path) -> list[dict]:
    """The JSON call records written to FAKE_DOCKER_JSON."""
    import json

    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
