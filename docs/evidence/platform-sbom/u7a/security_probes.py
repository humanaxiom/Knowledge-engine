"""security U7a gate probes (platform-sbom). python -I, gates image."""
import copy, json, re, sys, time, datetime
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
from tests import sbom_support as ss
sc = tl.load_sbom_check() if hasattr(tl, "load_sbom_check") else None
from tests.test_sbom_bundle import load_sbom_check
sc = load_sbom_check()
P = print
BS = chr(92)
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
POL = tl.policy_with_pgdg()
DOCS = tl.small_docs()
BASE = tl.good_lock(tl.SMALL_KEYS)
def probs(lock, pol=POL, docs=DOCS, arch="amd64"):
    text = lock if isinstance(lock, str) else tl.canon(lock)
    return sc.lock_problems(text, pol, docs, arch, today=datetime.date(2026, 10, 25))
P("== baseline good lock (SMALL_KEYS, policy+pgdg host, small_docs):", probs(BASE))
KEY = "pypi:psycopg@3.3.6"
def with_file(key, **ch):
    d = copy.deepcopy(BASE); d["components"][key]["files"][0].update(ch); return d
def with_up(key, **ch):
    d = copy.deepcopy(BASE); d["components"][key]["files"][0]["upstream"].update(ch); return d
P("\n== U7a-1. URL / host smuggling on the pypi file (want: rejected) ==")
sha = BASE["components"][KEY]["files"][0]["sha256"]
urls = {
 "userinfo host@evil": "https://files.pythonhosted.org@evil.example/x.tar.gz",
 "userinfo evil@host": "https://evil.example@files.pythonhosted.org/x.tar.gz",
 "user:pass@host": "https://u:p@files.pythonhosted.org/x.tar.gz",
 "IDN lookalike (Cyrillic o)": "https://files.pythonh\u043ested.org/x.tar.gz",
 "punycode": "https://xn--files-pythonhosted-org.example/x.tar.gz",
 "fullwidth dot": "https://files\uff0epythonhosted.org/x.tar.gz",
 "trailing dot": "https://files.pythonhosted.org./x.tar.gz",
 "port 443": "https://files.pythonhosted.org:443/x.tar.gz",
 "empty port": "https://files.pythonhosted.org:/x.tar.gz",
 "uppercase host": "https://FILES.pythonhosted.org/x.tar.gz",
 "percent-encoded host": "https://files%2Epythonhosted.org/x.tar.gz",
 "backslash before host": "https://evil.example" + BS + "@files.pythonhosted.org/x.tar.gz",
 "backslash after host": "https://files.pythonhosted.org" + BS + ".evil.example/x.tar.gz",
 "backslash path": "https://files.pythonhosted.org" + BS + "x.tar.gz",
 "http": "http://files.pythonhosted.org/x.tar.gz",
 "HTTP upper": "HTTP://files.pythonhosted.org/x.tar.gz",
 "HTTPS upper (still https)": "HTTPS://files.pythonhosted.org/x.tar.gz",
 "ftp": "ftp://files.pythonhosted.org/x.tar.gz",
 "file": "file:///etc/passwd",
 "scheme-relative": "//files.pythonhosted.org/x.tar.gz",
 "single slash": "https:/files.pythonhosted.org/x.tar.gz",
 "no slashes": "https:files.pythonhosted.org/x.tar.gz",
 "query": "https://files.pythonhosted.org/x.tar.gz?a=1",
 "fragment": "https://files.pythonhosted.org/x.tar.gz#a",
 "IPv4": "https://151.101.0.223/x.tar.gz",
 "IPv6": "https://[2a04:4e42::223]/x.tar.gz",
 "tab inside host": "https://files.python\thosted.org/x.tar.gz",
 "newline inside host": "https://files.python\nhosted.org/x.tar.gz",
 "CR in path": "https://files.pythonhosted.org/x\r.tar.gz",
 "leading space": " https://files.pythonhosted.org/x.tar.gz",
 "trailing space": "https://files.pythonhosted.org/x.tar.gz ",
 "leading NUL": "\x00https://files.pythonhosted.org/x.tar.gz",
 "space in path": "https://files.pythonhosted.org/a b.tar.gz",
 "non-ASCII path": "https://files.pythonhosted.org/\u00e9.tar.gz",
 "path traversal ../": "https://files.pythonhosted.org/../../evil",
 "other listed host (github.com) for pypi": "https://github.com/evil/repo/x.tar.gz",
 "not a string": 5,
}
for k, u in urls.items():
    pr = probs(with_file(KEY, url=u))
    P(f"  {k:42s} rejected={bool(pr)!s:5} {[x[:90] for x in pr[:1]]}")
