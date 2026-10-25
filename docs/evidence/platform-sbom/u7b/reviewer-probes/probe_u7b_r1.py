import sys, io, contextlib, tempfile, os, json, http.client, subprocess
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_resolve as t
import tests.test_sources_lock as tl
mod = t.load_resolver()
POL = t.policy()
def run_main(routes, needs):
    d = tempfile.mkdtemp()
    for n, v in (("needs.json", {"format": 1, "needs": needs}), ("lock.json", t.EMPTY_LOCK), ("policy.json", POL)):
        open(os.path.join(d, n), "w").write(json.dumps(v))
    open(os.path.join(d, "uv.lock"), "w").write('version = 1\n')
    out = os.path.join(d, "out"); os.mkdir(out)
    err, so = io.StringIO(), io.StringIO()
    with t.network(mod, routes), contextlib.redirect_stderr(err), contextlib.redirect_stdout(so):
        try:
            rc = mod.main(["--needs", os.path.join(d, "needs.json"), "--lock", os.path.join(d, "lock.json"),
                           "--policy", os.path.join(d, "policy.json"), "--uv-lock", os.path.join(d, "uv.lock"),
                           "--out", out, "--arch", "amd64"])
        except BaseException as e:
            rc = f"RAISED {type(e).__name__}: {e}"
    return rc, ascii(err.getvalue().strip())[:160], os.listdir(out)
def body_raising(exc):
    def gen():
        yield b"first chunk"
        raise exc
    return gen()
class Net(t.FakeNet):
    def __init__(self, routes, special): super().__init__(routes); self.special = special
    def __call__(self, url, timeout):
        if url in self.special:
            return self.special[url]()
        return super().__call__(url, timeout)
def run_special(special, needs, extra_routes=None):
    routes = dict(extra_routes or {})
    net = Net(routes, special)
    with mock.patch.object(mod, "OPENER", net):
        d = tempfile.mkdtemp()
        for n, v in (("needs.json", {"format": 1, "needs": needs}), ("lock.json", t.EMPTY_LOCK), ("policy.json", POL)):
            open(os.path.join(d, n), "w").write(json.dumps(v))
        open(os.path.join(d, "uv.lock"), "w").write('version = 1\n')
        out = os.path.join(d, "out"); os.mkdir(out)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            try:
                rc = mod.main(["--needs", os.path.join(d, "needs.json"), "--lock", os.path.join(d, "lock.json"),
                               "--policy", os.path.join(d, "policy.json"), "--uv-lock", os.path.join(d, "uv.lock"),
                               "--out", out, "--arch", "amd64"])
            except BaseException as e:
                rc = f"RAISED {type(e).__name__}: {str(e)[:80]}"
        return rc, ascii(err.getvalue().strip())[:160], os.listdir(out)
mav = {t.JAXB_KEY: t.need(t.JAXB_KEY, "ke-neo4j", "pkg:maven/javax.xml.bind/jaxb-api@2.2.12")}
sidecar = {t.JAXB_URL + ".sha1": t.ok(t.sha("sha1", t.JAR_BODY))}
print("## baseline maven route:", run_main(t.maven_routes(), mav))
print("## timeout raised by OPENER (tested case):", run_main({**sidecar, t.JAXB_URL: "timeout"}, mav))
for label, exc in (("TimeoutError mid-body", TimeoutError("The read operation timed out")),
                   ("http.client.IncompleteRead mid-body", http.client.IncompleteRead(b"x", 100)),
                   ("ConnectionResetError mid-body", ConnectionResetError("reset"))):
    print(f"## {label}:", run_special({t.JAXB_URL: lambda e=exc: SimpleNamespace(status=200, headers={}, body=body_raising(e))}, mav, sidecar))
