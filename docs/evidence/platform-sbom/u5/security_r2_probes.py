"""security U5 rework r2 probes (platform-sbom). python -I, gates image."""
import importlib.util, inspect, json, random, re, sys, time
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
new = load("sc_r2", "/work/scripts/sbom_check.py")
r1 = load("sc_r1", "/work/docs/evidence/platform-sbom/u5/r1-target-sbom_check.py")
head = load("sc_head", "/scratch/head_sbom_check.py")
sys.path.insert(0, "/work")
from tests import sbom_support as ss
H = "LicenseRef-" + "0123456789abcdef" * 4
P = print
def show(label, expr):
    n, i = new.needs_source(expr); o, oi = r1.needs_source(expr)
    P(f"  {label:56s} needs={n!s:5} unparsed={bool(i['unparsed'])!s:5} unident={bool(i['unidentified'])!s:5} (r1 needs={o!s:5} unparsed={bool(oi['unparsed'])})")

P("== R2-A. Reviewer R1-B1 inputs and punctuation / DocumentRef / prefix tricks ==")
rows = [
 ("B1 MIT,NOASSERTION", "MIT,NOASSERTION"),
 ("B1 MIT/NOASSERTION", "MIT/NOASSERTION"),
 ("B1 quoted NOASSERTION", '"NOASSERTION"'),
 ("B1 <hash>;", H + ";"),
 ("B1 DocumentRef-x:<hash>", "DocumentRef-x:" + H),
 ("B1 MIT OR DocumentRef-x:NONE", "MIT OR DocumentRef-x:NONE"),
 ("B1 MIT AND DocumentRef-x:noassertion", "MIT AND DocumentRef-x:noassertion"),
 ("doc DocumentRef-x:GPL-2.0-only", "DocumentRef-x:GPL-2.0-only"),
 ("doc DocumentRef-x:LicenseRef-GPL-2.0", "DocumentRef-x:LicenseRef-GPL-2.0"),
 ("doc DocumentRef-x:LicenseRef-https---gnu.org-x", "DocumentRef-x:LicenseRef-https---www.example.org-x"),
 ("doc lower-case prefix documentref-x:NONE", "documentref-x:NONE"),
 ("doc double prefix DocumentRef-a:DocumentRef-b:NONE", "DocumentRef-a:DocumentRef-b:NONE"),
 ("doc double prefix ...:DocumentRef-b:<hash>", "DocumentRef-a:DocumentRef-b:" + H),
 ("doc empty id DocumentRef-:NONE", "DocumentRef-:NONE"),
 ("doc prefix only DocumentRef-x:", "DocumentRef-x:"),
 ("doc MIT WITH DocumentRef-x:<hash>", "MIT WITH DocumentRef-x:" + H),
 ("doc MIT WITH DocumentRef-x:GPL-3.0-only", "MIT WITH DocumentRef-x:GPL-3.0-only"),
 ("doc DocumentRef-gpl:MIT (prefix holds gpl)", "DocumentRef-gpl:MIT"),
 ("idstring punct: MIT AND NOASSERTION.", "MIT AND NOASSERTION."),
 ("idstring punct: MIT AND NOASSERTION+", "MIT AND NOASSERTION+"),
 ("idstring punct: MIT AND -NONE", "MIT AND -NONE"),
 ("idstring punct: MIT AND NONE:", "MIT AND NONE:"),
 ("idstring punct: <hash>+", H + "+"),
 ("idstring punct: <hash>.x", H + ".x"),
 ("idstring punct: <hash>0 (65 hex)", H + "0"),
 ("idstring punct: x<hash>", "x" + H),
 ("idstring punct: MIT WITH <hash>+", "MIT WITH " + H + "+"),
 ("idstring punct: MIT AND LicenseRef-NONE", "MIT AND LicenseRef-NONE"),
 ("non-idstring: MIT AND GPL_2.0 (underscore)", "MIT AND GPL_2.0"),
 ("non-idstring: MIT OR GPL;", "MIT OR GPL;"),
 ("non-idstring: MIT OR Apache-2.0;", "MIT OR Apache-2.0;"),
 ("non-idstring: MIT OR (x=NOASSERTION)", "MIT OR (x=NOASSERTION)"),
 ("non-idstring: MIT OR Apache-2.0 WITH x;", "MIT OR Apache-2.0 WITH x;"),
 ("non-idstring: MIT OR LicenseRef-a@b", "MIT OR LicenseRef-a@b"),
 ("non-idstring: MIT OR <hash>#", "MIT OR " + H + "#"),
 ("non-idstring: NUL MIT\x00OR\x00NONE", "MIT\x00OR\x00NONE"),
 ("non-idstring: tab-only separators MIT\tOR\tGPL-2.0", "MIT\tOR\tGPL-2.0"),
 ("plus: GPL-2.0+", "GPL-2.0+"),
 ("plus: MIT+ OR Apache-2.0+", "MIT+ OR Apache-2.0+"),
 ("plus: MIT++", "MIT++"),
 ("WITH http ref: MIT WITH LicenseRef-https---x", "MIT WITH LicenseRef-https---example.org-x"),
 ("regress MIT OR GPL-2.0-only AND Apache-2.0", "MIT OR GPL-2.0-only AND Apache-2.0"),
 ("regress jna Apache-2.0 AND LGPL-2.1-only", "Apache-2.0 AND LGPL-2.1-only"),
]
for label, expr in rows:
    show(label, expr)

