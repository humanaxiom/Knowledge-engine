"""security U7a rework r2 probes (re-runs the r1 set; comparison is now r1) (platform-sbom). python -I, gates image."""
import copy, importlib.util, json, re, sys, time, datetime
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
from tests import sbom_support as ss
from tests.test_sbom_bundle import load_sbom_check
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
sc = load_sbom_check()
g0 = load("sc_u7a_green", "/work/docs/evidence/platform-sbom/u7a/r1-target-sbom_check.py")
P = print
BS = chr(92)
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
POL = tl.policy()
DOCS = tl.small_docs()
BASE = tl.good_lock(tl.SMALL_KEYS)
def probs(lock, pol=POL, docs=DOCS, arch="amd64"):
    text = lock if isinstance(lock, str) else tl.canon(lock)
    return sc.lock_problems(text, pol, docs, arch, today=datetime.date(2026, 10, 25))
base_p = probs(BASE)
P("== baseline good lock problems (no pgdg key in SMALL_KEYS; expect none):")
for x in base_p: P("   ", x[:160])
def only_new(pr):
    return [x for x in pr if x not in base_p]
KEY = "pypi:psycopg@3.3.6"
def setf(key, i=0, **ch):
    d = copy.deepcopy(BASE); d["components"][key]["files"][i].update(ch); return d
def show(label, d):
    pr = only_new(probs(d)); P(f"  {label:58s} rejected={bool(pr)!s:5} {[x[:100] for x in pr[:1]]}")

P("\n== R1-1. U7a smuggling set re-run on the pypi file (every row should now be rejected) ==")
url0 = BASE["components"][KEY]["files"][0]["url"]
urls = {
 "userinfo host@evil": "https://files.pythonhosted.org@evil.example/x.tar.gz",
 "IDN lookalike": "https://files.pythonh\u043ested.org/x.tar.gz", "fullwidth dot": "https://files\uff0epythonhosted.org/x.tar.gz",
 "trailing dot": "https://files.pythonhosted.org./x.tar.gz", "port": "https://files.pythonhosted.org:443/x.tar.gz",
 "uppercase host": "https://FILES.pythonhosted.org/x.tar.gz", "percent host": "https://files%2Epythonhosted.org/x.tar.gz",
 "backslash before host": "https://evil.example" + BS + "@files.pythonhosted.org/x.tar.gz",
 "HTTP": "HTTP://files.pythonhosted.org/x.tar.gz", "HTTPS upper": "HTTPS://files.pythonhosted.org/x.tar.gz",
 "tab in host": "https://files.python\thosted.org/x.tar.gz", "LF in host": "https://files.python\nhosted.org/x.tar.gz",
 "CR in path": url0.replace(".tar.gz", "\r.tar.gz"), "leading space": " " + url0, "trailing space": url0 + " ",
 "leading NUL": "\x00" + url0, "space in path": url0.replace("/ab/", "/a b/"), "non-ASCII path": url0.replace("/ab/", "/\u00e9/"),
 "../ in path": url0.replace("/ab/cd/", "/ab/../cd/"), "%2e%2e in path": url0.replace("/ab/cd/", "/ab/%2e%2e/cd/"),
 "backslash in path": url0.replace("/ab/cd/", "/ab" + BS + ".." + BS + "cd/"), "double quote in path": url0.replace("/ab/", '/a"b/'),
 "angle brackets in path": url0.replace("/ab/", "/<ab>/"), "empty segment //": url0.replace("/ab/", "//ab/"),
 "pypi on github.com": "https://github.com/evil/x/psycopg-3.3.6.tar.gz",
}
for k, u in urls.items():
    show(k, setf(KEY, url=u))
for k, ch in {"size 4 GiB": dict(size=4294967296), "size 4 GiB + 1": dict(size=4294967297), "size 10**30": dict(size=10 ** 30),
              "name CON": dict(name="CON"), "name a..b": dict(name="a..b"), "from with ESC": None}.items():
    if ch is None:
        d = copy.deepcopy(BASE); d["components"][KEY]["files"][0]["upstream"]["from"] = "uv.lock\x1b[2J"; show(k, d)
    else:
        show(k, setf(KEY, **ch))