P("\n== U7a-2. name / hash / size / upstream on the pypi file ==")
cases = {
 "name ../x": dict(name="../x"), "name /abs": dict(name="/etc/passwd"), "name a/b": dict(name="a/b"), "name NUL": dict(name="a\x00b"),
 "name ..": dict(name=".."), "name .hidden": dict(name=".x"), "name a..b": dict(name="a..b"), "name 256 chars": dict(name="a" * 256),
 "name CON (Windows reserved)": dict(name="CON"), "name aux.tar.gz": dict(name="aux.tar.gz"), "name backslash": dict(name="a" + BS + "b"),
 "name not the URL basename": dict(name="totally-different.tar.gz"), "name trailing dot": dict(name="x.tar.gz."),
 "name non-ASCII": dict(name="\u00e9.tar.gz"), "name newline": dict(name="a\nb"),
 "sha256 uppercase": dict(sha256=sha.upper()), "sha256 63": dict(sha256=sha[:-1]), "sha256 65": dict(sha256=sha + "0"),
 "sha256 fullwidth digit": dict(sha256=sha[:-1] + "\uff10"), "sha256 int": dict(sha256=5),
 "size 0": dict(size=0), "size -1": dict(size=-1), "size True": dict(size=True), "size 1.0": dict(size=1.0), "size '5'": dict(size="5"),
 "size 10**30 (huge)": dict(size=10 ** 30), "size 2**63": dict(size=2 ** 63),
 "a sixth key": dict(extra=1),
}
for k, ch in cases.items():
    pr = probs(with_file(KEY, **ch))
    P(f"  {k:42s} rejected={bool(pr)!s:5} {[x[:90] for x in pr[:1]]}")
ups = {"alg sha1 (pypi wants sha256)": dict(alg="sha1", value="a" * 40), "alg SHA256": dict(alg="SHA256"),
       "alg md5": dict(alg="md5", value="a" * 32), "value differs from sha256": dict(value="b" * 64),
       "value uppercase": dict(value=sha.upper()), "value 63": dict(value=sha[:-1]), "from blank": {"from": "  "},
       "from int": {"from": 5}, "from with ESC": {"from": "uv.lock\x1b[2J"}}
for k, ch in ups.items():
    pr = probs(with_up(KEY, **ch))
    P(f"  upstream {k:33s} rejected={bool(pr)!s:5} {[x[:90] for x in pr[:1]]}")

P("\n== U7a-3. Per-kind rules: is the URL bound to its kind's host and shape? ==")
def setf(key, i, **ch):
    d = copy.deepcopy(BASE); d["components"][key]["files"][i].update(ch); return d
deb = "deb:bash@5.2.15-2"
f0 = BASE["components"][deb]["files"][0]
P("  deb .dsc url:", f0["url"][:60], "| name", f0["name"])
for k, u in {"deb .dsc from github.com": "https://github.com/x/" + f0["upstream"]["value"],
             "deb .dsc /file/<other sha1>": "https://snapshot.debian.org/file/" + "0" * 40,
             "deb .dsc /file/<sha1>/": f0["url"] + "/", "deb .dsc /file/<SHA1 upper>": f0["url"].upper().replace("HTTPS://SNAPSHOT.DEBIAN.ORG", "https://snapshot.debian.org")}.items():
    P(f"  {k:42s} rejected={bool(probs(setf(deb, 0, url=u)))}")
P(f"  {'deb orig from files.pythonhosted.org':42s} rejected={bool(probs(setf(deb, 1, url='https://files.pythonhosted.org/x')))}")
for key in sorted(BASE["components"]):
    kind = key.split(":")[0]
    if kind == "deb":
        continue
    d = copy.deepcopy(BASE)
    for f in d["components"][key]["files"]:
        f["url"] = "https://files.pythonhosted.org/evil/" + f["name"] if kind != "pypi" else "https://github.com/evil/" + f["name"]
    P(f"  {key:42s} every file moved to another listed host: rejected={bool(probs(d))} {probs(d)[:1]}")
d = copy.deepcopy(BASE)
pg = [k for k in BASE["components"] if k.startswith("pgdg:")][0]
d["components"][pg]["files"] = [{"name": "anything.bin", "url": "https://github.com/evil/anything.bin", "sha256": "a" * 64, "size": 1,
                                 "upstream": {"alg": "sha256", "value": "a" * 64, "from": "x"}}]
P(f"  {pg}: one arbitrary file, no .dsc: rejected={bool(probs(d))} {probs(d)[:1]}")
P("  pgdg entry with the committed hosts (no apt-archive host):", [x[:110] for x in probs(BASE, pol=tl.policy())][:2])
neo = [k for k in BASE["components"] if k.startswith("neo4j:")]
P("  neo4j keys in BASE:", neo)

