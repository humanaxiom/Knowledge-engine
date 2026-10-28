"""security U7d code-audit probes (platform-sbom). python -I, gates image; fake network only."""
import copy, datetime, hashlib, importlib.util, json, sys, time
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
R = load("srv7d", "/work/scripts/sources_resolve.py")
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
from tests.test_sbom_bundle import load_sbom_check
sc = load_sbom_check()
P = print
NL = chr(10)
def show(label, fn):
    try:
        P(f"  {label:60s} -> {str(fn())[:110]}")
    except R.ResolveError as e:
        P(f"  {label:60s} -> ResolveError: {str(e)[:100]}")
    except Exception as e:
        P(f"  {label:60s} -> RAISED {type(e).__name__}: {str(e)[:80]}")
S1 = "a" * 64
def rel(sha_lines, extra="", sig=True, before="", after=""):
    body = "Origin: apt-archive.postgresql.org" + NL + "Suite: bookworm-pgdg-archive" + NL + "SHA256:" + NL + NL.join(sha_lines) + extra
    if not sig:
        return before + body
    return (before + "-----BEGIN PGP SIGNED MESSAGE-----" + NL + "Hash: SHA512" + NL + NL + body + NL +
            "-----BEGIN PGP SIGNATURE-----" + NL + "x" + NL + "-----END PGP SIGNATURE-----" + NL + after)
good = [f" {S1} 5043212 main/source/Sources", f" {'b' * 64} 734866 main/source/Sources.bz2"]
P("== U7d-1. InRelease stripping (_release_sources_sha256) ==")
show("baseline", lambda: R._release_sources_sha256(rel(good)))
show("a second signed block after the first", lambda: R._release_sources_sha256(rel(good, after=rel([f" {'c' * 64} 1 main/source/Sources"]))))
show("trailer text after END SIGNATURE with a SHA256 line", lambda: R._release_sources_sha256(rel(good, after="SHA256:" + NL + f" {'c' * 64} 1 main/source/Sources" + NL)))
show("unsigned prefix before BEGIN SIGNED MESSAGE", lambda: R._release_sources_sha256(rel(good, before="SHA256:" + NL + f" {'c' * 64} 1 main/source/Sources" + NL + NL)))
show("prefix line then the signed block", lambda: R._release_sources_sha256(rel(good, before="junk" + NL)))
show("dash-escaped SHA256 field ('- SHA256:')", lambda: R._release_sources_sha256(rel(good).replace(NL + "SHA256:", NL + "- SHA256:")))
show("dash-escaped continuation line", lambda: R._release_sources_sha256(rel(good).replace(NL + " " + S1, NL + "- " + " " + S1)))
show("CRLF throughout", lambda: R._release_sources_sha256(rel(good).replace(NL, chr(13) + NL)))
show("Sources listed twice in SHA256", lambda: R._release_sources_sha256(rel(good + [f" {'c' * 64} 1 main/source/Sources"])))
show("Sources line injected as continuation of another field", lambda: R._release_sources_sha256(rel(good, extra=NL + "Description: x" + NL + f" {'c' * 64} 1 main/source/Sources")))
show("a second SHA256 field (duplicate)", lambda: R._release_sources_sha256(rel(good, extra=NL + "SHA256:" + NL + f" {'c' * 64} 1 main/source/Sources")))
show("sha256 field 'sha256' lower-case duplicate", lambda: R._release_sources_sha256(rel(good, extra=NL + "sha256:" + NL + f" {'c' * 64} 1 main/source/Sources")))
show("Sources entry with upper-hex", lambda: R._release_sources_sha256(rel([f" {S1.upper()} 5043212 main/source/Sources"])))
show("a path variant ./main/source/Sources only", lambda: R._release_sources_sha256(rel([f" {S1} 5043212 ./main/source/Sources"])))
show("armour header with U+2028", lambda: R._release_sources_sha256(rel(good).replace("Hash: SHA512", "Hash: SHA" + chr(0x2028) + "512")))
show("NUL inside the signed body", lambda: R._release_sources_sha256(rel(good, extra=NL + "X: a" + chr(0) + "b")))

