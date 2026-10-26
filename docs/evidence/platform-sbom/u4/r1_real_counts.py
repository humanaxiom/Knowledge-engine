"""U4 rework round 1: per-image unlicensed counts on the real U3 package lists
(tests/fixtures/sbom-u3/) with the round-1 target checker (u4/r1-target-sbom_check.py)
and the U4 GREEN checker (scripts/sbom_check.py at RED time). Evidence only."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from tests import sbom_support as ss  # noqa: E402


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


green = load(REPO / "scripts" / "sbom_check.py")
target = load(Path(__file__).resolve().parent / "r1-target-sbom_check.py")
print("image       U4-GREEN  r1-target  of which unidentified (marked)   security's expected")
want = {"ke-app": 19, "ke-gateway": 0, "neo4j": 28, "phoenix": 35, "postgres": 25, "valkey": 1}
for image in ss.U3_IMAGES:
    doc = ss.u3_doc(image)
    g, t = green.unlicensed_report(doc), target.unlicensed_report(doc)
    marked = sum(1 for r in t["packages"] if r.get("unidentified"))
    print(f"{image:<11} {g['count']:>8}  {t['count']:>9}  {marked:>30}   {want[image]:>19}")