P("\n== R1-2. Binding rules (L-2) ==")
C = BASE["components"]
for k in sorted(C): P("   ", k, [f["url"][:100] for f in C[k]["files"]])
MV, TM, AP, NJ, DB = "maven:javax.xml.bind:jaxb-api@2.2.12", "temurin:jdk-21.0.12.1+1", "apk:readline@8.2.13-r1", "neo4j:neo4j@5.26.32", "deb:bash@5.2.15-2"
mv = C[MV]["files"][0]; tm = C[TM]["files"][0]; nj = C[NJ]["files"][0]
show("maven jar on github.com", setf(MV, url="https://github.com/x/y/" + mv["name"]))
show("maven jar at another version path", setf(MV, url=mv["url"].replace("/2.2.12/", "/2.2.11/")))
show("maven jar of another artifact (same dir)", setf(MV, url=mv["url"].rsplit("/", 1)[0] + "/jaxb-impl-2.2.12-sources.jar", name="jaxb-impl-2.2.12-sources.jar"))
show("maven binary jar, not -sources", setf(MV, url=mv["url"].replace("-sources.jar", ".jar"), name="jaxb-api-2.2.12.jar"))
t_dir, t_name = tm["url"].rsplit("/", 1)
P("   temurin url:", tm["url"])
show("temurin asset of another feature (17) in temurin21 repo", setf(TM, url=t_dir + "/OpenJDK17U-jdk-sources_17.0.1_12.tar.gz", name="OpenJDK17U-jdk-sources_17.0.1_12.tar.gz",
     upstream=dict(tm["upstream"], **{"from": "OpenJDK17U-jdk-sources_17.0.1_12.tar.gz.sha256.txt"})))
show("temurin same feature, another release tag", setf(TM, url=tm["url"].replace("jdk-21.0.12.1%2B1", "jdk-21.0.1%2B12")))
other = t_dir.rsplit("/", 1)[0] + "/jdk-21.0.1%2B12/OpenJDK21U-jdk-sources_21.0.1_12.tar.gz"
show("temurin same feature, other tag and other version asset", setf(TM, url=other, name="OpenJDK21U-jdk-sources_21.0.1_12.tar.gz",
     upstream=dict(tm["upstream"], **{"from": "OpenJDK21U-jdk-sources_21.0.1_12.tar.gz.sha256.txt"})))
show("temurin extra path segments", setf(TM, url=t_dir + "/x/y/" + t_name))
show("temurin repo temurin17-binaries", setf(TM, url=tm["url"].replace("temurin21-binaries", "temurin17-binaries")))
show("temurin a JDK binary, not sources (name)", setf(TM, url=t_dir + "/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz", name="OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz",
     upstream=dict(tm["upstream"], **{"from": "OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz.sha256.txt"})))
show("temurin asset named Evil-jdk-sources_x.tar.gz", setf(TM, url=t_dir + "/Evil-jdk-sources_x.tar.gz", name="Evil-jdk-sources_x.tar.gz",
     upstream=dict(tm["upstream"], **{"from": "Evil-jdk-sources_x.tar.gz.sha256.txt"})))
