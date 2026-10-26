"""security U5 rework r3 probes (platform-sbom). python -I, gates image."""
import importlib.util, inspect, json, random, re, sys, time
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
new = load("sc_r3", "/work/scripts/sbom_check.py")
r2 = load("sc_r2", "/work/docs/evidence/platform-sbom/u5/r2-target-sbom_check.py")
head = load("sc_head", "/scratch/head_sbom_check.py")
sys.path.insert(0, "/work")
from tests import sbom_support as ss
HX = "0123456789abcdef" * 4
H = "LicenseRef-" + HX
P = print
def show(label, expr):
    n, i = new.needs_source(expr); o, oi = r2.needs_source(expr)
    P(f"  {label:52s} needs={n!s:5} unparsed={bool(i['unparsed'])!s:5} unident={bool(i['unidentified'])!s:5} (r2 needs={o!s:5} unident={bool(oi['unidentified'])})")
P("== R3-A. R2-L1, review R2-B1/B2 inputs, pinned near-misses, new tricks ==")
rows = [
 ("R2-L1 <hash>+", H + "+"), ("R2-L1 MIT WITH <hash>+", "MIT WITH " + H + "+"), ("R2-L1 <hash>.x", H + ".x"),
 ("R2-L1 x<hash>", "x" + H), ("R2-L1 MIT AND NOASSERTION.", "MIT AND NOASSERTION."),
 ("R2-L1 MIT AND NOASSERTION+", "MIT AND NOASSERTION+"), ("R2-L1 MIT AND -NONE", "MIT AND -NONE"),
 ("R2-L1 65-hex stays ordinary", H + "0"), ("R2-L1 Public Domain <65 hex> (junk)", "Public Domain " + H + "0"),
 ("B2 MIT:NOASSERTION", "MIT:NOASSERTION"), ("B2 MIT+NOASSERTION", "MIT+NOASSERTION"),
 ("B1 DocumentRef-x:NONE+", "DocumentRef-x:NONE+"), ("I-7 documentref-x:NONE", "documentref-x:NONE"),
 ("I-7 DocumentRef-a:DocumentRef-b:NONE", "DocumentRef-a:DocumentRef-b:NONE"), ("I-7 DocumentRef-:NONE", "DocumentRef-:NONE"),
 ("I-7 MIT AND NONE:", "MIT AND NONE:"),
 ("pinned see NONE.txt here", "see NONE.txt here"), ("pinned NOASSERTIONS apply", "NOASSERTIONS apply"),
 ("pinned MIT-NOASSERTION", "MIT-NOASSERTION"), ("pinned LicenseRef-NONE", "LicenseRef-NONE"),
 ("trick ..NONE..", "MIT AND ..NONE.."), ("trick +-.NOASSERTION.-+", "MIT AND +-.NOASSERTION.-+"),
 ("trick NONE.NONE", "MIT AND NONE.NONE"), ("trick <hash>F (upper hex after)", H + "F"),
 ("trick <hash> with upper hex inside", "LicenseRef-" + HX[:-1] + "A"), ("trick LicenseRef-<hash> split by +", "LicenseRef-" + HX[:30] + "+" + HX[30:]),
 ("trick MIT WITH NONE.", "MIT WITH NONE."), ("trick MIT OR NOASSERTION+ (elected)", "MIT OR NOASSERTION+"),
 ("trick DocumentRef-x:-NONE-", "DocumentRef-x:-NONE-"), ("trick DocumentRef-NONE:MIT", "DocumentRef-NONE:MIT"),
 ("regress MIT OR GPL-2.0-only AND Apache-2.0", "MIT OR GPL-2.0-only AND Apache-2.0"),
 ("regress GPL-2.0+", "GPL-2.0+"), ("regress MIT+ OR Apache-2.0+", "MIT+ OR Apache-2.0+"),
]
for label, e in rows:
    show(label, e)

P("\n== R3-B. Monotonicity r2 -> r3 ==")
alpha = ["MIT", "Apache-2.0", "GPL-2.0-only", "LGPL-2.1+", H, H + "+", H + "0", "x" + H, "NONE", "none", "NOASSERTION",
         "NoAssertion", "AND", "OR", "WITH", "and", "or", "with", "(", ")", "Classpath-exception-2.0", "DocumentRef-x:",
         "LicenseRef-", "affero", "Public-Domain", ",", ";", "/", ":", ".", "+", "-", '"', "_", "#", "LicenseRef-https---x.org",
         "GPLv2orlater", "x", "F", "0"]
