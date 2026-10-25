"""security U7b rework r1 probes (platform-sbom). python -I, gates image; fake network plus a loopback HTTP server."""
import hashlib, http.client, importlib.util, io, json, os, socket, sys, threading, time, contextlib, tempfile, subprocess
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
R = load("srv1", "/work/scripts/sources_resolve.py")
P = print
BS = chr(92)
POLICY = json.load(open("/work/docker/source-policy.json"))
ALLOW = set(POLICY["hosts"])
calls = []
class Net:
    def __init__(self, routes): self.routes = routes
    def __call__(self, url, timeout):
        calls.append(url)
        r = self.routes.get(url)
        if r is None:
            return R.Response(404, {}, b"")
        return r() if callable(r) else R.Response(*r)
def try_fetch(label, start, routes, first_allow=frozenset()):
    calls.clear(); R.OPENER = Net(routes)
    try:
        r = R.fetch(start, ALLOW, first_allow=first_allow); list(r.body); out = f"OK status={r.status}"
    except R.ResolveError as e:
        out = f"refused: {str(e)[:95]}"
    except Exception as e:
        out = f"RAISED {type(e).__name__}"
    P(f"  {label:46s} requests={[c[:60] for c in calls]} -> {out}")
G = "https://github.com/a"
P("== R1-1. First URL and hops ==")
for k, u in {"port": "https://github.com:8443/a", "userinfo": "https://evil@github.com/a", "backslash userinfo": "https://evil.example" + BS + "@github.com/a",
             "fragment": G + "#x", "query on first URL (resolver template)": G + "?x=1", "%2B in first URL path": "https://github.com/a/jdk-21%2B1/x",
             "//": "https://github.com//a", "/./": "https://github.com/./a", "upper-case scheme": "HTTPS://github.com/a", "upper-case host": "https://GITHUB.com/a",
             "tab": "https://git\thub.com/a", "pypi.org without first_allow": "https://pypi.org/pypi/x/1/json"}.items():
    try_fetch(f"first: {k}", u, {u: (200, {}, b"x")})
try_fetch("first: pypi.org with first_allow (JSON route)", "https://pypi.org/pypi/x/1/json", {"https://pypi.org/pypi/x/1/json": (200, {}, b"{}")}, frozenset({"pypi.org"}))
try_fetch("pypi JSON 302 -> pypi.org/other (hop)", "https://pypi.org/pypi/x/1/json",
          {"https://pypi.org/pypi/x/1/json": (302, {"Location": "/other"}, b""), "https://pypi.org/other": (200, {}, b"{}")}, frozenset({"pypi.org"}))
hops = {"relative /b": "/b", "query on an allowed host (signed asset)": "https://release-assets.githubusercontent.com/x/y?sig=abc&exp=1",
        "query to a non-listed host": "https://evil.example/x?sig=1", "pypi.org on a hop": "https://pypi.org/x",
        "port": "https://github.com:8443/b", "userinfo": "https://evil@github.com/b", "fragment": "https://github.com/b#f",
        "%2e%2e in path": "https://github.com/%2e%2e/b", "%2B in path": "https://github.com/a%2Bb", "HTTPS upper raw": "HTTPS://evil.example/b",
        "Https mixed raw": "Https://github.com/b", "https: no slashes": "https:evil.example/b", "https:/ one slash": "https:/evil.example/b",
        "scheme-relative": "//evil.example/b", "tab in raw Location": "https://git\thub.com/b", "LF in raw Location": "https://github.com/b\nX",
        "backslash path": "https:" + BS + BS + "evil.example/b", "dot segment": "/./b", "raw space": "/b c", "non-ASCII raw": "/\u00e9",
        "javascript:": "javascript:x", "relative with colon a:b": "a:b"}
for k, loc in hops.items():
    try_fetch(f"302 -> {k}", G, {G: (302, {"Location": loc}, b""), "https://github.com/b": (200, {}, b"ok"),
                                  "https://release-assets.githubusercontent.com/x/y?sig=abc&exp=1": (200, {}, b"ok")})
loop = {G: (302, {"Location": "/a"}, b"")}
try_fetch("redirect loop", G, loop)

P("\n== R1-2. Streaming guards ==")
def gen_body(n_chunks, size=65536, raise_at=None):
    def mk():
        def g():
            for i in range(n_chunks):
                if raise_at is not None and i == raise_at:
                    raise http.client.IncompleteRead(b"", 1)
                yield b"\0" * size
        return R.Response(200, {}, g())
    return mk
R.MAX_BYTES = 10 * 65536
consumed = {"n": 0}
def counting():
    def g():
        for i in range(10 ** 6):
            consumed["n"] += 1
            yield b"\0" * 65536
    return R.Response(200, {}, g())
R.OPENER = Net({G: counting})
try:
    R.stream(G, ALLOW); P("  cap: no error")
except R.ResolveError as e:
    P(f"  cap (patched to 10 chunks): aborted after {consumed['n']} chunks pulled: {str(e)[:80]}")
