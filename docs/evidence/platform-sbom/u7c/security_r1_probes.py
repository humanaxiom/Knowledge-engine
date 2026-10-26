"""security U7c rework r1 probes (platform-sbom). python -I, gates image; fake network only."""
import copy, datetime, hashlib, importlib.util, json, sys, time
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
R = load("srv7cr1", "/work/scripts/sources_resolve.py")
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
from tests.test_sbom_bundle import load_sbom_check
sc = load_sbom_check()
P = print
NL = chr(10)
AK = "apk:readline@8.2.13-r1"
BASE = tl.good_lock(tl.SMALL_KEYS); POL = tl.policy(); DOCS = tl.small_docs()
def probs(lock):
    return sc.lock_problems(tl.canon(lock), POL, DOCS, "amd64", today=datetime.date(2026, 10, 25))
base_p = probs(BASE)
E = BASE["components"][AK]; C = E["commit"]
P("== U7c-r1-1. Item 9: the GitLab API raw form in lock-check ==")
P("  baseline problems:", base_p)
P("  baseline APKBUILD url:", E["files"][0]["url"])
API = "https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/"
GOOD = API + "main%2Freadline%2FAPKBUILD/raw?ref=" + C
P("  baseline equals the canonical form:", E["files"][0]["url"] == GOOD)
def rep(label, url, i=0, name=None):
    d = copy.deepcopy(BASE); f = d["components"][AK]["files"][i]; f["url"] = url
    if name:
        f["name"] = name
    pr = [x for x in probs(d) if x not in base_p]
    P(f"  {label:58s} accepted={not pr!s:5} {[x[:120] for x in pr[:1]]}")
rows = {
 "project alpine%2Faports%2F..": GOOD.replace("alpine%2Faports/", "alpine%2Faports%2F../"),
 "project alpine%2faports (lower hex)": GOOD.replace("alpine%2Faports", "alpine%2faports"),
 "project alpine%2FAports": GOOD.replace("alpine%2Faports", "alpine%2FAports"),
 "project numeric id 3": GOOD.replace("alpine%2Faports", "3"),
 "project alpine/aports (unencoded)": GOOD.replace("alpine%2Faports", "alpine/aports"),
 "ref twice": GOOD + "&ref=" + "f" * 40,
 "ref=HEAD": GOOD.replace("ref=" + C, "ref=HEAD"),
 "ref=<c>%00": GOOD + "%00",
 "ref upper-case commit": GOOD.replace(C, C.upper()),
 "ref another commit": GOOD.replace("ref=" + C, "ref=" + "f" * 40),
 "no query": GOOD.split("?")[0],
 "query x=1&ref=<c>": GOOD.replace("?ref=", "?x=1&ref="),
 "query ref=<c>&x=1": GOOD + "&x=1",
 "fragment": GOOD + "#x",
 "P %252F": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%252Freadline%252FAPKBUILD"),
 "P %2F..%2F": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2Freadline%2F..%2Freadline%2FAPKBUILD"),
 "P .%2F": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2Freadline%2F.%2FAPKBUILD"),
 "P %2e%2e segment": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2Freadline%2F%2e%2e%2FAPKBUILD"),
 "P lower-case %2f": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2freadline%2fAPKBUILD"),
 "P unicode %C3%A9": GOOD.replace("APKBUILD/raw", "APKBUIL%C3%A9/raw"),
 "P invalid UTF-8 %FF": GOOD.replace("APKBUILD/raw", "APKBUILD%FF/raw"),
 "P backslash %5C": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2Freadline%5CAPKBUILD"),
 "P subdirectory APKBUILD": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2Freadline%2Fsub%2FAPKBUILD"),
 "P other origin": GOOD.replace("readline", "bash"),
 "P other repo": GOOD.replace("main%2F", "community%2F"),
 "P empty segment %2F%2F": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2Freadline%2F%2FAPKBUILD"),
 "P raw / inside (two path segments)": GOOD.replace("main%2Freadline%2FAPKBUILD", "main%2Freadline/APKBUILD"),
 "metadata form (no /raw)": GOOD.replace("/raw?", "?"),
 "/raw/raw": GOOD.replace("/raw?", "/raw/raw?"),
 "old /-/raw/ form": f"https://gitlab.alpinelinux.org/alpine/aports/-/raw/{C}/main/readline/APKBUILD",
 "userinfo": GOOD.replace("https://", "https://u@"),
 "port 443": GOOD.replace("alpinelinux.org/", "alpinelinux.org:443/"),
 "upper-case host": GOOD.replace("gitlab.alpinelinux.org", "GITLAB.alpinelinux.org"),
 "api/v3": GOOD.replace("/api/v4/", "/api/v3/"),
 "HTTPS upper scheme": GOOD.replace("https://", "HTTPS://"),
}
for k, u in rows.items():
    rep(k, u)
