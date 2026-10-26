"""platform-sbom U5 rework round 1 RED: controls for tests/test_sbom_classifier.py
(the U5 classes and the ReworkR1* classes), with the U5 tree, smoke, scanner and
offline rows kept as regressions. Supersedes u5_controls.py for the classifier
rows (its anchors fit the U5 target only).

Base: the repository's files (U5 GREEN), with scripts/sbom_check.py replaced by
u5/r1-target-sbom_check.py (rework rulings 1-7 and additions a-b; design-notes
"N8 amendment, U5", "Rework round 1"). The "U5 sbom_check.py" rows run
u5/target-sbom_check.py, which equals the U5 GREEN checker.

Never writes the repository. It builds a temporary checkout holding the files
the harnesses read, with the U5 targets (docs/evidence/platform-sbom/u5/target-*)
in place, and runs real test methods on the targets and on mutants of them:
  A. the classifier, escaping and tree logic (scripts/sbom_check.py), by
     patching each test module's load_sbom_check;
  B. the PS-1.2 scanner exemption (tests/hardcoded_scan.py);
  C. the smoke no-plugin step (scripts/smoke.sh, fake docker);
  D. the offline check's ke-neo4j step (scripts/offline_check.sh; comment only).
Each "must fail" row names the one test method that must fail; "must pass"
rows run every listed method. Exit 1 if any row is unexpected.

Usage (needs bash, git and jq: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u5/r1_controls.py [--base repo]
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
from typing import Any, Callable
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests import test_engine_hardcoded as teh  # noqa: E402
from tests import test_neo4j_image as tni  # noqa: E402
from tests import test_offline_check as toc  # noqa: E402
from tests import test_sbom_classifier as tsc  # noqa: E402
from tests import test_stack_scripts as tss  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
TARGETS = {"scripts/sbom_check.py": "r1-target-sbom_check.py"}
COPY = ["scripts", "docker", "docker-compose.yml", "docker-compose.verify.yml", "docker-compose.sbom.yml",
        "docker-compose.offline.yml", ".env.example", "NOTICE.md", "licenses", "config", "uv.lock", "pyproject.toml",
        "tests/test_notice_ke_app.py", "tests/hardcoded_scan.py", ".github", "engine", "harness_telemetry"]


def make_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="u5r1-controls-"))
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


def head(rel: str) -> str:
    """The file as committed at U4b (HEAD), whatever the working tree holds."""
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "show", f"HEAD:{rel}"],
                          capture_output=True, text=True, check=True, encoding="utf-8").stdout


def row(group: str, name: str, must_fail: bool, problems: list[str]) -> None:
    failed = bool(problems)
    ok = failed == must_fail
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


def run_test(cls: type, method: str, patches: list[Any]) -> list[str]:
    """Run one test method under the patches; [] if it passed, else the failures."""
    suite = unittest.TestSuite([cls(method)])
    result = unittest.TestResult()
    with mock.patch.object(tni, "ROOT", ROOT), mock.patch.object(tss, "ROOT", ROOT), \
            mock.patch.object(toc, "ROOT", ROOT), mock.patch.object(toc, "OFFLINE_CHECK",
                                                                    ROOT / "scripts" / "offline_check.sh"):
        for p in patches:
            p.start()
        try:
            suite.run(result)
        finally:
            for p in patches:
                p.stop()
    bad = result.failures + result.errors
    return [f"{method}: " + str(b[1]).strip().splitlines()[-1] for b in bad]


def module_of(src: str) -> ModuleType:
    path = Path(tempfile.mkdtemp(prefix="u5r1-check-")) / "sbom_check.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"u5_mutant_{path.parent.name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- A. classifier, escaping and tree logic ----------------------------------------
R1_CLASSES = (tsc.ReworkR1UnknownLeavesTest, tsc.ReworkR1TokenRuleTest, tsc.ReworkR1NonAsciiTest,
              tsc.ReworkR1WithExceptionTest, tsc.ReworkR1PerPartTest, tsc.ReworkR1DriftLineTest)
CLASSIFIER_TESTS = [(cls, name) for cls in (tsc.GplIdTest, tsc.NeedsSourceTest, tsc.LicenceInputTest,
                                             tsc.ClassifyPackageTest, tsc.ClassifyDocumentTest, tsc.EscapingTest,
                                             *R1_CLASSES)
                    for name in unittest.defaultTestLoader.getTestCaseNames(cls)]
TREE_TESTS = [(tni.Neo4jTreeCheckTest, n) for n in unittest.defaultTestLoader.getTestCaseNames(tni.Neo4jTreeCheckTest)]
OTHER_LOGIC = [(tni.Neo4jConfigCheckTest, "test_neo4j_config_check_logic"),
               (tni.Neo4jTarCheckTest, "test_neo4j_tar_check_logic"),
               (tni.Neo4jSbomCheckTest, "test_neo4j_sbom_check_logic")]
ALL_LOGIC = CLASSIFIER_TESTS + TREE_TESTS + OTHER_LOGIC
BY_NAME = {name: cls for cls, name in ALL_LOGIC}


def logic_problems(mod: ModuleType, tests: list[tuple[type, str]]) -> list[str]:
    patches = [mock.patch.object(tsc, "load_sbom_check", lambda m=mod: m),
               mock.patch.object(tni, "load_sbom_check", lambda m=mod: m)]
    out: list[str] = []
    for cls, method in tests:
        out += run_test(cls, method, patches)
    return out


CHECK_SRC = text("scripts/sbom_check.py")
row("logic", f"TARGET: all {len(ALL_LOGIC)} logic tests", False, logic_problems(module_of(CHECK_SRC), ALL_LOGIC))
row("logic", "TARGET: test_neo4j_checker_cli (python -I on the copy)", False,
    run_test(tni.Neo4jCheckerCliTest, "test_neo4j_checker_cli", []))
HEAD_MOD = module_of(head("scripts/sbom_check.py"))
for name in ("test_classifier_table", "test_licence_input_selection", "test_classify_document_skips_root_and_applies_always",
             "test_validate_rejects_trailing_newline_spdxid_and_prints_escaped",
             "test_drift_problems_escape_debian_name_and_cpython_version", "test_finish_argv_patterns_fullmatch",
             "test_tree_listing_records_regular_file_size", "test_tree_check_compares_size_and_hard_links_both_ways"):
    row("logic", f"HEAD sbom_check.py: {name}", True, logic_problems(HEAD_MOD, [(BY_NAME[name], name)]))
U5_MOD = module_of((HERE / "target-sbom_check.py").read_text(encoding="utf-8"))
for name in ("test_unknown_leaves_any_case", "test_unknown_runs_in_unparseable_text", "test_unknown_exception_ids",
             "test_wider_token_rule_ids", "test_wider_token_rule_expressions", "test_non_ascii_expressions",
             "test_non_ascii_package", "test_gpl_family_exception_id", "test_drift_success_line_is_clean_and_non_namespaced",
             "test_is_gpl_id_pattern_and_token_rule", "test_unknown_leaves_need_source_and_are_unidentified"):
    row("logic", f"U5 sbom_check.py: {name}", True, logic_problems(U5_MOD, [(BY_NAME[name], name)]))
for name in ("test_unparseable_part_does_not_hide_an_unknown_leaf", "test_each_part_is_classified_alone"):
    # B1 was a test gap: the U5 checker already classifies per part
    row("logic", f"U5 sbom_check.py: {name} (guard, green before round 1)", False,
        logic_problems(U5_MOD, [(BY_NAME[name], name)]))
for name in ("test_neo4j_tree_check_logic", "test_psycopg_problems_escape"):  # re-targeted / guard: green on HEAD
    row("logic", f"HEAD sbom_check.py: {name} (guard, green before U5)", False,
        logic_problems(HEAD_MOD, [(BY_NAME[name], name)]))

MUTANTS: dict[str, tuple[Callable[[str], str], str]] = {
    "L-4 open: the classifier uses the report's _missing (hash = missing)": (swap(
        "    return isinstance(value, str) and value not in MISSING\n\n\ndef _input_parts",
        "    return not _missing(value)\n\n\ndef _input_parts"), "test_both_fields_set"),
    "L-4 open (licence_input)": (swap(
        "    return isinstance(value, str) and value not in MISSING\n\n\ndef _input_parts",
        "    return not _missing(value)\n\n\ndef _input_parts"), "test_licence_input_selection"),
    "NONE/NOASSERTION leaves read as known ids": (swap(
        "    return bool(HASH_ID_RE.fullmatch(id_)) or (id_.isascii() and id_.upper() in UNKNOWN_LEAVES)",
        "    return bool(HASH_ID_RE.fullmatch(id_))"), "test_unknown_leaves_need_source_and_are_unidentified"),
    "R1-1: NONE/NOASSERTION leaves case-sensitive (U5 round 0)": (swap(
        "(id_.isascii() and id_.upper() in UNKNOWN_LEAVES)", "(id_ in UNKNOWN_LEAVES)"), "test_unknown_leaves_any_case"),
    "R1-1: the whole-field predicate case-folded too (none = missing)": (swap(
        "    return isinstance(value, str) and value not in MISSING\n\n\ndef _input_parts",
        "    return isinstance(value, str) and value.upper() not in MISSING\n\n\ndef _input_parts"),
        "test_unknown_leaves_any_case"),
    "hash ids case-insensitive": (swap("    return bool(HASH_ID_RE.fullmatch(id_)) or",
                                       '    return bool(re.fullmatch(r"LicenseRef-[0-9a-fA-F]{64}", id_)) or'),
                                  "test_unknown_leaves_need_source_and_are_unidentified"),
    "R1-1: junk NONE/NOASSERTION runs ignored (B2 open)": (swap(
        '        r.isascii() and r.upper() in UNKNOWN_LEAVES for r in re.split(r"[\\s()]+", text))',
        "        False for r in ())"), "test_unknown_runs_in_unparseable_text"),
    "R1-1: junk runs case-sensitive": (swap("r.isascii() and r.upper() in UNKNOWN_LEAVES for r in",
                                            "r in UNKNOWN_LEAVES for r in"), "test_unknown_runs_in_unparseable_text"),
    "R1-1: junk NONE as a substring, not a run": (swap(
        'any(\n        r.isascii() and r.upper() in UNKNOWN_LEAVES for r in re.split(r"[\\s()]+", text))',
        "any(k in text.upper() for k in UNKNOWN_LEAVES)"), "test_unknown_runs_in_unparseable_text"),
    "R1-b: unknown exception ids not read": (swap("        if _unknown_id(exc):  # addition b",
                                                  "        if False:  # addition b"), "test_unknown_exception_ids"),
    "R1-b: an unknown exception listed but not needing source": (swap(
        "        if _unknown_id(exc):  # addition b: an unknown exception id\n            return True, unparsed, True",
        "        if _unknown_id(exc):  # addition b: an unknown exception id\n            return needs, unparsed, True"),
        "test_unknown_exception_ids"),
    "R1-4: the exception slot not read (U5 round 0)": (swap("        if _pattern_hit(exc) or _token_hit(exc):  # ruling 4",
                                                            "        if False:  # ruling 4"), "test_gpl_family_exception_id"),
    "R1-4: a GPL exception listed but not needing source": (swap(
        "            return True, True, unidentified\n", "            return needs, True, unidentified\n"),
        "test_gpl_family_exception_id"),
    "R1-4: a GPL exception needs source but is not listed": (swap(
        "            return True, True, unidentified\n", "            return True, unparsed, unidentified\n"),
        "test_gpl_family_exception_id"),
    "R1-2: the N8a token rule (U5 round 0)": (swap(
        '    return (any("gpl" in t or t == "affero" for t in tokens)\n            or bool(GPL_PHRASE_RE.search(" ".join(tokens))))',
        '    return any(re.fullmatch(r"(a|l)?gpl(v?\\d+)?", t) for t in tokens)'), "test_wider_token_rule_ids"),
    "R1-2: no affero": (swap('"gpl" in t or t == "affero"', '"gpl" in t'), "test_wider_token_rule_ids"),
    "R1-2: no phrase": (swap('            or bool(GPL_PHRASE_RE.search(" ".join(tokens))))', "            or False)"),
                        "test_wider_token_rule_ids"),
    "R1-a: phrase singular only": (swap("general public licen[cs]es?(?: |$)", "general public licen[cs]e(?: |$)"),
                                   "test_wider_token_rule_expressions"),
    "R1-2: phrase words anywhere (not consecutive)": (swap(
        '            or bool(GPL_PHRASE_RE.search(" ".join(tokens))))',
        '            or ({"general", "public"} <= set(tokens) and any(t.startswith("licen") for t in tokens)))'),
        "test_wider_token_rule_ids"),
    "R1-2: `lesser` alone a hit": (swap('"gpl" in t or t == "affero"', '"gpl" in t or t in ("affero", "lesser")'),
                                   "test_wider_token_rule_ids"),
    "R1-2: `general` alone a hit": (swap('"gpl" in t or t == "affero"', '"gpl" in t or t in ("affero", "general")'),
                                    "test_wider_token_rule_ids"),
    "R1-3: no non-ASCII rule": (swap("    if not expr.isascii():  # rework ruling 3", "    if False:  # rework ruling 3"),
                                "test_non_ascii_expressions"),
    "R1-3: no non-ASCII rule, operators by str.upper() (dotless i = WITH)": (swap(
        "    if not expr.isascii():  # rework ruling 3", "    if False:  # rework ruling 3",
        '        return t.upper() if t is not None and t.isascii() else ""', '        return t.upper() if t is not None else ""'),
        "test_non_ascii_expressions"),
    "R1-3: non-ASCII needs source but is not listed": (swap(
        '        return True, {"unparsed": True, "unidentified": _unknown_in_text(expr)}',
        '        return True, {"unparsed": False, "unidentified": _unknown_in_text(expr)}'), "test_non_ascii_expressions"),
    # No row for "the ok line without _clean": with the non-namespaced set
    # the line can only hold the one version that equals the licence files'
    # `CPython X.Y.Z:` (digits and dots), so that mutant is equivalent; the
    # _clean is defence in depth (ruling 5 asks for both).
    "R1-5: drift ok line raw AND from _named (the U5 line)": (swap(
        "CPython {_clean(', '.join(py))}", "CPython {', '.join(py)}",
        "    py = sorted(_cpython(docs[0]))", '    py = sorted(_named(docs[0], "generic").get("python", set()))'),
        "test_drift_success_line_is_clean_and_non_namespaced"),
    "R1-5: drift ok line from _named (namespaced rows too)": (swap(
        "    py = sorted(_cpython(docs[0]))", '    py = sorted(_named(docs[0], "generic").get("python", set()))'),
        "test_drift_success_line_is_clean_and_non_namespaced"),
    "R1-6 (B1): classify the joined text, not each part": (swap(
        "    for part in parts:\n        n, info = needs_source(part)",
        "    for part in ([licence_input(pkg)] if parts else []):\n        n, info = needs_source(part)"),
        "test_each_part_is_classified_alone"),
    "needs(OR) = any": (swap('if node[0] == "and" else all(r[0] for r in results)',
                             'if node[0] == "and" else any(r[0] for r in results)'), "test_classifier_table"),
    "needs(AND) = all": (swap('needs = any(r[0] for r in results) if node[0] == "and"',
                              'needs = all(r[0] for r in results) if node[0] == "and"'), "test_classifier_table"),
    "precedence inverted (OR binds tighter than AND)": (swap('return binary("OR", lambda: binary("AND", primary))',
                                                            'return binary("AND", lambda: binary("OR", primary))'),
                                                       "test_precedence_and_parentheses"),
    "an unclosed parenthesis accepted": (swap('            if peek() != ")":\n                raise _Unparsed\n            take()\n',
                                              '            if peek() == ")":\n                take()\n'),
                                         "test_unparseable_text"),
    "operators case-sensitive": (swap('        return t.upper() if t is not None and t.isascii() else ""',
                                      '        return t if t is not None and t.isascii() else ""'),
                                 "test_operators_any_case"),
    "WITH reads gpl(X) only (an unknown X passes)": (swap(
        "        needs, unparsed, unidentified = _leaf(node[1])\n",
        "        needs, unparsed, unidentified = (True, False, False) if is_gpl_id(node[1]) else (False, False, False)\n"),
        "test_unknown_leaves_need_source_and_are_unidentified"),
    "no token rule (ids)": (swap("    if _token_hit(id_):\n        return True, True, False",
                                 "    if False:\n        return True, True, False"), "test_url_folded_ids"),
    "no token rule (is_gpl_id)": (swap("(_pattern_hit(id_) or _token_hit(id_))", "_pattern_hit(id_)"),
                                  "test_is_gpl_id_pattern_and_token_rule"),
    "token-rule ids not listed unparsed": (swap("    if _token_hit(id_):\n        return True, True, False",
                                                "    if _token_hit(id_):\n        return True, url, False"),
                                           "test_named_licenseref_rows"),
    "http ids not listed unparsed": (swap('url = id_.lower().startswith("licenseref-") and "http" in id_.lower()',
                                          "url = False"), "test_url_folded_ids"),
    "http matched case-sensitively": (swap('and "http" in id_.lower()', 'and "http" in id_'), "test_url_folded_ids"),
    "LicenseRef- stripped before lower-casing": (swap(
        '    low = id_.lower()\n    if low.startswith("licenseref-"):\n        low = low[len("licenseref-"):]',
        '    low = (id_[len("LicenseRef-"):] if id_.startswith("LicenseRef-") else id_).lower()'),
        "test_named_licenseref_rows"),
    "junk: hash ids ignored (listing only)": (swap("    return bool(HASH_ID_RE.search(text)) or any(", "    return any("),
                                              "test_unparseable_text"),
    "junk: \\bgpl\\b instead of the token rule": (swap(
        "        return _token_hit(expr) or unknown,",
        '        return bool(re.search(r"\\bgpl\\b", expr, re.I)) or unknown,'), "test_unparseable_text"),
    "deep nesting raises (RecursionError not caught)": (swap("except (_Unparsed, RecursionError):", "except _Unparsed:"),
                                                       "test_needs_source_never_raises"),
    "licence_input joins without parentheses": (swap('" AND ".join(f"({x})" for x in parts)', '" AND ".join(parts)'),
                                                "test_licence_input_selection"),
    "both set: declared only": (swap("    parts = [v for v in (declared, concluded) if _set(v)]\n",
                                     "    parts = [v for v in (declared, concluded) if _set(v)][:1]\n"),
                                "test_both_fields_set"),
    "files read when declared is set": (swap(
        "    if not parts:\n        raw = pkg.get(\"licenseInfoFromFiles\")\n"
        "        parts = [f for f in raw if _set(f)] if isinstance(raw, list) else []",
        "    if True:\n        raw = pkg.get(\"licenseInfoFromFiles\")\n"
        "        parts = parts + ([f for f in raw if _set(f)] if isinstance(raw, list) else [])"),
        "test_licence_input_selection"),
    "type rule dropped (any non-missing value is set)": (swap(
        "    return isinstance(value, str) and value not in MISSING\n\n\ndef _input_parts",
        "    return value is not None and value not in MISSING\n\n\ndef _input_parts"), "test_licence_input_type_rule"),
    "classify_document includes the DESCRIBES root": (swap(
        "    for pkg in _packages(doc):\n        row = classify_package(pkg)",
        "    for pkg in [p for p in doc.get(\"packages\") or [] if isinstance(p, dict)]:\n        row = classify_package(pkg)"),
        "test_classify_document_skips_root_and_applies_always"),
    "always does not force needs": (swap('        if row["always"]:\n            row["needs"] = True\n', ""),
                                    "test_classify_document_skips_root_and_applies_always"),
    "always (real policy) not applied": (swap('        if row["always"]:\n            row["needs"] = True\n', ""),
                                         "test_classify_document_real_neo4j_rows"),
    "validate: SPDXID with match ($ before a final newline)": (swap("SPDXID_RE.fullmatch(sid)", "SPDXID_RE.match(sid)"),
                                                              "test_validate_rejects_trailing_newline_spdxid_and_prints_escaped"),
    "validate: SPDXID printed raw": (swap('p.append(f"package {_clean(sid)} has no name")',
                                          'p.append(f"package {sid} has no name")'),
                                     "test_validate_rejects_trailing_newline_spdxid_and_prints_escaped"),
    "validate: created with match": (swap("RFC3339_UTC.fullmatch(", "RFC3339_UTC.match("),
                                     "test_validate_rejects_created_with_trailing_newline"),
    "drift: Debian name printed raw": (swap("the Debian package {_clean(n)}", "the Debian package {n}"),
                                       "test_drift_problems_escape_debian_name_and_cpython_version"),
    "drift: CPython version printed raw": (swap("the ke-app SBOM lists {_clean(sorted(py)[0])}",
                                                "the ke-app SBOM lists {sorted(py)[0]}"),
                                           "test_drift_problems_escape_debian_name_and_cpython_version"),
    "finish: --name/--git-sha with match": (swap("        if not rx.fullmatch(value):", "        if not rx.match(value):"),
                                            "test_finish_argv_patterns_fullmatch"),
    "tree: size not recorded": (swap('m.size if kind == "file" else 0', "0"), "test_tree_listing_records_regular_file_size"),
    "tree: size not compared": (swap('m.size if kind == "file" else 0', "0"),
                                "test_tree_check_compares_size_and_hard_links_both_ways"),
    "tree: hard links resolved in the official listing only (U4b)": (swap(
        "    official, image = _resolve_hardlinks(official), _resolve_hardlinks(image)\n",
        "    official = _resolve_hardlinks(official)\n"), "test_tree_check_compares_size_and_hard_links_both_ways"),
    "tree: a hard link takes size 0, not its target's": (swap('out[rel] = ("file", entry[1], entry[2], entry[3], target[4], "")',
                                                              'out[rel] = ("file", entry[1], entry[2], entry[3], 0, "")'),
                                                         "test_tree_check_compares_size_and_hard_links_both_ways"),
    "tree: a hard link takes its target's mode": (swap('out[rel] = ("file", entry[1], entry[2], entry[3], target[4], "")',
                                                       'out[rel] = ("file", target[1], target[2], target[3], target[4], "")'),
                                                  "test_tree_check_compares_size_and_hard_links_both_ways"),
}
for name, (m, method) in MUTANTS.items():
    try:
        mod = module_of(m(CHECK_SRC))
    except AssertionError as exc:
        row("logic", name, True, [])  # an anchor that no longer fits is a BAD row, never a silent pass
        print(f"    anchor: {exc}")
        continue
    row("logic", name, True, logic_problems(mod, [(BY_NAME[method], method)]))

JOINED = swap("    for part in parts:\n        n, info = needs_source(part)",
              "    for part in ([licence_input(pkg)] if parts else []):\n        n, info = needs_source(part)")
row("logic", "R1-6 (B1): joined-text mutant vs the B1 rows alone (survives under ruling 1; documented)", False,
    logic_problems(module_of(JOINED(CHECK_SRC)), [(BY_NAME["test_unparseable_part_does_not_hide_an_unknown_leaf"],
                                                   "test_unparseable_part_does_not_hide_an_unknown_leaf")]))
row("logic", "R1-6 (B1): joined-text mutant on the U5 checker vs the B1 rows (killed before ruling 1)", True,
    logic_problems(module_of(JOINED((HERE / "target-sbom_check.py").read_text(encoding="utf-8"))),
                   [(BY_NAME["test_unparseable_part_does_not_hide_an_unknown_leaf"],
                     "test_unparseable_part_does_not_hide_an_unknown_leaf")]))

# ---- B. the PS-1.2 scanner exemption -----------------------------------------------
subprocess.run(["git", "init", "-q", str(ROOT)], check=True)  # the repository scan lists files with git
SCAN_SRC = text("tests/hardcoded_scan.py")
SCAN_TESTS = [(teh.ScannerContractTest, "test_dockerfile_exemption_skips_continuation_lines"),
              (teh.ScannerContractTest, "test_dockerfile_exemption_covers_only_its_instruction_line"),
              (teh.ScannerContractTest, "test_exemption_covers_only_its_symbol_and_path"),
              (teh.ScannerWideningTest, "test_n4_exemption_covers_only_the_assignment_line"),
              (teh.RepositoryScanTest, "test_no_hardcoded_ports")]


def scan_rows(label: str, src: str, must_fail: bool, only: str | None = None) -> None:
    mod = module_of(src)
    problems: list[str] = []
    with mock.patch.object(teh, "ROOT", ROOT):
        for cls, method in SCAN_TESTS:
            if only and method != only:
                continue
            problems += run_test(cls, method, [mock.patch("tests.hardcoded_scan.find_hardcoded", mod.find_hardcoded)])
    row("exemption", label, must_fail, problems)


scan_rows("TARGET scanner", SCAN_SRC, False)
scan_rows("HEAD scanner (no continuation rule)", head("tests/hardcoded_scan.py"), True,
          "test_dockerfile_exemption_skips_continuation_lines")
for name, m in {
    "previous line not right-stripped": swap('prev.rstrip().endswith("\\\\")', 'prev.endswith("\\\\")'),
    "any backslash in the previous line": swap('prev.rstrip().endswith("\\\\")', '"\\\\" in prev'),
    "prev never updated": swap("            prev = line\n", ""),
}.items():
    scan_rows(name, m(SCAN_SRC), True, "test_dockerfile_exemption_skips_continuation_lines")
scan_rows("the exemption never applies (control: the passing half is exercised)", swap(
    "            if not continued and any(", "            if False and any(")(SCAN_SRC), True,
    "test_dockerfile_exemption_skips_continuation_lines")

# ---- C. smoke ------------------------------------------------------------------------
SMOKE = text("scripts/smoke.sh")
SMOKE_TESTS = ("test_smoke_checks_no_fleet_plugin_in_neo4j", "test_smoke_fails_when_the_fleet_plugin_is_in_neo4j",
               "test_smoke_never_evaluates_the_neo4j_output")


def smoke_rows(label: str, src: str, must_fail: bool) -> None:
    (ROOT / "scripts" / "smoke.sh").write_text(src, encoding="utf-8", newline="\n")
    try:
        problems: list[str] = []
        for method in SMOKE_TESTS:
            problems += run_test(tni.SmokeNoFleetPluginTest, method, [])
        row("smoke", label, must_fail, problems)
    finally:
        (ROOT / "scripts" / "smoke.sh").write_text(SMOKE, encoding="utf-8", newline="\n")


smoke_rows("TARGET", SMOKE, False)
PRUNE = "\\( -path /proc -o -path /sys -o -path /dev \\) -prune -o "
for name, m in {
    "HEAD smoke (-xdev, U4b)": lambda t: head("scripts/smoke.sh"),
    "prune kept, -xdev added back": swap("find / " + PRUNE, "find / -xdev " + PRUNE),
    "-mount instead of the prune": swap("find / " + PRUNE, "find / -mount "),
    "only /proc pruned": swap(PRUNE, "-path /proc -prune -o "),
    "/dev not pruned": swap(PRUNE, "\\( -path /proc -o -path /sys \\) -prune -o "),
    "no prune at all": swap("find / " + PRUNE, "find / "),
    "the exec status ignored": swap("-print)\" || {", "-print)\" || true; true || {"),
}.items():
    smoke_rows(name, m(SMOKE), True)

# ---- D. offline check (the U5 change is one comment) ---------------------------------
OFFLINE_TESTS = ("test_offline_check_runs_ke_neo4j_check", "test_offline_check_fails_on_ke_neo4j_problems")
problems = []
for method in OFFLINE_TESTS:
    problems += run_test(tni.OfflineKeNeo4jTest, method, [])
row("offline", "TARGET (drift_work comment)", False, problems)
row("offline", "TARGET has the drift_work comment (ruling 9)", False,
    [] if "# drift_work is reused" in text("scripts/offline_check.sh") else ["no drift_work comment"])

bad = [r for r in rows if not r[3]]
print(f"\nU5 rework r1 controls ({'repo' if BASE_REPO else 'targets'}): {len(rows)} rows, "
      f"{sum(r[2] == 'must fail' for r in rows)} must-fail, {sum(r[2] == 'must pass' for r in rows)} must-pass, "
      f"{len(bad)} unexpected")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if bad else 0)
