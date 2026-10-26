import sys, copy, io, contextlib, time, tempfile, os, json
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_lock as t
m = t.load_sbom_check()
P = t.policy(); D = t.small_docs()
B = chr(92)
def run(name, lock=None, raw=None):
    t0 = time.perf_counter()
    p = m.lock_problems(raw if raw is not None else t.canon(lock), P, D, "amd64")
    dt = time.perf_counter() - t0
    print(f"{name}: {'PASSES' if p == [] else 'refused: ' + ascii(p[0])[:140]} ({dt:.3f} s)")
def mut(key, ch):
    d = t.good_lock(t.SMALL_KEYS); ch(d["components"][key]); return d
f0 = lambda e: e["files"][0]
keys = sorted(t.SMALL_KEYS)
TEM = "temurin:jdk-21.0.12.1+1"; PYP = "pypi:psycopg-c@3.3.6"; MAV = "maven:javax.xml.bind:jaxb-api@2.2.12"; APK = "apk:readline@8.2.13-r1"; NEO = "neo4j:neo4j@5.26.32"; DEB = "deb:bash@5.2.15-2"
print("## baseline"); run("good small lock", t.good_lock(t.SMALL_KEYS))
print("  temurin url:", t.good_lock(t.SMALL_KEYS)["components"][TEM]["files"][0]["url"].split("github.com")[1])
print("  pypi url:", t.good_lock(t.SMALL_KEYS)["components"][PYP]["files"][0]["url"].split(".org")[1])
pre = lambda e: f0(e)["url"].rsplit("/", 2)[0]
print("## R1-B1 inputs (temurin, pypi)")
for label, mid in (("%2e%2e x4", "/%2e%2e/%2e%2e/%2e%2e/%2e%2e/attacker/repo/releases/download/x"), ("%2E%2E x4", "/%2E%2E/%2E%2E/%2E%2E/%2E%2E/attacker/repo/releases/download/x"),
                   ("..%2F", "/..%2F..%2F..%2F..%2Fattacker"), ("backslash", "/x" + B + ".." + B + ".." + B + "attacker" + B + "repo"), ("./", "/."), ("extra subdir", "/any/deeper")):
    run("temurin " + label, mut(TEM, lambda e: f0(e).update(url=pre(e) + mid + "/" + f0(e)["name"])))
run("pypi /%2e%2e/<name>", mut(PYP, lambda e: f0(e).update(url="https://files.pythonhosted.org/%2e%2e/" + f0(e)["name"])))
print("## R1-N1 temurin binding")
run("tag jdk-17.0.1%2B1", mut(TEM, lambda e: f0(e).update(url=f0(e)["url"].replace("jdk-21.0.12.1%2B1", "jdk-17.0.1%2B1"))))
run("tag with + unencoded", mut(TEM, lambda e: f0(e).update(url=f0(e)["url"].replace("%2B", "+"))))
run("tag with %2b lower", mut(TEM, lambda e: f0(e).update(url=f0(e)["url"].replace("%2B", "%2b"))))
run("JRE asset name", mut(TEM, lambda e: (f0(e).update(name=f0(e)["name"].replace("jdk-sources", "jre"), url=f0(e)["url"].replace("jdk-sources", "jre")), f0(e)["upstream"].update({"from": f0(e)["name"] + ".sha256.txt"}))))
print("## further shapes")
run("pypi path upper hex", mut(PYP, lambda e: f0(e).update(url=f0(e)["url"].replace("/packages/", "/packages/").upper().replace("HTTPS://FILES.PYTHONHOSTED.ORG", "https://files.pythonhosted.org").replace(f0(e)["name"].upper(), f0(e)["name"]))))
run("pypi path ;params in name", mut(PYP, lambda e: f0(e).update(name=f0(e)["name"] + ";x", url=f0(e)["url"] + ";x")))
run("maven ..; segment", mut(MAV, lambda e: f0(e).update(url=f0(e)["url"].replace("/maven2/", "/maven2/..;/maven2/"))))
run("apk gitlab path with %2F", mut(APK, lambda e: f0(e).update(url=f0(e)["url"].replace("/main/", "%2Fmain/"))))
run("deb /file/<sha1>/ trailing slash", mut(DEB, lambda e: f0(e).update(url=f0(e)["url"] + "/")))
run("neo4j trailing //", mut(NEO, lambda e: f0(e).update(url=f0(e)["url"].replace("/tags/", "/tags//"))))
run("host with trailing dot", mut(MAV, lambda e: f0(e).update(url=f0(e)["url"].replace("repo1.maven.org", "repo1.maven.org."))))
run("empty path host only", mut(PYP, lambda e: f0(e).update(url="https://files.pythonhosted.org")))
print("## security R1-L1 timing")
adv = "a-" * 123 + "-1.tar.gz"
run(f"adversarial {len(adv)}-char pypi name", mut(PYP, lambda e: f0(e).update(name=adv, url=f0(e)["url"].rsplit("/",1)[0] + "/" + adv)))
big = "a-" * 25000 + "1.tar.gz"
run(f"{len(big)}-char name", mut(PYP, lambda e: f0(e).update(name=big, url=f0(e)["url"].rsplit("/",1)[0] + "/" + big)))
print("## CLI FAIL lines")
d = tempfile.mkdtemp()
sp = os.path.join(d, "x.json"); open(sp, "w").write(json.dumps(D["postgres"]))
pp = os.path.join(d, "policy.json"); open(pp, "w").write(json.dumps(P))
def cli(lock_text, policy_path=pp, missing=False):
    lp = os.path.join(d, "lock.json")
    if not missing: open(lp, "w", newline="").write(lock_text)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = m.main(["lock-check", "--lock", lp if not missing else os.path.join(d, "nope.json"), "--policy", policy_path, "--arch", "amd64", "--sbom", "postgres=" + sp])
    return rc, ascii(err.getvalue().strip().replace(d, "<tmp>"))[:150]
print("  missing file:", cli("", missing=True))
print("  invalid JSON:", cli("{"))
print("  100000-deep:", cli("[" * 100000 + "]" * 100000))
bad = os.path.join(d, "bad.json"); open(bad, "w").write('{"hosts": 5, "always": [], "exempt": []}')
print("  exception inside the check:", cli(t.canon(t.good_lock(t.SMALL_KEYS)), bad))
print("## 182 keys")
needs, probs = m.lock_needs(t.policy(), t.fixture_docs())
print("  keys", len(needs), "== FIXTURE_KEYS:", set(needs) == set(t.FIXTURE_KEYS), "problems", probs)