P("\n== U7a-4. Raw control characters in messages (key from the lock; key from an SBOM purl) ==")
d = copy.deepcopy(BASE); d["components"]["deb:x\x1b[2J@1"] = copy.deepcopy(BASE["components"][deb])
out = probs(d); raw = [x for x in out if CTRL.search(x)]
P(f"  lock key 'deb:x<ESC>[2J@1': problems={len(out)} raw-control lines={len(raw)} {[repr(x)[:120] for x in raw[:3]]}")
d = copy.deepcopy(BASE); d["components"]["apk:x\x9b2J@1-r0"] = copy.deepcopy(BASE["components"][deb]); d["components"]["apk:x\x9b2J@1-r0"]["kind"] = "apk"
out = probs(d); raw = [x for x in out if CTRL.search(x)]
P(f"  lock key 'apk:x<CSI>2J@1-r0': problems={len(out)} raw-control lines={len(raw)} {[repr(x)[:120] for x in raw[:3]]}")
docs = copy.deepcopy(DOCS)
docs["postgres"] = ss.spdx_doc("postgres", [{"purl": "pkg:deb/debian/evil@1?upstream=ev%1b%5b2Jil%401", "declared": "GPL-2.0-only"},
                                            {"purl": "pkg:deb/debian/ok%1b%5d0%3bT%07@1", "declared": "GPL-2.0-only"},
                                            {"purl": "pkg:pypi/x%1b@1", "declared": "GPL-2.0-only"}])
out = probs(BASE, docs=docs); raw = [x for x in out if CTRL.search(x)]
P(f"  SBOM purls with %1b in upstream/name/version: problems={len(out)} raw-control lines={len(raw)}")
for x in raw[:4]: P("     ", repr(x)[:170])

P("\n== U7a-5. lock_needs: can a needs=True row map to no key and no problem? ==")
odd = ["pkg:deb/debian/x@1", "pkg:deb/debian/x@1:2.0-1", "pkg:deb/debian/x@1%3A2.0-1", "pkg:deb/debian/x@1?upstream=", "pkg:deb/debian/x@1?upstream=%40",
       "pkg:deb/debian/x@1?upstream=src%40", "pkg:deb/debian/x@1?upstream=src@2", "pkg:deb/debian/x@1.pgdg12", "pkg:deb/ubuntu/x@1",
       "pkg:deb/x@1", "pkg:DEB/debian/x@1", "pkg:apk/alpine/x@1-r0", "pkg:apk/alpine/x@1-r0?upstream=", "pkg:apk/wolfi/x@1-r0",
       "pkg:maven/org.neo4j/neo4j-x@9.9", "pkg:maven/org.neo4jx/y@1", "pkg:maven/jrt-fs/jrt-fs@1", "pkg:generic/oracle/openjdk@21",
       "pkg:generic/oracle/openjdk@21-LTS", "pkg:generic/x/y@1", "pkg:pypi/A_B@1", "pkg:npm/x@1", "pkg:golang/x/y@1", "pkg:cargo/x@1",
       "pkg:gem/x@1", "pkg:github/x/y@1", "pkg:oci/x@sha256%3Aab", "pkg:deb/debian/x", "pkg:deb/debian/@1", "not-a-purl", "", None]
for purl in odd:
    pk = [{"purl": purl, "declared": "GPL-2.0-only"}] if purl is not None else [{"purl": None, "declared": "GPL-2.0-only"}]
    try:
        dd = ss.spdx_doc("postgres", pk)
    except Exception as x:
        P(f"  {purl!r:46s} spdx_doc RAISED {type(x).__name__}"); continue
    rows = [r for r in sc.classify_document("postgres", dd, [], []) if r["needs"]]
    needs, mapping = sc.lock_needs({"always": [], "exempt": []}, {"postgres": dd})
    keys = sorted(needs)
    valid = [k for k in keys if k.split(":")[0] in sc.LOCK_KEY_RES and sc.LOCK_KEY_RES[k.split(":")[0]].fullmatch(k)]
    P(f"  {purl!r:46s} needs_rows={len(rows)} keys={keys} valid={bool(valid) if keys else '-'} problems={len(mapping)}")

P("\n== U7a-6. ReDoS / cost on the new regexes and functions ==")
def t(label, f):
    s = time.perf_counter()
    try:
        r = f(); out = str(r)[:40]
    except BaseException as e:
        out = "RAISED " + type(e).__name__
    P(f"  {label:58s} {time.perf_counter()-s:7.3f}s {out}")