P("\n== U7d-2. Sources binding (pgdg_index, fake network) ==")
calls = []
class Net:
    def __init__(self, routes): self.routes = routes
    def __call__(self, url, timeout):
        calls.append(url); r = self.routes.get(url)
        if r is None:
            return R.Response(404, {}, b"")
        return r() if callable(r) else R.Response(*r)
ALLOW = set(json.load(open("/work/docker/source-policy.json"))["hosts"])
BASE_D = "https://apt-archive.postgresql.org/pub/repos/apt/dists/bookworm-pgdg-archive"
def stanza(pkg, ver, extra=""):
    return f"Package: {pkg}" + NL + f"Version: {ver}" + NL + f"Directory: pool/main/p/{pkg}" + NL + f"Checksums-Sha256: {'d' * 64} 10 {pkg}_{ver}.dsc" + extra
src_ok = (stanza("postgresql-common", "293.pgdg12+1") + NL + NL + stanza("other", "1") + NL).encode()
def routes_for(body, declared=None, size=None):
    sha = declared or hashlib.sha256(body).hexdigest()
    inrel = rel([f" {sha} {size if size is not None else len(body)} main/source/Sources"]).encode()
    pulled = {"n": 0}
    def src():
        def g():
            for i in range(0, len(body), 7):
                pulled["n"] += 7; yield body[i:i + 7]
        return R.Response(200, {}, g())
    return {BASE_D + "/InRelease": (200, {}, inrel), BASE_D + "/main/source/Sources": src}, pulled
def idx(body, **kw):
    rt, pulled = routes_for(body, **kw); R.OPENER = Net(rt)
    try:
        out = R.pgdg_index("bookworm-pgdg-archive", ALLOW, {"postgresql-common"})
        return f"kept={sorted(out)} pulled={pulled['n']}"
    except R.ResolveError as e:
        return f"ResolveError: {str(e)[:80]} (pulled {pulled['n']} of {len(body)})"
show("baseline", lambda: idx(src_ok))
big = src_ok + (stanza("x", "1") + NL + NL).encode() * 2000
show("body longer than Release size: read stops at size+1 chunk", lambda: idx(big, size=len(src_ok)))
show("hash mismatch with the needed stanza inside: nothing kept", lambda: idx(src_ok, declared="0" * 64))
show("body shorter than Release size", lambda: idx(src_ok, size=len(src_ok) + 5))
show("CRLF stanza boundaries", lambda: idx(src_ok.replace(b"\n", b"\r\n")))
show("needed stanza twice (same Package/Version)", lambda: idx(src_ok + (NL + stanza("postgresql-common", "293.pgdg12+1") + NL).encode()))
show("duplicate field inside one stanza", lambda: idx((stanza("postgresql-common", "293.pgdg12+1") + NL + "Version: 9" + NL).encode()))
show("whitespace-only line splits a stanza (deb822 rule)", lambda: idx((stanza("postgresql-common", "293.pgdg12+1").replace("Directory", " " + NL + "Directory") + NL).encode()))
show("U+2028 inside an unrelated stanza", lambda: idx(src_ok + ("Package: z" + NL + "Description: a" + chr(0x2028) + NL).encode()))
show("non-UTF-8 byte in an unrelated stanza", lambda: idx(src_ok + b"Package: z\nDescription: \xff\n"))
t0 = time.perf_counter(); nolines = b"a" * (60 << 20)
rt, _ = routes_for(nolines); R.OPENER = Net(rt)
def big_chunks():
    def g():
        for i in range(0, len(nolines), 1 << 16):
            yield nolines[i:i + (1 << 16)]
    return R.Response(200, {}, g())
rt[BASE_D + "/main/source/Sources"] = big_chunks; R.OPENER = Net(rt)
try:
    R.pgdg_index("bookworm-pgdg-archive", ALLOW, {"x"})
except R.ResolveError as e:
    pass
P(f"  60 MiB with no blank line (buffer rescanned per chunk): {time.perf_counter() - t0:.1f}s")

