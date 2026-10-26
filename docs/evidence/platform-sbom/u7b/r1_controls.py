"""platform-sbom U7b rework round 1 RED: controls for the round-1 tests in
tests/test_sources_resolve.py (ReworkR1*) and tests/test_sources_lock.py
(ReworkR1PendingNeo4jCliTest).

Never writes the repository. It builds a temporary root holding the files the
harnesses read, with the round-1 targets (docs/evidence/platform-sbom/u7b/
r1-target-*) in place, and runs real test methods on the targets, on the U7b
GREEN tree (the saved U7b targets, u7b/target-sources_resolve.py,
target-sources_lock.sh and target-sbom_check.py) and on mutants of each target. Each "must fail" row names
the one test method that must fail. Exit 1 if any row is unexpected.

Usage (needs bash, git and jq: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7b/r1_controls.py [--base repo]
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
TARGETS = {"scripts/sources_resolve.py": "r1-target-sources_resolve.py",
           "scripts/sources_lock.sh": "r1-target-sources_lock.sh",
           "scripts/sbom_check.py": "r1-target-sbom_check.py"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml",
        "docker-compose.sources.yml", ".env.example", ".gitignore", ".dockerignore", "pyproject.toml", "uv.lock",
        "LICENSE", "NOTICE.md", "config", "licenses", "docs/quickstart.md", ".github", "tests/fixtures"]
WORK = Path(tempfile.mkdtemp(prefix="u7b-r1-controls-"))
rows: list[tuple[str, str, str, bool]] = []


def text_of(rel: str) -> str:
    return (REPO / rel if BASE_REPO else HERE / TARGETS[rel]).read_text(encoding="utf-8")


SRC = {rel: text_of(rel) for rel in TARGETS}
# The U7b GREEN baseline is the saved U7b targets (byte-equal to the U7b GREEN
# tree, checked at the round-1 RED), never the repository, which holds round 1
# once its GREEN lands (orchestrator, 2026-10-25).
U7B_SAVED = {"scripts/sources_resolve.py": "target-sources_resolve.py",
             "scripts/sources_lock.sh": "target-sources_lock.sh", "scripts/sbom_check.py": "target-sbom_check.py"}
GREEN_U7B = {rel: (HERE / name).read_text(encoding="utf-8") for rel, name in U7B_SAVED.items()}


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
    spec = importlib.util.spec_from_file_location(f"u7b_r1_check_{path.parent.parent.name}", path)
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
    """The test methods `cls` defines itself (not inherited ones)."""
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls) if n in vars(cls)]


def every(cls: type) -> list[tuple[type, str]]:
    return [(cls, n) for n in unittest.defaultTestLoader.getTestCaseNames(cls)]


R1_CLASSES = [tsr.ReworkR1TransportTest, tsr.ReworkR1MainTest, tsr.ReworkR1RealOpenerTest, tsr.ReworkR1HopRulesTest,
              tsr.ReworkR1PypiScopeTest, tsr.ReworkR1KeysTest, tsr.ReworkR1LockScriptRunTest,
              tsl.ReworkR1PendingNeo4jCliTest]
NEW = [t for cls in R1_CLASSES for t in own(cls)]
U7B = [t for cls in (tsr.ResolverHopsTest, tsr.ResolverParsersTest, tsr.ResolverRoutesTest, tsr.ResolverMergeTest,
                     tsr.ResolverMainTest, tsr.LockNeedsTest, tsr.SourcesComposeTest, tsr.SourcesLockScriptStaticTest,
                     tsr.SourcesLockScriptRunTest) for t in every(cls)]
U7A = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.LockCheckCliTest)
       for t in every(cls)]
# Guards: round-1 tests that the U7b GREEN tree already passes (they pin a
# behaviour round 1 must keep, so a mutant row or the target row covers them).
GUARDS = {(tsr.ReworkR1HopRulesTest, "test_a_hop_may_carry_a_query"),
          (tsr.ReworkR1PypiScopeTest, "test_the_json_request_itself_is_allowed")}

TROOT = make_root(dict(SRC))
row("target", f"TARGET: the {len(NEW)} round-1 tests", False, [p for c, m in NEW for p in run_test(c, m, TROOT)])
row("target", f"TARGET: the {len(U7B)} U7b tests", False, [p for c, m in U7B for p in run_test(c, m, TROOT)])
row("target", f"TARGET: {len(U7A)} U7a lock regression tests", False, [p for c, m in U7A for p in run_test(c, m, TROOT)])

GROOT = make_root(dict(GREEN_U7B))
for cls, method in NEW:
    guard = (cls, method) in GUARDS
    row("u7b", f"U7b GREEN: {cls.__name__}.{method}" + (" (guard)" if guard else ""), not guard,
        run_test(cls, method, GROOT))

RES, SH, CHK = "scripts/sources_resolve.py", "scripts/sources_lock.sh", "scripts/sbom_check.py"
T, R = tsr.ReworkR1TransportTest, tsr.ReworkR1LockScriptRunTest
MUTANTS: dict[str, tuple[str, Callable[[str], str], type, str]] = {
    # item 1: transport errors, deadline, byte cap, main
    "a body error uncaught": (RES, swap(
        "        except (OSError, ValueError, http.client.HTTPException) as exc:\n"
        "            raise _transport(host, url, exc, timeout) from None\n", ""), T, "test_errors_while_reading_the_body"),
    "only OSError caught at open": (RES, swap(
        "        except (OSError, ValueError, http.client.HTTPException) as exc:\n"
        "            raise _transport(host, current, exc, timeout) from None",
        "        except OSError as exc:\n            raise _transport(host, current, exc, timeout) from None"),
        T, "test_errors_while_opening"),
    "the error text, not its class": (RES, swap(
        '    return ResolveError(f"{host}: {type(exc).__name__}: {_clean(url)}")',
        '    return ResolveError(f"{host}: {_clean(exc)}: {_clean(url)}")'), T, "test_errors_while_opening"),
    "the deadline dropped": (RES, swap(
        "        if time.monotonic() - started > DEADLINE:\n"
        '            raise ResolveError(f"{host}: deadline {DEADLINE:g} s passed: {_clean(url)}")',
        "        if False:\n"
        '            raise ResolveError(f"{host}: deadline {DEADLINE:g} s passed: {_clean(url)}")'),
        T, "test_the_deadline"),
    "the deadline 6000 s": (RES, swap("DEADLINE = 600  #", "DEADLINE = 6000  #"), T, "test_the_deadline"),
    "the byte cap dropped": (RES, swap("        if size > MAX_BYTES:\n", "        if False:\n"), T, "test_the_byte_cap"),
    "the byte cap checked after the chunk is handed on": (RES, swap(
        "        size += len(chunk)\n        if size > MAX_BYTES:\n"
        '            raise ResolveError(f"{host}: more than {MAX_BYTES} bytes: {_clean(url)}")\n        yield chunk',
        "        yield chunk\n        size += len(chunk)\n        if size > MAX_BYTES + len(chunk):\n"
        '            raise ResolveError(f"{host}: more than {MAX_BYTES} bytes: {_clean(url)}")'), T, "test_the_byte_cap"),
    "the byte cap off by one": (RES, swap("        if size > MAX_BYTES:\n", "        if size >= MAX_BYTES:\n"),
                                T, "test_the_byte_cap"),
    "main: an OSError writing /out escapes": (RES, swap(
        "    except Exception as exc:  # noqa: BLE001 - round 1, item 1: one FAIL line, never a traceback\n"
        '        print(f"sources_lock: FAIL (resolve: -: {type(exc).__name__}: {_clean(exc)}; the lock is unchanged)",\n'
        "              file=sys.stderr)\n        return 1\n", ""), tsr.ReworkR1MainTest,
        "test_an_error_writing_out_is_one_fail_line"),
    "main: a wrong-typed needs entry not named": (RES, swap(
        '        if not isinstance(needs[key], dict) or not isinstance(needs[key].get("route", {}), dict):',
        "        if False:"), tsr.ReworkR1MainTest, "test_wrong_typed_needs_are_one_fail_line"),
    # item 10: error bodies
    "the real opener reads a whole error body": (RES, swap("        exc.read(ERROR_BODY_LIMIT)", "        exc.read()"),
                                                 tsr.ReworkR1RealOpenerTest, "test_error_bodies_are_read_to_1_mib_only"),
    # item 3: hop rules
    "a port allowed on a hop": (RES, swap('    if port is not None or u.netloc.endswith(":"):', "    if False:"),
                                tsr.ReworkR1HopRulesTest, "test_bad_hops_are_refused_and_never_requested"),
    "userinfo allowed on a hop": (RES, swap('    if "@" in u.netloc:', "    if False:"),
                                  tsr.ReworkR1HopRulesTest, "test_bad_hops_are_refused_and_never_requested"),
    "a fragment allowed on a hop": (RES, swap('    if "#" in url:', "    if False:"),
                                    tsr.ReworkR1HopRulesTest, "test_bad_hops_are_refused_and_never_requested"),
    "a percent allowed on a hop": (RES, swap('(not first and "%" in u.path)', "False"),
                                   tsr.ReworkR1HopRulesTest, "test_bad_hops_are_refused_and_never_requested"),
    "the raw Location not checked (a tab dropped by the join)": (RES, swap(
        "            if not PRINTABLE.fullmatch(loc):  # before the join", "            if False:  # before the join"),
        tsr.ReworkR1HopRulesTest, "test_bad_hops_are_refused_and_never_requested"),
    "the scheme not compared literally": (RES, swap(
        '            if ":" in loc.split("/", 1)[0] and not loc.startswith("https://"):', "            if False:"),
        tsr.ReworkR1HopRulesTest, "test_bad_hops_are_refused_and_never_requested"),
    "a query refused on a hop": (RES, swap('    if "#" in url:', '    if "#" in url or (not first and u.query):'),
                                 tsr.ReworkR1HopRulesTest, "test_a_hop_may_carry_a_query"),
    "a percent refused in a first url": (RES, swap('(not first and "%" in u.path)', '("%" in u.path)'),
                                         tsr.ReworkR1HopRulesTest, "test_the_first_url"),
    "a port allowed on the first url": (RES, swap('    if port is not None or u.netloc.endswith(":"):',
                                                  '    if not first and (port is not None or u.netloc.endswith(":")):'),
                                        tsr.ReworkR1HopRulesTest, "test_the_first_url"),
    # item 8: pypi.org
    "pypi.org allowed everywhere": (RES, swap(
        '    allow = {h for h in policy.get("hosts") or [] if isinstance(h, str)}\n',
        '    allow = {h for h in policy.get("hosts") or [] if isinstance(h, str)} | {PYPI_JSON_HOST}\n'),
        tsr.ReworkR1PypiScopeTest, "test_a_maven_redirect_to_pypi_org_is_refused"),
    "pypi.org allowed on the JSON request's hops": (RES, swap(
        "        if host not in (allow | set(first_allow) if hop == 0 else allow):",
        "        if host not in (allow | set(first_allow)):"),
        tsr.ReworkR1PypiScopeTest, "test_a_redirect_of_the_json_request_to_pypi_org_is_refused"),
    "pypi.org refused for the JSON request too": (RES, swap(
        "                              first_allow=frozenset({PYPI_JSON_HOST})))",
        "                              first_allow=frozenset()))"),
        tsr.ReworkR1PypiScopeTest, "test_the_json_request_itself_is_allowed"),
    # item 11: keys first
    "a key not validated": (RES, swap("        if not valid_key(key):", "        if False:"),
                            tsr.ReworkR1KeysTest, "test_bad_keys_are_refused_before_any_request"),
    "the deb/pgdg kind rule dropped": (RES, swap(
        '    return kind not in ("deb", "pgdg") or ((".pgdg" in key) == (kind == "pgdg"))', "    return True"),
        tsr.ReworkR1KeysTest, "test_bad_keys_are_refused_before_any_request"),
    # item 2: --pending-neo4j
    "lock-check: pending decided on the first 20": (CHK, swap(
        "    return all(x in neo for x in problems)", "    return all(x in neo for x in problems[:20])"),
        tsl.ReworkR1PendingNeo4jCliTest, "test_the_reviewers_79_problem_lock_exits_1"),
    "lock-check: any miss counts as pending": (CHK, swap(
        '    neo = {line for key, line in _coverage_misses(needs, covered, arch) if key.startswith("neo4j:")}',
        "    neo = {line for key, line in _coverage_misses(needs, covered, arch)}"),
        tsl.ReworkR1PendingNeo4jCliTest, "test_the_reviewers_79_problem_lock_exits_1"),
    "lock-check: a non-miss neo4j problem counts": (CHK, swap(
        "    return all(x in neo for x in problems)", '    return all(x in neo or "neo4j:" in x for x in problems)'),
        tsl.ReworkR1PendingNeo4jCliTest, "test_other_problems_with_a_neo4j_miss_exit_1"),
    "lock-check: pending exits 1": (CHK, swap("        return 3 if pending else 1", "        return 1"),
                                    tsl.ReworkR1PendingNeo4jCliTest, "test_only_neo4j_misses_exit_3"),
    "script: pending decided by grep on the printed (truncated) list": (SH, swap(
        '  "${sbom_args[@]}" --pending-neo4j > "$work/check.out"', '  "${sbom_args[@]}" > "$work/check.out"',
        '  3) pending=1 ;;\n',
        "  1) if ! grep -v -- 'needs source; the lock has no neo4j:neo4j@' \"$work/check.err\" | grep -q .; then\n"
        '       pending=1; else cat -- "$work/check.err" >&2; fail "check: sbom_check.py lock-check found problems"; fi ;;\n'),
        R, "test_a_truncated_neo4j_list_is_not_pending"),
    "script: exit 3 from lock-check treated as a failure": (SH, swap("  3) pending=1 ;;\n", ""),
                                                            R, "test_neo4j_pending_exit_3"),
    # items 4, 5, 6, 9, 12: the script
    "script: chmod dropped": (SH, swap('chmod 0644 -- "$tmp" || fail "check: cannot chmod $tmp"  # round 1, item 9\n', ""),
                              R, "test_happy_path_exit_0"),
    "script: sboms/tmp not created": (SH, swap(
        'mkdir -- "$work/tars" "$work/sboms" "$work/sboms/tmp" "$work/in" "$work/out"\n'
        'chmod 0700 -- "$work/tars" "$work/sboms" "$work/sboms/tmp" "$work/in" "$work/out"\n',
        'mkdir -- "$work/tars" "$work/sboms" "$work/in" "$work/out"\n'
        'chmod 0700 -- "$work/tars" "$work/sboms" "$work/in" "$work/out"\n'), R, "test_happy_path_exit_0"),
    "script: no git diff --stat": (SH, swap("git diff --stat -- docker/sources.lock.json\n", ""), R, "test_happy_path_exit_0"),
    "script: resolve skipped (the old lock copied)": (SH, swap(
        '[ -f "$work/out/lock.new.json" ] || fail "resolve: no lock.new.json was written"\n',
        '[ -f "$work/out/lock.new.json" ] || fail "resolve: no lock.new.json was written"\n'
        'cp -- "$work/in/sources.lock.json" "$work/out/lock.new.json"\n'), R, "test_happy_path_exit_0"),
    "script: the temp file not removed by the trap": (SH, swap(
        '  if [ -n "$tmp" ]; then rm -f -- "$tmp"; fi  # round 1, item 5\n', ""),
        R, "test_the_temp_file_is_removed_on_failure"),
    "script: jq not checked first": (SH, swap("for tool in jq git docker; do", "for tool in git docker; do"),
                                     R, "test_tools_first"),
    "script: the tools checked after compose": (SH, swap(
        '# U7b rework round 1, item 4: the tools first.\nfor tool in jq git docker; do\n'
        '  command -v "$tool" > /dev/null 2>&1 || fail "tools: $tool not on PATH"\ndone\n', "",
        'compose=(docker compose -f docker-compose.yml --env-file .env.example)\n',
        'compose=(docker compose -f docker-compose.yml --env-file .env.example)\n'
        '"${compose[@]}" version > /dev/null 2>&1 || true\nfor tool in jq git docker; do\n'
        '  command -v "$tool" > /dev/null 2>&1 || fail "tools: $tool not on PATH"\ndone\n'), R, "test_tools_first"),
    "script: an extra image accepted": (SH, swap(
        '  case " ${six[*]} " in *" $name "*) ;; *) fail "images: $name is not one of the six bundled images" ;; esac\n',
        "  :\n"), R, "test_exactly_the_six_images"),
    "script: a missing image accepted": (SH, swap(
        '  case " ${names[*]} " in *" $name "*) ;; *) fail "images: $name is missing from the stack" ;; esac\n',
        "  :\n"),
        R, "test_exactly_the_six_images"),
    "script: the ke-neo4j tar a literal": (SH, swap('"${sbom_args[@]}" "${tar_args[@]}" \\',
                                                    '"${sbom_args[@]}" --tar "ke-neo4j=/tars/ke-neo4j.tar" \\'),
                                           R, "test_the_neo4j_tar_is_not_a_literal"),
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
print(f"\nU7b rework round 1 controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