N = 1000000
for kind, rx in sc.LOCK_KEY_RES.items():
    for lab, s in (("digits+!", f"{kind}:a@" + "1" * N + "!"), ("a-a-+@", f"{kind}:" + "a-" * (N // 2) + "@"),
                   ("1.1.+!", f"{kind}:neo4j@" + "1." * (N // 2) + "!"), ("-r-r", f"{kind}:a@1" + "-r" * (N // 2) + "x"),
                   ("jdk 1.", f"{kind}:jdk-" + "1." * (N // 2) + "+")):
        t(f"LOCK_KEY_RES[{kind}] {lab}", lambda rx=rx, s=s: bool(rx.fullmatch(s)))
t("LOCK_FILE_NAME_RE 1MB", lambda: bool(sc.LOCK_FILE_NAME_RE.fullmatch("a" * N)))
t("HEX_RE 1MB + g", lambda: bool(sc.HEX_RE.fullmatch("a" * N + "g")))
t("SNAPSHOT_PATH_RE 1MB", lambda: bool(sc.SNAPSHOT_PATH_RE.fullmatch("/file/" + "a" * N)))
t("NEO4J_FROM_RE 1MB", lambda: bool(sc.NEO4J_FROM_RE.fullmatch("second fetch: security " + "1" * N)))
t("_url_problems 1MB url", lambda: len(sc._url_problems("w", "https://" + "a" * N, {"x"})))
t("_url_problems 1MB of @", lambda: len(sc._url_problems("w", "https://" + "@" * N, {"x"})))
t("json.loads deep [ * 100000 via lock_problems", lambda: sc.lock_problems("[" * 100000 + "]" * 100000, POL, DOCS, "amd64"))
big = copy.deepcopy(BASE)
for i in range(20000):
    big["components"][f"deb:p{i}@1.0-1"] = copy.deepcopy(BASE["components"][deb])
t("lock_problems 20000 entries", lambda: len(probs(big)))
t("lock_needs on the six fixtures", lambda: len(sc.lock_needs(tl.policy(), tl.fixture_docs())[0]))
t("sample_keys on a lock with a non-int size", lambda: sc.sample_keys(with_file(KEY, size="5"), "amd64"))

P("\n== U7a-7. Fixture coverage: lock_needs on the six real fixtures ==")
needs, mapping = sc.lock_needs(tl.policy(), tl.fixture_docs())
by = {}
for k, v in needs.items(): by[v["kind"]] = by.get(v["kind"], 0) + 1
P(f"  keys={len(needs)} by kind={dict(sorted(by.items()))} mapping problems={mapping}")
invalid = [k for k in needs if not sc.LOCK_KEY_RES[k.split(':')[0]].fullmatch(k)]
P(f"  needed keys that no valid lock entry could carry (fail closed, but would block): {invalid}")
rows_needs = sum(1 for img, d in tl.fixture_docs().items() for r in sc.classify_document(img, d, tl.policy()['always'], tl.policy()['exempt']) if r['needs'])
P(f"  needs rows={rows_needs}, packages mapped={sum(len(v['packages']) for v in needs.values())}, problems={len(mapping)}")

P("\n== U7a-8. lock-check CLI ==")
import subprocess, tempfile, os
W = tempfile.mkdtemp()
def w(n, s):
    p = os.path.join(W, n); open(p, "w", encoding="utf-8", newline="").write(s); return p
lockp = w("lock.json", tl.canon(BASE)); polp = w("pol.json", json.dumps(POL))
sb = [f"{k}={w(k + '.json', json.dumps(v))}" for k, v in DOCS.items()]
def cli(*a):
    r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "lock-check", *a], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()[:160]
args = []
for s in sb: args += ["--sbom", s]
P("  good:", cli("--lock", lockp, "--policy", polp, "--arch", "amd64", *args))
P("  arch x86:", cli("--lock", lockp, "--policy", polp, "--arch", "x86", *args))
P("  --sbom '-x=/etc/passwd':", cli("--lock", lockp, "--policy", polp, "--arch", "amd64", "--sbom", "-x=/etc/passwd"))
P("  --sbom 'ke app=...':", cli("--lock", lockp, "--policy", polp, "--arch", "amd64", "--sbom", "ke app=" + lockp))
P("  missing lock file:", cli("--lock", os.path.join(W, "nope"), "--policy", polp, "--arch", "amd64", *args))
P("  deep JSON lock:", cli("--lock", w("deep.json", "[" * 100000 + "]" * 100000), "--policy", polp, "--arch", "amd64", *args))
P("  CRLF lock (not canonical):", cli("--lock", w("crlf.json", tl.canon(BASE).replace("\n", "\r\n")), "--policy", polp, "--arch", "amd64", *args))