ap = C[AP]; commit = ap["commit"]
P("   apk urls:", [f["url"] for f in ap["files"]])
show("apk APKBUILD at another commit", setf(AP, 0, url=ap["files"][0]["url"].replace(commit, "f" * 40)))
show("apk APKBUILD from community (repo main)", setf(AP, 0, url=ap["files"][0]["url"].replace("/main/", "/community/")))
show("apk APKBUILD of another origin", setf(AP, 0, url=ap["files"][0]["url"].replace("/readline/", "/bash/")))
show("apk APKBUILD from distfiles", setf(AP, 0, url="https://distfiles.alpinelinux.org/distfiles/v3.23/APKBUILD"))
show("apk tarball at another branch", setf(AP, 1, url=ap["files"][1]["url"].replace("/v3.23/", "/v3.22/")))
show("apk tarball raw from gitlab at the commit", setf(AP, 1, url=f"https://gitlab.alpinelinux.org/alpine/aports/-/raw/{commit}/main/readline/" + ap["files"][1]["name"]))
show("apk tarball raw from gitlab at another commit", setf(AP, 1, url=f"https://gitlab.alpinelinux.org/alpine/aports/-/raw/{'e'*40}/main/readline/" + ap["files"][1]["name"]))
d = copy.deepcopy(BASE); d["components"][AP]["commit"] = "f" * 40
show("apk entry commit changed (urls keep the old one)", d)
P("   pypi url:", C[KEY]["files"][0]["url"])
pyurl = C[KEY]["files"][0]["url"]
def pyname(n):
    return setf(KEY, url=pyurl.rsplit("/", 1)[0] + "/" + n, name=n)
for n in ("Psycopg-3.3.6.tar.gz", "psycopg_c-3.3.6.tar.gz", "psycopg-c-3.3.6.tar.gz", "psycopg-3.3.7.tar.gz", "psycopg-3.3.6-1.tar.gz",
          "psycopg-binary-3.3.6.tar.gz", "psycopg-3.3.6.zip", "psycopg-3.3.6-py3-none-any.whl", "PSYCOPG-3.3.6.tar.gz", "psycopg.-3.3.6.tar.gz",
          "psycopg--3.3.6.tar.gz"):
    show(f"pypi name {n}", pyname(n))
show("pypi url basename differs from name", setf(KEY, url=pyurl.rsplit("/", 1)[0] + "/other-3.3.6.tar.gz"))
db = C[DB]["files"]
show("deb .dsc url sha1 != upstream sha1", setf(DB, 0, url="https://snapshot.debian.org/file/" + "0" * 40))
d = copy.deepcopy(BASE); d["components"][DB]["files"][0]["upstream"]["value"] = "0" * 40
show("deb .dsc upstream sha1 changed (url keeps old)", d)
show("deb orig on gitlab", setf(DB, 1, url="https://gitlab.alpinelinux.org/x/" + db[1]["name"]))
show("deb orig /file/<40 hex> but upper case", setf(DB, 1, url=db[1]["url"].upper().replace("HTTPS://SNAPSHOT.DEBIAN.ORG/FILE/", "https://snapshot.debian.org/file/")))
d = copy.deepcopy(BASE); d["components"][DB]["files"] = d["components"][DB]["files"][:1]
show("deb only the .dsc (no other file)", d)
d = copy.deepcopy(BASE); d["components"][NJ]["files"].append(copy.deepcopy(nj)); d["components"][NJ]["files"][1]["name"] = "x.tar.gz"
show("neo4j second file", d)
show("neo4j another tag", setf(NJ, url=nj["url"].replace("5.26.32", "5.26.31")))
show("neo4j name other than <ver>.tar.gz", setf(NJ, name="neo4j-5.26.32.tar.gz"))
d = copy.deepcopy(BASE); d["components"][NJ]["files"][0]["upstream"]["alg"] = "sha1"; d["components"][NJ]["files"][0]["upstream"]["value"] = "a" * 40
show("neo4j upstream alg sha1", d)
d = copy.deepcopy(BASE); d["components"][NJ]["files"][0]["upstream"]["value"] = "b" * 64
show("neo4j upstream value != file sha256", d)
show("neo4j from codeload.github.com", setf(NJ, url="https://codeload.github.com/neo4j/neo4j/tar.gz/refs/tags/5.26.32"))
P("  KIND_HOSTS subset of the committed policy hosts:", {h for v in sc.KIND_HOSTS.values() for h in v} <= set(tl.policy()["hosts"]),
  "| pgdg hosts:", sc.KIND_HOSTS["pgdg"])

