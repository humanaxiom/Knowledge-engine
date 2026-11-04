"""platform-sbom U7d RED: controls for the U7d tests (U7d* classes in
tests/test_sources_resolve.py and tests/test_sources_lock.py, the changed U6
host test, and the U7a/U7b/U7c tests U7d changes).

Never writes the repository. It builds a temporary root with the U7d targets
(docs/evidence/platform-sbom/u7d/target-*: the resolver, sbom_check.py,
sources_lock.sh and source-policy.json) in place and runs real test methods
on the targets, on the U7c baseline (the SAVED u7c/r1-target-* files, equal to
86f7831, with the committed policy and script) and on mutants of each target.
Each "must fail" row names the one test method that must fail. Exit 1 if any
row is unexpected.

Usage (in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7d/u7d_controls.py [--base repo]
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

from tests import test_offline_bundle as tob  # noqa: E402
from tests import test_sbom_obligations as tso  # noqa: E402
from tests import test_sources_lock as tsl  # noqa: E402
from tests import test_sources_resolve as tsr  # noqa: E402

HERE = Path(__file__).resolve().parent
U7C = HERE.parent / "u7c"
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGETS = {"scripts/sources_resolve.py": "target-sources_resolve.py",
           "scripts/sources_lock.sh": "target-sources_lock.sh",
           "scripts/sbom_check.py": "target-sbom_check.py",
           "docker/source-policy.json": "target-source-policy.json"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml",
        "docker-compose.sources.yml", ".env.example", ".gitignore", ".dockerignore", "pyproject.toml", "uv.lock",
        "LICENSE", "NOTICE.md", "config", "licenses", "docs/quickstart.md", ".github", "tests/fixtures"]
WORK = Path(tempfile.mkdtemp(prefix="u7d-controls-"))
rows: list[tuple[str, str, str, bool]] = []


def head(rel: str) -> str:
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


SRC = {rel: (REPO / rel if BASE_REPO else HERE / name).read_text(encoding="utf-8") for rel, name in TARGETS.items()}
BASELINE = {"scripts/sources_resolve.py": (U7C / "r1-target-sources_resolve.py").read_text(encoding="utf-8"),
            "scripts/sbom_check.py": (U7C / "r1-target-sbom_check.py").read_text(encoding="utf-8"),
            "scripts/sources_lock.sh": head("scripts/sources_lock.sh"),
            "docker/source-policy.json": head("docker/source-policy.json")}


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
    spec = importlib.util.spec_from_file_location(f"u7d_check_{path.parent.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_test(cls: type, method: str, root: Path) -> list[str]:
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    check = module_at(root / "scripts" / "sbom_check.py")
    pol = root / "docker" / "source-policy.json"
    patches = [mock.patch.object(tsr, "RESOLVER", root / "scripts" / "sources_resolve.py"),
               mock.patch.object(tsr, "LOCK_SH", root / "scripts" / "sources_lock.sh"),
               mock.patch.object(tsr, "SOURCES_COMPOSE", root / "docker-compose.sources.yml"),
               mock.patch.object(tsr, "ROOT", root), mock.patch.object(tob, "ROOT", root),
               mock.patch.object(tsl, "ROOT", root), mock.patch.object(tsl, "POLICY", pol),
               mock.patch.object(tso, "POLICY", pol),
               mock.patch.object(tsr, "load_sbom_check", lambda m=check: m),
               mock.patch.object(tsl, "load_sbom_check", lambda m=check: m),
               mock.patch.object(tsl, "fn", lambda name, m=check: getattr(m, name))]
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


U7D_CLASSES = [tsr.U7dRetryConstantsTest, tsr.U7dRetryTest, tsr.U7dCarriedTest, tsr.U7dPgdgRouteTest,
               tsr.U7dLockNeedsTest, tsr.U7dCoverageTest, tsr.U7dScriptStaticTest, tsl.U7dPgdgLockRulesTest,
               tsl.U7dApkSegmentNameTest]
CHANGED = [(tso.PolicyU6SchemaTest, "test_hosts_are_the_fetch_hosts"),
           (tsr.U7cCarriedTest, "test_pgdg_is_no_longer_skipped"),
           (tsr.ReworkR1MainTest, "test_a_body_error_is_one_fail_line"),
           (tsl.LockSchemaTest, "test_good_full_lock_passes"),
           (tsl.ReworkR1BindingTest, "test_pgdg_files_need_the_tenth_host")]
NEW = [t for cls in U7D_CLASSES for t in own(cls)] + CHANGED
OLD_CLASSES = (tsr.ResolverHopsTest, tsr.ResolverParsersTest, tsr.ResolverRoutesTest, tsr.ResolverMergeTest,
               tsr.ResolverMainTest, tsr.LockNeedsTest, tsr.SourcesComposeTest, tsr.SourcesLockScriptStaticTest,
               tsr.SourcesLockScriptRunTest, tsr.ReworkR1TransportTest, tsr.ReworkR1MainTest,
               tsr.ReworkR1RealOpenerTest, tsr.ReworkR1HopRulesTest, tsr.ReworkR1PypiScopeTest, tsr.ReworkR1KeysTest,
               tsr.ReworkR1LockScriptRunTest, tsr.U7cDebRouteTest, tsr.U7cApkRouteTest, tsr.U7cCoverageTest,
               tsr.U7cCarriedTest, tsr.U7cLockNeedsTest, tsr.U7cLockScriptRunTest, tsr.ReworkR1U7cApkbuildTest,
               tsr.ReworkR1U7cDscTest, tsr.ReworkR1U7cApkbuildAssignTest, tsr.ReworkR1U7cListingTest,
               tsr.ReworkR1U7cApiUrlResolverTest)
OLD = [t for cls in OLD_CLASSES for t in every(cls) if t not in CHANGED]
U7A = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.LockCheckCliTest,
                     tsl.ReworkR1BindingTest, tsl.ReworkR1PendingNeo4jCliTest, tsl.U7cApkLockRulesTest,
                     tsl.ReworkR1U7cApkbuildPathTest, tsl.ReworkR1U7cApiUrlTest, tso.PolicyU6SchemaTest)
       for t in own(cls) if t not in CHANGED]
# Guards: U7d rows the U7c baseline already passes (each keeps a behaviour U7d
# must not lose; a mutant row or the target row covers it).
GUARDS = {(tsr.U7dRetryConstantsTest, "test_fetch_retries_nothing_by_default"),
          (tsr.U7dRetryTest, "test_never_retried"),
          (tsr.U7dCarriedTest, "test_a_dsc_with_its_first_entry_on_the_field_line")}

TROOT = make_root(dict(SRC))
row("target", f"TARGET: the {len(NEW)} U7d tests", False, [p for c, m in NEW for p in run_test(c, m, TROOT)])
row("target", f"TARGET: the {len(OLD)} U7b and U7c tests", False, [p for c, m in OLD for p in run_test(c, m, TROOT)])
row("target", f"TARGET: {len(U7A)} U7a/U7c lock and U6 policy tests", False,
    [p for c, m in U7A for p in run_test(c, m, TROOT)])

BROOT = make_root(dict(BASELINE))
for cls, method in NEW:
    guard = (cls, method) in GUARDS
    row("u7c", f"U7c baseline: {cls.__name__}.{method}" + (" (guard)" if guard else ""), not guard,
        run_test(cls, method, BROOT))

RES, SH, CHK, POL = "scripts/sources_resolve.py", "scripts/sources_lock.sh", "scripts/sbom_check.py", \
    "docker/source-policy.json"
RC, RT, CT, PR, LN, CV, ST = (tsr.U7dRetryConstantsTest, tsr.U7dRetryTest, tsr.U7dCarriedTest, tsr.U7dPgdgRouteTest,
                              tsr.U7dLockNeedsTest, tsr.U7dCoverageTest, tsr.U7dScriptStaticTest)
PL, SN = tsl.U7dPgdgLockRulesTest, tsl.U7dApkSegmentNameTest
MUTANTS: dict[str, tuple[str, Callable[[str], str], type, str]] = {
    # retry (R1-R6, security 3-6)
    "retry: none at all": (RES, swap("RETRIES = 3\n", "RETRIES = 0\n"), RT, "test_the_lines_and_waits"),
    "retry: fetch() retries by default": (RES, swap(
        "def fetch(url: str, allow: set[str], *, retries: int = 0, **kw: Any) -> Response | None:",
        "def fetch(url: str, allow: set[str], *, retries: int = 3, **kw: Any) -> Response | None:"),
        RC, "test_fetch_retries_nothing_by_default"),
    "retry: other waits": (RES, swap("RETRY_WAITS = (10, 30, 60)", "RETRY_WAITS = (1, 2, 3)"), RT, "test_the_lines_and_waits"),
    "retry: 5xx not retried": (RES, swap("        if 500 <= r.status < 600:  # R2", "        if False:  # R2"),
                               RT, "test_retried_statuses"),
    "retry: 4xx retried too": (RES, swap("        if 500 <= r.status < 600:  # R2", "        if 400 <= r.status < 600:  # R2"),
                               RT, "test_never_retried"),
    "retry: other OSErrors retried": (RES, swap(
        '    return ResolveError(f"{host}: {type(exc).__name__}: {_clean(url)}")',
        '    return _Retryable(f"{host}: {type(exc).__name__}: {_clean(url)}", "x")'), RT, "test_never_retried"),
    "retry: the query printed": (RES, swap('    return _clean(head) + ("?<query omitted>" if sep else "")',
                                           "    return _clean(url)"), RT, "test_a_query_is_omitted_from_retry_lines"),
    "retry: no run budget": (RES, swap('                if _RUN["retries"] >= RUN_RETRIES:', "                if False:"),
                             RT, "test_the_run_budget"),
    "retry: no run deadline": (RES, swap('    if _RUN["active"] and time.monotonic() - _RUN["start"] + ahead > RUN_DEADLINE:',
                                         "    if False:"), RT, "test_the_run_deadline"),
    "retry: the wait not checked against the run deadline": (RES, swap(
        "            wait = RETRY_WAITS[n]\n            _run_clock(wait)\n", "            wait = RETRY_WAITS[n]\n"),
        RT, "test_the_run_deadline"),
    "retry: the pause skipped on retries": (RES, swap(
        "        doc = json.loads(text(url, allow, TEXT_LIMIT, before=_snapshot_wait))",
        "        _snapshot_wait()\n        doc = json.loads(text(url, allow, TEXT_LIMIT))"),
        RT, "test_the_snapshot_pause_holds_for_retries"),
    # parsers
    "deb822: a non-field line skipped": (RES, swap(
        "        if not ok:\n            raise ResolveError(f\"{_clean(label)}: line {no} is not a field or continuation\")",
        "        if not ok:\n            current = None\n            continue"), CT, "test_a_line_that_is_not_a_field"),
    "deb822: duplicates across stanzas refused": (RES, swap(
        "            fields, seen, current = {}, set(), None", "            fields, current = {}, None"),
        CT, "test_parse_deb822"),
    # pgdg route
    "pgdg: no route (skipped)": (RES, swap('ROUTES = ("temurin", "maven", "pypi", "neo4j", "deb", "apk", "pgdg")',
                                           'ROUTES = ("temurin", "maven", "pypi", "neo4j", "deb", "apk")'),
                                 PR, "test_the_entries"),
    "pgdg: Sources not bound to Release (sha)": (RES, swap("        if h.hexdigest() != want_sha:", "        if False:"),
                                                 PR, "test_failures"),
    "pgdg: Sources not bound to Release (size)": (RES, swap("        if size != want_size:", "        if False:"),
                                                  PR, "test_failures"),
    "pgdg: two Release entries accepted": (RES, swap("    if len(hits) > 1:\n        raise ResolveError(\"Release lists",
                                                     "    if False:\n        raise ResolveError(\"Release lists"),
                                           PR, "test_failures"),
    "pgdg: the 64 MiB cap dropped": (RES, swap("            if size > SOURCES_CAP:", "            if False:"),
                                     PR, "test_the_caps"),
    "pgdg: Directory not checked": (RES, swap('    if stanza.get("Directory") != f"pool/main/{p}/{src}":', "    if False:"),
                                    PR, "test_failures"),
    "pgdg: the .dsc sha256 not compared": (RES, swap('    if digests["sha256"] != listed[dsc][0]:', "    if False:"),
                                           PR, "test_failures"),
    "pgdg: Sources and .dsc not cross-checked": (RES, swap(
        "    if {n: (h, z) for h, z, n in sha256s} != {n: v for n, v in listed.items() if n != dsc}:", "    if False:"),
        PR, "test_failures"),
    "pgdg: the pool letter always the first": (RES, swap(
        '    return src[:4] if src.startswith("lib") else src[:1]', "    return src[:1]"), PR, "test_the_pool_rule"),
    "pgdg: InRelease not written": (RES, swap(
        "        for suite, raw in sorted(_PGDG_INRELEASE.items()):", "        for suite, raw in []:"),
        PR, "test_main_writes_the_inrelease"),
    "pgdg: the route not checked": (RES, swap(
        "            raise ResolveError(f\"pgdg {key}: route is malformed ({field})\")", "            pass"),
        PR, "test_a_malformed_route"),
    # lock side and lock-needs
    "lock: pgdg host dropped": (CHK, swap('"pgdg": (PGDG_HOST,)', '"pgdg": ()'), PL, "test_the_good_entry"),
    "lock: suite not required": (CHK, swap(' | ({"suite"} if kind == "pgdg" else set())', ""), PL, "test_bad_entries"),
    "lock: suite any text": (CHK, swap('PGDG_SUITE_RE = re.compile(r"[a-z]+-pgdg-archive")',
                                       'PGDG_SUITE_RE = re.compile(r".+")'), PL, "test_bad_entries"),
    "lock: the pool path not exact": (CHK, swap("        if path != want_path:", "        if False:"),
                                      PL, "test_bad_entries"),
    "lock: pgdg from texts not checked": (CHK, swap(
        '            if fup.get("alg") != "sha256" or fup.get("from") != frm:', '            if fup.get("alg") != "sha256":'),
        PL, "test_bad_entries"),
    "lock: R1-N1 dropped": (CHK, swap("    if not all(LOCK_FILE_NAME_RE.fullmatch(x) for x in parts[2:-1]):  # U7c review R1-N1",
                                      "    if False:  # U7c review R1-N1"), SN, "test_middle_segments"),
    "lock-needs: the suite always bookworm": (CHK, swap(
        'PGDG_SUITES = {12: "bookworm", 13: "trixie"}', 'PGDG_SUITES = {12: "bookworm", 13: "bookworm"}'),
        LN, "test_trixie_and_unknown"),
    # policy and script
    "policy: nine hosts": (POL, swap('"apt-archive.postgresql.org", ', ""), tso.PolicyU6SchemaTest,
                           "test_hosts_are_the_fetch_hosts"),
    "script: the InRelease not copied": (SH, swap('    cp -- "$f" docs/evidence/platform-sbom/u7d/\n', "    :\n"),
                                         ST, "test_the_inrelease_is_copied"),
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
print(f"\nU7d controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