f1 = E["files"][1]
P("  second apk file url:", f1["url"][:120])
d = copy.deepcopy(BASE); g = d["components"][AK]["files"]
g.append({"name": "a.patch", "url": API + f"main%2Freadline%2Fsub%2Fa.patch/raw?ref={C}", "sha256": "1" * 64, "size": 1,
          "upstream": {"alg": "sha256", "value": "1" * 64, "from": f"gitlab files API content_sha256 at {C}"}})
P(f"  extra sha256 file in a subdirectory via the API form: accepted={not [x for x in probs(d) if x not in base_p]}")
MV = "maven:javax.xml.bind:jaxb-api@2.2.12"
d = copy.deepcopy(BASE); d["components"][MV]["files"][0]["url"] = GOOD
P(f"  the API form on a maven entry: problems={[x[:90] for x in probs(d) if x not in base_p][:2]}")
d = copy.deepcopy(BASE); d["components"]["pypi:psycopg@3.3.6"]["files"][0]["url"] += "?ref=" + C
P(f"  a query on a pypi url: problems={[x[:90] for x in probs(d) if x not in base_p][:1]}")

P("\n== U7c-r1-2. The 307 bot challenge and the hop rules (fake network) ==")
calls = []
class Net:
    def __init__(self, routes): self.routes = routes
    def __call__(self, url, timeout):
        calls.append(url); r = self.routes.get(url)
        return R.Response(404, {}, b"") if r is None else R.Response(*r)
ALLOW = set(POL["hosts"])
def tf(label, start, routes):
    calls.clear(); R.OPENER = Net(routes)
    try:
        r = R.fetch(start, ALLOW); list(r.body); out = f"OK {r.status}"
    except R.ResolveError as e:
        out = f"refused: {str(e)[:120]}"
    P(f"  {label:44s} requests={len(calls)} -> {out}")
rel_chal = "?__goaway_challenge=cookie&__goaway_id=abc"
tf("307 relative ?challenge, then 418", GOOD, {GOOD: (307, {"Location": rel_chal}, b""), GOOD.split("?")[0] + rel_chal: (418, {}, b"")})
abs_chal = "https://gitlab.alpinelinux.org/alpine/aports/-/raw/x?__goaway_challenge=cookie"
tf("307 absolute plain path ?challenge, then 418", GOOD, {GOOD: (307, {"Location": abs_chal}, b""), abs_chal: (418, {}, b"")})
tf("307 without Location", GOOD, {GOOD: (307, {}, b"")})
tf("307 to another project path (no %)", GOOD, {GOOD: (307, {"Location": "/api/v4/projects/1/repository/files/x/raw?ref=1"}, b""),
                                                 "https://gitlab.alpinelinux.org/api/v4/projects/1/repository/files/x/raw?ref=1": (200, {}, b"x")})
tf("307 to another host", GOOD, {GOOD: (307, {"Location": "https://evil.example/x"}, b"")})
tf("first request 200 (no hop)", GOOD, {GOOD: (200, {}, b"apkbuild")})

P("\n== U7c-r1-3. parse_dsc separators, duplicates, size ==")
def show(label, fn):
    try:
        P(f"  {label:58s} -> {str(fn())[:110]}")
    except R.ResolveError as e:
        P(f"  {label:58s} -> ResolveError: {str(e)[:100]}")
    except Exception as e:
        P(f"  {label:58s} -> RAISED {type(e).__name__}: {str(e)[:80]}")
