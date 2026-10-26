"""platform-sbom U7b RED: controls for tests/test_sources_resolve.py (the
resolver, lock-needs, docker-compose.sources.yml, scripts/sources_lock.sh).

Never writes the repository. It builds a temporary root holding the files the
harnesses read, with the U7b targets (docs/evidence/platform-sbom/u7b/target-*)
in place, and runs real test methods on the targets, on the committed U7a tree
(git HEAD) and on mutants of each target. Each "must fail" row names the one
test method that must fail. Exit 1 if any row is unexpected.

Usage (needs bash, git and jq: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7b/u7b_controls.py [--base repo]
`--base repo` uses the repository's own files instead of the targets (GREEN).
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
from tests import test_sources_lock as tsl  # noqa: E402
from tests import test_sources_resolve as tsr  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGETS = {"scripts/sources_resolve.py": "target-sources_resolve.py", "scripts/sources_lock.sh": "target-sources_lock.sh",
           "docker-compose.sources.yml": "target-docker-compose.sources.yml", "scripts/sbom_check.py": "target-sbom_check.py"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml", ".env.example",
        ".gitignore", ".dockerignore", "pyproject.toml", "uv.lock", "LICENSE", "NOTICE.md", "config", "licenses",
        "docs/quickstart.md", ".github", "tests/fixtures"]
WORK = Path(tempfile.mkdtemp(prefix="u7b-controls-"))
rows: list[tuple[str, str, str, bool]] = []


def text_of(rel: str) -> str:
    return (REPO / rel if BASE_REPO else HERE / TARGETS[rel]).read_text(encoding="utf-8")


SRC = {rel: text_of(rel) for rel in TARGETS}


def head(rel: str) -> str | None:
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


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
    spec = importlib.util.spec_from_file_location(f"u7b_check_{path.parent.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_test(cls: type, method: str, root: Path) -> list[str]:
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    check = module_at(root / "scripts" / "sbom_check.py") if (root / "scripts" / "sbom_check.py").is_file() else None
    patches = [mock.patch.object(tsr, "RESOLVER", root / "scripts" / "sources_resolve.py"),
               mock.patch.object(tsr, "LOCK_SH", root / "scripts" / "sources_lock.sh"),
               mock.patch.object(tsr, "SOURCES_COMPOSE", root / "docker-compose.sources.yml"),
               mock.patch.object(tsr, "ROOT", root), mock.patch.object(tob, "ROOT", root)]
    if check is not None:
        patches += [mock.patch.object(tsr, "load_sbom_check", lambda m=check: m),
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
    print(f"{'ok ' if ok else 'BAD'} [{group}] {name:<66} {'must fail' if must_fail else 'must pass'} | {detail}")


def swap(*pairs: str) -> Callable[[str], str]:
    def change(t: str) -> str:
        for old, new in zip(pairs[::2], pairs[1::2]):
            if t.count(old) != 1:
                raise AssertionError(f"mutant anchor found {t.count(old)} times: {old[:70]!r}")
            t = t.replace(old, new, 1)
        return t
    return change


def names(cls: type) -> list[tuple[type, str]]:
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls)]


TESTS = [t for cls in (tsr.ResolverHopsTest, tsr.ResolverParsersTest, tsr.ResolverRoutesTest, tsr.ResolverMergeTest,
                       tsr.ResolverMainTest, tsr.LockNeedsTest, tsr.SourcesComposeTest, tsr.SourcesLockScriptStaticTest,
                       tsr.SourcesLockScriptRunTest) for t in names(cls)]
REGRESSION = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.LockCheckCliTest)
              for t in names(cls)]
BY_NAME = {n: c for c, n in TESTS + REGRESSION}
assert len(BY_NAME) == len(set(n for _, n in TESTS + REGRESSION)) and     len({n for _, n in TESTS}) == len(TESTS), "two test methods share a name: a row could run the wrong one"
GUARDS = {"test_hardening_check_rejects_loosened_services", "test_never_run_by_verify_or_ci"}

TROOT = make_root(dict(SRC))
row("target", f"TARGET: the {len(TESTS)} U7b tests", False,
    [p for cls, m in TESTS for p in run_test(cls, m, TROOT)])
row("target", f"TARGET: {len(REGRESSION)} U7a lock regression tests", False,
    [p for cls, m in REGRESSION for p in run_test(cls, m, TROOT)])

HROOT = make_root({rel: head(rel) for rel in TARGETS})
for cls, method in TESTS:
    guard = method in GUARDS
    row("head", f"HEAD (U7a): {method}" + (" (guard)" if guard else ""), not guard, run_test(cls, method, HROOT))

MUTANTS: dict[str, tuple[str, Callable[[str], str], str]] = {
    # the resolver
    "a redirect host not checked": ("scripts/sources_resolve.py", swap(
        "        if host not in allow:\n            raise ResolveError(f\"redirect to",
        "        if hop == 0 and host not in allow:\n            raise ResolveError(f\"redirect to"), "test_hop_rules_and_messages"),
    "an http redirect followed": ("scripts/sources_resolve.py", swap(
        '        if u.scheme != "https":\n', '        if u.scheme not in ("https", "http"):\n'), "test_hop_rules_and_messages"),
    "six redirects allowed": ("scripts/sources_resolve.py", swap("MAX_HOPS = 5\n", "MAX_HOPS = 6\n"),
                              "test_hop_rules_and_messages"),
    "a retry after a non-2xx": ("scripts/sources_resolve.py", swap(
        '        if not 200 <= r.status < 300:\n            raise ResolveError(f"{host}: HTTP {r.status}: {_clean(current)}")\n'
        '        return r',
        '        if not 200 <= r.status < 300:\n            r = OPENER(current, timeout)\n'
        '        if not 200 <= r.status < 300:\n            raise ResolveError(f"{host}: HTTP {r.status}: {_clean(current)}")\n'
        '        return r'), "test_hop_rules_and_messages"),
    "the temurin sidecar not compared": ("scripts/sources_resolve.py", swap(
        '    if got["sha256"] != want:\n        raise ResolveError(f"{asset}: sha256 mismatch',
        '    if False:\n        raise ResolveError(f"{asset}: sha256 mismatch'), "test_temurin"),
    "the tag taken from the SBOM alone": ("scripts/sources_resolve.py", swap(
        "    if not ver or ver != run or ver != sbom:", "    ver = sbom\n    if not ver:"), "test_release_file_and_tag"),
    "the maven .sha1 not compared": ("scripts/sources_resolve.py", swap(
        '    if got["sha1"] != want:', '    if False:'), "test_maven"),
    "the .sha1 any length": ("scripts/sources_resolve.py", swap(
        '    if not re.fullmatch(r"[0-9a-f]{40}", first):', '    if not re.fullmatch(r"[0-9a-f]+", first):'),
        "test_sidecar_parsers"),
    "pypi JSON: the first of several sdists": ("scripts/sources_resolve.py", swap(
        "    if len(sdists) != 1:", "    if not sdists:"), "test_uv_lock_and_pypi_json"),
    "pypi JSON: the sdist host not checked": ("scripts/sources_resolve.py", swap(
        '    if urlsplit(url).hostname != "files.pythonhosted.org" or', "    if"), "test_uv_lock_and_pypi_json"),
    "pypi: uv.lock ignored (always the JSON)": ("scripts/sources_resolve.py", swap(
        "    sd = uv_lock_sdist(uv_lock_text, name, ver)\n    if sd is not None:",
        "    sd = None\n    if sd is not None:"), "test_pypi"),
    "pypi: the sdist not compared with the JSON": ("scripts/sources_resolve.py", swap(
        '    if got["sha256"] != sd["sha256"]:', '    if False:'), "test_pypi"),
    "neo4j: the TOFU entry written": ("scripts/sources_resolve.py", swap(
        "                candidates.append(neo4j_candidate(key, allow))\n                continue",
        "                c = neo4j_candidate(key, allow)\n                candidates.append(c)\n"
        "                comps[key] = {'kind': 'neo4j', 'arches': [arch], 'origin': 'manual', 'files': []}\n"
        "                continue"), "test_neo4j_candidate_is_printed_never_written"),
    "a manual entry rewritten": ("scripts/sources_resolve.py", swap(
        '        if isinstance(old, dict) and old.get("origin") == "manual":\n            continue  # never rewritten',
        '        if False:\n            continue  # never rewritten'), "test_merge_rules"),
    "arches not merged": ("scripts/sources_resolve.py", swap(
        '            entry["arches"] = sorted(set(old.get("arches") or []) | {arch})', "            pass"), "test_merge_rules"),
    "an unneeded generated entry kept": ("scripts/sources_resolve.py", swap(
        "        if key in needs or not isinstance(e, dict)", "        if True or key in needs or not isinstance(e, dict)"),
        "test_merge_rules"),
    "--refresh ignored": ("scripts/sources_resolve.py", swap(
        "        if isinstance(old, dict) and arch in (old.get(\"arches\") or []) and not refresh:",
        "        if isinstance(old, dict) and arch in (old.get(\"arches\") or []):"), "test_merge_rules"),
    "a failed run still writes": ("scripts/sources_resolve.py", swap(
        '        print(f"sources_lock: FAIL (resolve: {exc}; the lock is unchanged)", file=sys.stderr)\n        return 1',
        '        print(f"sources_lock: FAIL (resolve: {exc}; the lock is unchanged)", file=sys.stderr)\n'
        '        open(os.path.join(a.out, "lock.new.json"), "w").close()\n        return 1'), "test_failure_writes_nothing"),
    "a cache file left in the out dir": ("scripts/sources_resolve.py", swap(
        '    os.replace(tmp, os.path.join(a.out, "lock.new.json"))',
        '    os.replace(tmp, os.path.join(a.out, "lock.new.json"))\n    open(os.path.join(a.out, "cache.json"), "w").close()'),
        "test_writes_only_the_out_lock"),
    "neo4j candidates exit 0": ("scripts/sources_resolve.py", swap("    return 3 if candidates else 0", "    return 0"),
                                "test_neo4j_candidate_exit_3"),
    "a bad arch accepted": ("scripts/sources_resolve.py", swap("    if a.arch not in ARCHES:", "    if False:"),
                            "test_resolver_bad_arguments_exit_2"),
    # lock-needs
    "lock-needs: a missing release file not a problem": ("scripts/sbom_check.py", swap(
        "            if release is None:\n                problems.append(", "            if False:\n                problems.append("),
        "test_lock_needs_doc_on_the_fixtures"),
    "lock-needs: the bottom layer's release wins": ("scripts/sbom_check.py", swap(
        "                        found = data.read(1 << 20) if data is not None else None",
        "                        found = found or (data.read(1 << 20) if data is not None else None)"),
        "test_release_from_the_saved_tar"),
    "lock-needs: the deb route keeps no epoch": ("scripts/sbom_check.py", swap(
        '            route = {"src": name, "ver": ver}', '            route = {"src": name, "ver": ver.split(":")[-1]}'),
        "test_lock_needs_doc_on_the_fixtures"),
    # the compose file
    "compose: a KE_* key in the environment": ("docker-compose.sources.yml", swap(
        '      PYTHONDONTWRITEBYTECODE: "1"', '      PYTHONDONTWRITEBYTECODE: "1"\n      KE_MODEL_UPSTREAM: ${KE_MODEL_UPSTREAM:-}'),
        "test_sources_resolve_service_hardening"),
    "compose: host networking": ("docker-compose.sources.yml", swap("    pull_policy: never\n",
                                                                     "    pull_policy: never\n    network_mode: host\n"),
                                 "test_sources_resolve_service_hardening"),
    "compose: writable root": ("docker-compose.sources.yml", swap("    read_only: true\n    tmpfs:", "    read_only: false\n    tmpfs:"),
                               "test_sources_resolve_service_hardening"),
    "compose: /in writable": ("docker-compose.sources.yml", swap(
        "        target: /in\n        read_only: true\n", "        target: /in\n"), "test_sources_resolve_service_hardening"),
    "compose: capabilities kept": ("docker-compose.sources.yml", swap("    cap_drop:\n      - ALL\n", ""),
                                   "test_sources_resolve_service_hardening"),
    "compose: pulls": ("docker-compose.sources.yml", swap("    pull_policy: never\n", "    pull_policy: missing\n"),
                       "test_sources_resolve_service_hardening"),
    # the script
    "script: the image check dropped": ("scripts/sources_lock.sh", swap(
        '    || fail "images: $ref not found: run scripts/build.sh first"', "    || true"),
        "test_refuses_when_an_image_is_missing"),
    "script: the floor check dropped": ("scripts/sources_lock.sh", swap(
        '[ "$avail" -ge 7340032 ] || fail', '[ "$avail" -ge 0 ] || fail'), "test_refuses_below_the_floor"),
    "script: a bad arch accepted": ("scripts/sources_lock.sh", swap("case \"$arch\" in amd64|arm64) ;; *) usage ;; esac",
                                                                    "case \"$arch\" in *) ;; esac"),
                                    "test_bad_arguments_exit_2"),
    "script: the move before lock-check": ("scripts/sources_lock.sh", swap(
        "# --- 5. check, then write --------------------------------------------------------\n",
        "# --- 5. check, then write --------------------------------------------------------\n"
        "mv -f -- \"$work/out/lock.new.json\" docker/sources.lock.json\n"), "test_sources_lock_sh_shape"),
    "script: no git diff --stat": ("scripts/sources_lock.sh", swap("git diff --stat -- docker/sources.lock.json\n", ""),
                                   "test_sources_lock_sh_shape"),
    "script: the .env read": ("scripts/sources_lock.sh", swap(
        "compose=(docker compose -f docker-compose.yml --env-file .env.example)",
        "compose=(docker compose -f docker-compose.yml --env-file .env)"), "test_sources_lock_sh_shape"),
    "script: a KE_* value passed into the resolver": ("scripts/sources_lock.sh", swap(
        "  run --rm --pull never sources-resolve --arch",
        "  run --rm --pull never -e KE_MODEL_UPSTREAM sources-resolve --arch"), "test_sources_lock_sh_shape"),
    "script: no exit 3": ("scripts/sources_lock.sh", swap("  exit 3\nfi\nexit 0", "  exit 0\nfi\nexit 0"),
                          "test_sources_lock_sh_shape"),
}
for name, (rel, m, method) in MUTANTS.items():
    try:
        files = dict(SRC)
        files[rel] = m(SRC[rel])
    except AssertionError as exc:
        row("mutant", name, True, [])
        print(f"    anchor: {exc}")
        continue
    row("mutant", name, True, run_test(BY_NAME[method], method, make_root(files)))

bad = [r for r in rows if not r[3]]
print(f"\nU7b controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
