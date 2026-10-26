# Simulates the proposed fix on a copy of the module (no repo file is changed).
import importlib.util, sys, re, unittest
sys.path.insert(0, r"c:\repos\Knowledge-engine")
from tests import sbom_support as ss
def load(n):
    spec = importlib.util.spec_from_file_location(n, r"c:\repos\Knowledge-engine\scripts\sbom_check.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
cur, fix = load("cur"), load("fix")
fix.RUN_SPLIT_RE = re.compile(r"[^A-Za-z0-9.-]+")
def _unknown_id(id_):
    bare = fix._bare(id_)
    bare = bare[:-1] if bare.endswith("+") else bare
    return bool(fix.HASH_ID_RE.fullmatch(bare)) or (bare.isascii() and bare.upper() in fix.UNKNOWN_LEAVES)
fix._unknown_id = _unknown_id
H = "LicenseRef-" + "0123456789abcdef"*4
for e in ["NOASSERTION+", "none+", f"{H}+", f"MIT WITH NOASSERTION+", "MIT:NOASSERTION", "MIT+NOASSERTION", "NOASSERTION:", "DocumentRef-:NONE", "see NONE.txt here", "MIT-NOASSERTION"]:
    print(ascii(e), "fix:", fix.needs_source(e))
for image in ss.U3_IMAGES:
    doc = ss.spdx_doc(image, ss.u3_rows(image))
    print(image, "real rows equal under fix:", cur.classify_document(image, doc, []) == fix.classify_document(image, doc, []))
import tests.test_sbom_classifier as t
t.load_sbom_check = lambda: fix
r = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(t))
print("existing classifier tests under fix: ran", r.testsRun, "failures", len(r.failures), "errors", len(r.errors))