P("\n== R1-3. Escaping (L-3): raw control bytes in any message ==")
d = copy.deepcopy(BASE); d["components"]["deb:x\x1b[2J@1"] = copy.deepcopy(BASE["components"][DB])
d["components"]["apk:x\x9b2J@1-r0"] = copy.deepcopy(BASE["components"][DB]); d["components"]["apk:x\x9b2J@1-r0"]["kind"] = "apk"
d["components"][KEY]["files"][0]["name"] = "a\x1b[2J"
d["components"][KEY]["files"][0]["url"] = pyurl + "\x1b]0;T\x07"
d["components"][KEY]["files"][0]["extra\x1b"] = 1
docs = copy.deepcopy(DOCS)
docs["postgres"] = ss.spdx_doc("postgres", [{"purl": "pkg:deb/debian/evil@1?upstream=ev%1b%5b2Jil%401", "declared": "GPL-2.0-only"},
                                            {"purl": "pkg:pypi/x%1b@1", "declared": "GPL-2.0-only"}])
out = probs(d, docs=docs); raw = [x for x in out if CTRL.search(x)]
P(f"  hostile lock keys, name, url, file key + SBOM purls: problems={len(out)} raw-control lines={len(raw)} {[repr(x)[:120] for x in raw[:3]]}")

P("\n== R1-4. Robustness: wrong types never raise; CLI never prints a traceback ==")
shapes = {"lock not str": 5, "deep JSON": "[" * 100000 + "]" * 100000, "components list": json.dumps({"format": 1, "components": []}),
          "entry list": tl.canon({"format": 1, "components": {KEY: []}}), "files dict": tl.canon({"format": 1, "components": {KEY: dict(C[KEY], files={})}}),
          "file list": tl.canon({"format": 1, "components": {KEY: dict(C[KEY], files=[[]])}}),
          "upstream list": tl.canon({"format": 1, "components": {KEY: dict(C[KEY], files=[dict(C[KEY]['files'][0], upstream=[])])}}),
          "arches dicts": tl.canon({"format": 1, "components": {KEY: dict(C[KEY], arches=[{}])}}),
          "name int": tl.canon({"format": 1, "components": {KEY: dict(C[KEY], files=[dict(C[KEY]['files'][0], name=5)])}}),
          "apk commit int": tl.canon({"format": 1, "components": {AP: dict(C[AP], commit=5)}}),
          "key int-like": '{"components": {"5": {}}, "format": 1}', "NaN format": '{"components": {}, "format": NaN}',
          "huge int": '{"components": {}, "format": ' + "9" * 5000 + '}'}
for k, s in shapes.items():
    try:
        r = sc.lock_problems(s, POL, DOCS, "amd64"); P(f"  {k:20s} problems={len(r)} {[x[:70] for x in r[:1]]}")
    except BaseException as e:
        P(f"  {k:20s} RAISED {type(e).__name__}: {str(e)[:80]}")
import subprocess, tempfile, os
W = tempfile.mkdtemp()
def w(n, s):
    p = os.path.join(W, n); open(p, "w", encoding="utf-8", newline="").write(s); return p
polp = w("pol.json", json.dumps(POL)); sb = []
for k, v in DOCS.items(): sb += ["--sbom", f"{k}={w(k + '.json', json.dumps(v))}"]
for k, s in (("deep JSON", "[" * 100000 + "]" * 100000), ("huge int", shapes["huge int"]), ("good", tl.canon(BASE))):
    r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "lock-check", "--lock", w("l.json", s), "--policy", polp, "--arch", "amd64", *sb],
                       capture_output=True, text=True)
    P(f"  CLI {k:12s} rc={r.returncode} traceback={'Traceback' in r.stderr} {(r.stdout + r.stderr).strip().splitlines()[0][:120] if (r.stdout + r.stderr).strip() else ''}")
