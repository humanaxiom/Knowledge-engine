"""platform-sbom U7a rework round 2 RED: controls for tests/test_sources_lock.py
(the U7a, ReworkR1* and ReworkR2* classes) and the U7a carry rows, with the
classifier and policy tests kept as regressions. Supersedes r1_controls.py
(its anchors fit the round-1 target only).

Never writes the repository. Each row runs real test methods with
scripts/sbom_check.py replaced by docs/evidence/platform-sbom/u7a/r2-target-sbom_check.py,
by the round-1 GREEN checker (u7a/r1-target-sbom_check.py), by the U7a GREEN
checker (u7a/target-sbom_check.py), by the committed U6 checker (git HEAD
66781a9), or by a mutant of the round-2 target.
The CLI test runs the checker from a temporary root holding that file.
Each "must fail" row names the one test method that must fail. Exit 1 if any
row is unexpected.

Usage (run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7a/r2_controls.py [--base repo]
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
WORK = Path(tempfile.mkdtemp(prefix="u7ar2-controls-"))
rows: list[tuple[str, str, str, bool]] = []
CHECK_SRC = (REPO / "scripts" / "sbom_check.py" if BASE_REPO else HERE / "r2-target-sbom_check.py").read_text(encoding="utf-8")


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


R1_TESTS = [t for cls in (tsl.ReworkR1Neo4jBindingTest, tsl.ReworkR1CharsetTest, tsl.ReworkR1BindingTest,
                          tsl.ReworkR1CompletenessAndKeysTest, tsl.ReworkR1TypesTest, tsl.ReworkR1CleanAndSizeTest,
                          tsl.ReworkR1CliTest) for t in names(cls)]
R2_TESTS = [t for cls in (tsl.ReworkR2PlainPathTest, tsl.ReworkR2TemurinBindingTest, tsl.ReworkR2PypiPathTest,
                          tsl.ReworkR2RedosTest, tsl.ReworkR2CliLineTest) for t in names(cls)]
LOCK_TESTS = [t for cls in (tsl.LockNeedsTest, tsl.LockSchemaTest, tsl.LockCoverageTest, tsl.SampleKeysTest,
                            tsl.LockCheckCliTest) for t in names(cls)] + R1_TESTS + R2_TESTS
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
    if (cls, method) in R1_TESTS + R2_TESTS:
        continue
    row("head", f"HEAD (U6): {method}", True, run_test(cls, method, HEAD_MOD, HROOT))
U7A_MOD, UROOT = setup((HERE / "target-sbom_check.py").read_text(encoding="utf-8"))
GUARDS = {"test_good_names"}  # the U7a checker already accepts these (green guards)
for cls, method in R1_TESTS + [(tsl.LockSchemaTest, "test_bad_shapes")]:
    if method in ("test_lock_check_never_shows_a_traceback",):
        pass
    guard = method in GUARDS
    row("u7a", f"U7a checker: {method}" + (" (guard)" if guard else ""), not guard,
        run_test(cls, method, U7A_MOD, UROOT))
R1_MOD, R1ROOT = setup((HERE / "r1-target-sbom_check.py").read_text(encoding="utf-8"))
for cls, method in R2_TESTS + [(tsl.ReworkR1BindingTest, "test_per_kind_hosts_paths_and_names")]:
    row("r1", f"r1 checker: {method}", True, run_test(cls, method, R1_MOD, R1ROOT))
for cls, method in CARRY:
    row("head", f"HEAD (U6): {method} (carry guard, green before U7a)", False, run_test(cls, method, HEAD_MOD, HROOT))

MUTANTS: dict[str, tuple[Callable[[str], str], str]] = {
    # deb's own per-kind rule (snapshot.debian.org/file/<sha1>) also refuses a
    # foreign deb host, so the dropped-host-check mutant is aimed at neo4j and
    # pypi, whose URLs only the host check guards.
    "a kind's host check dropped (neo4j)": (swap(
        '        p += _file_problems(where, f, hosts, kind)',
        '        p += _file_problems(where, f, (hosts if kind != "neo4j" else '
        'type("AnyHost", (), {"__contains__": lambda s, x: True})()), kind)'), "test_bad_shapes"),
    "a kind's host check dropped (pypi)": (swap(
        '        p += _file_problems(where, f, hosts, kind)',
        '        p += _file_problems(where, f, (hosts if kind != "pypi" else '
        'type("AnyHost", (), {"__contains__": lambda s, x: True})()), kind)'), "test_bad_shapes"),
    "http accepted": (swap('    if not url.startswith("https://"):', '    if not url.startswith(("https://", "http://")):'),
                      "test_bad_shapes"),
    "userinfo accepted": (swap('    if u.username is not None or u.password is not None or "@" in u.netloc:',
                               "    if False:"), "test_bad_shapes"),
    "a stale entry ignored": (swap("    for key in sorted(covered - set(needs)):",
                                   "    for key in sorted(covered - set(needs) - covered):"), "test_a_stale_key_is_reported"),
    "a miss message with a wrong key (kind dropped)": (swap(
        "needs source; the lock has no {_clean(key)} for ", "needs source; the lock has no {_clean(key).split(':', 1)[1]} for "),
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
    "size true accepted": (swap('    if type(f["size"]) is not int or not 0 < f["size"] <= MAX_FILE_SIZE:',
                                '    if not isinstance(f["size"], int) or not 0 < f["size"] <= MAX_FILE_SIZE:'),
                           "test_bad_shapes"),
    "the .dsc name keeps the epoch": (swap(
        """            want = f"{name_part}_{ver.split(':', 1)[1] if ':' in ver else ver}.dsc\"""",
        """            want = f"{name_part}_{ver}.dsc\""""), "test_good_small_lock_passes"),
    "a neo4j second fetch dated after today accepted": (swap("            if when > today:", "            if False:"),
                                                       "test_bad_shapes"),
    "R1-2: urlsplit before the charset check": (swap(
        '    p = _str_problems(where, "url", url)\n    if p:\n        return p\n    u = _split(url)\n',
        '    u = _split(url) if isinstance(url, str) else None\n'
        '    p = _str_problems(where, "url", urlunsplit(u) if u is not None else url)\n    if p:\n        return p\n'),
        "test_printable_ascii_before_parsing"),
    "R1-2: the round-trip check dropped": (swap(
        '    if urlunsplit(u) != url:\n        p.append(', '    if False:\n        p.append('),
        "test_url_round_trips_and_scheme_is_lower_case_https"),
    "R1-2: upper-case HTTPS accepted": (swap('    if not url.startswith("https://"):',
                                             '    if not url.lower().startswith("https://"):'),
                                        "test_url_round_trips_and_scheme_is_lower_case_https"),
    "R1-2: from held to 0x21-0x7e (no space)": (swap(
        '    q += _str_problems(where, "upstream.from", up["from"], space=True)',
        '    q += _str_problems(where, "upstream.from", up["from"])'), "test_url_round_trips_and_scheme_is_lower_case_https"),
    "R1-2: from allows any character": (swap(
        '    q += _str_problems(where, "upstream.from", up["from"], space=True)', '    q += []'),
        "test_printable_ascii_before_parsing"),
    "R1-3: deb host binding dropped": (swap('    if host not in KIND_HOSTS[kind]:',
                                            '    if host not in KIND_HOSTS[kind] and kind != "deb":'),
                                       "test_per_kind_hosts_paths_and_names"),
    "R1-3: apk host binding dropped": (swap('    if host not in KIND_HOSTS[kind]:',
                                            '    if host not in KIND_HOSTS[kind] and kind != "apk":'),
                                       "test_per_kind_hosts_paths_and_names"),
    "R1-3: neo4j host binding dropped": (swap('    if host not in KIND_HOSTS[kind]:',
                                              '    if host not in KIND_HOSTS[kind] and kind != "neo4j":'),
                                         "test_per_kind_hosts_paths_and_names"),
    "R1-3: temurin host binding dropped": (swap('    if host not in KIND_HOSTS[kind]:',
                                                '    if host not in KIND_HOSTS[kind] and kind != "temurin":'),
                                           "test_per_kind_hosts_paths_and_names"),
    "R1-3: pypi host binding dropped": (swap('    if host not in KIND_HOSTS[kind]:',
                                             '    if host not in KIND_HOSTS[kind] and kind != "pypi":'),
                                        "test_per_kind_hosts_paths_and_names"),
    "R1-3: maven host binding dropped": (swap('    if host not in KIND_HOSTS[kind]:',
                                              '    if host not in KIND_HOSTS[kind] and kind != "maven":'),
                                         "test_per_kind_hosts_paths_and_names"),
    "R1-3: pgdg allowed (a host in the policy suffices)": (swap(
        '    if kind == "pgdg":\n        return [f"{where}: {_clean(name)}: pgdg has no allowed host until Q71"]\n', ''),
        "test_any_pgdg_file_is_a_problem_until_q71"),
    "R1-3: the last-segment rule dropped": (swap(
        '    if path.rsplit("/", 1)[-1] != name:', '    if False:'), "test_per_kind_hosts_paths_and_names"),
    "R1-3: the .. segment rule dropped": (swap('    if any(seg in (".", "..") for seg in segs):',
                                               '    if any(seg == "." for seg in segs):'),
                                          "test_per_kind_hosts_paths_and_names"),
    "R1-3: pypi name not PEP 503-normalised (psycopg_c refused)": (swap(
        '        if parts is None or _norm(parts[0]) != name_part or parts[1] != ver:',
        '        if parts is None or parts[0] != name_part or parts[1] != ver:'), "test_good_names"),
    "R1-3: apk GitLab path not bound to the commit": (swap(
        '            want = f"/alpine/aports/-/raw/{entry.get(\'commit\')}/{entry.get(\'repo\')}/{name_part}/{name}"',
        '            want = path'), "test_per_kind_hosts_paths_and_names"),
    "R1-1: neo4j alg sha1 accepted": (swap('            if fup.get("alg") != "sha256":',
                                           '            if fup.get("alg") not in ("sha256", "sha1"):'),
                                      "test_neo4j_entry_binds_one_sha256_file"),
    "R1-1: two neo4j files accepted": (swap('        if len(entry["files"]) != 1:\n            p.append(f"{where}: neo4j:',
                                            '        if len(entry["files"]) > 2:\n            p.append(f"{where}: neo4j:'),
                                       "test_neo4j_entry_binds_one_sha256_file"),
    "R1-1: neo4j value not bound to the file sha256": (swap(
        '            elif fup.get("value") != f.get("sha256"):', '            elif False:'),
        "test_neo4j_entry_binds_one_sha256_file"),
    "R1-4: a .dsc-only deb accepted": (swap(
        '            if not others:\n                p.append(', '            if False:\n                p.append('),
        "test_deb_needs_more_than_the_dsc"),
    "R1-5: an extra entry key accepted": (swap(
        '    extra = [f"{where}: unexpected key {_clean(k)}" for k in sorted(set(entry) - want, key=str)]',
        '    extra = []'), "test_exact_key_sets"),
    "R1-6: arches items not type-checked (sorted() raises)": (swap(
        '    if not isinstance(arches, list) or not all(isinstance(a, str) for a in arches):',
        '    if not isinstance(arches, list):'), "test_wrong_types_are_problems"),
    "R1-6: lock-check lets an exception through": (swap(
        '    try:\n        problems = lock_problems(text, policy, docs, a.arch)\n'
        '    except Exception as exc:  # noqa: BLE001 - fail closed with one message, never a traceback (rework r1, N5)\n'
        '        print(f"lock-check: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)\n'
        '        return 1\n',
        '    problems = lock_problems(text, policy, docs, a.arch)\n'), "test_lock_check_never_shows_a_traceback"),
    "R1-6: lock-check: RecursionError not caught on reading": (swap(
        '    except (OSError, ValueError, RecursionError) as exc:  # UnicodeDecodeError',
        '    except (OSError, ValueError) as exc:  # UnicodeDecodeError'),
        "test_lock_check_never_shows_a_traceback"),
    "R1-8: the key printed raw in the miss message": (swap(
        "needs source; the lock has no {_clean(key)} for ", "needs source; the lock has no {key} for "),
        "test_keys_printed_clean"),
    "R1-9: the size cap dropped": (swap('    if type(f["size"]) is not int or not 0 < f["size"] <= MAX_FILE_SIZE:',
                                        '    if type(f["size"]) is not int or not 0 < f["size"]:'), "test_size_cap"),
    "R2-1: the % check dropped": (swap(
        '        if "%" in seg and not (kind == "temurin" and i == TEMURIN_TAG_SEGMENT and "%" not in seg.replace("%2B", "")):',
        '        if False:'), "test_url_paths_are_plain"),
    "R2-1: %2B allowed anywhere": (swap(
        '        if "%" in seg and not (kind == "temurin" and i == TEMURIN_TAG_SEGMENT and "%" not in seg.replace("%2B", "")):',
        '        if "%" in seg.replace("%2B", ""):'), "test_url_paths_are_plain"),
    "R2-1: %2b (any case) allowed in the tag": (swap(
        '"%" not in seg.replace("%2B", "")):', '"%" not in seg.replace("%2B", "").replace("%2b", "")):'),
        "test_url_paths_are_plain"),
    "R2-1: backslash allowed": (swap(' or "\\\\" in url or any(seg == "" for seg in segs[1:]):',
                                     ' or any(seg == "" for seg in segs[1:]):'), "test_url_paths_are_plain"),
    "R2-1: . segment allowed": (swap('    if any(seg in (".", "..") for seg in segs):',
                                     '    if any(seg == ".." for seg in segs):'), "test_url_paths_are_plain"),
    "R2-1: empty segment allowed": (swap(' or any(seg == "" for seg in segs[1:]):', ':'), "test_url_paths_are_plain"),
    "R2-2: temurin tag not bound": (swap(
        '        want = f"/adoptium/temurin{feature}-binaries/releases/download/jdk-{tver.replace(\'+\', \'%2B\')}/{asset}"',
        '        want = path if path.startswith(f"/adoptium/temurin{feature}-binaries/releases/download/") '
        'and path.endswith("/" + asset) else "-"'),
        "test_temurin_bound_to_the_key"),
    "R2-2: asset version not bound": (swap(
        """        if path != want or name != asset:""",
        """        if path.rsplit("/", 1)[0] != want.rsplit("/", 1)[0] or not name.startswith(f"OpenJDK{feature}U-jdk-sources_"):"""),
        "test_temurin_bound_to_the_key"),
    "R2-3: CLI line wording changed (the read path)": (swap(
        '    except (OSError, ValueError, RecursionError) as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors\n'
        '        print(f"lock-check: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)',
        '    except (OSError, ValueError, RecursionError) as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors\n'
        '        print(f"sbom_check: lock-check: {type(exc).__name__}: {_clean(exc)}", file=sys.stderr)'),
        "test_exception_line"),
    "R2-3: CLI line wording changed (the check path)": (swap(
        '        print(f"lock-check: FAIL ({type(exc).__name__}: {_clean(exc)})", file=sys.stderr)\n        return 1\n    if problems:',
        '        print(f"sbom_check: lock-check: the check failed: {type(exc).__name__}: {_clean(exc)}", file=sys.stderr)\n'
        '        return 1\n    if problems:'), "test_exception_line"),
    "R2-3: the lock not parsed in the read block (nested lock is a problem, not FAIL)": (swap(
        '        json.loads(text)  # read errors and deep nesting are a FAIL line here (rework round 2, item 3)\n', ''),
        "test_exception_line"),
    # No row for "the message not cleaned": every caught exception's text here
    # already escapes control characters (OSError shows the file name by repr), so
    # the _clean on that line is defence in depth (equivalent mutant).
    "R2-4: the old pypi regex, the skip dropped (the round-1 path)": (swap(
        '    if not LOCK_FILE_NAME_RE.fullmatch(name) or ".." in name:\n        return []  # already',
        '    if False:\n        return []  # already',
        '        parts = _pypi_parts(name)\n        if parts is None or _norm(parts[0]) != name_part or parts[1] != ver:',
        '        m = re.fullmatch(r"([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)-(.+)\\.tar\\.gz", name)\n'
        '        if not m or _norm(m.group(1)) != name_part or m.group(2) != ver:'), "test_adversarial_pypi_names"),
    "R2-4: the skip dropped (new regex)": (swap(
        '    if not LOCK_FILE_NAME_RE.fullmatch(name) or ".." in name:\n        return []  # already',
        '    if False:\n        return []  # already'), "test_adversarial_pypi_names"),
    "R2-5: the pypi path binding dropped": (swap(
        '        if not PYPI_PATH_RE.fullmatch(path.rsplit("/", 1)[0] + "/") or path.rsplit("/", 1)[-1] != name:',
        '        if False:'), "test_pypi_path_layout"),
    "R2-5: pypi hex case-insensitive": (swap(
        'PYPI_PATH_RE = re.compile(r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/")',
        'PYPI_PATH_RE = re.compile(r"/packages/[0-9a-fA-F]{2}/[0-9a-fA-F]{2}/[0-9a-fA-F]{60}/")'), "test_pypi_path_layout"),
    "R2-5: pypi third segment any length": (swap(
        'PYPI_PATH_RE = re.compile(r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/")',
        'PYPI_PATH_RE = re.compile(r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]+/")'), "test_pypi_path_layout"),
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
print(f"\nU7a rework r2 controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