print("## OPENER raises http.client.InvalidURL (ValueError):", run_special({t.JAXB_URL: lambda: (_ for _ in ()).throw(http.client.InvalidURL("bad"))}, mav, sidecar))
print("## OPENER raises http.client.BadStatusLine:", run_special({t.JAXB_URL: lambda: (_ for _ in ()).throw(http.client.BadStatusLine("x"))}, mav, sidecar))
print("## hop: redirect to an allowed host on port 8443 / with userinfo")
for loc in ("https://repo1.maven.org:8443/x.jar", "https://user:pw@repo1.maven.org/x.jar", "https://repo1.maven.org\t.evil.example/x.jar"):
    with t.network(mod, {"https://repo1.maven.org/a": t.moved(loc), loc: t.ok(b"x")}) as net:
        try:
            r = mod.fetch("https://repo1.maven.org/a", {"repo1.maven.org"})
            print("  ", ascii(loc), "-> FOLLOWED, calls:", [ascii(c) for c in net.calls])
        except Exception as e:
            print("  ", ascii(loc), "->", type(e).__name__, ascii(str(e))[:100])
print("## lock-check truncation: missing neo4j + missing pypi:pandas (and pgdg) - what sources_lock.sh sees")
check = tl.load_sbom_check()
keys = set(tl.FIXTURE_KEYS) - {"neo4j:neo4j@5.26.32", "pypi:pandas@2.3.3"} - {k for k in tl.FIXTURE_KEYS if k.startswith("pgdg:")}
probs = check.lock_problems(tl.canon(tl.good_lock(keys)), tl.policy(), tl.fixture_docs(), "amd64")
first20 = probs[:20]
others = [p for p in probs if "the lock has no neo4j:neo4j@" not in p]
print("   problems:", len(probs), "| non-neo4j problems:", len(others), "e.g.", ascii(others[:2])[:200])
print("   first 20 printed by lock-check are all neo4j misses:", all("the lock has no neo4j:neo4j@" in p for p in first20))

print("## r1: pypi JSON sdist url with an encoded traversal (server-supplied, treated as a first request)")
pk = "pypi:pandas@2.3.3"
bad_sd = "https://files.pythonhosted.org/packages/33/01/%2e%2e/%2e%2e/" + "d" * 60 + "/pandas-2.3.3.tar.gz"
js = json.dumps({"urls": [{"packagetype": "sdist", "url": bad_sd, "digests": {"sha256": t.sha("sha256", t.PANDAS_BODY)}}]})
needs = {pk: t.need(pk, "phoenix", "pkg:pypi/pandas@2.3.3")}
with t.network(mod, {"https://pypi.org/pypi/pandas/2.3.3/json": t.ok(js), bad_sd: t.ok(t.PANDAS_BODY)}) as net:
    try:
        new, c, sk = mod.resolve(needs, t.EMPTY_LOCK, POL, "version = 1" + chr(10), "amd64")
        print("   requested:", [ascii(x) for x in net.calls])
        lp = check.lock_problems(check.lock_text(new), tl.policy(), {"phoenix": tl.ss.spdx_doc("phoenix", [{"purl": "pkg:pypi/pandas@2.3.3", "declared": "LicenseRef-" + "ab"*32}])}, "amd64")
        print("   resolver wrote the entry; U7a lock_problems:", ascii(lp[:1])[:160])
    except Exception as e:
        print("   ", type(e).__name__, ascii(str(e))[:160], "requested:", [ascii(x) for x in net.calls])
print("## r1: --pending-neo4j decision on the reviewer B2 input")
print("   only_neo4j_misses:", check.only_neo4j_misses(probs, tl.canon(tl.good_lock(keys)), tl.policy(), tl.fixture_docs(), "amd64"))
keys2 = set(tl.FIXTURE_KEYS) - {"neo4j:neo4j@5.26.32"}
probs2 = check.lock_problems(tl.canon(tl.good_lock(keys2)), tl.policy(), tl.fixture_docs(), "amd64")
print("   neo4j only (pgdg entries present, so pgdg host problems):", len(probs2), check.only_neo4j_misses(probs2, tl.canon(tl.good_lock(keys2)), tl.policy(), tl.fixture_docs(), "amd64"))