r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "lock-check", "--lock", w("l.json", tl.canon(BASE)), "--policy", w("p.json", "[" * 100000), "--arch", "amd64", *sb], capture_output=True, text=True)
P(f"  CLI deep policy  rc={r.returncode} traceback={'Traceback' in r.stderr}")

P("\n== R1-5. ReDoS / cost on the new checks ==")
def t(label, f):
    s = time.perf_counter()
    try:
        r = f(); out = str(r)[:40]
    except BaseException as e:
        out = "RAISED " + type(e).__name__
    P(f"  {label:60s} {time.perf_counter()-s:8.3f}s {out}")
for n in (1000, 10000, 50000):
    t(f"PYPI_DIST_RE 'a-' * {n} (no .tar.gz)", lambda n=n: bool(sc.PYPI_DIST_RE.fullmatch("a-" * n)))
    t(f"PYPI_DIST_RE 'a-' * {n} + '.tar.g'", lambda n=n: bool(sc.PYPI_DIST_RE.fullmatch("a-" * n + ".tar.g")))
    t(f"TEMURIN_ASSET_RE 'a-jdk-sources_' + '.' * {n}", lambda n=n: bool(sc.TEMURIN_ASSET_RE.fullmatch("a-jdk-sources_" + "." * n)))
t("PRINTABLE_RE 1MB + DEL", lambda: bool(sc.PRINTABLE_RE.fullmatch("a" * 1000000 + "\x7f")))
big_name = "a-" * 50000 + ".tar.g"
t("lock_problems: pypi file with a 100k-char a- name", lambda: len(probs(setf(KEY, name=big_name, url=pyurl.rsplit('/', 1)[0] + '/' + big_name))))
big = copy.deepcopy(BASE)
for i in range(20000): big["components"][f"deb:p{i}@1.0-1"] = copy.deepcopy(BASE["components"][DB])
t("lock_problems 20000 entries", lambda: len(probs(big)))

P("\n== R1-6. lock_needs unchanged vs rework r1 (u7a/r1-target-sbom_check.py) ==")
pol, fdocs = tl.policy(), tl.fixture_docs()
a = sc.lock_needs(pol, fdocs); b = g0.lock_needs(pol, fdocs)
P(f"  keys r1={len(a[0])} green={len(b[0])} equal={a == b} problems={a[1]}")
import inspect
P("  component_key/lock_needs/classify_document/unlicensed_report source equal to r1:",
  all(inspect.getsource(getattr(g0, f)) == inspect.getsource(getattr(sc, f)) for f in ("component_key", "lock_needs", "classify_document", "unlicensed_report", "_clean")))

P("\n== R2-1. Plain-path rule (review R1-B1) on real-shaped URLs ==")
pyu = C[KEY]["files"][0]["url"]; pdir, pname = pyu.rsplit("/", 1)
mvu = C[MV]["files"][0]["url"]
def tricks(base_dir, name):
    return {
     "%2e%2e segment": base_dir + "/%2e%2e/" + name, "%2E%2E segment": base_dir + "/%2E%2E/" + name, ".%2e segment": base_dir + "/.%2e/" + name,
     "%2E. segment": base_dir + "/%2E./" + name, "..%5c": base_dir + "/..%5c" + name, "backslash dot-dot": base_dir + BS + ".." + BS + name,
     "%2f in a segment": base_dir + "%2f" + name, "//": base_dir + "//" + name, "/./": base_dir + "/./" + name, "/../": base_dir + "/../" + name,
     "trailing /": base_dir + "/" + name + "/", "%2B in a non-tag segment": base_dir + "/%2B/" + name, "%25 (encoded %)": base_dir + "/%25/" + name,
     "%252e%252e (double-encoded)": base_dir + "/%252e%252e/" + name, "overlong UTF-8 %c0%ae": base_dir + "/%c0%ae%c0%ae/" + name,
     "fullwidth percent": base_dir + "/\uff05\u0032\u0065/" + name, "U+2024 one-dot leader": base_dir + "/\u2024\u2024/" + name,
     "%00": base_dir + "/a%00/" + name, "semicolon param": base_dir + ";x/" + name,
    }