base = "Source: x" + NL + "Version: 1-1" + NL + "Files:" + NL + " " + "b" * 32 + " 1 a"
signed = lambda body: "-----BEGIN PGP SIGNED MESSAGE-----" + NL + "Hash: SHA256" + NL + NL + body + NL + "-----BEGIN PGP SIGNATURE-----" + NL + "x" + NL + "-----END PGP SIGNATURE-----" + NL
show("baseline", lambda: sorted(R.parse_dsc(base)))
for label, ch in (("U+0085 in a value", chr(0x85)), ("U+2028 in a value", chr(0x2028)), ("U+2029 in a value", chr(0x2029)), ("VT in a value", chr(11)),
                  ("FF in a value", chr(12)), ("0x1c in a value", chr(0x1c)), ("DEL in a value", chr(0x7f)), ("NUL in a value", chr(0)), ("ESC in a value", chr(27)),
                  ("lone CR in a value", chr(13)), ("TAB in a value (allowed)", chr(9))):
    show(label, lambda ch=ch: sorted(R.parse_dsc(base.replace("Source: x", "Homepage: a" + ch + "b" + NL + "Source: x"))))
show("U+2028 in a field name", lambda: R.parse_dsc("Sou" + chr(0x2028) + "rce: x" + NL + base))
show("U+0085 in a field name", lambda: R.parse_dsc("Ho" + chr(0x85) + "me: x" + NL + base))
show("U+2028 in a continuation line", lambda: R.parse_dsc(base + NL + " c" + chr(0x2028) + "d"))
show("U+2028 in the armour (Hash header)", lambda: R.parse_dsc(signed(base).replace("Hash: SHA256", "Hash: SHA" + chr(0x2028) + "256")))
show("U+2028 in the signature block", lambda: R.parse_dsc(signed(base).replace(NL + "x" + NL, NL + "x" + chr(0x2028) + NL)))
show("U+2028 in an ignored non-field line", lambda: R.parse_dsc("junk line " + chr(0x2028) + NL + base))
show("U+2028 after the END PGP SIGNATURE", lambda: sorted(R.parse_dsc(signed(base) + "tail" + chr(0x2028))))
show("duplicate Files", lambda: R.parse_dsc(base + NL + "Files:" + NL + " " + "b" * 32 + " 1 b"))
show("duplicate case-blind (files)", lambda: R.parse_dsc(base + NL + "files: x"))
show("duplicate Source after a blank line (two paragraphs)", lambda: R.parse_dsc(base + NL + NL + "Source: evil"))
show("CRLF file", lambda: sorted(R.parse_dsc(base.replace(NL, chr(13) + NL))))
show("U+FEFF BOM first", lambda: sorted(R.parse_dsc(chr(0xfeff) + base)))
show("U+200B zero-width space in a value", lambda: R.parse_dsc(base.replace("Source: x", "Source: x" + chr(0x200b))).get("Source"))
t0 = time.perf_counter(); R.parse_dsc("Description: " + "a" * 1000000 + NL + base); P(f"  1 MB single field: {time.perf_counter() - t0:.3f}s")
t0 = time.perf_counter(); R.parse_dsc("Description: a" + NL + (" b" + NL) * 400000 + base); P(f"  400k continuation lines: {time.perf_counter() - t0:.3f}s")

P("\n== U7c-r1-4. Listing truncation rule (resolve_apk with a crafted 100-entry listing) ==")
blobs = [{"path": "main/readline/APKBUILD", "name": "APKBUILD", "type": "blob", "mode": "100644"}] + \
        [{"path": f"main/readline/f{i}", "name": f"f{i}", "type": "blob", "mode": "100644"} for i in range(99)]
route = {"origin": "readline", "ver": "8.2.13-r1", "commit": C, "branch": "v3.23"}
tree = lambda repo: R.APORTS_API + "/tree?path=" + R.quote(f"{repo}/readline", safe="") + f"&ref={C}&recursive=true&per_page=100"
for label, hdr in (("100 entries, no x-next-page", {}), ("100 entries, x-next-page empty", {"x-next-page": ""}),
                   ("100 entries, x-next-page 2", {"x-next-page": "2"}), ("100 entries, x-next-page ' ' (space)", {"x-next-page": " "})):
    calls.clear()
    R.OPENER = Net({tree("main"): (200, hdr, json.dumps(blobs).encode()), tree("community"): (404, {}, b"")})
    try:
        R.resolve_apk(AK, route, "amd64", ALLOW); out = "resolved"
    except R.ResolveError as e:
        out = f"ResolveError: {str(e)[:90]}"
    P(f"  {label:40s} -> {out} (requests {len(calls)})")
P("  tree url path query encodes the repo/origin:", tree("main").split("?", 1)[1][:40])
