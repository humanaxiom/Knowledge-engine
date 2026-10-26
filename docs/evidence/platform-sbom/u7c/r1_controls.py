"""platform-sbom U7c rework round 1 RED: controls for the ReworkR1U7c* tests
(tests/test_sources_resolve.py and tests/test_sources_lock.py).

Never writes the repository. It builds a temporary root with the round-1
targets (docs/evidence/platform-sbom/u7c/r1-target-*) in place and runs real
test methods on the targets, on the U7c baseline (the SAVED u7c/target-*
files, byte-equal to the U7c GREEN tree) and on mutants of each target. Each
"must fail" row names the one test method that must fail. Exit 1 if any row
is unexpected.

Usage (in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \
    --profile gates run --rm gates \
    uv run --locked python docs/evidence/platform-sbom/u7c/r1_controls.py [--base repo]
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests import test_offline_bundle as tob  # noqa: E402
from tests import test_sources_lock as tsl  # noqa: E402
from tests import test_sources_resolve as tsr  # noqa: E402

HERE = Path(__file__).resolve().parent
U7B = HERE.parent / "u7b"
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGETS = {"scripts/sources_resolve.py": "r1-target-sources_resolve.py",
           "scripts/sources_lock.sh": "target-sources_lock.sh",
           "scripts/sbom_check.py": "r1-target-sbom_check.py"}
BASELINE = {"scripts/sources_resolve.py": "target-sources_resolve.py",
            "scripts/sources_lock.sh": "target-sources_lock.sh",
            "scripts/sbom_check.py": "target-sbom_check.py"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml",
        "docker-compose.sources.yml", ".env.example", ".gitignore", ".dockerignore", "pyproject.toml", "uv.lock",
        "LICENSE", "NOTICE.md", "config", "licenses", "docs/quickstart.md", ".github", "tests/fixtures"]
WORK = Path(tempfile.mkdtemp(prefix="u7c-r1-controls-"))
rows: list[tuple[str, str, str, bool]] = []

SRC = {rel: (REPO / rel if BASE_REPO else HERE / name).read_text(encoding="utf-8") for rel, name in TARGETS.items()}
SAVED_U7C = {rel: (HERE / name).read_text(encoding="utf-8") for rel, name in BASELINE.items()}


def make_root(files: dict[str, str | None]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="root-", dir=WORK))
    for rel in COPY:
        src = REPO / rel
        if src.is_dir():
            shutil.copytree(src, root / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / rel)
    for rel, content in files.items():
        path = root / rel
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    return root


def module_at(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"u7c_r1_check_{path.parent.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_test(cls: type, method: str, root: Path) -> list[str]:
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    check = module_at(root / "scripts" / "sbom_check.py")
    patches = [mock.patch.object(tsr, "RESOLVER", root / "scripts" / "sources_resolve.py"),
               mock.patch.object(tsr, "LOCK_SH", root / "scripts" / "sources_lock.sh"),
               mock.patch.object(tsr, "SOURCES_COMPOSE", root / "docker-compose.sources.yml"),
               mock.patch.object(tsr, "ROOT", root), mock.patch.object(tob, "ROOT", root),
               mock.patch.object(tsl, "ROOT", root),
               mock.patch.object(tsr, "load_sbom_check", lambda m=check: m),
               mock.patch.object(tsl, "load_sbom_check", lambda m=check: m)]
    for p in patches:
        p.start()
    try:
        suite.run(result)
    finally:
        for p in patches:
            p.stop()
    return [f"{method}: " + str(b[1]).strip().splitlines()[-1] for b in result.failures + result.errors]


def row(group: str, name: str, must_fail: bool, problems: list[str]) -> None:
    ok = bool(problems) == must_fail
    rows.append((group, name, "must fail" if must_fail else "must pass", ok))
    detail = problems[0][:110] if problems else "no problem"
    print(f"{'ok ' if ok else 'BAD'} [{group}] {name:<70} {'must fail' if must_fail else 'must pass'} | {detail}",
          flush=True)


def swap(*pairs: str) -> Callable[[str], str]:
    def change(t: str) -> str:
        for old, new in zip(pairs[::2], pairs[1::2]):
            if t.count(old) != 1:
                raise AssertionError(f"mutant anchor found {t.count(old)} times: {old[:70]!r}")
            t = t.replace(old, new, 1)
        return t
    return change


def own(cls: type) -> list[tuple[type, str]]:
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls) if n in vars(cls)]


def every(cls: type) -> list[tuple[type, str]]:
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls)]


R1_CLASSES = [tsr.ReworkR1U7cApkbuildTest, tsr.ReworkR1U7cDscTest, tsr.ReworkR1U7cApkbuildAssignTest,
              tsr.ReworkR1U7cListingTest, tsl.ReworkR1U7cApkbuildPathTest, tsl.ReworkR1U7cApiUrlTest,
              tsr.ReworkR1U7cApiUrlResolverTest]
NEW = [t for cls in R1_CLASSES for t in own(cls)]
OLD_CLASSES = (tsr.ResolverHopsTest, tsr.ResolverParsersTest, tsr.ResolverRoutesTest, tsr.ResolverMergeTest,
               tsr.ResolverMainTest, tsr.LockNeedsTest, tsr.SourcesComposeTest, tsr.SourcesLockScriptStaticTest,
               tsr.SourcesLockScriptRunTest, tsr.ReworkR1TransportTest, tsr.ReworkR1MainTest,
               tsr.ReworkR1RealOpenerTest, tsr.ReworkR1HopRulesTest, tsr.ReworkR1PypiScopeTest, tsr.ReworkR1KeysTest,
               tsr.ReworkR1LockScriptRunTest, tsr.U7cDebRouteTest, tsr.U7cApkRouteTest, tsr.U7cCoverageTest,
               tsr.U7cCarriedTest, tsr.U7cLockNeedsTest, tsr.U7cLockScriptRunTest)
OLD = [t for cls in OLD_CLASSES for t in every(cls)]
U7A = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.LockCheckCliTest,
                     tsl.ReworkR1PendingNeo4jCliTest, tsl.U7cApkLockRulesTest) for t in own(cls)]

TROOT = make_root(dict(SRC))
row("target", f"TARGET: the {len(NEW)} round-1 tests", False, [p for c, m in NEW for p in run_test(c, m, TROOT)])
row("target", f"TARGET: the {len(OLD)} U7b, U7b-r1 and U7c tests", False,
    [p for c, m in OLD for p in run_test(c, m, TROOT)])
row("target", f"TARGET: {len(U7A)} U7a and U7c lock tests", False, [p for c, m in U7A for p in run_test(c, m, TROOT)])

BROOT = make_root(dict(SAVED_U7C))
# Guard: the CRLF row pins behaviour the U7c baseline already has (splitlines);
# its mutant row ("dsc: CRLF not folded") covers it.
# test_bad_forms: the U7c baseline refuses the item-9 form for every file, so
# each row finds some problem there; the item-9 mutant rows prove each row.
GUARDS = {(tsr.ReworkR1U7cDscTest, "test_crlf_parses_like_lf"), (tsl.ReworkR1U7cApiUrlTest, "test_bad_forms")}
for cls, method in NEW:
    guard = (cls, method) in GUARDS
    row("u7c", f"U7c (saved targets): {cls.__name__}.{method}" + (" (guard)" if guard else ""), not guard,
        run_test(cls, method, BROOT))

B = chr(92)
RES, CHK = "scripts/sources_resolve.py", "scripts/sbom_check.py"
AP, DS, AS, LI = (tsr.ReworkR1U7cApkbuildTest, tsr.ReworkR1U7cDscTest, tsr.ReworkR1U7cApkbuildAssignTest,
                  tsr.ReworkR1U7cListingTest)
LP = tsl.ReworkR1U7cApkbuildPathTest
AU, AR = tsl.ReworkR1U7cApiUrlTest, tsr.ReworkR1U7cApiUrlResolverTest
BAD = f'DSC_BAD_CHARS = re.compile("[{B}x00-{B}x08{B}x0b-{B}x1f{B}x7f-{B}x9f{B}u2028{B}u2029]")'
MUTANTS: dict[str, tuple[str, Callable[[str], str], type, str]] = {
    # item 9: the apk GitLab url form
    "item 9: the old /-/raw/ form accepted": (CHK, swap(
        "    if shape is None:\n        return \"want",
        "    if shape is None:\n        return None if \"/alpine/aports/-/raw/\" in url else \"want"),
        AU, "test_bad_forms"),
    "item 9: the query not exact (ref plus another param)": (CHK, swap(
        'APK_API_QUERY_RE = re.compile(r"ref=([^&#=]*)")', 'APK_API_QUERY_RE = re.compile(r"ref=([^#]*)")',
        '    if not re.fullmatch(r"[0-9a-f]{40}", ref) or ref != entry.get("commit"):',
        '    if ref[:40] != entry.get("commit"):'), AU, "test_bad_forms"),
    "item 9: a non-canonical %2f accepted": (CHK, swap('    if quote(decoded, safe="") != seg:', "    if False:"),
                                             AU, "test_bad_forms"),
    "item 9: the /raw suffix optional": (CHK, swap('repository/files/([^/?#]+)/raw")', 'repository/files/([^/?#]+)(?:/raw)?")'),
                                         AU, "test_bad_forms"),
    "item 9: the resolver requests the old /-/raw/ form": (RES, swap(
        "        return f\"{APORTS_API}/files/{quote(f'{repo}/{origin}/{rel}', safe='')}/raw?ref={commit}\"",
        "        return f\"https://{GITLAB}/alpine/aports/-/raw/{commit}/{repo}/{origin}/{rel}\""),
        AR, "test_the_request_forms"),
    "lock: the APKBUILD path unpinned": (CHK, swap('    if name == "APKBUILD" and len(parts) != 3:', "    if False:"),
                                         LP, "test_the_apkbuild_path_is_exact"),
    "resolver: a subdirectory APKBUILD accepted": (RES, swap(
        '    if "APKBUILD" not in blobs or blobs["APKBUILD"] != "APKBUILD":', '    if "APKBUILD" not in blobs:'),
        AP, "test_only_a_subdirectory_apkbuild"),
    "dsc: last-wins duplicate field": (RES, swap("        if field.lower() in seen:", "        if False:"),
                                       DS, "test_duplicate_fields"),
    "dsc: duplicates compared case-sensitively": (RES, swap("        if field.lower() in seen:", "        if field in seen:",
                                                            "        seen.add(field.lower())", "        seen.add(field)"),
                                                  DS, "test_duplicate_fields"),
    "dsc: splitlines()": (RES, swap('    lines = body.replace("' + B + 'r' + B + 'n", "' + B + 'n").split("' + B + 'n")',
                                    "    lines = body.splitlines()"), DS, "test_control_characters"),
    "dsc: CRLF not folded": (RES, swap('    lines = body.replace("' + B + 'r' + B + 'n", "' + B + 'n").split("' + B + 'n")',
                                       '    lines = body.split("' + B + 'n")'), DS, "test_crlf_parses_like_lf"),
    "dsc: only C0 and DEL refused": (RES, swap(BAD, f'DSC_BAD_CHARS = re.compile("[{B}x00-{B}x08{B}x0b-{B}x1f{B}x7f]")'),
                                     DS, "test_control_characters"),
    "dsc: a lone CR allowed": (RES, swap(BAD, f'DSC_BAD_CHARS = re.compile("[{B}x00-{B}x08{B}x0b{B}x0c{B}x0e-{B}x1f'
                                              f'{B}x7f-{B}x9f{B}u2028{B}u2029]")'), DS, "test_control_characters"),
    "apkbuild: the first assignment read": (RES, swap('        if len(re.findall(rf"(?m)^{field}=", body)) > 1:',
                                                      "        if False:"), AS, "test_repeated_assignments"),
    "apkbuild: indented assignments counted": (RES, swap('        if len(re.findall(rf"(?m)^{field}=", body)) > 1:',
                                                         f'        if len(re.findall(rf"(?m)^{B}s*{{field}}=", body)) > 1:'),
                                               AS, "test_repeated_assignments"),
    "listing: a full page taken as complete": (RES, swap(
        '        if isinstance(listing, list) and len(listing) >= 100 and headers.get("x-next-page", None) != "":',
        "        if False:"), LI, "test_a_full_page"),
    "listing: a missing x-next-page taken as empty": (RES, swap(
        'headers.get("x-next-page", None) != "":', 'headers.get("x-next-page", "") != "":'), LI, "test_a_full_page"),
    "listing: the path not encoded": (RES, swap("tree?path={quote(f'{repo}/{origin}', safe='')}&ref=",
                                                "tree?path={repo}/{origin}&ref="), LI, "test_the_path_is_encoded"),
}
for name, (rel, m, cls, method) in MUTANTS.items():
    try:
        files = dict(SRC)
        files[rel] = m(SRC[rel])
    except AssertionError as exc:
        row("mutant", name, True, [])
        print(f"    anchor: {exc}")
        continue
    row("mutant", f"{name} -> {method}", True, run_test(cls, method, make_root(files)))

bad = [r for r in rows if not r[3]]
print(f"\nU7c rework round 1 controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