for k, u in tricks(pdir, pname).items():
    show(f"pypi {k}", setf(KEY, url=u))
for k, u in list(tricks(mvu.rsplit("/", 1)[0], mvu.rsplit("/", 1)[1]).items())[:6]:
    show(f"maven {k}", setf(MV, url=u))

P("\n== R2-2. pypi Warehouse layout ==")
segs = pdir.split("/")
a, b, c = segs[-3], segs[-2], segs[-1]
root = "https://files.pythonhosted.org"
lay = {"good": f"{root}/packages/{a}/{b}/{c}/{pname}", "upper-case hex": f"{root}/packages/{a.upper()}/{b}/{c.upper()}/{pname}",
       "59 hex": f"{root}/packages/{a}/{b}/{c[:-1]}/{pname}", "61 hex": f"{root}/packages/{a}/{b}/{c}0/{pname}",
       "extra segment": f"{root}/packages/{a}/{b}/{c}/x/{pname}", "missing segment": f"{root}/packages/{a}/{c}/{pname}",
       "not /packages/": f"{root}/pkgs/{a}/{b}/{c}/{pname}", "legacy /packages/source/p/psycopg/": f"{root}/packages/source/p/psycopg/{pname}",
       "non-hex": f"{root}/packages/zz/{b}/{c}/{pname}"}
for k, u in lay.items():
    pr = only_new(probs(setf(KEY, url=u)))
    P(f"  {k:42s} rejected={bool(pr)!s:5} {[x[:100] for x in pr[:1]]}")
d = copy.deepcopy(BASE); f = d["components"]["pypi:psycopg-c@3.3.6"]["files"][0]
f["name"] = "psycopg_c-3.3.6.tar.gz"; f["url"] = f["url"].rsplit("/", 1)[0] + "/psycopg_c-3.3.6.tar.gz"
P(f"  pypi:psycopg-c named psycopg_c-3.3.6.tar.gz: problems={only_new(probs(d))}")

P("\n== R2-3. temurin exact form ==")
TF = C[TM]["files"][0]
tu, tn = TF["url"], TF["name"]
want = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz"
P(f"  baseline url equals the design form: {tu == want} | name {tn} | from {TF['upstream']['from']}")
def tm_with(url, name=None, frm=None):
    d = copy.deepcopy(BASE); f = d["components"][TM]["files"][0]; f["url"] = url
    if name:
        f["name"] = name
    f["upstream"]["from"] = frm or (f["name"] + ".sha256.txt")
    return d
tdir = tu.rsplit("/", 1)[0]
rows = {
 "asset of feature 17 in temurin21": (tdir + "/OpenJDK17U-jdk-sources_17.0.1_12.tar.gz", "OpenJDK17U-jdk-sources_17.0.1_12.tar.gz"),
 "another tag": (tu.replace("jdk-21.0.12.1%2B1", "jdk-21.0.1%2B12"), None),
 "another version asset": (tdir + "/OpenJDK21U-jdk-sources_21.0.1_12.tar.gz", "OpenJDK21U-jdk-sources_21.0.1_12.tar.gz"),
 "extra segments": (tdir + "/x/" + tn, None),
 "Evil-jdk-sources_x": (tdir + "/Evil-jdk-sources_x.tar.gz", "Evil-jdk-sources_x.tar.gz"),
 "plus unencoded in tag": (tu.replace("%2B", "+"), None), "%2b lower in tag": (tu.replace("%2B", "%2b"), None),
 "%2B%2B in tag": (tu.replace("%2B", "%2B%2B"), None), "%252B in tag": (tu.replace("%2B", "%252B"), None),
 "%2B in asset": (tdir + "/" + tn.replace("_1.tar", "%2B1.tar"), None),
 "JRE asset": (tdir + "/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz", "OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz"),
 "JDK binary asset": (tdir + "/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz", "OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz"),
 "temurin17 repo": (tu.replace("temurin21-binaries", "temurin17-binaries"), None),
}
for k, (u, n) in rows.items():
    pr = only_new(probs(tm_with(u, n)))
    P(f"  {k:42s} rejected={bool(pr)!s:5} {[x[:100] for x in pr[:1]]}")