P("\n== U7d-3. Retry loop (patched SLEEP; run state active) ==")
sleeps = []
R.SLEEP = lambda s: sleeps.append(s)
def run(label, routes, fn, budget=20, deadline=10800, start_offset=0.0, before=None):
    sleeps.clear(); calls.clear(); R.OPENER = Net(routes)
    R.RUN_RETRIES = budget; R.RUN_DEADLINE = deadline
    R._RUN.update(retries=0, start=time.monotonic() - start_offset, active=1); R._ACTIVE_RETRIES[0] = 3
    try:
        out = fn()
    except R.ResolveError as e:
        out = f"ResolveError: {str(e)[:85]}"
    finally:
        R._RUN["active"] = 0; R._ACTIVE_RETRIES[0] = 0
    P(f"  {label:48s} requests={len(calls)} sleeps={sleeps} -> {str(out)[:95]}")
G = "https://github.com/a"
seq = lambda *items: (lambda it=iter(items): (lambda: R.Response(*next(it))))()
run("503 x3 then 200", {G: seq((503, {}, b""), (503, {}, b""), (503, {}, b""), (200, {}, b"ok"))}, lambda: R.stream(G, ALLOW)[1])
run("503 x4 (budget per request exhausted)", {G: seq(*[(503, {}, b"")] * 4)}, lambda: R.stream(G, ALLOW)[1])
run("404 (never retried)", {G: (404, {}, b"")}, lambda: R.stream(G, ALLOW)[1])
run("418 (never retried)", {G: (418, {}, b"")}, lambda: R.stream(G, ALLOW)[1])
run("429 (never retried)", {G: (429, {"Retry-After": "1"}, b"")}, lambda: R.stream(G, ALLOW)[1])
def reset():
    raise ConnectionResetError("reset")
def tmo():
    raise TimeoutError()
run("ConnectionResetError (never retried)", {G: reset}, lambda: R.stream(G, ALLOW)[1])
import ssl
def sslerr():
    raise ssl.SSLError("cert")
run("ssl.SSLError (never retried)", {G: sslerr}, lambda: R.stream(G, ALLOW)[1])
run("TimeoutError x1 then 200", {G: seq((200, {}, b"")) and (lambda it=iter([tmo, lambda: R.Response(200, {}, b"ok")]): (lambda: next(it)()))()}, lambda: R.stream(G, ALLOW)[1])
def midbody_then_ok():
    state = {"n": 0}
    def mk():
        state["n"] += 1
        if state["n"] == 1:
            def g():
                yield b"PARTIAL"
                raise TimeoutError()
            return R.Response(200, {}, g())
        return R.Response(200, {}, b"full body")
    return mk
run("mid-body timeout then 200 (fresh hashers)", {G: midbody_then_ok()}, lambda: R.stream(G, ALLOW)[0]["sha256"] == hashlib.sha256(b"full body").hexdigest())
run("5xx on hop 2 restarts from hop 1", {G: (302, {"Location": "/b"}, b""), "https://github.com/b": seq((502, {}, b""), (200, {}, b"ok"))}, lambda: R.stream(G, ALLOW)[1])
run("run budget 2: third retry refused, no sleep", {G: seq(*[(503, {}, b"")] * 4)}, lambda: R.stream(G, ALLOW)[1], budget=2)
run("run deadline: a wait past it fails before sleeping", {G: (503, {}, b"")}, lambda: R.stream(G, ALLOW)[1], deadline=100, start_offset=95)
run("run deadline already passed: no request", {G: (200, {}, b"ok")}, lambda: R.stream(G, ALLOW)[1], deadline=100, start_offset=101)
run("retries=0 default for fetch()", {G: (503, {}, b"")}, lambda: R.fetch(G, ALLOW).status)
pauses = []
R.SNAPSHOT_PAUSE = 0
orig_wait = R._snapshot_wait
R._snapshot_wait = lambda: pauses.append(1)
SN = "https://snapshot.debian.org/mr/package/bash/5.2.15-2/srcfiles?fileinfo=1"
run("snapshot 503 x3 then 200: pause per attempt", {SN: seq(*[(503, {}, b"")] * 3, (200, {}, b"{}"))}, lambda: (R.resolve_deb("deb:bash@5.2.15-2", "amd64", ALLOW), None))
P(f"  snapshot pauses before attempts: {len(pauses)}")
R._snapshot_wait = orig_wait
run("final error after retries keeps the full URL", {G + "?sig=SECRET": seq(*[(503, {}, b"")] * 4)}, lambda: R.stream(G + "?sig=SECRET", ALLOW)[1])
import io, contextlib
err = io.StringIO()
with contextlib.redirect_stderr(err):
    run("retry line text", {G + "?sig=SECRET": seq((503, {}, b""), (200, {}, b"ok"))}, lambda: R.stream(G + "?sig=SECRET", ALLOW)[1])