P("\n== R2-B. Monotonicity r1 -> r2 (seeded random expressions, punctuation-rich alphabet) ==")
alpha = ["MIT", "Apache-2.0", "GPL-2.0-only", "LGPL-2.1+", H, H + "+", "NONE", "none", "NOASSERTION", "NoAssertion",
         "AND", "OR", "WITH", "and", "or", "with", "(", ")", "Classpath-exception-2.0", "DocumentRef-x:", "DocumentRef-a:",
         "LicenseRef-", "LicenseRef-GNU-General-Public-License", "affero", "Public-Domain", ",", ";", "/", ":", ".", "+",
         '"', "=", "_", "#", "@", "LicenseRef-https---x.org", "GPLv2orlater", "x", "-"]
rnd = random.Random(20261025)
regress, counts = [], {"both": 0, "r2_only": 0, "r1_only": 0, "neither": 0}
unparsed_lost = []
for _ in range(100000):
    parts = [rnd.choice(alpha) for _ in range(rnd.randint(1, 9))]
    e = rnd.choice([" ", " ", "", "-", "\t"]).join(parts)
    n, ni = new.needs_source(e); o, oi = r1.needs_source(e)
    if o and not n:
        regress.append(e)
    if (oi["unparsed"] or oi["unidentified"]) and not (n or ni["unparsed"] or ni["unidentified"]):
        unparsed_lost.append(e)
    counts["both" if (o and n) else "r2_only" if n else "r1_only" if o else "neither"] += 1
P(f"  100000 expressions: {counts}; needs regressions (r1 True, r2 False): {len(regress)} {regress[:5]}")
P(f"  listed-in-r1 but neither needs nor listed in r2: {len(unparsed_lost)} {unparsed_lost[:5]}")

P("\n== R2-C. Real U3 rows: r1 -> r2 changes ==")
always = json.load(open("/work/docker/source-policy.json"))["always"]
leaves_bad = 0; leaves = 0
for image in ss.U3_IMAGES:
    name = "ke-neo4j" if image == "neo4j" else image
    d = ss.spdx_doc(name, ss.u3_rows(image))
    a = new.classify_document(name, d, always); b = r1.classify_document(name, d, always)
    ch = [(x["purl"], y["needs"], x["needs"]) for x, y in zip(a, b) if x != y]
    for r in a:
        for t in re.findall(r"[^\s()]+", r["expression"] or ""):
            if t.upper() not in ("AND", "OR", "WITH"):
                leaves += 1; leaves_bad += not new.LEAF_RE.fullmatch(t)
    P(f"  {name:10s} rows={len(a)} needs r2={sum(r['needs'] for r in a)} (r1 {sum(r['needs'] for r in b)}) changed={len(ch)} {ch[:3]}")
