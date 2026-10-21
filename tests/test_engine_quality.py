"""platform-config PS-1.6 (quality gates) and PS-1.8 (Python 3.12 pinned).

Static checks of pyproject.toml, uv.lock and scripts/test.sh. The recorded
RED runs that show each threshold failing (PS-1.6) are evidence, not tests.
"""

from __future__ import annotations

import re
import tomllib
import unittest

from tests.engine_support import ROOT

PYPROJECT = ROOT / "pyproject.toml"
TEST_SH = ROOT / "scripts" / "test.sh"
FIRST_PARTY = ("engine", "harness_telemetry")


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _code_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def _dep_names(deps: list[str]) -> set[str]:
    return {re.split(r"[\s<>=!~\[;]", d, maxsplit=1)[0].lower().replace("_", "-") for d in deps}


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _clause_allows(clause: str, version: tuple[int, int, int]) -> bool:
    """One PEP 440 clause against a final release. Unknown syntax fails loudly."""
    match = re.fullmatch(r"(==|!=|>=|<=|>|<)(\d+(?:\.\d+)*)(\.\*)?", clause)
    if match is None:
        raise AssertionError(f"unsupported requires-python clause: {clause!r}")
    op, number, wildcard = match.groups()
    bound = _version(number)
    if wildcard:
        if op not in ("==", "!="):
            raise AssertionError(f"wildcard only valid with == or !=: {clause!r}")
        same = version[:len(bound)] == bound
        return same if op == "==" else not same
    padded = bound + (0,) * (3 - len(bound))
    return {
        "==": version == padded, "!=": version != padded,
        ">=": version >= padded, "<=": version <= padded,
        ">": version > padded, "<": version < padded,
    }[op]


def _specifier_allows(spec: str, version: tuple[int, int, int]) -> bool:
    clauses = [c for c in spec.replace(" ", "").split(",") if c]
    return bool(clauses) and all(_clause_allows(c, version) for c in clauses)


# Probe releases: every 3.12.x must be allowed, everything else refused.
_ALLOWED = [(3, 12, 0), (3, 12, 1), (3, 12, 9), (3, 12, 99)]
_REFUSED = [(2, 7, 18), (3, 0, 0), (3, 11, 0), (3, 11, 99), (3, 13, 0),
            (3, 13, 5), (3, 14, 0), (4, 0, 0), (4, 12, 0)]


class PythonPinTest(unittest.TestCase):
    def test_python_pinned_to_312(self):
        # pyproject.toml is hand-written source: the literal is pinned.
        self.assertEqual(_pyproject()["project"]["requires-python"].replace(" ", ""),
                         ">=3.12,<3.13")
        # uv.lock is a generated artifact and must not be hand-edited
        # (orchestrator ruling, 2026-10-18, platform-config; CLAUDE.md
        # "Generated artifacts"). uv normalises the constraint (e.g. to
        # "==3.12.*"), so criterion 10 / PS-1.8 is checked by equivalence:
        # the lock's specifier allows 3.12.x and nothing else.
        lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
        match = re.search(r'^requires-python\s*=\s*"([^"]+)"', lock, re.M)
        self.assertIsNotNone(match, "uv.lock has no requires-python")
        spec = match.group(1)
        for version in _ALLOWED:
            with self.subTest(allowed=version):
                self.assertTrue(_specifier_allows(spec, version),
                                f"uv.lock requires-python {spec!r} refuses {version}")
        for version in _REFUSED:
            with self.subTest(refused=version):
                self.assertFalse(_specifier_allows(spec, version),
                                 f"uv.lock requires-python {spec!r} allows {version}")

    def test_pin_equivalence_check_accepts_uv_forms_and_rejects_others(self):
        """Guards the checker above: uv's forms pass, looser/other pins fail."""
        def pins_312(spec: str) -> bool:
            return (all(_specifier_allows(spec, v) for v in _ALLOWED)
                    and not any(_specifier_allows(spec, v) for v in _REFUSED))

        for spec in ("==3.12.*", ">=3.12,<3.13", ">=3.12, <3.13", ">=3.12.0,<3.13.0"):
            with self.subTest(equivalent=spec):
                self.assertTrue(pins_312(spec))
        for spec in (">=3.12", "==3.11.*", ">=3.11,<3.13", ">=3.12,<3.14", "==3.12.1"):
            with self.subTest(not_equivalent=spec):
                self.assertFalse(pins_312(spec))


class DependenciesTest(unittest.TestCase):
    def test_engine_dependencies_declared(self):
        project = _pyproject()
        runtime = _dep_names(project["project"].get("dependencies", []))
        for name in ("pydantic-settings", "pyyaml", "httpx"):
            with self.subTest(runtime=name):
                self.assertIn(name, runtime)
        dev = _dep_names(project.get("dependency-groups", {}).get("dev", []))
        for name in ("coverage", "mypy", "types-pyyaml"):
            with self.subTest(dev=name):
                self.assertIn(name, dev)
        packages = project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        for pkg in FIRST_PARTY:
            with self.subTest(wheel=pkg):
                self.assertIn(pkg, packages)


class QualityGateTest(unittest.TestCase):
    def test_test_sh_enforces_coverage_and_mypy(self):
        tool = _pyproject().get("tool", {})

        coverage = tool.get("coverage", {})
        run = coverage.get("run", {})
        report = coverage.get("report", {})
        self.assertIs(run.get("branch"), True, "branch coverage must be on")
        self.assertEqual(sorted(run.get("source", [])), sorted(FIRST_PARTY))
        self.assertEqual(report.get("fail_under"), 80)

        mypy = tool.get("mypy", {})
        self.assertIs(mypy.get("strict"), True)
        files = mypy.get("files", [])
        files = [files] if isinstance(files, str) else files
        self.assertEqual(sorted(f.rstrip("/") for f in files), sorted(FIRST_PARTY))
        self.assertIn("pydantic.mypy", mypy.get("plugins", []))

        lines = _code_lines(TEST_SH.read_text(encoding="utf-8"))
        body = "\n".join(lines)
        for step in (r"coverage\s+run\s+-p\b", r"coverage\s+combine\b",
                     r"coverage\s+report\b", r"\bmypy\b"):
            with self.subTest(step=step):
                matching = [line for line in lines if re.search(step, line)]
                self.assertTrue(matching, f"test.sh does not run {step}")
                for line in matching:
                    self.assertRegex(line, r"\buv\s+run\s+--locked\b", line)
        # Every unittest invocation runs under coverage.
        for line in lines:
            if re.search(r"-m\s+unittest\b", line):
                with self.subTest(unittest_line=line):
                    self.assertRegex(line, r"coverage\s+run\s+-p\b")
        # The report runs after the tests, and mypy is not skipped in fast mode.
        self.assertLess(body.find("unittest"), body.find("coverage report"))
        self.assertNotRegex(body, r'"\$mode"\s*=\s*"full"[^\n]*\n[^\n]*\bmypy\b')

    def test_tests_excluded_from_measurement(self):
        tool = _pyproject().get("tool", {})
        self.assertNotIn("tests", tool.get("coverage", {}).get("run", {}).get("source", []))
        files = tool.get("mypy", {}).get("files", [])
        self.assertNotIn("tests", files)


if __name__ == "__main__":
    unittest.main()
