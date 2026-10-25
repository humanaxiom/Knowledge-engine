"""platform-sbom U6 RED: controls for the U6 tests (tests/test_sbom_obligations.py
PolicyU6SchemaTest; tests/test_sbom_classifier.py U6ExemptMatchesTest,
U6ClassifyDocumentExemptTest, U6SegmentRuleTest), with the earlier classifier
and policy tests kept as regressions.

Never writes the repository. It builds a temporary tree with the U6 targets
(docs/evidence/platform-sbom/u6/target-sbom_check.py and
target-source-policy.json) and runs real test methods on the targets, on the
committed U5 files (git HEAD d8ffa2d), and on mutants of each target:
  A. the targets: every listed test passes;
  B. HEAD (U5): each U6 test fails;
  C. sbom_check.py mutants (target policy);
  D. source-policy.json mutants (target checker).
Each "must fail" row names the one test method that must fail. Exit 1 if any
row is unexpected.

Usage (run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u6/u6_controls.py [--base repo]
`--base repo` uses the repository's own files instead of the targets (GREEN).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests import test_neo4j_image as tni  # noqa: E402
from tests import test_sbom_classifier as tsc  # noqa: E402
from tests import test_sbom_obligations as tso  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
WORK = Path(tempfile.mkdtemp(prefix="u6-controls-"))
rows: list[tuple[str, str, str, bool]] = []


def head(rel: str) -> str:
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"],
                          capture_output=True, text=True, check=True, encoding="utf-8").stdout


def source(rel: str, target: str) -> str:
    return (REPO / rel if BASE_REPO else HERE / target).read_text(encoding="utf-8")


CHECK_SRC = source("scripts/sbom_check.py", "target-sbom_check.py")
POLICY_SRC = source("docker/source-policy.json", "target-source-policy.json")


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


def module_of(src: str) -> ModuleType:
    path = Path(tempfile.mkdtemp(prefix="u6-check-", dir=WORK)) / "sbom_check.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"u6_mutant_{path.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def policy_file(text: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix="u6-policy-", dir=WORK)) / "source-policy.json"
    path.write_text(text, encoding="utf-8")
    return path


def run_test(cls: type, method: str, mod: ModuleType, policy: Path) -> list[str]:
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    patches = [mock.patch.object(m, "load_sbom_check", lambda x=mod: x) for m in (tsc, tso, tni)]
    patches += [mock.patch.object(m, "POLICY", policy) for m in (tsc, tso, tni)]
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


U6_TESTS = (names(tso.PolicyU6SchemaTest) + names(tsc.U6ExemptMatchesTest) + names(tsc.U6ClassifyDocumentExemptTest)
            + names(tsc.U6SegmentRuleTest))
REGRESSION = [(cls, n) for cls in (tsc.GplIdTest, tsc.NeedsSourceTest, tsc.LicenceInputTest, tsc.ClassifyPackageTest,
                                   tsc.ClassifyDocumentTest, tsc.EscapingTest, tsc.ReworkR1UnknownLeavesTest,
                                   tsc.ReworkR1TokenRuleTest, tsc.ReworkR1NonAsciiTest, tsc.ReworkR1WithExceptionTest,
                                   tsc.ReworkR1PerPartTest, tsc.ReworkR2LeafCharsetTest, tsc.ReworkR2DocumentRefTest,
                                   tsc.ReworkR2WithUrlTest, tsc.ReworkR2RealRowsTest, tsc.ReworkR3DecoratedIdsTest,
                                   tsc.ReworkR3RunSplitTest, tso.UnlicensedReportTest, tso.ReworkR1UnlicensedTest,
                                   tso.ReworkR1PolicyTest)
              for n in unittest.defaultTestLoader.getTestCaseNames(cls)]
REGRESSION += [(tso.NamedComponentsTest, "test_source_policy_always_covers_psc22_components"),
               (tso.NamedComponentsTest, "test_named_gpl_components_need_source_whatever_the_generator_says")]
REGRESSION += names(tni.Neo4jPolicyAndNoticeTest)
BY_NAME = {n: c for c, n in U6_TESTS + REGRESSION}


def problems_of(mod: ModuleType, policy: Path, tests: list[tuple[type, str]]) -> list[str]:
    out: list[str] = []
    for cls, method in tests:
        out += run_test(cls, method, mod, policy)
    return out


TARGET_MOD = module_of(CHECK_SRC)
TARGET_POLICY = policy_file(POLICY_SRC)

# ---- A. targets ---------------------------------------------------------------------------
row("target", f"TARGET: the {len(U6_TESTS)} U6 tests", False, problems_of(TARGET_MOD, TARGET_POLICY, U6_TESTS))
row("target", f"TARGET: {len(REGRESSION)} classifier/policy regression tests", False,
    problems_of(TARGET_MOD, TARGET_POLICY, REGRESSION))

# ---- B. HEAD (U5) -------------------------------------------------------------------------
HEAD_MOD = module_of(head("scripts/sbom_check.py"))
HEAD_POLICY = policy_file(head("docker/source-policy.json"))
for cls, method in U6_TESTS:
    if method == "test_policy_schema_rejects_bad_shapes":  # the oracle's own controls: green before U6
        row("head", f"HEAD (U5): {method} (guard)", False, run_test(cls, method, HEAD_MOD, HEAD_POLICY))
        continue
    row("head", f"HEAD (U5): {method}", True, run_test(cls, method, HEAD_MOD, HEAD_POLICY))
row("head", "HEAD checker + TARGET policy: test_source_policy_has_exactly_hosts_always_exempt", False,
    run_test(tso.PolicyU6SchemaTest, "test_source_policy_has_exactly_hosts_always_exempt", HEAD_MOD, TARGET_POLICY))
row("head", "TARGET checker + HEAD policy: test_real_rows_with_the_committed_exempt", True,
    run_test(tsc.U6ClassifyDocumentExemptTest, "test_real_rows_with_the_committed_exempt", TARGET_MOD, HEAD_POLICY))

# ---- C. sbom_check.py mutants ---------------------------------------------------------------
CHECK_MUTANTS: dict[str, tuple[Callable[[str], str], str]] = {
    "exempt matching ignores the version": (swap(
        "        hits = [sid for sid, key in keys if key == want]",
        '        hits = [sid for sid, key in keys if key.rsplit("@", 1)[0] == want.rsplit("@", 1)[0]]'),
        "test_exempt_void_on_version_bump"),
    "exempt matching by version prefix": (swap(
        "        hits = [sid for sid, key in keys if key == want]",
        "        hits = [sid for sid, key in keys if key.startswith(want)]"), "test_exempt_void_on_version_bump"),
    "exempt matching case-folded": (swap(
        "        hits = [sid for sid, key in keys if key == want]",
        "        hits = [sid for sid, key in keys if key.lower() == want.lower()]"), "test_exempt_matches_exact_versioned_purl"),
    # No row for "an entry carrying qualifiers accepted": a qualifier-bearing
    # entry never equals a qualifier-stripped purl, so it still matches
    # nothing and is a problem (equivalent; the message text is not pinned).
    "no void-on-bump problem": (swap(
        "        if not hits:\n            problems.append(f\"{image}: exempt entry matches nothing",
        "        if False:\n            problems.append(f\"{image}: exempt entry matches nothing"), "test_exempt_void_on_version_bump"),
    "other images' entries applied": (swap(
        '        if not isinstance(entry, dict) or entry.get("image") != image:\n            continue\n        want',
        '        if not isinstance(entry, dict):\n            continue\n        want'), "test_exempt_matches_exact_versioned_purl"),
    "always beats exempt (both matched: needs left True)": (swap(
        '        if row["exempt"]:\n            row["needs"] = False  # a reviewed exemption clears it, `always` or not\n'
        '        elif row["always"]:\n            row["needs"] = True',
        '        if row["always"]:\n            row["needs"] = True\n        elif row["exempt"]:\n            row["needs"] = False'),
        "test_exempt_clears_needs_also_under_always"),
    "exempt alone does not clear needs": (swap(
        '            row["needs"] = False  # a reviewed exemption clears it, `always` or not\n',
        '            pass  # a reviewed exemption clears it, `always` or not\n'), "test_exempt_clears_needs_also_under_always"),
    "exempt clears needs but always no longer forces it": (swap(
        '        elif row["always"]:\n            row["needs"] = True', ""), "test_exempt_clears_needs_also_under_always"),
    "the exempt flag only on matched rows": (swap(
        '        row["exempt"] = sid in exempted\n', '        if sid in exempted:\n            row["exempt"] = True\n'),
        "test_exempt_clears_needs_also_under_always"),
    "segment rule dropped (U5 round 3)": (swap(
        '    return (not bare.lower().startswith("licenseref-")\n'
        '            and any(seg.upper() in UNKNOWN_LEAVES for seg in re.split(r"[.-]", bare)))',
        "    return False"), "test_segment_rule"),
    "segment rule also inside LicenseRef- ids": (swap(
        '    return (not bare.lower().startswith("licenseref-")\n            and any(',
        "    return (True\n            and any("), "test_segment_rule"),
    "segment rule on `-` only": (swap('re.split(r"[.-]", bare)', 're.split(r"-", bare)'), "test_segment_rule"),
    "segment rule case-sensitive": (swap("any(seg.upper() in UNKNOWN_LEAVES for seg in",
                                         "any(seg in UNKNOWN_LEAVES for seg in"), "test_segment_rule"),
    "segment rule on parsed leaves only (runs keep `see NONE.txt here`)": (swap(
        "    return bool(HASH_ID_RE.search(text)) or any(_unknown_id(r) for r in RUN_SPLIT_RE.split(text) if r)",
        "    return bool(HASH_ID_RE.search(text)) or any(r.isascii() and r.strip('.-+').upper() in UNKNOWN_LEAVES"
        " for r in RUN_SPLIT_RE.split(text) if r)"), "test_segment_rule_in_runs"),
}
for name, (m, method) in CHECK_MUTANTS.items():
    try:
        mod = module_of(m(CHECK_SRC))
    except AssertionError as exc:
        row("checker", name, True, [])
        print(f"    anchor: {exc}")
        continue
    row("checker", name, True, run_test(BY_NAME[method], method, mod, TARGET_POLICY))

# ---- D. source-policy.json mutants ---------------------------------------------------------
policy = json.loads(POLICY_SRC)


def pol(fn: Callable[[dict[str, Any]], None]) -> str:
    d = json.loads(POLICY_SRC)
    fn(d)
    return json.dumps(d, indent=1)


def set_host(d: dict[str, Any], old: str, new: str) -> None:
    d["hosts"] = [new if h == old else h for h in d["hosts"]]


OPENJDK = "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS"
POLICY_MUTANTS: dict[str, tuple[str, str]] = {
    "a host with a scheme": (pol(lambda d: set_host(d, "github.com", "https://github.com")),
                             "test_source_policy_has_exactly_hosts_always_exempt"),
    "a host with a path": (pol(lambda d: set_host(d, "repo1.maven.org", "repo1.maven.org/maven2")),
                           "test_source_policy_has_exactly_hosts_always_exempt"),
    "a wildcard host": (pol(lambda d: set_host(d, "objects.githubusercontent.com", "*.githubusercontent.com")),
                        "test_source_policy_has_exactly_hosts_always_exempt"),
    "a tenth host (valid, not N4's)": (pol(lambda d: d["hosts"].append("pypi.org")), "test_hosts_are_the_fetch_hosts"),
    "a fetch host missing": (pol(lambda d: d["hosts"].remove("codeload.github.com")), "test_hosts_are_the_fetch_hosts"),
    "a fourth key": (pol(lambda d: d.update(overrides=[])), "test_source_policy_has_exactly_hosts_always_exempt"),
    "reviewed loosened (no date)": (pol(lambda d: d["exempt"][0].update(reviewed="security")),
                                    "test_source_policy_has_exactly_hosts_always_exempt"),
    "reviewed loosened (another reviewer)": (pol(lambda d: d["exempt"][1].update(reviewed="tester 2026-10-25")),
                                             "test_source_policy_has_exactly_hosts_always_exempt"),
    "reviewed with an impossible date": (pol(lambda d: d["exempt"][0].update(reviewed="security 2026-02-30")),
                                         "test_source_policy_has_exactly_hosts_always_exempt"),
    "jna bumped in the entry (void)": (pol(lambda d: d["exempt"][0].update(package="pkg:maven/com.sun.jna/jna@5.16.0")),
                                       "test_source_policy_has_exactly_hosts_always_exempt"),
    "jna bumped: the real-row test": (pol(lambda d: d["exempt"][0].update(package="pkg:maven/com.sun.jna/jna@5.16.0")),
                                      "test_real_rows_with_the_committed_exempt"),
    "a reason without the jar sha256": (pol(lambda d: d["exempt"][1].update(reason="Apache-2.0 elected (pom OR)")),
                                        "test_source_policy_has_exactly_hosts_always_exempt"),
    "the javassist entry dropped": (pol(lambda d: d["exempt"].pop(1)), "test_exempt_entries_jna_and_javassist"),
    "jaxb-api exempted too": (pol(lambda d: d["exempt"].append(dict(d["exempt"][0], package=
                                                                    "pkg:maven/javax.xml.bind/jaxb-api@2.2.12"))),
                              "test_exempt_entries_jna_and_javassist"),
    "an always-matched package exempted (openjdk)": (pol(lambda d: d["exempt"].append(dict(d["exempt"][0],
                                                                                         package=OPENJDK))),
                                                     "test_real_rows_with_the_committed_exempt"),
    "the entry under image neo4j (pre-U4b name)": (pol(lambda d: d["exempt"][0].update(image="neo4j")),
                                                   "test_source_policy_has_exactly_hosts_always_exempt"),
}
for name, (text, method) in POLICY_MUTANTS.items():
    row("policy", name, True, run_test(BY_NAME[method], method, TARGET_MOD, policy_file(text)))

bad = [r for r in rows if not r[3]]
print(f"\nU6 controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
