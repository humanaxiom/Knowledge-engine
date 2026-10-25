"""security U5 rework r1 probes (platform-sbom). python -I, gates image."""
import importlib.util, inspect, json, random, re, sys, time
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
new = load("sc_r1", "/work/scripts/sbom_check.py")
u5 = load("sc_u5", "/work/docs/evidence/platform-sbom/u5/target-sbom_check.py")
head = load("sc_head", "/scratch/head_sbom_check.py")
sys.path.insert(0, "/work")
from tests import sbom_support as ss
H = "LicenseRef-" + "0123456789abcdef" * 4
HU = "LicenseRef-" + "0123456789ABCDEF" * 4
P = print

def show(label, expr):
    n, i = new.needs_source(expr); o, _ = u5.needs_source(expr)
    P(f"  {label:58s} needs={n!s:5} unparsed={bool(i['unparsed'])!s:5} unident={bool(i['unidentified'])!s:5} (U5 GREEN needs={o})")

P("== R1-A. Rework rules on the earlier fail-open inputs and new ones ==")
rows = [
 ("L-1 LicenseRef-GNU-General-Public-License-v2", "LicenseRef-GNU-General-Public-License-v2"),
 ("L-1 LicenseRef-GNU-Affero-General-Public-License", "LicenseRef-GNU-Affero-General-Public-License"),
 ("L-1 junk GNU General Public License v2", "GNU General Public License v2"),
 ("L-1 GPLv2orlater", "GPLv2orlater"),
 ("L-1 plural LicenseRef-GNU-General-Public-Licenses", "LicenseRef-GNU-General-Public-Licenses"),
 ("L-1 British General-Public-Licence", "LicenseRef-General-Public-Licence"),
 ("L-1 Lesser-General-Public-License-2.1", "LicenseRef-GNU-Lesser-General-Public-License-2.1"),
 ("L-1 Library-General-Public-License", "LicenseRef-GNU-Library-General-Public-License"),
 ("L-1 UPPER GENERAL_PUBLIC_LICENSE", "LicenseRef-GNU_GENERAL_PUBLIC_LICENSE"),
 ("L-1 residual camel GeneralPublicLicense (one token)", "LicenseRef-GNUGeneralPublicLicense"),
 ("L-1 residual gnu.org copyleft-lesser URL", "LicenseRef-https---www.gnu.org-copyleft-lesser.html"),
 ("L-1 residual G.P.L. dotted", "LicenseRef-G.P.L.-v2"),
 ("L-1 not a hit: General-Public-Domain-License", "LicenseRef-General-Public-Domain-License"),
 ("L-1 not a hit: Mozilla Public License", "LicenseRef-Mozilla-Public-License-2.0"),
 ("L-2 noassertion", "noassertion"),
 ("L-2 NoAssertion AND MIT", "NoAssertion AND MIT"),
 ("L-2 MIT OR none", "MIT OR none"),
 ("L-2 junk MIT AND AND noassertion", "MIT AND AND noassertion"),
 ("L-2 junk MIT NOASSERTION", "MIT NOASSERTION"),
 ("L-2 junk Public Domain AND (NoAssertion", "Public Domain AND (NoAssertion"),
 ("L-2 depth 3000 none", "(" * 3000 + "none" + ")" * 3000),
 ("L-2 ordinary: LicenseRef-NONE", "LicenseRef-NONE"),
 ("L-2 ordinary: NOASSERTIONS", "NOASSERTIONS"),
 ("L-3 Cyrillic ER", "G\u0420L-3.0-only"),
 ("L-3 fullwidth GPL", "\uff27\uff30\uff2c-3.0"),
 ("L-3 ZWJ", "G\u200dPL-2.0"),
 ("L-3 dotless-i: MIT w-i-th GPL-3.0-only", "MIT w\u0131th GPL-3.0-only"),
 ("L-3 dotless-i: MIT w-i-th Classpath-exception-2.0", "MIT w\u0131th Classpath-exception-2.0"),
 ("L-3 NEL separator MIT NEL OR NEL Apache-2.0", "MIT\x85OR\x85Apache-2.0"),
 ("L-3 NBSP after MIT", "MIT\u00a0OR Apache-2.0"),
 ("L-4 MIT WITH GPL-3.0-only", "MIT WITH GPL-3.0-only"),
 ("L-4 MIT WITH <hash>", f"MIT WITH {H}"),
 ("L-4 MIT WITH noassertion", "MIT WITH noassertion"),
 ("L-4 MIT WITH NONE", "MIT WITH NONE"),
 ("L-4 MIT WITH upper-hex hash (I-4)", f"MIT WITH {HU}"),
 ("L-4 MIT WITH GPL-3.0-linking-exception", "MIT WITH GPL-3.0-linking-exception"),
 ("L-4 MIT WITH LicenseRef-General-Public-License", "MIT WITH LicenseRef-General-Public-License"),
 ("L-4 MIT OR Apache-2.0 WITH GPL-3.0-only", "MIT OR Apache-2.0 WITH GPL-3.0-only"),
 ("L-4 Apache-2.0 WITH LLVM-exception (no source)", "Apache-2.0 WITH LLVM-exception"),
 ("L-4 GPL-2.0-only WITH Classpath-exception-2.0", "GPL-2.0-only WITH Classpath-exception-2.0"),
 ("L-4 MIT with (lower) GPL-2.0", "MIT with GPL-2.0"),
 ("L-4 MIT WITH affero", "MIT WITH affero"),
 ("I-4 bare upper-hex hash", HU),
 ("regress MIT OR GPL-2.0-only AND Apache-2.0", "MIT OR GPL-2.0-only AND Apache-2.0"),
 ("regress LGPL-2.1-or-later OR Apache-2.0", "LGPL-2.1-or-later OR Apache-2.0"),
]
for label, expr in rows:
    show(label, expr)
