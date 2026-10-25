"""security U6 gate probes (platform-sbom). python -I, gates image."""
import copy, importlib.util, inspect, json, random, re, sys, time
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
new = load("sc_u6", "/work/scripts/sbom_check.py")
u5 = load("sc_u5c", "/scratch/u5c_sbom_check.py")
head0 = load("sc_head", "/scratch/head_sbom_check.py")
sys.path.insert(0, "/work")
from tests import sbom_support as ss
import tests.test_sbom_obligations as tob
POL = json.load(open("/work/docker/source-policy.json"))
ALWAYS, EXEMPT = POL["always"], POL["exempt"]
JNA = "pkg:maven/com.sun.jna/jna@5.15.0"
P = print
def doc(purls):
    pk = [{"SPDXID": "SPDXRef-root", "name": "root"}] + [
        {"SPDXID": f"SPDXRef-{i}", "name": f"p{i}", "licenseDeclared": "GPL-2.0-only",
         "externalRefs": [{"referenceType": "purl", "referenceLocator": u}]} for i, u in enumerate(purls)]
    return {"packages": pk, "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-root"}]}

P("== U6-1. exempt_matches: crafted SBOM purls against the real jna entry ==")
cases = {
 "exact": JNA, "qualifiers": JNA + "?type=jar&classifier=x", "subpath": JNA + "#com/sun/jna", "qual+subpath": JNA + "?a=b#c",
 "version prefix 5.15": "pkg:maven/com.sun.jna/jna@5.15", "version suffix 5.15.0.1": JNA + ".1", "version 5.15.0-SNAPSHOT": JNA + "-SNAPSHOT",
 "percent-encoded dot 5.15%2E0": "pkg:maven/com.sun.jna/jna@5.15%2E0", "percent-encoded name j%6Ea": "pkg:maven/com.sun.jna/j%6Ea@5.15.0",
 "upper-case namespace": "pkg:maven/com.sun.JNA/jna@5.15.0", "upper-case type": "pkg:MAVEN/com.sun.jna/jna@5.15.0",
 "@ in namespace": "pkg:maven/com.sun@jna/jna@5.15.0", "extra namespace segment": "pkg:maven/x/com.sun.jna/jna@5.15.0",
 "other type pkg:generic": "pkg:generic/com.sun.jna/jna@5.15.0", "trailing space": JNA + " ", "trailing newline": JNA + "\n",
 "leading space": " " + JNA, "no namespace": "pkg:maven/jna@5.15.0", "? in version position": "pkg:maven/com.sun.jna/jna?@5.15.0",
 "jna-platform": "pkg:maven/net.java.dev.jna/jna-platform@5.15.0", "NUL inside": "pkg:maven/com.sun.jna/jna@5.15.0\x00x",
}
for k, u in cases.items():
    f, pr = new.exempt_matches("ke-neo4j", doc([u]), EXEMPT[:1])
    P(f"  {k:32s} cleared={bool(f)!s:5} problems={len(pr)}")
f, pr = new.exempt_matches("ke-neo4j", doc([JNA, JNA + "?type=jar", "pkg:maven/x/y@1"]), EXEMPT[:1])
P(f"  two packages with jna's purl (+1 other): cleared={f} problems={pr}")
d2 = doc([JNA, "pkg:maven/evil/gpl@1"]); d2["packages"][2]["SPDXID"] = "SPDXRef-0"
rows = new.classify_document("ke-neo4j", d2, ALWAYS, EXEMPT)
P("  duplicate SPDXID (a GPL package reusing jna's SPDXID):", [(r["purl"], r["needs"], r["exempt"]) for r in rows],
  "| validate():", [x for x in new.validate(dict(d2, spdxVersion="SPDX-2.3")) if "unique" in x])
f, pr = new.exempt_matches("valkey", doc([JNA]), EXEMPT)
P(f"  other image (valkey) with jna's purl: cleared={f} problems={pr}")
bad_entries = [{"image": "ke-neo4j", "package": p} for p in ("pkg:maven/com.sun.jna/jna", JNA + "?type=jar", JNA + "#x", "", None, 5,
               "pkg:maven/com.sun.jna/jna@", "pkg:maven/com.sun.jna/jna@5.15.0\x1b[2J")]
for e in bad_entries:
    f, pr = new.exempt_matches("ke-neo4j", doc([JNA, JNA + "?type=jar"]), [e])
    P(f"  entry package={e['package']!r:44} cleared={f} problems={[x[:80] for x in pr]}")
