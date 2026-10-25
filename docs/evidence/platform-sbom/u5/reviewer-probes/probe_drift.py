import json, sys, io, contextlib, os
sys.path.insert(0, r"c:\repos\Knowledge-engine")
from tests import sbom_support as ss
from tests.test_sbom_bundle import load_sbom_check
m = load_sbom_check()
S = sys.argv[1]
app = ss.ke_app_doc(extra=({"purl": "pkg:generic/x/python@" + ss.licence_version() + "%1b%5b2J", "declared": "MIT"},))
base = ss.fake_base_doc()
for n, d in (("app.json", app), ("base.json", base)):
    open(os.path.join(S, n), "w", encoding="utf-8").write(json.dumps(d))
lic = [str(ss.ROOT / p) for p in ss.LICENCE_FILES]
argv = ["drift", "--sbom", os.path.join(S, "app.json"), "--base", os.path.join(S, "base.json"),
        "--added-from", str(ss.ROOT / "tests" / "test_notice_ke_app.py"), "--libpq", ss.libpq_pin(),
        "--lock", str(ss.ROOT / "uv.lock")] + sum((["--licence", p] for p in lic), [])
out, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    rc = m.main(argv)
print("rc", rc); print("stdout", ascii(out.getvalue())); print("stderr", ascii(err.getvalue()))