R.MAX_BYTES = 4294967296
for label, exc in (("IncompleteRead", http.client.IncompleteRead(b"", 1)), ("OSError", OSError("reset")), ("TimeoutError", TimeoutError()),
                   ("ValueError", ValueError("x"))):
    def mk(exc=exc):
        def g():
            yield b"x"
            raise exc
        return R.Response(200, {}, g())
    R.OPENER = Net({G: mk})
    try:
        R.stream(G, ALLOW); P(f"  {label}: no error")
    except R.ResolveError as e:
        P(f"  {label:14s} mid-body -> ResolveError: {e}")
    except BaseException as e:
        P(f"  {label:14s} mid-body -> escapes {type(e).__name__}")
def slow_chunks():
    def g():
        for i in range(100):
            time.sleep(0.1); yield b"x"
    return R.Response(200, {}, g())
R.DEADLINE = 1; R.OPENER = Net({G: slow_chunks}); t0 = time.perf_counter()
try:
    R.stream(G, ALLOW)
except R.ResolveError as e:
    P(f"  deadline (patched 1 s), many small chunks: aborted at {time.perf_counter() - t0:.1f}s: {str(e)[:60]}")

P("\n== R1-3. Drip-feed against the real opener (loopback HTTP; DEADLINE patched to 2 s, per-op timeout 5 s) ==")
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); port = srv.getsockname()[1]
def serve():
    c, _ = srv.accept(); c.recv(65536)
    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\nContent-Type: application/octet-stream\r\n\r\n")
    try:
        for i in range(400):
            c.sendall(b"x"); time.sleep(0.05)   # 1 byte per 50 ms, well inside the 5 s per-op timeout
    except OSError:
        pass
    c.close()
threading.Thread(target=serve, daemon=True).start()
url = f"http://127.0.0.1:{port}/drip"
result = {}
def run():
    t0 = time.monotonic()
    try:
        r = R._default_opener(url, 5)
        body = R._guarded(r, "127.0.0.1", url, t0, 5)
        n = 0
        for chunk in body:
            n += len(chunk)
        result["out"] = f"completed {n} bytes"
    except R.ResolveError as e:
        result["out"] = f"ResolveError after {time.monotonic() - t0:.1f}s: {str(e)[:70]}"
    except BaseException as e:
        result["out"] = f"{type(e).__name__} after {time.monotonic() - t0:.1f}s"
th = threading.Thread(target=run, daemon=True); t0 = time.monotonic(); th.start(); th.join(12)
P(f"  after {time.monotonic() - t0:.1f}s: {'still blocked inside one read (deadline 2 s not enforced within a chunk)' if th.is_alive() else result.get('out')}")

P("\n== R1-4. sources_lock.sh paths (no docker; tools check runs first) ==")
env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
for t in ("jq", "git", "docker"):
    P(f"  {t} on PATH: {bool(subprocess.run(['bash', '-c', f'command -v {t}'], capture_output=True, env=env).stdout)}")
r = subprocess.run(["bash", "/work/scripts/sources_lock.sh", "--arch", "amd64"], capture_output=True, text=True, env=env, cwd="/tmp")
P(f"  run with the tools missing: rc={r.returncode} stderr={r.stderr.strip()[:120]!r}")
src = open("/work/scripts/sources_lock.sh").read()
for needle in ("chmod 0644 -- \"$tmp\"", "if [ -n \"$tmp\" ]; then rm -f -- \"$tmp\"; fi", "--pending-neo4j", "six=(ke-app ke-gateway ke-neo4j phoenix postgres valkey)", "3) pending=1 ;;"):
    P(f"  script has {needle!r}: {needle in src}")
P("  grep in step 5:", "grep -v" in src.split("# --- 5.", 1)[1])
import json, os, subprocess, sys, tempfile
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
P = print
W = tempfile.mkdtemp()
def wj(n, o):
    p = os.path.join(W, n); open(p, "w").write(json.dumps(o)); return p
POLICY = json.load(open("/work/docker/source-policy.json")); polp = wj("pol.json", POLICY)
fd = tl.fixture_docs(); keys = sorted(tl.FIXTURE_KEYS)
args = []
for img, d in fd.items():
    args += ["--sbom", f"{img}={wj(img + '.json', d)}"]
def check(keep, label):
    lp = os.path.join(W, "l.json"); open(lp, "w", newline="").write(tl.canon(tl.good_lock(keep)))
    r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "lock-check", "--lock", lp, "--policy", polp, "--arch", "amd64", *args, "--pending-neo4j"],
                       capture_output=True, text=True)
    P(f"  {label:58s} rc={r.returncode} lines={len(r.stderr.strip().splitlines())}")
P("== R1-5. M-1 re-run: lock-check --pending-neo4j on the real fixtures ==")
check([k for k in keys if not k.startswith(("neo4j:", "pgdg:"))], "all but neo4j and pgdg (73 neo4j + 5 pgdg misses)")
check([k for k in keys if not k.startswith("neo4j:") and k != "temurin:jdk-21.0.12.1+1"], "all but neo4j and temurin")
check([k for k in keys if not k.startswith("pgdg:")], "all but pgdg")
