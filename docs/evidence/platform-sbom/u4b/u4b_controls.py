"""platform-sbom U4b RED: controls for tests/test_neo4j_image.py (PSC-26).

Never writes the repository. It builds a temporary checkout holding the
files the harnesses read, with the U4b targets (docs/evidence/platform-sbom/
u4b/target-*) in place, and runs:
  A. the static checks of tests/test_neo4j_image.py on the targets and on
     mutants of them;
  B. the full-check logic tests (Neo4j*CheckTest, Neo4jCheckerCliTest) on
     target-sbom_check.py and on mutants of its logic;
  C. the smoke tests (SmokeNoFleetPluginTest) on target-smoke.sh and mutants;
  D. the offline check tests (OfflineKeNeo4jTest) on target-offline_check.sh
     and mutants.
Rows: "must pass" or "must fail"; exit 1 if any row is unexpected.

Usage (needs bash, git and jq: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u4b/u4b_controls.py [--base repo]
`--base repo` uses the repository's own files instead of the targets (GREEN).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
import yaml  # noqa: E402

from tests import neo4j_support as ns  # noqa: E402
from tests import test_neo4j_image as tni  # noqa: E402
from tests import test_offline_check as toc  # noqa: E402
from tests import test_stack_scripts as tss  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGETS = {"docker/neo4j.Dockerfile": "target-neo4j.Dockerfile", "docker-compose.yml": "target-docker-compose.yml",
           "scripts/build.sh": "target-build.sh", "scripts/build.ps1": "target-build.ps1",
           "NOTICE.md": "target-NOTICE.md", "docker/source-policy.json": "target-source-policy.json",
           "scripts/offline_check.sh": "target-offline_check.sh", "scripts/smoke.sh": "target-smoke.sh",
           "scripts/sbom_check.py": "target-sbom_check.py"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml",
        "docker-compose.offline.yml", ".env.example", "NOTICE.md", "licenses", "config", "uv.lock", "pyproject.toml",
        "tests/test_notice_ke_app.py", ".github"]


def make_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="u4b-controls-"))
    for rel in COPY:
        src = REPO / rel
        if src.is_dir():
            shutil.copytree(src, root / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / rel)
    if not BASE_REPO:
        for rel, target in TARGETS.items():
            shutil.copyfile(HERE / target, root / rel)
    return root


ROOT = make_root()
rows: list[tuple[str, str, str, bool]] = []


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def u4(rel: str) -> str:
    """The file as committed at U4 (HEAD), whatever the working tree holds."""
    import subprocess
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"], capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout


def row(group: str, name: str, must_fail: bool, problems: list[str]) -> None:
    failed = bool(problems)
    ok = failed == must_fail
    rows.append((group, name, "must fail" if must_fail else "must pass", ok))
    detail = problems[0][:110] if problems else "no problem"
    print(f"{'ok ' if ok else 'BAD'} [{group}] {name:<62} {'must fail' if must_fail else 'must pass'} | {detail}")


def swap(old: str, new: str) -> Callable[[str], str]:
    def change(t: str) -> str:
        if old not in t:
            raise AssertionError(f"mutant anchor not found: {old[:60]!r}")
        return t.replace(old, new, 1)
    return change


def run_test(cls: type, method: str, patches: list[Any]) -> list[str]:
    """Run one test method under the patches; [] if it passed, else the failure."""
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    with mock.patch.multiple("tests.test_neo4j_image", ROOT=ROOT), mock.patch.object(tss, "ROOT", ROOT), \
            mock.patch.object(toc, "ROOT", ROOT), mock.patch.object(toc, "OFFLINE_CHECK", ROOT / "scripts" /
                                                                    "offline_check.sh"):
        for p in patches:
            p.start()
        try:
            suite.run(result)
        finally:
            for p in patches:
                p.stop()
    bad = result.failures + result.errors
    return [str(b[1]).strip().splitlines()[-1] for b in bad]


# ---- A. static checks ---------------------------------------------------------
dock = text("docker/neo4j.Dockerfile")
row("dockerfile build", "TARGET", False, tni.dockerfile_build_problems(dock))
for name, m in {"no rm of products/": swap("RUN rm -rf /var/lib/neo4j/products\n", ""),
                "unpinned FROM": swap(ns.OFFICIAL_REF, "neo4j:5-community"),
                "no flatten (FROM scratch -> FROM runtime)": swap("FROM scratch", "FROM runtime"),
                "apt-get install in the build stage": swap("RUN rm -rf /var/lib/neo4j/products",
                                                          "RUN rm -rf /var/lib/neo4j/products && apt-get install -y jq"),
                "COPY --chown on the flatten": swap("COPY --from=runtime / /", "COPY --chown=7474 --from=runtime / /")
                }.items():
    row("dockerfile build", name, True, tni.dockerfile_build_problems(m(dock)))
row("dockerfile config", "TARGET", False, tni.dockerfile_config_problems(dock))
for name, m in {"no EXPOSE": swap("EXPOSE 7473 7474 7687\n", ""), "USER neo4j": swap("WORKDIR", "USER neo4j\nWORKDIR"),
                "Env order swapped (LANG first)": swap("ENV PATH=", "ENV LANG=C.UTF-8 \\\n    PATH="),
                "a LABEL": swap("WORKDIR", "LABEL a=b\nWORKDIR"), "no CMD": swap('CMD ["neo4j"]\n', "")}.items():
    row("dockerfile config", name, True, tni.dockerfile_config_problems(m(dock)))
compose = text("docker-compose.yml")
row("compose", "TARGET", False, tni.compose_neo4j_problems(yaml.safe_load(compose), compose))
for name, m in {"official image (U4)": swap("ke-neo4j:${KE_IMAGE_TAG:-local}", ns.OFFICIAL_REF),
                "no build": swap("    build:\n      context: .\n      dockerfile: docker/neo4j.Dockerfile\n", ""),
                "retries 18 -> 3": swap("      retries: 18\n", "      retries: 3\n")}.items():
    mutated = m(compose)
    row("compose", name, True, tni.compose_neo4j_problems(yaml.safe_load(mutated), mutated))
inputs = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8", errors="replace")
          for p in sorted(ROOT.glob("docker-compose*.yml")) + sorted(
              q for top in ("docker", "scripts", ".github") for q in (ROOT / top).rglob("*") if q.is_file())}
row("official ref", "TARGET build inputs", False, tni.official_ref_problems(inputs))
row("official ref", "offline_check.sh with the literal ref", True, tni.official_ref_problems(
    dict(inputs, **{"scripts/offline_check.sh": inputs["scripts/offline_check.sh"] + f"\n# {ns.OFFICIAL_REF}\n"})))
for script in ("build.sh", "build.ps1"):
    row("build scripts", f"TARGET {script}", False, tni.build_script_problems(script, text(f"scripts/{script}")))
    row("build scripts", f"U4 {script} (HEAD)", True,
        tni.build_script_problems(script, u4(f"scripts/{script}")))
row("policy", "TARGET", False, tni.policy_problems(json.loads(text("docker/source-policy.json"))["always"]))
row("policy", "U4 policy (HEAD)", True,
    tni.policy_problems(json.loads(u4("docker/source-policy.json"))["always"]))
base = ns.dockerfile_base_ref(ROOT / "docker" / "neo4j.Dockerfile") or ""
row("notice", "TARGET", False, tni.notice_neo4j_problems(text("NOTICE.md"), base))
row("notice", "U4 NOTICE.md (HEAD)", True,
    tni.notice_neo4j_problems(u4("NOTICE.md"), base))
row("notice", "TARGET saying `used unmodified`", True, tni.notice_neo4j_problems(
    text("NOTICE.md").replace("Neo4j Community itself is unmodified", "Neo4j Community, used unmodified,"), base))

# ---- B. full-check logic: target-sbom_check.py and mutants of its logic --------
CHECK_SRC = text("scripts/sbom_check.py")


def module_of(src: str) -> ModuleType:
    path = Path(tempfile.mkdtemp(prefix="u4b-check-")) / "sbom_check.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"u4b_mutant_{path.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up
    spec.loader.exec_module(mod)
    return mod


LOGIC = [(tni.Neo4jConfigCheckTest, "test_neo4j_config_check_logic"),
         (tni.Neo4jTarCheckTest, "test_neo4j_tar_check_logic"),
         (tni.Neo4jSbomCheckTest, "test_neo4j_sbom_check_logic"),
         (tni.Neo4jTreeCheckTest, "test_neo4j_tree_check_logic")]


def logic_rows(label: str, src: str, must_fail: dict[str, bool]) -> None:
    mod = module_of(src)
    for cls, method in LOGIC:
        problems = run_test(cls, method, [mock.patch.object(tni, "load_sbom_check", lambda m=mod: m)])
        row("logic", f"{label}: {method}", must_fail.get(method, False), problems)


logic_rows("TARGET", CHECK_SRC, {})
row("logic", "TARGET: test_neo4j_checker_cli", False, run_test(tni.Neo4jCheckerCliTest, "test_neo4j_checker_cli", []))
for name, (m, method) in {
    "config: Env compared as a set": (swap("        if want != have:\n", "        if (sorted(want) if key == 'Env' and want "
                                                                         "else want) != (sorted(have) if key == 'Env' "
                                                                         "and have else have):\n"),
                                       "test_neo4j_config_check_logic"),
    "config: User not compared": (swap('("Entrypoint", "Cmd", "Env", "User", ', '("Entrypoint", "Cmd", "Env", '),
                                  "test_neo4j_config_check_logic"),
    "tar: only the last layer read": (swap("            for name in layers:\n", "            for name in layers[-1:]:\n"),
                                      "test_neo4j_tar_check_logic"),
    "tar: only the first manifest entry": (swap("        for entry in manifest:\n", "        for entry in manifest[:1]:\n"),
                                           "test_neo4j_tar_check_logic"),
    "tar: whiteouts not checked": (swap('        elif base == ".wh.products"', '        elif False and base == ".wh.products"'),
                                   "test_neo4j_tar_check_logic"),
    "sbom: purl only, not the name": (swap('                or FLEET in str(pkg.get("name", "")).lower()):', "                ):"),
                                      "test_neo4j_sbom_check_logic"),
    "sbom: exact version 1.2.0 only": (swap("n.split(\"@\", 1)[0].split(\"?\", 1)[0] == FLEET_PURL", "n.split(\"?\", 1)[0] == "
                                                                                                    "FLEET_PURL + "
                                                                                                    "'@1.2.0'"),
                                       "test_neo4j_sbom_check_logic"),
    "sbom: Temurin not required": (swap('                  ("the Temurin OpenJDK", "pkg:generic/oracle/openjdk"))', ")"),
                                   "test_neo4j_sbom_check_logic"),
    "tree: mode not compared": (swap("        if tuple(have) != tuple(want):", "        if tuple(have)[:1] + tuple(have)[2:]"
                                                                             " != tuple(want)[:1] + tuple(want)[2:]:"),
                                "test_neo4j_tree_check_logic"),
    "tree: added paths allowed": (swap("    for rel in sorted(set(image) - set(official)):\n",
                                       "    for rel in sorted(set(image) - set(official) - set(image)):\n"),
                                  "test_neo4j_tree_check_logic"),
}.items():
    mod = module_of(m(CHECK_SRC))
    cls = {c[1]: c[0] for c in LOGIC}[method]
    row("logic", name, True, run_test(cls, method, [mock.patch.object(tni, "load_sbom_check", lambda m=mod: m)]))

# ---- C. smoke ----------------------------------------------------------------------
SMOKE = text("scripts/smoke.sh")
SMOKE_TESTS = ("test_smoke_checks_no_fleet_plugin_in_neo4j", "test_smoke_fails_when_the_fleet_plugin_is_in_neo4j",
               "test_smoke_never_evaluates_the_neo4j_output")


def smoke_rows(label: str, src: str, must_fail: bool) -> None:
    (ROOT / "scripts" / "smoke.sh").write_text(src, encoding="utf-8", newline="\n")
    try:
        problems = []
        for method in SMOKE_TESTS:
            problems += [f"{method}: {p}" for p in run_test(tni.SmokeNoFleetPluginTest, method, [])]
        row("smoke", label, must_fail, problems)
    finally:
        (ROOT / "scripts" / "smoke.sh").write_text(SMOKE, encoding="utf-8", newline="\n")


smoke_rows("TARGET", SMOKE, False)
for name, m in {
    "no -xdev": swap("find / -xdev ", "find / "),
    "no control path (compare with empty)": swap(" -o -path /var/lib/neo4j/LICENSE.txt", "").__call__,
    "first line only (read -r)": swap('[ "$fleet_out" = /var/lib/neo4j/LICENSE.txt ]',
                                      'read -r fleet_first <<< "$fleet_out"; [ "$fleet_first" = /var/lib/neo4j/LICENSE.txt ]'),
    "the exec status ignored": swap("-print)\" || {", "-print)\" || true; true || {"),
    "the output evaluated (eval echo)": swap('[ "$fleet_out" = /var/lib/neo4j/LICENSE.txt ] || {',
                                             'fleet_out="$(eval echo "$fleet_out")"\n[ "$fleet_out" = /var/lib/neo4j/LICENSE.txt ] || {'),
    "the step removed (U4 smoke, HEAD)": lambda t: u4("scripts/smoke.sh"),
}.items():
    if name == "no control path (compare with empty)":
        src = swap(" -o -path /var/lib/neo4j/LICENSE.txt", "")(SMOKE).replace(
            '[ "$fleet_out" = /var/lib/neo4j/LICENSE.txt ]', '[ -z "$fleet_out" ]')
    else:
        src = m(SMOKE)
    smoke_rows(name, src, True)

# ---- D. offline check ------------------------------------------------------------------
OFFLINE = text("scripts/offline_check.sh")
OFFLINE_TESTS = ("test_offline_check_runs_ke_neo4j_check", "test_offline_check_fails_on_ke_neo4j_problems")


def offline_rows(label: str, src: str, must_fail: bool) -> None:
    (ROOT / "scripts" / "offline_check.sh").write_text(src, encoding="utf-8", newline="\n")
    try:
        problems = []
        for method in OFFLINE_TESTS:
            problems += [f"{method}: {p}" for p in run_test(tni.OfflineKeNeo4jTest, method, [])]
        row("offline", label, must_fail, problems)
    finally:
        (ROOT / "scripts" / "offline_check.sh").write_text(OFFLINE, encoding="utf-8", newline="\n")


offline_rows("TARGET", OFFLINE, False)
for name, m in {
    "the step removed (U4 offline_check.sh, HEAD)": lambda t: u4("scripts/offline_check.sh"),
    "no --network none on the checker": swap("docker run --rm --network none --read-only --cap-drop ALL --security-opt "
                                             "no-new-privileges --pull never \\\n  --user \"$(id -u):$(id -g)\" --label "
                                             "\"com.docker.compose.project=${project}-sbomcheck\" \\\n  -v \"$repo_host/"
                                             "scripts/sbom_check.py:/opt/ke/sbom_check.py:ro\" \\\n  -v \"$(hostpath \"$PWD/"
                                             "$bundle_rel/app/sboms\"):/sboms:ro\" \\\n  -v \"$(hostpath \"$PWD/$bundle_rel/"
                                             "images\")",
                                             "docker run --rm --read-only --cap-drop ALL --security-opt "
                                             "no-new-privileges --pull never \\\n  --user \"$(id -u):$(id -g)\" --label "
                                             "\"com.docker.compose.project=${project}-sbomcheck\" \\\n  -v \"$repo_host/"
                                             "scripts/sbom_check.py:/opt/ke/sbom_check.py:ro\" \\\n  -v \"$(hostpath \"$PWD/"
                                             "$bundle_rel/app/sboms\"):/sboms:ro\" \\\n  -v \"$(hostpath \"$PWD/$bundle_rel/"
                                             "images\")"),
    "a failed check ignored": swap('  || die "the ke-neo4j check failed', '  || true; [ 1 ] || die "the ke-neo4j check failed'),
    "the official image pulled by tag": swap('docker pull "$neo4j_base"', 'docker pull "${neo4j_base%@*}"'),
    "the SBOM not passed (tar and config only)": swap("  --sbom /sboms/ke-neo4j.spdx.json --tar", "  --sbom /neo4j/config-as-sbom.json --tar"),
}.items():
    offline_rows(name, m(OFFLINE), True)

# ---- E. the PS-1.2 exemption for the neo4j EXPOSE line (orchestrator U4b ruling 1) ----
from tests import test_engine_hardcoded as teh  # noqa: E402
import subprocess  # noqa: E402

subprocess.run(["git", "init", "-q", str(ROOT)], check=True)  # the repository scan lists files with git

SCAN_SRC = (REPO / "tests" / "hardcoded_scan.py").read_text(encoding="utf-8")
EXEMPT_TESTS = [(teh.ScannerContractTest, "test_dockerfile_exemption_covers_only_its_instruction_line"),
                (teh.ScannerWideningTest, "test_n4_exemption_covers_only_the_assignment_line"),
                (teh.ScannerContractTest, "test_exemption_covers_only_its_symbol_and_path"),
                (teh.RepositoryScanTest, "test_no_hardcoded_ports")]


def scan_rows(label: str, src: str, must_fail: bool) -> None:
    mod = module_of(src)
    problems = []
    with mock.patch.object(teh, "ROOT", ROOT):
        for cls, method in EXEMPT_TESTS:
            problems += [f"{method}: {p}" for p in run_test(
                cls, method, [mock.patch("tests.hardcoded_scan.find_hardcoded", mod.find_hardcoded)])]
    row("exemption", label, must_fail, problems)


scan_rows("TARGET Dockerfile + the exemption", SCAN_SRC, False)
for name, m in {
    "path-wide: every line of docker/neo4j.Dockerfile exempt": swap(
        'return re.compile(rf"^\\s*{re.escape(symbol)}\\s*$")', 'return re.compile(r"")'),
    "prefix match: any line starting EXPOSE 7473 7474 7687": swap(
        'return re.compile(rf"^\\s*{re.escape(symbol)}\\s*$")', 'return re.compile(rf"^\\s*{re.escape(symbol)}")'),
    "exact-line rule for every path (Python too)": swap("    if _is_dockerfile(path):\n", "    if True:\n"),
    "any Dockerfile path (path not compared)": swap("            if any(path == p and rx.match(line) for p, rx in exempt):",
                                                    "            if any((path == p or _is_dockerfile(path)) and rx.match(line)"
                                                    " for p, rx in exempt):"),
    "no Dockerfile form (assignment only, the U4 scanner)": swap("    if _is_dockerfile(path):\n", "    if False:\n"),
}.items():
    scan_rows(name, m(SCAN_SRC), True)

bad = [r for r in rows if not r[3]]
print(f"\nU4b controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if bad else 0)
