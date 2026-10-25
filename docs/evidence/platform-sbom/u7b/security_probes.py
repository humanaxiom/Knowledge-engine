"""security U7b gate probes (platform-sbom). python -I, gates image; fake network only."""
import hashlib, http.client, importlib.util, io, json, os, sys, tempfile, time, contextlib
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
R = load("srv", "/work/scripts/sources_resolve.py")
P = print
POLICY = json.load(open("/work/docker/source-policy.json"))
ALLOW = set(POLICY["hosts"]) | {R.PYPI_JSON_HOST}
calls = []
class Net:
    def __init__(self, routes): self.routes = routes
    def __call__(self, url, timeout):
        calls.append(url)
        r = self.routes.get(url)
        if r is None:
            return R.Response(404, {}, b"")
        if callable(r):
            return r()
        return R.Response(*r)
def try_fetch(label, start, routes):
    calls.clear(); R.OPENER = Net(routes)
    try:
        r = R.fetch(start, ALLOW); out = f"OK status={r.status}"
    except R.ResolveError as e:
        out = f"refused: {str(e)[:90]}"
    except Exception as e:
        out = f"RAISED {type(e).__name__}: {str(e)[:60]}"
    P(f"  {label:46s} requests={[c[:70] for c in calls]} -> {out}")

P("== U7b-1. fetch: first URL and redirect hops (fake network) ==")
G = "https://github.com/a"
try_fetch("first URL http", "http://github.com/a", {})
try_fetch("first URL not in hosts", "https://evil.example/a", {})
try_fetch("first URL port :8443", "https://github.com:8443/a", {"https://github.com:8443/a": (200, {}, b"x")})
try_fetch("first URL userinfo evil@github.com", "https://evil@github.com/a", {"https://evil@github.com/a": (200, {}, b"x")})
try_fetch("first URL github.com@evil", "https://github.com@evil.example/a", {})
try_fetch("first URL upper-case host", "https://GITHUB.com/a", {"https://GITHUB.com/a": (200, {}, b"x")})
try_fetch("first URL trailing dot", "https://github.com./a", {})
try_fetch("first URL IDN look-alike", "https://g\u0456thub.com/a", {})
try_fetch("first URL backslash userinfo", "https://evil.example\@github.com/a", {"https://evil.example\@github.com/a": (200, {}, b"x")})
for k, loc in {"relative /b": "/b", "relative b": "b", "scheme-relative //evil": "//evil.example/b", "http": "http://github.com/b",
               "userinfo evil@github": "https://evil@github.com/b", "github@evil": "https://github.com@evil.example/b",
               "port": "https://github.com:8443/b", "IDN": "https://g\u0456thub.com/b", "trailing dot": "https://github.com./b",
               "pypi.org (any route)": "https://pypi.org/x", "backslash https:\\evil": "https:\\evil.example/b",
               "tab in host": "https://evil\t.example/b", "tab making github": "https://git\thub.com/b",
               "CRLF in Location": "https://github.com/b\r\nX: y", "data: URL": "data:text/plain,x", "file:": "file:///etc/passwd",
               "javascript:": "javascript:alert(1)", "empty Location": ""}.items():
    try_fetch(f"302 -> {k}", G, {G: (302, {"Location": loc}, b""), "https://github.com/b": (200, {}, b"ok")})
try_fetch("308 -> relative", G, {G: (308, {"Location": "/b"}, b""), "https://github.com/b": (200, {}, b"ok")})
try_fetch("3xx without Location", G, {G: (302, {}, b"")})
try_fetch("304 Not Modified", G, {G: (304, {}, b"")})
loop = {G: (302, {"Location": "/a"}, b"")}
try_fetch("redirect loop to itself", G, loop)
chain = {f"https://github.com/{i}": (302, {"Location": f"/{i+1}"}, b"") for i in range(10)}
chain["https://github.com/5"] = (200, {}, b"ok")
try_fetch("5 redirects then 200", "https://github.com/0", chain)
chain["https://github.com/5"] = (302, {"Location": "/6"}, b""); chain["https://github.com/6"] = (200, {}, b"ok")
try_fetch("6 redirects", "https://github.com/0", chain)
try_fetch("200 with body on hop 1 (final)", G, {G: (200, {"Location": "https://evil.example/"}, b"body")})
try_fetch("100 Continue status", G, {G: (100, {}, b"")})

P("\n== U7b-2. Streaming ==")
data = os.urandom(300000)
def chunked(b, n=65536):
    for i in range(0, len(b), n):
        yield b[i:i + n]