P(f"  real leaves: {leaves}; not fullmatching LEAF_RE: {leaves_bad}")

P("\n== R2-D. unlicensed_report untouched vs HEAD ==")
P("  sources identical:", all(inspect.getsource(getattr(head, f)) == inspect.getsource(getattr(new, f))
      for f in ("unlicensed_report", "_missing", "_hash_only", "report_lines", "_clean", "_packages", "_roots", "_purl")))
for image in ss.U3_IMAGES:
    d = ss.spdx_doc(image, ss.u3_rows(image))
    a, b = head.unlicensed_report(d), new.unlicensed_report(d)
    P(f"  {image:10s} HEAD={a['count']:3d} r2={b['count']:3d} equal={a == b} lines-equal={head.report_lines(image, a) == new.report_lines(image, b)}")

P("\n== R2-E. ReDoS / cost: LEAF_RE, DOCREF_RE, RUN_SPLIT_RE, _bare, _unknown_in_text, needs_source ==")
def t(label, f):
    s = time.perf_counter()
    try:
        r = f(); out = str(r)[:50]
    except BaseException as e:
        out = "RAISED " + type(e).__name__
    P(f"  {label:58s} {time.perf_counter()-s:7.3f}s {out}")
N = 1000000
t("LEAF_RE.fullmatch DocumentRef- + a*1M + !", lambda: new.LEAF_RE.fullmatch("DocumentRef-" + "a" * N + "!"))
t("LEAF_RE.fullmatch DocumentRef- + a*1M (no colon)", lambda: new.LEAF_RE.fullmatch("DocumentRef-" + "a" * N))
t("LEAF_RE.fullmatch (DocumentRef-a:)*50k", lambda: new.LEAF_RE.fullmatch("DocumentRef-a:" * 50000))
t("LEAF_RE.fullmatch a*1M + ++", lambda: new.LEAF_RE.fullmatch("a" * N + "++"))
t("LEAF_RE.fullmatch -.*500k + :", lambda: new.LEAF_RE.fullmatch("-." * 500000 + ":"))
t("DOCREF_RE.match DocumentRef- + a*1M", lambda: new.DOCREF_RE.match("DocumentRef-" + "a" * N))
t("_bare DocumentRef- + a*1M + :x", lambda: len(new._bare("DocumentRef-" + "a" * N + ":x")))
t("RUN_SPLIT_RE.split ,*1M", lambda: len(new.RUN_SPLIT_RE.split("," * N)))
t("RUN_SPLIT_RE.split a,*500k", lambda: len(new.RUN_SPLIT_RE.split("a," * 500000)))
t("_unknown_in_text DocumentRef-a:*70k", lambda: new._unknown_in_text("DocumentRef-a:" * 70000))
t("_unknown_in_text (DocumentRef-x:NONE,)*60k", lambda: new._unknown_in_text("DocumentRef-x:NONE," * 60000))
t("_unknown_in_text x,*500k", lambda: new._unknown_in_text("x," * 500000))
t("needs_source width 200k MIT AND DocumentRef-x:MIT", lambda: new.needs_source("MIT AND DocumentRef-x:MIT " * 100000 + "AND MIT"))
t("needs_source 1MB punctuation junk", lambda: new.needs_source("MIT; " * 200000))
t("needs_source 1MB single bad leaf", lambda: new.needs_source("a" * N + ";"))
t("needs_source depth 100000 DocumentRef-x:NONE", lambda: new.needs_source("(" * 100000 + "DocumentRef-x:NONE" + ")" * 100000))