pr = only_new(probs(tm_with(tu, None, "OpenJDK21U-jdk-sources_21.0.1_12.tar.gz.sha256.txt")))
P(f"  {'from naming another asset':42s} rejected={bool(pr)!s:5} {[x[:100] for x in pr[:1]]}")

P("\n== R2-4. Timing: R1-L1 and _plain_path ==")
names = {"a- x 50000": "a-" * 50000,
         "255-char a- ... -3.3.6.tar.gz": ("a-" * 200)[:255 - len("-3.3.6.tar.gz")] + "-3.3.6.tar.gz",
         "255-char aaaa-3.3.6.tar.gz": "a" * (255 - len("-3.3.6.tar.gz")) + "-3.3.6.tar.gz"}
for label, n in names.items():
    d = copy.deepcopy(BASE); f = d["components"][KEY]["files"][0]; f["name"] = n; f["url"] = pdir + "/" + n
    t(f"lock_problems pypi name {label} ({len(n)} chars)", lambda d=d: [x[:60] for x in only_new(probs(d))][:2])
t("_plain_path 1 MB of /a", lambda: sc._plain_path("/a" * 500000, "https://x" + "/a" * 500000, None))
t("_plain_path 1 MB of %2B tag segment", lambda: sc._plain_path("/a/b/c/d/" + "%2B" * 333000 + "/x", "u", "temurin"))
t("_plain_path 1 MB of %%2B2B", lambda: sc._plain_path("/a/b/c/d/" + "%%2B2B" * 160000 + "/x", "u", "temurin"))
t("_url_problems 1 MB url", lambda: len(sc._url_problems("w", "https://files.pythonhosted.org" + "/a" * 500000, {"files.pythonhosted.org"})))
t("_pypi_parts 1 MB", lambda: sc._pypi_parts("a-" * 500000 + ".tar.gz"))
t("PYPI_DIST_RE fullmatch 1 MB a- then -", lambda: bool(sc.PYPI_DIST_RE.fullmatch("a-" * 500000 + "-")))
t("PYPI_PATH_RE 1 MB", lambda: bool(sc.PYPI_PATH_RE.fullmatch("/packages/aa/bb/" + "a" * 1000000 + "/")))

P("\n== R2-5. CLI FAIL line ==")
cases = {"missing file": None, "invalid JSON": "{", "deep nesting": "[" * 100000 + "]" * 100000, "bad UTF-8": bytes([255, 254])}
for k, s in cases.items():
    if s is None:
        path = os.path.join(W, "absent.json")
    elif isinstance(s, bytes):
        path = os.path.join(W, "bad.json"); open(path, "wb").write(s)
    else:
        path = w("x.json", s)
    r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "lock-check", "--lock", path, "--policy", polp, "--arch", "amd64", *sb], capture_output=True, text=True)
    lines = r.stderr.strip().splitlines()
    P(f"  {k:14s} rc={r.returncode} stderr-lines={len(lines)} traceback={'Traceback' in r.stderr} {lines[0][:110] if lines else ''}")
d = copy.deepcopy(BASE); d["components"][KEY]["files"][0]["name"] = "x" + chr(27) + "[2J"
r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "lock-check", "--lock", w("e.json", tl.canon(d)), "--policy", polp, "--arch", "amd64", *sb], capture_output=True, text=True)
P(f"  hostile name  rc={r.returncode} raw-control={bool(CTRL.search(r.stderr.rstrip(chr(10))))} lines={len(r.stderr.strip().splitlines())}")