P("  is_gpl_id:", {s: new.is_gpl_id(s) for s in ("GPLX", "LGPL2", "LicenseRef-General-Public-Domain-License", "affero", "Affero-1.0", "MPL-2.0", "LicenseRef-Public-Domain")})

P("\n== R1-B. Monotonicity: no input needs source under U5 GREEN but not under r1 ==")
alpha = ["MIT", "Apache-2.0", "GPL-2.0-only", "LGPL-2.1+", "BSD-3-Clause", H, HU, "NONE", "none", "NOASSERTION", "NoAssertion",
         "AND", "OR", "WITH", "and", "or", "with", "w\u0131th", "(", ")", "Classpath-exception-2.0", "GPL-3.0-linking-exception",
         "LicenseRef-GNU-General-Public-License", "General", "Public", "License", "Licenses", "affero", "Public-Domain",
         "LicenseRef-https---www.gnu.org-licenses-gpl.html", "\u0420", "GPLv2orlater", "x"]
rnd = random.Random(20261024)
regress = []
counts = {"both": 0, "new_only": 0, "neither": 0}
for _ in range(60000):
    parts = [rnd.choice(alpha) for _ in range(rnd.randint(1, 9))]
    sep = rnd.choice([" ", " ", "", "-", "\t"])
    e = sep.join(parts)
    n = new.needs_source(e)[0]; o = u5.needs_source(e)[0]
    if o and not n:
        regress.append(e)
    counts["both" if (o and n) else "new_only" if n else "neither"] += 1
P(f"  60000 random expressions: {counts}; regressions (U5 True, r1 False): {len(regress)} {regress[:5]}")

