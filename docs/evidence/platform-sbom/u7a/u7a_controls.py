"""platform-sbom U7a RED: controls for tests/test_sources_lock.py (the source
lock's pure half) and the U7a carry rows (tests/test_sbom_obligations.py
PolicyU6SchemaTest, tests/test_sbom_classifier.py U6ExemptMatchesTest), with
the classifier and policy tests kept as regressions.

Never writes the repository. Each row runs real test methods with
scripts/sbom_check.py replaced by docs/evidence/platform-sbom/u7a/target-sbom_check.py,
by the committed U6 checker (git HEAD 66781a9), or by a mutant of the target.
The CLI test runs the checker from a temporary root holding that file.
Each "must fail" row names the one test method that must fail. Exit 1 if any
row is unexpected.

Usage (run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7a/u7a_controls.py [--base repo]
`--base repo` uses the repository's own scripts/sbom_check.py (GREEN).
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests import test_neo4j_image as tni  # noqa: E402
from tests import test_sbom_classifier as tsc  # noqa: E402
from tests import test_sbom_obligations as tso  # noqa: E402
from tests import test_sources_lock as tsl  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
WORK = Path(tempfile.mkdtemp(prefix="u7a-controls-"))
rows: list[tuple[str, str, str, bool]] = []
CHECK_SRC = (REPO / "scripts" / "sbom_check.py" if BASE_REPO else HERE / "target-sbom_check.py").read_text(encoding="utf-8")


def head(rel: str) -> str:
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"],
                          capture_output=True, text=True, check=True, encoding="utf-8").stdout


def row(group: str, name: str, must_fail: bool, problems: list[str]) -> None:
    ok = bool(problems) == must_fail
    rows.append((group, name, "must fail" if must_fail else "must pass", ok))
    detail = problems[0][:110] if problems else "no problem"
    print(f"{'ok ' if ok else 'BAD'} [{group}] {name:<66} {'must fail' if must_fail else 'must pass'} | {detail}")


def swap(*pairs: str) -> Callable[[str], str]:
    def change(t: str) -> str:
        for old, new in zip(pairs[::2], pairs[1::2]):
            if t.count(old) != 1:
                raise AssertionError(f"mutant anchor found {t.count(old)} times: {old[:70]!r}")
            t = t.replace(old, new, 1)
        return t
    return change


def setup(src: str) -> tuple[ModuleType, Path]:
    root = Path(tempfile.mkdtemp(prefix="u7a-root-", dir=WORK))
    (root / "scripts").mkdir()
    path = root / "scripts" / "sbom_check.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"u7a_mutant_{root.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod, root


def run_test(cls: type, method: str, mod: ModuleType, root: Path) -> list[str]:
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    patches = [mock.patch.object(m, "load_sbom_check", lambda x=mod: x) for m in (tsc, tso, tni, tsl)]
    patches.append(mock.patch.object(tsl, "ROOT", root))
    for p in patches:
        p.start()
    try:
        suite.run(result)
    finally:
        for p in patches:
            p.stop()
    return [f"{method}: " + str(b[1]).strip().splitlines()[-1] for b in result.failures + result.errors]


def names(cls: type) -> list[tuple[type, str]]:
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls)]


LOCK_TESTS = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.SampleKeysTest,
                            tsl.LockCheckCliTest) for t in names(cls)]
CARRY = [(tso.PolicyU6SchemaTest, "test_policy_schema_rejects_bad_shapes"),
         (tsc.U6ExemptMatchesTest, "test_exempt_matches_strip_the_package_subpath")]
REGRESSION = [t for cls in (tsc.GplIdTest, tsc.NeedsSourceTest, tsc.LicenceInputTest, tsc.ClassifyPackageTest,
                            tsc.ClassifyDocumentTest, tsc.EscapingTest, tsc.ReworkR2RealRowsTest,
                            tsc.ReworkR3DecoratedIdsTest, tsc.U6ExemptMatchesTest, tsc.U6ClassifyDocumentExemptTest,
                            tsc.U6SegmentRuleTest, tso.PolicyU6SchemaTest, tso.UnlicensedReportTest)
              for t in names(cls)]
BY_NAME = {n: c for c, n in LOCK_TESTS + CARRY + REGRESSION}


def problems_of(mod: ModuleType, root: Path, tests: list[tuple[type, str]]) -> list[str]:
    out: list[str] = []
    for cls, method in tests:
        out += run_test(cls, method, mod, root)
    return out


TARGET, TROOT = setup(CHECK_SRC)
row("target", f"TARGET: the {len(LOCK_TESTS)} lock tests", False, problems_of(TARGET, TROOT, LOCK_TESTS))
row("target", "TARGET: the 2 carry rows (g), (h)", False, problems_of(TARGET, TROOT, CARRY))
row("target", f"TARGET: {len(REGRESSION)} classifier/policy regression tests", False,
    problems_of(TARGET, TROOT, REGRESSION))

HEAD_MOD, HROOT = setup(head("scripts/sbom_check.py"))
for cls, method in LOCK_TESTS:
    row("head", f"HEAD (U6): {method}", True, run_test(cls, method, HEAD_MOD, HROOT))
for cls, method in CARRY:
    row("head", f"HEAD (U6): {method} (carry guard, green before U7a)", False, run_test(cls, method, HEAD_MOD, HROOT))

MUTANTS: dict[str, tuple[Callable[[str], str], str]] = {
    # deb's own per-kind rule (snapshot.debian.org/file/<sha1>) also refuses a
    # foreign deb host, so the dropped-host-check mutant is aimed at neo4j and
    # pypi, whose URLs only the host check guards.
    "a kind's host check dropped (neo4j)": (swap(
        '        p += _file_problems(f"lock: {_clean(key)}", f, hosts)',
        '        p += _file_problems(f"lock: {_clean(key)}", f, hosts if kind != "neo4j" else '
        'type("AnyHost", (), {"__contains__": lambda s, x: True})())'), "test_bad_shapes"),
    "a kind's host check dropped (pypi)": (swap(
        '        p += _file_problems(f"lock: {_clean(key)}", f, hosts)',
        '        p += _file_problems(f"lock: {_clean(key)}", f, hosts if kind != "pypi" else '
        'type("AnyHost", (), {"__contains__": lambda s, x: True})())'), "test_bad_shapes"),
    "http accepted": (swap('    if u.scheme != "https":', '    if u.scheme not in ("https", "http"):'), "test_bad_shapes"),
    "userinfo accepted": (swap('    if u.username is not None or u.password is not None or "@" in u.netloc:',
                               "    if False:"), "test_bad_shapes"),
    "a stale entry ignored": (swap("    for key in sorted(covered - set(needs)):",
                                   "    for key in sorted(covered - set(needs) - covered):"), "test_a_stale_key_is_reported"),
    "a miss message with a wrong key (kind dropped)": (swap(
        "needs source; the lock has no {key} for {arch}: ", "needs source; the lock has no {key.split(':', 1)[1]} for {arch}: "),
        "test_small_lock_missing_key_exact_message"),
    "a miss reported once per key, not per package": (swap(
        '            for pkg in needs[key]["packages"]:', '            for pkg in needs[key]["packages"][:1]:'),
        "test_a_missing_key_names_every_package"),
    "an arm64-only entry covers amd64": (swap(
        '               and arch in e["arches"]}', '               and bool(e["arches"])}'), "test_arches"),
    "sample picking the largest": (swap("        if kind not in best or (total, key) < best[kind]:",
                                        "        if kind not in best or (total, key) > best[kind]:"), "test_sample_keys"),
    "sample ignoring the arch": (swap('        if not isinstance(entry, dict) or arch not in (entry.get("arches") or []):',
                                      "        if not isinstance(entry, dict):"), "test_sample_keys"),
    "sample ties broken by the largest key": (swap("        if kind not in best or (total, key) < best[kind]:",
                                                   "        if kind not in best or (total, -len(best)) < (best[kind][0], 0) "
                                                   "or (total == best[kind][0] and key > best[kind][1]):"),
                                              "test_sample_keys"),
    "the .pgdg mapping dropped": (swap(
        '        return (f"pgdg:{src}@{srcver}" if ".pgdg" in srcver else f"deb:{src}@{srcver}"), None',
        '        return f"deb:{src}@{srcver}", None'), "test_needs_from_the_fixtures"),
    "the version percent-decoding wrong (raw)": (swap(
        '    ver = unquote(m.group("version"))\n    q = _qualifiers(purl)', '    ver = m.group("version")\n    q = _qualifiers(purl)'),
        "test_needs_from_the_fixtures"),
    "the epoch dropped": (swap('        srcver = srcver or ver\n', '        srcver = (srcver or ver).split(":", 1)[-1]\n'),
                          "test_needs_from_the_fixtures"),
    "the epoch dropped (mapping table)": (swap('        srcver = srcver or ver\n',
                                               '        srcver = (srcver or ver).split(":", 1)[-1]\n'), "test_mapping_table"),
    "upstream ignored for deb (binary name)": (swap('        src, _, srcver = up.partition("@") if up else (name, "", ver)',
                                                    '        src, _, srcver = (name, "", ver)'), "test_mapping_table"),
    "the jrt-fs build check dropped": (swap('        if build is None or ver != build:', '        if build is None:'),
                                       "test_mapping_table"),
    "neo4j-group rows without a neo4j row pass as maven": (swap(
        '            if ctx.get("neo4j") is None:\n                return None,',
        '            if False:\n                return None,'), "test_mapping_table"),
    "unknown purl types fall to maven": (swap(
        '    if ptype == "pypi":\n        return f"pypi:{_norm(name)}@{ver}", None\n    return None, unmapped',
        '    if ptype == "pypi":\n        return f"pypi:{_norm(name)}@{ver}", None\n    return f"maven:{ns}:{name}@{ver}", None'),
        "test_mapping_table"),
    "pypi names not PEP 503": (swap('        return f"pypi:{_norm(name)}@{ver}", None', '        return f"pypi:{name}@{ver}", None'),
                               "test_mapping_table"),
    "exempt ignored by lock_needs (jna gets a key)": (swap('    exempt = policy.get("exempt") or []\n    needs:',
                                                           '    exempt = []\n    needs:'), "test_needs_from_the_fixtures"),
    "the canonical-form check dropped": (swap('    if lock != lock_text(data):', '    if False:'), "test_bad_shapes"),
    "lock_text not sorted": (swap("    return json.dumps(lock, indent=1, sort_keys=True, ensure_ascii=True) + \"\\n\"",
                                  "    return json.dumps(lock, indent=1, ensure_ascii=True) + \"\\n\""),
                             "test_lock_text_is_canonical"),
    "size true accepted": (swap('    if type(f["size"]) is not int or f["size"] <= 0:',
                                '    if not isinstance(f["size"], int) or f["size"] <= 0:'), "test_bad_shapes"),
    "the .dsc name keeps the epoch": (swap(
        """            want = f"{name_part}_{ver.split(':', 1)[1] if ':' in ver else ver}.dsc\"""",
        """            want = f"{name_part}_{ver}.dsc\""""), "test_good_small_lock_passes"),
    "a neo4j second fetch dated after today accepted": (swap("            if when > today:", "            if False:"),
                                                       "test_bad_shapes"),
    "lock-check prints every problem (no first-20 cut)": (swap(
        "        for line in problems[:20]:\n            print(f\"sbom_check: lock-check:",
        "        for line in problems:\n            print(f\"sbom_check: lock-check:"), "test_lock_check_cli"),
    "lock-check: a bad arch exits 1": (swap(
        '        print(f"sbom_check: lock-check: --arch {a.arch!r} is not amd64 or arm64", file=sys.stderr)\n        return 2',
        '        print(f"sbom_check: lock-check: --arch {a.arch!r} is not amd64 or arm64", file=sys.stderr)\n        return 1'),
        "test_lock_check_cli"),
}
for name, (m, method) in MUTANTS.items():
    try:
        mod, root = setup(m(CHECK_SRC))
    except AssertionError as exc:
        row("mutant", name, True, [])
        print(f"    anchor: {exc}")
        continue
    row("mutant", name, True, run_test(BY_NAME[method], method, mod, root))

bad = [r for r in rows if not r[3]]
print(f"\nU7a controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