R.OPENER = Net({G: (200, {"Content-Length": "10"}, chunked(data))})
d, size = R.stream(G, ALLOW)
P(f"  Content-Length lies (10): size={size} == {len(data)}: {size == len(data)}; sha256 exact: {d['sha256'] == hashlib.sha256(data).hexdigest()}")
gz = __import__("gzip").compress(b"A" * 1000000)
R.OPENER = Net({G: (200, {"Content-Encoding": "gzip"}, gz)})
d, size = R.stream(G, ALLOW)
P(f"  Content-Encoding gzip body: hashed raw bytes={size == len(gz)} (raw {len(gz)}, decoded would be 1000000)")
def endless():
    def gen():
        n = 0
        while n < 3 * 1024 ** 3 // 65536:  # 3 GiB of zeros, generated
            n += 1
            yield b"\0" * 65536
    return R.Response(200, {}, gen())
t0 = time.perf_counter()
R.OPENER = Net({G: endless})
try:
    d, size = R.stream(G, ALLOW); P(f"  3 GiB body: streamed with no cap: size={size} in {time.perf_counter() - t0:.1f}s (no size limit in stream())")
except Exception as e:
    P(f"  3 GiB body: {type(e).__name__}")
def bad_body(exc):
    def mk():
        def gen():
            yield b"x" * 10
            raise exc
        return R.Response(200, {}, gen())
    return mk
for label, exc in (("IncompleteRead mid-body", http.client.IncompleteRead(b"x", 5)), ("ssl/OSError mid-body", OSError("reset")),
                   ("TimeoutError mid-body", TimeoutError())):
    R.OPENER = Net({G: bad_body(exc)})
    try:
        R.stream(G, ALLOW); P(f"  {label:30s} no error")
    except R.ResolveError as e:
        P(f"  {label:30s} ResolveError (controlled): {e}")
    except BaseException as e:
        P(f"  {label:30s} escapes as {type(e).__name__} (not ResolveError)")
R.OPENER = Net({G: (200, {}, b"a" * (2 << 20))})
try:
    R.text(G, ALLOW)
except R.ResolveError as e:
    P(f"  text() 2 MiB: refused: {e}")

P("\n== U7b-3. main(): a body error mid-stream, and the TOFU/merge rules ==")
W = tempfile.mkdtemp()
def wj(n, o):
    p = os.path.join(W, n); open(p, "w").write(json.dumps(o)); return p
uvp = os.path.join(W, "uv.lock"); open(uvp, "w").write(open("/work/uv.lock").read())
polp = wj("pol.json", POLICY)
def run_main(needs, lock, routes):
    out = tempfile.mkdtemp(dir=W); R.OPENER = Net(routes)
    err, so = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(so):
            rc = R.main(["--needs", wj("needs.json", {"needs": needs}), "--lock", wj("lock.json", lock), "--policy", polp,
                         "--uv-lock", uvp, "--out", out, "--arch", "amd64"])
    except BaseException as e:
        rc = f"RAISED {type(e).__name__}"
    written = os.path.exists(os.path.join(out, "lock.new.json"))
    new = json.load(open(os.path.join(out, "lock.new.json"))) if written else None
    return rc, written, new, so.getvalue(), err.getvalue(), sorted(os.listdir(out))
mv_key = "maven:javax.xml.bind:jaxb-api@2.2.12"
mvu = "https://repo1.maven.org/maven2/javax/xml/bind/jaxb-api/2.2.12/jaxb-api-2.2.12-sources.jar"
jar = b"PK" + os.urandom(1000)
need_mv = {mv_key: {"kind": "maven", "packages": [], "route": {}}}
rc, wr, new, so, er, ls = run_main(need_mv, {"format": 1, "components": {}},
                                   {mvu + ".sha1": (200, {}, hashlib.sha1(jar).hexdigest().encode()), mvu: bad_body(http.client.IncompleteRead(b"", 1))})
P(f"  maven jar body fails mid-stream: rc={rc} lock.new.json written={wr} out={ls} stderr={er[:100]!r}")
rc, wr, new, so, er, ls = run_main(need_mv, {"format": 1, "components": {}},
                                   {mvu + ".sha1": (200, {}, hashlib.sha1(jar).hexdigest().encode()), mvu: (200, {}, jar)})