P("  retry line:", err.getvalue().strip())

P("\n== U7d-4. pgdg lock rules (fixture lock, 182 keys) ==")
FD = tl.fixture_docs(); POL = tl.policy(); LOCK = tl.good_lock(tl.FIXTURE_KEYS)
def probs(lock):
    return sc.lock_problems(tl.canon(lock), POL, FD, "amd64", today=datetime.date(2026, 10, 25))
base_p = probs(LOCK); P("  baseline problems:", base_p[:3])
PK = "pgdg:postgresql-common@293.pgdg12+1"; E = LOCK["components"][PK]
P("  baseline pgdg urls:", [f["url"] for f in E["files"]], "suite", E.get("suite"))
def rep(label, fn):
    d = copy.deepcopy(LOCK); fn(d["components"][PK])
    pr = [x for x in probs(d) if x not in base_p]
    P(f"  {label:56s} accepted={not pr!s:5} {[x[:110] for x in pr[:1]]}")
u0 = E["files"][0]["url"]
rep("pool letter q instead of p", lambda e: e["files"][0].update(url=u0.replace("/main/p/", "/main/q/")))
rep("pool letter post (lib-style for a non-lib src)", lambda e: e["files"][0].update(url=u0.replace("/main/p/", "/main/post/")))
rep("dists path instead of pool", lambda e: e["files"][0].update(url=u0.replace("/pool/main/p/postgresql-common/", "/dists/bookworm-pgdg-archive/")))
rep("+ encoded as %2B", lambda e: e["files"][0].update(url=u0.replace("+", "%2B")))
rep("another src directory", lambda e: e["files"][0].update(url=u0.replace("/postgresql-common/", "/postgresql-16/")))
rep("apt.postgresql.org host", lambda e: e["files"][0].update(url=u0.replace("apt-archive.", "apt.")))
rep("snapshot.debian.org host", lambda e: e["files"][0].update(url="https://snapshot.debian.org/file/" + "a" * 40))
rep("query on the url", lambda e: e["files"][0].update(url=u0 + "?x=1"))
rep("suite bookworm-pgdg (non-archive)", lambda e: e.update(suite="bookworm-pgdg"))
rep("suite with a slash", lambda e: e.update(suite="bookworm-pgdg-archive/../x"))
rep("suite upper case", lambda e: e.update(suite="Bookworm-pgdg-archive"))
rep("suite trixie-pgdg-archive (packages are bookworm)", lambda e: (e.update(suite="trixie-pgdg-archive"), e["files"][0]["upstream"].update({"from": "apt-archive.postgresql.org trixie-pgdg-archive Sources"})))
rep("from naming another suite than the entry", lambda e: e["files"][0]["upstream"].update({"from": "apt-archive.postgresql.org trixie-pgdg-archive Sources"}))
rep("suite missing", lambda e: e.pop("suite"))
rep("a sixth key", lambda e: e.update(x=1))
rep("sha1 upstream on the .dsc", lambda e: e["files"][0]["upstream"].update({"alg": "sha1", "value": "a" * 40}))
rep(".dsc only", lambda e: e.update(files=e["files"][:1]))
P("  libp pool rule (sbom_check binding) for a lib src:", sc.KIND_HOSTS["pgdg"], R.pgdg_pool("libpq"), R.pgdg_pool("lib"), R.pgdg_pool("postgresql-16"))
