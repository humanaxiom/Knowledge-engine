import sys, unittest
sys.path.insert(0, r"c:\repos\Knowledge-engine")
from tests.test_sbom_bundle import load_sbom_check
m = load_sbom_check()
def joined(pkg):
    e = m.licence_input(pkg)
    if e is None:
        n, info = False, {"unparsed": False, "unidentified": False}
    else:
        n, info = m.needs_source(e)
    return {"needs": n, "expression": e, "unlicensed": e is None, "unparsed": info["unparsed"],
            "unidentified": info["unidentified"], "purl": m._purl(pkg), "spdxid": pkg.get("SPDXID"), "name": pkg.get("name")}
m.classify_package = joined
import tests.test_sbom_classifier as t
t.load_sbom_check = lambda: m
r = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(t))
print("MUTANT joined-text: failures", len(r.failures), "errors", len(r.errors), "ran", r.testsRun)
# control: break classify_package outright to prove the patch is live
m.classify_package = lambda pkg: {"needs": False, "expression": None, "unlicensed": True, "unparsed": False, "unidentified": False, "purl": None, "spdxid": pkg.get("SPDXID"), "name": pkg.get("name")}
r = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(t))
print("CONTROL broken: failures", len(r.failures), "errors", len(r.errors))