P(f"  maven good: rc={rc} written={wr} out={ls} entry={(new or {}).get('components', {}).get(mv_key, {}).get('files', [{}])[0].get('url', '')[:60]}")
nk = "neo4j:neo4j@5.26.32"; nu = "https://github.com/neo4j/neo4j/archive/refs/tags/5.26.32.tar.gz"
cl = "https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32"
tarball = os.urandom(5000)
need_nj = {nk: {"kind": "neo4j", "packages": [], "route": {"ver": "5.26.32"}}}
rc, wr, new, so, er, ls = run_main(need_nj, {"format": 1, "components": {}}, {nu: (302, {"Location": cl}, b""), cl: (200, {}, tarball)})
P(f"  neo4j TOFU (no entry): rc={rc} written={wr} neo4j in new lock={nk in (new or {}).get('components', {})} stdout={so.strip()[:140]}")
manual = {"kind": "neo4j", "origin": "manual", "arches": ["amd64"], "files": [{"name": "x"}]}
calls.clear()
rc, wr, new, so, er, ls = run_main(need_nj, {"format": 1, "components": {nk: manual}}, {nu: (302, {"Location": cl}, b""), cl: (200, {}, tarball)})
P(f"  neo4j manual entry present: rc={rc} requests={len(calls)} manual kept identical={new['components'].get(nk) == manual}")
gen_over_manual = {"kind": "maven", "origin": "manual", "arches": ["amd64"], "files": [{"name": "keep"}]}
rc, wr, new, so, er, ls = run_main(need_mv, {"format": 1, "components": {mv_key: gen_over_manual}},
                                   {mvu + ".sha1": (200, {}, hashlib.sha1(jar).hexdigest().encode()), mvu: (200, {}, jar)})
P(f"  maven key with a manual entry + --no-refresh: kept={new['components'].get(mv_key) == gen_over_manual}")
rc2 = R.main(["--needs", wj("n2.json", {"needs": need_mv}), "--lock", wj("l2.json", {"format": 1, "components": {mv_key: gen_over_manual}}), "--policy", polp,
              "--uv-lock", uvp, "--out", tempfile.mkdtemp(dir=W), "--arch", "amd64", "--refresh"])
P(f"  same with --refresh: rc={rc2} (manual skipped before refresh is read: line 333)")
stale_manual = {"other:manual@1": {"kind": "neo4j", "origin": "manual", "arches": ["amd64"], "files": []}}
rc, wr, new, so, er, ls = run_main({}, {"format": 1, "components": stale_manual}, {})
P(f"  a manual entry no image needs: kept={'other:manual@1' in new['components']} (lock-check then flags it)")
P(f"  candidate line escapes control chars: {json.dumps({'k': chr(27)})}")

P("\n== U7b-4. sources_lock.sh step 5 pending rule against a truncated lock-check output ==")
sys.path.insert(0, "/work")
import subprocess
import tests.test_sources_lock as tl
fd = tl.fixture_docs()
keys = sorted(tl.FIXTURE_KEYS)
keep = [k for k in keys if not k.startswith(("neo4j:", "pgdg:"))]
lock = tl.good_lock(keep)
lp = os.path.join(W, "lock.new.json"); open(lp, "w", newline="").write(tl.canon(lock))
args = []
for img, d in fd.items():
    args += ["--sbom", f"{img}={wj(img + '.spdx.json', d)}"]
r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "lock-check", "--lock", lp, "--policy", polp, "--arch", "amd64", *args],
                   capture_output=True, text=True)
errp = os.path.join(W, "check.err"); open(errp, "w").write(r.stderr)
lines = r.stderr.strip().splitlines()
P(f"  lock-check rc={r.returncode}; lines printed={len(lines)}; neo4j-miss lines={sum('the lock has no neo4j:neo4j@' in l for l in lines)}; "
  f"pgdg-miss lines printed={sum('the lock has no pgdg:' in l for l in lines)}")
allp = tl.fn("lock_problems")(tl.canon(lock), POLICY, fd, "amd64")
P(f"  full problem list: {len(allp)} problems; pgdg misses={sum('the lock has no pgdg:' in x for x in allp)}; neo4j misses={sum('the lock has no neo4j:' in x for x in allp)}")
sh = ("check_rc=%d; pending=0; if [ \"$check_rc\" -eq 1 ] && [ -s %s ] && ! grep -v -- 'needs source; the lock has no neo4j:neo4j@' %s | grep -q .; "
      "then pending=1; fi; echo pending=$pending") % (r.returncode, errp, errp)
P("  script rule (lines 141-143) on that output:", subprocess.run(["bash", "-c", sh], capture_output=True, text=True).stdout.strip())
P("  mktemp default mode (as in line 149):", subprocess.run(["bash", "-c", "cd /tmp && f=$(mktemp ./.x.XXXXXXXX) && stat -c %a \"$f\" && rm -f \"$f\""], capture_output=True, text=True).stdout.strip())