P("\n== R1-C. Real U3 rows: classification changes U5 GREEN -> r1 ==")
always = json.load(open("/work/docker/source-policy.json"))["always"]
for image in ss.U3_IMAGES:
    name = "ke-neo4j" if image == "neo4j" else image
    d = ss.spdx_doc(name, ss.u3_rows(image))
    a = new.classify_document(name, d, always); b = u5.classify_document(name, d, always)
    flips = [(x["purl"], y["needs"], x["needs"], x["unparsed"], x["unidentified"]) for x, y in zip(a, b) if x != y]
    P(f"  {name:10s} rows={len(a)} needs r1={sum(r['needs'] for r in a)} (U5 {sum(r['needs'] for r in b)}) changed rows={len(flips)}")
    for f in flips[:12]:
        P("     ", str(f)[:200])

P("\n== R1-D. unlicensed_report unchanged vs HEAD (six fixtures) ==")
P("  sources identical:", all(inspect.getsource(getattr(head, f)) == inspect.getsource(getattr(new, f))
                               for f in ("unlicensed_report", "_missing", "_hash_only", "report_lines", "_clean", "_packages", "_roots", "_purl")))
for image in ss.U3_IMAGES:
    d = ss.spdx_doc(image, ss.u3_rows(image))
    a, b = head.unlicensed_report(d), new.unlicensed_report(d)
    P(f"  {image:10s} HEAD={a['count']:3d} r1={b['count']:3d} equal={a == b} lines-equal={head.report_lines(image, a) == new.report_lines(image, b)}")

P("\n== R1-E. ReDoS / cost on the widened token rule, phrase regex, _unknown_in_text, _cpython ==")
def t(label, f):
    s = time.perf_counter()
    try:
        r = f(); out = str(r)[:60]
    except BaseException as e:
        out = "RAISED " + type(e).__name__
    P(f"  {label:52s} {time.perf_counter()-s:7.3f}s {out}")
t("_token_hit general public x150k + licensx", lambda: new._token_hit("general public " * 150000 + "licensx"))
t("_token_hit general x300k", lambda: new._token_hit("general " * 300000))
t("_token_hit general-public-licen x60k", lambda: new._token_hit("general-public-licen" * 60000))
t("GPL_PHRASE_RE.search general public licen x60k", lambda: new.GPL_PHRASE_RE.search("general public licen " * 60000))
t("GPL_PHRASE_RE.search 1M spaces", lambda: new.GPL_PHRASE_RE.search(" " * 1000000))
t("_token_hit 1MB a-", lambda: new._token_hit("a-" * 500000))
t("_unknown_in_text 1MB paren-space", lambda: new._unknown_in_text("( " * 500000))
t("_unknown_in_text 1MB LicenseRef-", lambda: new._unknown_in_text("LicenseRef-" * 90000))
t("needs_source 1MB non-ASCII", lambda: new.needs_source("\u0420" * 1000000))
t("needs_source 1MB general public junk", lambda: new.needs_source("general public " * 70000 + "("))
t("needs_source width 200k MIT WITH x OR", lambda: new.needs_source("MIT WITH x OR " * 200000 + "MIT"))
t("needs_source depth 100000 MIT WITH GPL", lambda: new.needs_source("(" * 100000 + "MIT WITH GPL-3.0" + ")" * 100000))
big = {"packages": [{"SPDXID": "SPDXRef-x", "externalRefs": [{"referenceType": "purl",
        "referenceLocator": "pkg:generic/" + "a/" * 500000 + "python"}]}], "relationships": []}
t("_cpython purl pkg:generic/ + a/ x500k (no @)", lambda: new._cpython(big))
big2 = {"packages": [{"SPDXID": f"SPDXRef-{i}", "externalRefs": [{"referenceType": "purl",
        "referenceLocator": f"pkg:generic/python@3.12.{i}"}]} for i in range(100000)], "relationships": []}
t("_cpython 100k packages", lambda: len(new._cpython(big2)))
t("PURL_RE.match pkg:a/ + 1M slashes", lambda: new.PURL_RE.match("pkg:a/" + "/" * 1000000))
t("PURL_RE.match pkg:a/ + b/ x500k + @", lambda: bool(new.PURL_RE.match("pkg:a/" + "b/" * 500000 + "@")))
