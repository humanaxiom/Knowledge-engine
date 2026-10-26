import sys, json, copy, re
sys.path.insert(0, r"c:\repos\Knowledge-engine")
from urllib.parse import unquote
import tests.test_sources_lock as t
m = t.load_sbom_check()
P = t.policy_with_pgdg(); D = t.small_docs()
def run(name, lock, raw=None):
    try:
        p = m.lock_problems(raw if raw is not None else t.canon(lock), P, D, "amd64")
        print(f"{name}: {'PASSES' if p == [] else p[:2]}")
    except Exception as e:
        print(f"{name}: RAISES {type(e).__name__}: {e}")
def mut(key, ch):
    d = t.good_lock(t.SMALL_KEYS); ch(d["components"][key]); return d
NEO, DEB, MAV, PYP, TEM, APK = "neo4j:neo4j@5.26.32", "deb:bash@5.2.15-2", "maven:javax.xml.bind:jaxb-api@2.2.12", "pypi:psycopg@3.3.6", "temurin:jdk-21.0.12.1+1", "apk:readline@8.2.13-r1"
print("## baseline"); run("good small lock", t.good_lock(t.SMALL_KEYS))
print("## candidate fail-opens")
run("neo4j upstream alg sha1, unrelated value, second-fetch from", mut(NEO, lambda e: e["files"][0]["upstream"].update(alg="sha1", value="0"*40)))
run("neo4j upstream alg sha512, unrelated value", mut(NEO, lambda e: e["files"][0]["upstream"].update(alg="sha512", value="0"*128)))
run("neo4j two files", mut(NEO, lambda e: e["files"].append(dict(copy.deepcopy(e["files"][0]), name="extra.tar.gz"))))
run("neo4j url on github.com/attacker/x, any name", mut(NEO, lambda e: e["files"][0].update(name="x.tar.gz", url="https://github.com/attacker/x/archive/refs/tags/5.26.32.tar.gz")))
run("deb with only the .dsc (no orig/debian tar)", mut(DEB, lambda e: e["files"].pop(1)))
run("entry with an extra key", mut(DEB, lambda e: e.update(skip=True)))
run("maven sources jar served from files.pythonhosted.org, other name", mut(MAV, lambda e: e["files"][0].update(name="evil-1.0-sources.jar", url="https://files.pythonhosted.org/x/evil-1.0-sources.jar")))
run("pypi sdist named for another package", mut(PYP, lambda e: e["files"][0].update(name="other-9.9.tar.gz")))
run("temurin asset on repo1.maven.org", mut(TEM, lambda e: e["files"][0].update(url="https://repo1.maven.org/x.tar.gz")))
run("apk APKBUILD only, no sha512 files", mut(APK, lambda e: e["files"].pop(1)))
run("pgdg entry with no .dsc (no pgdg rules)", mut("pgdg:postgresql-common@293.pgdg12+1", lambda e: e["files"].pop(0)))
run("url with a tab inside the host (urlsplit drops it)", mut(PYP, lambda e: e["files"][0].update(url=e["files"][0]["url"].replace("files.python", "files.py\tthon"))))
run("url with a newline in the path", mut(PYP, lambda e: e["files"][0].update(url=e["files"][0]["url"].replace("/packages", "/pack\nages"))))
run("url with a space in the path", mut(PYP, lambda e: e["files"][0].update(url=e["files"][0]["url"].replace("/packages", "/pack ages"))))
run("url with path traversal", mut(PYP, lambda e: e["files"][0].update(url="https://files.pythonhosted.org/../../etc/passwd")))
run("url with backslash before @", mut(PYP, lambda e: e["files"][0].update(url="https://files.pythonhosted.org\@evil.example/x")))
run("arches [['amd64']] (unhashable)", mut(DEB, lambda e: e.update(arches=[["amd64"]])))
run("arches [1, 'amd64'] (mixed types)", mut(DEB, lambda e: e.update(arches=[1, "amd64"])))
run("files: [1] non-dict file", mut(PYP, lambda e: e.update(files=[1])))
run("upstream from non-str", mut(PYP, lambda e: e["files"][0]["upstream"].update({"from": 5})))
run("component value null", None, t.canon({"format": 1, "components": dict(t.good_lock(t.SMALL_KEYS)["components"], **{"deb:x@1": None})}))
run("lock JSON array", None, "[]\n")
run("format true", None, t.canon(dict(t.good_lock(t.SMALL_KEYS), format=True)))
print("## 182 keys: independent derivation")
pol = t.policy(); docs = t.fixture_docs()
mine = set()
for image, doc in docs.items():
    rows = m.classify_document(image, doc, pol["always"], pol["exempt"])
    nv = next((unquote(r["purl"].split("@",1)[1].split("?")[0]) for r in rows if (r["purl"] or "").startswith("pkg:maven/org.neo4j/neo4j@")), None)
    for r in rows:
        if not r["needs"]: continue
        pu = r["purl"]; base, _, qs = pu.partition("?"); q = dict(x.split("=",1) for x in qs.split("&") if "=" in x)
        typ = base.split(":",1)[1].split("/",1)[0]; path, ver = base.split("@",1); ver = unquote(ver); parts = path.split("/")
        if typ == "deb":
            up = unquote(q.get("upstream","")); src, _, sv = up.partition("@"); src = src or unquote(parts[-1]); sv = sv or ver
            mine.add(("pgdg" if ".pgdg" in sv else "deb") + f":{src}@{sv}")
        elif typ == "apk": mine.add(f"apk:{unquote(q.get('upstream','')).split('@')[0] or unquote(parts[-1])}@{ver}")
        elif typ == "generic": mine.add("temurin:jdk-" + ver.removesuffix("-LTS"))
        elif typ == "maven":
            g, a = parts[1], parts[2]
            if g == "jrt-fs": continue
            if (g in ("org.neo4j","com.neo4j") or g.startswith(("org.neo4j.","com.neo4j."))) and ver == nv: mine.add(f"neo4j:neo4j@{ver}")
            else: mine.add(f"maven:{g}:{a}@{ver}")
        elif typ == "pypi": mine.add("pypi:" + re.sub(r"[-_.]+","-",unquote(parts[-1])).lower() + "@" + ver)
        else: mine.add("UNMAPPED " + pu)
print("  independent", len(mine), "== FIXTURE_KEYS:", mine == set(t.FIXTURE_KEYS), "diff", sorted(mine ^ set(t.FIXTURE_KEYS))[:5])
