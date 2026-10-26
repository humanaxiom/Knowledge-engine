import importlib.util, sys, json, random, copy
sys.path.insert(0, r"c:\repos\Knowledge-engine")
from tests import sbom_support as ss
def load(p, n):
    spec = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
cur = load(r"c:\repos\Knowledge-engine\scripts\sbom_check.py", "cur")
head = load(sys.argv[1], "head")
pol = json.load(open(r"c:\repos\Knowledge-engine\docker\source-policy.json", encoding="utf-8"))
always, exempt = pol["always"], pol["exempt"]
JNA = "pkg:maven/com.sun.jna/jna@5.15.0"
print("## 1. duplicate SPDXID: a GPL package sharing jna's SPDXID")
doc = ss.spdx_doc("ke-neo4j", [{"purl": JNA, "declared": "NOASSERTION", "concluded": "Apache-2.0 AND LGPL-2.1-only"},
                               {"purl": "pkg:deb/debian/bash@5.2.15-2?arch=amd64", "declared": "GPL-3.0-or-later"}])
doc["packages"][2]["SPDXID"] = doc["packages"][1]["SPDXID"]
for r in cur.classify_document("ke-neo4j", doc, [], exempt):
    print(" ", r["purl"], "needs", r["needs"], "exempt", r["exempt"])
print("  validate on that doc:", [p for p in cur.validate(doc) if "unique" in p])
print("## 2. package purl with a subpath")
d2 = ss.spdx_doc("ke-neo4j", [{"purl": JNA + "?type=jar#META-INF", "declared": "MIT"}])
print(" ", cur.exempt_matches("ke-neo4j", d2, exempt))
print("## 3. real rows: HEAD (U5) vs current with exempt=() row by row; with the real exempt, changed rows")
for fx in ss.U3_IMAGES:
    image = "ke-neo4j" if fx == "neo4j" else fx
    d = ss.spdx_doc(image, ss.u3_rows(fx))
    a = head.classify_document(image, d, always)
    b = cur.classify_document(image, d, always)
    same = all({k: v for k, v in y.items() if k != "exempt"} == x and y["exempt"] is False for x, y in zip(a, b)) and len(a) == len(b)
    c = cur.classify_document(image, d, always, exempt)
    ch = [(y["purl"].split("?")[0], {k for k in y if y[k] != z.get(k)}) for y, z in zip(c, b) if y != z]
    print(" ", image, len(a), "U5-equal:", same, "changed with exempt:", ch)
print("## 4. segment rule monotone vs HEAD: random expressions")
random.seed(7)
atoms = ["MIT", "GPL-2.0-only", "NONE", "noassertion", "MIT-NONE", "NONE.txt", "LicenseRef-NONE", "x-NOASSERTION-y",
         "LGPL-NONE", "Apache-2.0", "DocumentRef-a:NONE-1", "Public", "Domain", "NONEX", "LicenseRef-" + "ab"*32, "a.none.b"]
ops = ["AND", "OR", "WITH", "(", ")", ",", ":", "+"]
lost_needs = lost_listing = flips = 0
for _ in range(100000):
    e = " ".join(random.choice(atoms + ops) for _ in range(random.randint(1, 7)))
    for x in (e, e.replace(" ", random.choice(["", "-", "."]))):
        n0, i0 = head.needs_source(x); n1, i1 = cur.needs_source(x)
        if n0 and not n1: lost_needs += 1
        if (i0["unparsed"] or i0["unidentified"]) and not (i1["unparsed"] or i1["unidentified"]): lost_listing += 1
        if (n0, i0) != (n1, i1): flips += 1
print("  checked 200000; lost needs:", lost_needs, "lost listing:", lost_listing, "changed:", flips)
print("  LGPL-NONE head", head.needs_source("LGPL-NONE"), "cur", cur.needs_source("LGPL-NONE"))
