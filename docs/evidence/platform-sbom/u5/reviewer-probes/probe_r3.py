import importlib.util, sys
sys.path.insert(0, r"c:\repos\Knowledge-engine")
from tests import sbom_support as ss
def load(p, n):
    spec = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
E = r"c:\repos\Knowledge-engine\docs\evidence\platform-sbom\u5"
cur = load(r"c:\repos\Knowledge-engine\scripts\sbom_check.py", "cur")
r1 = load(E + r"\r1-target-sbom_check.py", "r1"); r2 = load(E + r"\r2-target-sbom_check.py", "r2")
H = "LicenseRef-" + "0123456789abcdef"*4
H65 = H + "a"
print("## round-2 findings (R2-B1, R2-B2) and security R2-L1")
for e in ["NOASSERTION+", "none+", "DocumentRef-x:NONE+", f"{H}+", f"MIT AND {H}+", f"DocumentRef-x:{H}+",
          "MIT WITH NOASSERTION+", f"MIT WITH {H}+", "MIT:NOASSERTION", "MIT+NOASSERTION", "NOASSERTION+MIT",
          "NOASSERTION:", "DocumentRef-:NONE", "Public Domain MIT:NOASSERTION", f"{H}.x", f"x{H}",
          "MIT AND NOASSERTION.", "MIT AND -NONE", "NOASSERTION..", "-NONE-"]:
    print(ascii(e), cur.needs_source(e))
print("## near-misses and opaque idstrings (ruled ordinary)")
for e in ["see NONE.txt here", "NOASSERTIONS apply", "MIT-NOASSERTION", "LicenseRef-NONE", H65, f"MIT AND {H65}",
          f"Public Domain {H65}", "NOASSERTION.NONE", "NOASSERTION-2.0", "LicenseRef-NOASSERTION",
          "LicenseRef-" + "0123456789ABCDEF"*4, "DocumentRef-x:LicenseRef-NONE"]:
    print(ascii(e), cur.needs_source(e))
print("## other shapes")
for e in ["NOASSERTION_", "MIT AND NoAssertion+", "MIT WITH -NONE", "MIT WITH x" + H, "(NONE+)", "MIT OR NONE+",
          "DocumentRef-a.b-c:NOASSERTION", "GPL-2.0-only+", "DocumentRef-x:GPL-2.0+"]:
    print(ascii(e), cur.needs_source(e))
print("## snapshot: image counts cur | equal to r1 row-by-row | equal to r2 row-by-row")
for image in ss.U3_IMAGES:
    doc = ss.spdx_doc(image, ss.u3_rows(image))
    a, b, c = (m.classify_document(image, doc, []) for m in (cur, r1, r2))
    cnt = (len(a),) + tuple(sum(bool(r[k]) for r in a) for k in ("needs","unparsed","unidentified","unlicensed"))
    print(image, cnt, a == b, a == c)