for e in ([None], ["x"], [{"image": None}], [{"package": JNA}]):
    try:
        f, pr = new.exempt_matches("ke-neo4j", doc([JNA]), e); P(f"  malformed entry list {e!r:36} cleared={f} problems={pr}")
    except Exception as x:
        P(f"  malformed entry list {e!r:36} RAISED {type(x).__name__}")
try:
    P("  exempt=None:", new.classify_document("ke-neo4j", doc([JNA]), ALWAYS, None))
except Exception as x:
    P(f"  exempt=None RAISED {type(x).__name__} (fails closed, nothing cleared)")

P("\n== U6-2. Schema oracle (tests.test_sbom_obligations.u6_policy_problems) on further mutations ==")
good = tob.u6_good_policy()
P("  committed policy problems:", tob.u6_policy_problems(POL), "| oracle good:", tob.u6_policy_problems(good))
def ch(f):
    d = copy.deepcopy(good); f(d); return d
FW = "".join(chr(0xff10 + int(c)) if c.isdigit() else c for c in "2026-10-25")
muts = {
 "reviewed fullwidth digits": ch(lambda d: d["exempt"][0].update(reviewed="security " + FW)),
 "reviewed Arabic-Indic digits": ch(lambda d: d["exempt"][0].update(reviewed="security " + "".join(chr(0x660 + int(c)) if c.isdigit() else c for c in "2026-10-25"))),
 "reviewed double space": ch(lambda d: d["exempt"][0].update(reviewed="security  2026-10-25")),
 "reviewed trailing newline": ch(lambda d: d["exempt"][0].update(reviewed="security 2026-10-25\n")),
 "reviewed Security (capital)": ch(lambda d: d["exempt"][0].update(reviewed="Security 2026-10-25")),
 "reviewed future 2099-01-01": ch(lambda d: d["exempt"][0].update(reviewed="security 2099-01-01")),
 "reviewed 2026-02-30": ch(lambda d: d["exempt"][0].update(reviewed="security 2026-02-30")),
 "reviewed list": ch(lambda d: d["exempt"][0].update(reviewed=["security 2026-10-25"])),
 "host trailing dot": ch(lambda d: d["hosts"].append("github.com.")),
 "host trailing newline": ch(lambda d: d["hosts"].append("github.com\n")),
 "host userinfo": ch(lambda d: d["hosts"].append("user@github.com")),
 "host IPv6 literal": ch(lambda d: d["hosts"].append("[::1]")),
 "host decimal IP 2130706433": ch(lambda d: d["hosts"].append("2130706433")),
 "host punycode xn--": ch(lambda d: d["hosts"].append("xn--80ak6aa92e.com")),
 "host extra subdomain evil.github.com": ch(lambda d: d["hosts"].append("evil.github.com")),
 "host non-string": ch(lambda d: d["hosts"].append(5)),
 "hosts not a list (str)": ch(lambda d: d.update(hosts="github.com")),
 "package trailing space": ch(lambda d: d["exempt"][0].update(package=JNA + " ")),
 "package with @ in namespace": ch(lambda d: d["exempt"][0].update(package="pkg:maven/com.sun@jna/jna@5.15.0")),
 "package upper-case": ch(lambda d: d["exempt"][0].update(package="pkg:maven/com.sun.JNA/jna@5.15.0")),
 "image wrong case KE-neo4j": ch(lambda d: d["exempt"][0].update(image="KE-neo4j")),
 "duplicate by case-variant package": ch(lambda d: d["exempt"].append(dict(d["exempt"][0], package="pkg:maven/com.sun.jna/jna@5.15.0?x=1"))),
 "exempt is a dict": ch(lambda d: d.update(exempt={"a": 1})),
 "entry is a list": ch(lambda d: d["exempt"].append(["x"])),
 "reason sha256 upper-hex": ch(lambda d: d["exempt"][0].update(reason="Apache-2.0 elected; sha256 " + "A" * 64)),
 "reason 'unelected'": ch(lambda d: d["exempt"][0].update(reason="sha256 " + "a" * 64 + " unelected")),
}
for k, d in muts.items():
    try:
        pr = tob.u6_policy_problems(d); P(f"  {k:40s} rejected={bool(pr)!s:5} {pr[:1]}"[:200])
    except Exception as x:
        P(f"  {k:40s} RAISED {type(x).__name__}: {x}"[:200])
P("  committed hosts == U6_HOSTS:", set(POL["hosts"]) == tob.U6_HOSTS, "| len", len(POL["hosts"]), "| keys", sorted(POL))