rnd = random.Random(20261025)
reg, lost, c = [], [], {"both": 0, "r3_only": 0, "r2_only": 0, "neither": 0}
for _ in range(150000):
    e = rnd.choice([" ", " ", "", "-", "+", ":", "."]).join(rnd.choice(alpha) for _ in range(rnd.randint(1, 9)))
    n, ni = new.needs_source(e); o, oi = r2.needs_source(e)
    if o and not n: reg.append(e)
    if (o or oi["unparsed"] or oi["unidentified"]) and not (n or ni["unparsed"] or ni["unidentified"]): lost.append(e)
    c["both" if (o and n) else "r3_only" if n else "r2_only" if o else "neither"] += 1
P(f"  150000 expressions: {c}; needs regressions: {len(reg)} {reg[:5]}; lost listings: {len(lost)} {lost[:5]}")
uni = sum(1 for _ in range(1))
P("\n== R3-C. Real rows r2 -> r3 ==")
always = json.load(open("/work/docker/source-policy.json"))["always"]
for image in ss.U3_IMAGES:
    name = "ke-neo4j" if image == "neo4j" else image
    d = ss.spdx_doc(name, ss.u3_rows(image))
    a = new.classify_document(name, d, always); b = r2.classify_document(name, d, always)
    P(f"  {name:10s} rows={len(a)} needs r3={sum(r['needs'] for r in a)} (r2 {sum(r['needs'] for r in b)}) changed={sum(x != y for x, y in zip(a, b))}")
P("\n== R3-D. unlicensed_report untouched vs HEAD ==")
P("  sources identical:", all(inspect.getsource(getattr(head, f)) == inspect.getsource(getattr(new, f))
      for f in ("unlicensed_report", "_missing", "_hash_only", "report_lines", "_clean", "_packages", "_roots", "_purl")),
  "| HASH_ID_RE unchanged:", head.HASH_ID_RE.pattern == new.HASH_ID_RE.pattern)
for image in ss.U3_IMAGES:
    d = ss.spdx_doc(image, ss.u3_rows(image))
    a, b = head.unlicensed_report(d), new.unlicensed_report(d)
    P(f"  {image:10s} HEAD={a['count']:3d} r3={b['count']:3d} equal={a == b} lines-equal={head.report_lines(image, a) == new.report_lines(image, b)}")
P("\n== R3-E. ReDoS / cost: HASH_IN_RE, the trim, RUN_SPLIT_RE, _unknown_id, needs_source ==")
def t(label, f):
    s = time.perf_counter()
    try:
        r = f(); out = str(r)[:50]
    except BaseException as e:
        out = "RAISED " + type(e).__name__
    P(f"  {label:56s} {time.perf_counter()-s:7.3f}s {out}")
N = 1000000
t("HASH_IN_RE.search LicenseRef- * 90k", lambda: new.HASH_IN_RE.search("LicenseRef-" * 90000))
t("HASH_IN_RE.search LicenseRef- + hex*1M", lambda: new.HASH_IN_RE.search("LicenseRef-" + "a" * N))
t("HASH_IN_RE.search (LicenseRef- + 63 hex) * 13k", lambda: new.HASH_IN_RE.search(("LicenseRef-" + HX[:63] + "g") * 13000))
t("HASH_IN_RE.search (LicenseRef- + 65 hex) * 13k", lambda: new.HASH_IN_RE.search(("LicenseRef-" + HX + "0") * 13000))
t("_unknown_id .-+ * 333k + NONE + .-+ * 333k", lambda: new._unknown_id(".-+" * 333000 + "NONE" + ".-+" * 333000))
t("_unknown_id DocumentRef-x: + .*1M", lambda: new._unknown_id("DocumentRef-x:" + "." * N))
t("RUN_SPLIT_RE.split +:*500k", lambda: len(new.RUN_SPLIT_RE.split("+:" * 500000)))
t("_unknown_in_text a+ * 500k", lambda: new._unknown_in_text("a+" * 500000))
t("_unknown_in_text (NONE: )*100k", lambda: new._unknown_in_text("x:NONE+ " * 100000))
t("needs_source 1MB .-+ junk", lambda: new.needs_source("MIT AND " + ".-+" * 333000))
t("needs_source width 200k MIT AND NOASSERTION.", lambda: new.needs_source("MIT AND NOASSERTION. " * 100000 + "AND MIT"))
t("needs_source width 100k MIT OR <hash>+", lambda: new.needs_source(("MIT OR " + H + "+ ") * 50000 + "OR MIT"))
t("needs_source depth 100000 NONE+", lambda: new.needs_source("(" * 100000 + "NONE+" + ")" * 100000))
