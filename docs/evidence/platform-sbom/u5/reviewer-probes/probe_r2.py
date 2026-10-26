import importlib.util, sys
sys.path.insert(0, r"c:\repos\Knowledge-engine")
from tests import sbom_support as ss
def load(p, n):
    spec = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
cur = load(r"c:\repos\Knowledge-engine\scripts\sbom_check.py", "cur")
r1 = load(r"c:\repos\Knowledge-engine\docs\evidence\platform-sbom\u5\r1-target-sbom_check.py", "r1")
H = "LicenseRef-" + "0123456789abcdef"*4
for e in ["NOASSERTION+", "none+", f"{H}+", f"MIT AND {H}+", f"DocumentRef-x:{H}+", "DocumentRef-x:NONE+",
          "MIT WITH NOASSERTION+", f"MIT WITH {H}+", "MIT:NOASSERTION", "MIT+NOASSERTION", "NOASSERTION+MIT",
          "Public Domain MIT:NOASSERTION", "NOASSERTION:", "MIT-NOASSERTION", "DocumentRef-:NONE",
          f"DocumentRef-x:DocumentRef-y:{H}", "MIT AND NOASSERTION+ AND Zlib"]:
    print(ascii(e), cur.needs_source(e))
print("snapshot: image (rows, needs, unparsed, unidentified, unlicensed) cur | r1 | full row-by-row equal")
for image in ss.U3_IMAGES:
    doc = ss.spdx_doc(image, ss.u3_rows(image))
    a, b = cur.classify_document(image, doc, []), r1.classify_document(image, doc, [])
    cnt = lambda rows: (len(rows),) + tuple(sum(bool(r[k]) for r in rows) for k in ("needs","unparsed","unidentified","unlicensed"))
    print(image, cnt(a), cnt(b), a == b)