P("\n== U6-3. Segment rule: nothing weaker than U5 (d8ffa2d), ReDoS, real rows ==")
H = "LicenseRef-" + "0123456789abcdef" * 4
alpha = ["MIT", "Apache-2.0", "GPL-2.0-only", "LGPL-2.1+", H, H + "+", "NONE", "none", "NOASSERTION", "NoAssertion", "AND", "OR",
         "WITH", "and", "or", "with", "(", ")", "Classpath-exception-2.0", "DocumentRef-x:", "DocumentRef-NONE:", "LicenseRef-",
         "licenseref-", "affero", "Public-Domain", ",", ";", ":", ".", "+", "-", "x", "2.0", "NONEX", "NOASSERTIONS", "txt"]
rnd = random.Random(20261025)
reg, lost, c = [], [], {"both": 0, "u6_only": 0, "u5_only": 0, "neither": 0}
for _ in range(150000):
    e = rnd.choice([" ", " ", "", "-", ".", "+", ":"]).join(rnd.choice(alpha) for _ in range(rnd.randint(1, 9)))
    n, ni = new.needs_source(e); o, oi = u5.needs_source(e)
    if o and not n: reg.append(e)
    if (o or oi["unparsed"] or oi["unidentified"]) and not (n or ni["unparsed"] or ni["unidentified"]): lost.append(e)
    c["both" if (o and n) else "u6_only" if n else "u5_only" if o else "neither"] += 1
P(f"  150000 expressions: {c}; needs regressions: {len(reg)} {reg[:3]}; lost listings: {len(lost)} {lost[:3]}")
for e in ("NOASSERTION.NONE", "NOASSERTION-2.0", "MIT-NOASSERTION", "MIT AND NONE.NONE", "none-mit", "DocumentRef-x:NONE-1",
          "LicenseRef-NONE", "licenseref-none", "LicenseRef-NOASSERTION", "DocumentRef-x:LicenseRef-NONE", "NOASSERTIONS", "NONEX-1",
          "NOASSERTIONS apply", "see NONE.txt here", "DocumentRef-NONE:MIT", "MIT WITH x-NONE", "LicenseRefX-NONE", "Licenseref-.NONE"):
    n, i = new.needs_source(e); P(f"  {e:34s} needs={n!s:5} unparsed={bool(i['unparsed'])!s:5} unident={bool(i['unidentified'])}")
def t(label, f):
    s = time.perf_counter(); r = f(); P(f"  {label:50s} {time.perf_counter()-s:7.3f}s {str(r)[:30]}")
t("_unknown_id 1MB of '.-'", lambda: new._unknown_id(".-" * 500000 + "x"))
t("_unknown_id 1MB 'a.' segments", lambda: new._unknown_id("a." * 500000 + "a"))
t("_unknown_id 1MB 'a-' + NONE", lambda: new._unknown_id("a-" * 500000 + "NONE"))
t("needs_source 200k 'x-y AND'", lambda: new.needs_source("x-y AND " * 200000 + "x"))
t("needs_source 1MB junk 'a.b, '", lambda: new.needs_source("a.b, " * 200000))
t("exempt_matches 100k packages x 2 entries", lambda: len(new.exempt_matches("ke-neo4j", doc([f"pkg:maven/a/b@{i}" for i in range(100000)] + [JNA]), EXEMPT)[0]))
P("\n  real rows: U6 classify_document(image, doc, always, exempt) vs U5 classify_document(image, doc, always)")
for image in ss.U3_IMAGES:
    name = "ke-neo4j" if image == "neo4j" else image
    d = ss.spdx_doc(name, ss.u3_rows(image))
    a = new.classify_document(name, d, ALWAYS, EXEMPT); b = u5.classify_document(name, d, ALWAYS)
    diff = []
    for x, y in zip(a, b):
        xx = dict(x); ex = xx.pop("exempt")
        if xx != y or ex: diff.append((x["purl"], y["needs"], x["needs"], ex, x["always"], x["unparsed"]))
    P(f"  {name:10s} rows={len(a)} needs u6={sum(r['needs'] for r in a)} (u5 {sum(r['needs'] for r in b)}) changed={diff}")
P("\n== U6-4. unlicensed_report untouched vs U4b HEAD c300d88 and vs U5 ==")
P("  sources identical to c300d88:", all(inspect.getsource(getattr(head0, f)) == inspect.getsource(getattr(new, f))
      for f in ("unlicensed_report", "_missing", "_hash_only", "report_lines", "_clean", "_packages", "_roots", "_purl")))
for image in ss.U3_IMAGES:
    d = ss.spdx_doc(image, ss.u3_rows(image))
    P(f"  {image:10s} count={new.unlicensed_report(d)['count']:3d} equal-to-c300d88={head0.unlicensed_report(d) == new.unlicensed_report(d)}")
