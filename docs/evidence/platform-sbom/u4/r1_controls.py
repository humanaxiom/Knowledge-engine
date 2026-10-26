"""platform-sbom U4 rework round 1 RED: controls for the tests below the
"U4 rework round 1" banner of tests/test_sbom_obligations.py and the fake
syft cache model in tests/fake_docker.py.

Never writes the repository. Reuses run_tree() of u4_controls.py (a
temporary tree with the given bundle.sh, sbom_check.py, offline_check.sh,
compose file and docker/source-policy.json; harness ROOTs patched), with the
round-1 targets (u4/r1-target-*) as the base. Each row runs the named real
test methods on the targets ("must pass") or on one mutant of them ("must
fail": at least one of the named tests fails). `--base repo` uses the
repository's own files as the base (for GREEN).

Usage (bash, git and jq needed: run it in the gates image, from the repo root):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \
    --profile gates run --rm gates \
    uv run --locked python docs/evidence/platform-sbom/u4/r1_controls.py [--base repo]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import u4_controls as u4c  # noqa: E402

from tests import fake_docker  # noqa: E402
from tests import test_sbom_obligations as tso  # noqa: E402

REPO = u4c.REPO
if u4c.BASE_REPO:
    def _read(rel: str) -> str:
        return (REPO / rel).read_text(encoding="utf-8")
    B, C, D = _read("scripts/bundle.sh"), _read("scripts/sbom_check.py"), _read("docker-compose.sbom.yml")
    O, P = _read("scripts/offline_check.sh"), _read("docker/source-policy.json")
else:
    def _read(rel: str) -> str:
        return (HERE / rel).read_text(encoding="utf-8")
    B, C, D = _read("r1-target-bundle.sh"), _read("r1-target-sbom_check.py"), _read("r1-target-docker-compose.sbom.yml")
    O, P = _read("r1-target-offline_check.sh"), _read("r1-target-source-policy.json")

sub = u4c.sub
rows = u4c.rows


def T(cls: type, *names: str) -> list:
    return [cls(n) for n in names]


U = tso.ReworkR1UnlicensedTest
COUNT = T(U, "test_hash_only_licences_count_as_unlicensed")
MARK = T(U, "test_hash_rows_marked_unidentified_in_report_lines")
REAL = T(U, "test_real_package_lists_report_hash_only_rows")
ESC = T(U, "test_report_lines_escape_control_characters")
ODD = T(U, "test_unlicensed_report_survives_odd_external_refs")
POL = T(tso.ReworkR1PolicyTest, "test_always_flags_gcc_runtime_jrt_fs_and_alpine_subpackages")
DR = tso.ReworkR1DriftTest
SUMMARY = T(DR, "test_drift_prints_one_summary_line_on_success")
FORK = T(DR, "test_drift_accepts_forked_psycopg_c_lock")
UPSTREAM = T(DR, "test_psycopg_check_splits_upstream_at_at")
ADDED = T(DR, "test_added_packages_errors_are_value_errors")
BT = tso.ReworkR1BundleTest
TMPFS = T(BT, "test_sbom_tmp_tmpfs_is_mode_1777_not_exec")
NOWARN = T(BT, "test_bundle_syft_runs_print_no_cache_warning")
MODEL = T(BT, "test_fake_syft_models_the_cache_warning")
BOUT = T(BT, "test_bundle_output_marks_unidentified_and_escapes_generator_text")
FT = tso.ReworkR1DiskFloorTest
FPARENT = T(FT, "test_bundle_floor_on_out_parent_when_out_exists")
FOUT = T(FT, "test_bundle_floor_on_out_when_out_exists")
FBOTH = T(FT, "test_bundle_floor_both_filesystems_fit")
FONE = T(FT, "test_bundle_floor_probes_once_on_one_filesystem")
OFF = T(tso.ReworkR1OfflineTest, "test_offline_drift_step_labelled_summarised_and_quiet")
ALL = (COUNT + MARK + REAL + ESC + ODD + POL + SUMMARY + FORK + UPSTREAM + ADDED + TMPFS + NOWARN + MODEL + BOUT
       + FPARENT + FOUT + FBOTH + FONE + OFF)
# U4 tests the rework must keep green (existing report, policy, drift, carry).
KEEP = [tso.UnlicensedReportTest("test_unlicensed_packages_are_reported"),
        tso.UnlicensedBundleOutputTest("test_bundle_output_lists_unlicensed_packages_per_image"),
        tso.NamedComponentsTest("test_source_policy_always_covers_psc22_components"),
        tso.DriftLogicTest("test_ke_app_sbom_lists_libpq5_and_psycopg_c_not_binary"),
        tso.DriftLogicTest("test_added_packages_read_from_notice_test_module"),
        tso.DriftOfflineCheckTest("test_offline_check_runs_image_side_drift_check"),
        tso.SbomCarryU4Test("test_sbom_generator_cache_under_tmp")]


def run(group: str, name: str, want_fail: bool, tests: list, *, check: str = C, bundle: str = B, compose: str = D,
        offline: str = O, policy: str = P) -> None:
    fresh = [type(t)(t._testMethodName) for t in tests]  # noqa: SLF001
    u4c.row(group, name, want_fail, u4c.run_tree(fresh, bundle=bundle, check=check, compose=compose,
                                                   offline=offline, policy=policy))


def c(old: str, new: str, count: int = 1) -> str:
    return sub(C, old, new, count)


HASH_FN_IDS = "    return bool(ids) and all(HASH_ID_RE.fullmatch(i) for i in ids)\n"
SKIP_WITH = '        elif tok.upper() == "WITH":\n            skip = True\n'
OPS = '        elif tok.upper() not in ("AND", "OR"):\n'
SPLIT = 're.split(r"[\\s()]+", value)'
CLEAN = '    return CONTROL_RE.sub(lambda m: f"\\\\x{ord(m.group()):02x}", str(value))\n'
LIBPQ_UP = '_qualifiers(purl).get("upstream", "").split("@", 1)[0])'
SUMMARY_PRINT = '    print(f"sbom_check: drift: ok: added {\', \'.join(sorted(added))}; no pip; CPython {\', \'.join(py)} "\n'


def check_rows() -> None:
    g = "sbom_check.py (H-1)"
    run(g, "TARGET (all round-1 tests + kept U4 tests)", False, ALL + KEEP)
    run(g, "no hash rule (U4 GREEN _missing)", True, COUNT + MARK + REAL + BOUT,
        check=c("MISSING or _hash_only(value)\n", "MISSING\n"))
    run(g, "hex case-insensitive", True, COUNT,
        check=c('HASH_ID_RE = re.compile(r"LicenseRef-[0-9a-f]{64}")', 'HASH_ID_RE = re.compile(r"LicenseRef-[0-9a-fA-F]{64}")'))
    run(g, "16..64 hex accepted", True, COUNT,
        check=c('HASH_ID_RE = re.compile(r"LicenseRef-[0-9a-f]{64}")', 'HASH_ID_RE = re.compile(r"LicenseRef-[0-9a-f]{16,64}")'))
    run(g, "prefix match (match, not fullmatch)", True, COUNT, check=c(HASH_FN_IDS, HASH_FN_IDS.replace("fullmatch", "match")))
    run(g, "any id a hash (not all)", True, COUNT, check=c(HASH_FN_IDS, HASH_FN_IDS.replace("all(", "any(")))
    run(g, "WITH exception kept as an id", True, COUNT,
        check=c(SKIP_WITH, '        elif tok.upper() == "WITH":\n            pass\n'))
    run(g, "WITH itself kept as an id", True, COUNT, check=c(SKIP_WITH, ""))
    run(g, "operators case-sensitive", True, COUNT,
        check=c(OPS, '        elif tok not in ("AND", "OR"):\n').replace('elif tok.upper() == "WITH"', 'elif tok == "WITH"'))
    run(g, "parentheses not split", True, COUNT, check=c(SPLIT, 're.split(r"\\s+", value)'))
    run(g, "hash rule on declared only", True, COUNT,
        check=c('    return not isinstance(value, str) or value in MISSING or _hash_only(value)\n',
                '    return not isinstance(value, str) or value in MISSING\n')
        .replace('if _missing(pkg.get("licenseDeclared")) and', 'if (_missing(pkg.get("licenseDeclared")) or '
                 '_hash_only(pkg.get("licenseDeclared"))) and', 1))
    run(g, "files entries without the hash rule", True, COUNT,
        check=c('files = [f for f in raw if not _missing(f)]',
                'files = [f for f in raw if isinstance(f, str) and f not in MISSING]'))
    g = "sbom_check.py (marker, L-3, N4)"
    run(g, "no marker", True, MARK + BOUT, check=c('out.append(line + (f" {UNIDENTIFIED}" if r.get("unidentified") else ""))',
                                               "out.append(line)"))
    run(g, "marker on every row", True, MARK + BOUT,
        check=c('out.append(line + (f" {UNIDENTIFIED}" if r.get("unidentified") else ""))',
                'out.append(line + f" {UNIDENTIFIED}")'))
    run(g, "marker only for a hash in licenseDeclared", True, MARK,
        check=c('"unidentified": any(_hash_only(f) for f in fields)', '"unidentified": _hash_only(pkg.get("licenseDeclared"))'))
    run(g, "no escaping", True, ESC + BOUT, check=c(CLEAN, "    return str(value)\n"))
    run(g, "escape C0 only (C1 U+009B kept)", True, ESC + BOUT,
        check=c('CONTROL_RE = re.compile(r"[\\x00-\\x1f\\x7f-\\x9f]")', 'CONTROL_RE = re.compile(r"[\\x00-\\x1f]")'))
    run(g, "escape ESC only (newline kept)", True, ESC + BOUT,
        check=c('CONTROL_RE = re.compile(r"[\\x00-\\x1f\\x7f-\\x9f]")', 'CONTROL_RE = re.compile(r"[\\x1b\\x9b]")'))
    run(g, "purl escaped, name not", True, ESC + BOUT,
        check=c("{_clean(r['spdxid'])} {_clean(r['name'])} (no purl)", "{_clean(r['spdxid'])} {r['name']} (no purl)"))
    run(g, "externalRefs unguarded (U4 GREEN)", True, ODD,
        check=c("    for ref in refs if isinstance(refs, list) else []:\n", "    for ref in refs or []:\n"))
    run(g, "None locator as text (U4 GREEN)", True, ODD,
        check=c("            return loc if isinstance(loc, str) and loc else None\n", "            return str(loc)\n"))
    g = "sbom_check.py (drift N1-N3, N6)"
    run(g, "libpq5 upstream not split at @ (U4 GREEN)", True, UPSTREAM, check=c(LIBPQ_UP, '_qualifiers(purl).get("upstream", ""))'))
    run(g, "libpq5 upstream prefix match", True, UPSTREAM,
        check=c("    if (libpq_pin, f\"postgresql-{major}\") not in libpq:\n",
                "    if not any(v == libpq_pin and u.startswith(f\"postgresql-{major}\") for v, u in libpq):\n"))
    run(g, "SyntaxError not wrapped", True, ADDED,
        check=c("    except SyntaxError as exc:\n        raise ValueError", "    except ValueError as exc:\n        raise ValueError"))
    run(g, "TypeError not wrapped", True, ADDED,
        check=c("except (ValueError, TypeError, SyntaxError, RecursionError) as exc:", "except ValueError as exc:"))
    run(g, "forked lock read as one version (U4 GREEN)", True, FORK,
        check=c("    problems += psycopg_problems(docs[0], a.libpq, locked)\n",
                "    problems += psycopg_problems(docs[0], a.libpq, next(iter(locked)) if len(locked) == 1 else \"?\")\n"))
    run(g, "psycopg-c check dropped (forked lock passes anything)", True, FORK,
        check=c("    if not want & pypi.get(\"psycopg-c\", set()):\n", "    if False:\n"))
    run(g, "no summary line (U4 GREEN)", True, SUMMARY + FORK + OFF,
        check=c('    print(f"sbom_check: drift: ok:', '    _unused = (f"sbom_check: drift: ok:'))
    run(g, "summary on two lines", True, SUMMARY,
        check=c(SUMMARY_PRINT, SUMMARY_PRINT.replace("no pip; ", "no pip;\\n")))
    run(g, "summary without `no pip`", True, SUMMARY, check=c(SUMMARY_PRINT, SUMMARY_PRINT.replace("no pip; ", "")))
    run(g, "summary without the libpq5 pin", True, SUMMARY + OFF,
        check=c("libpq5 {a.libpq} (postgresql-{major})", "libpq5 (postgresql-{major})"))
    run(g, "summary without the added set", True, SUMMARY,
        check=c("added {', '.join(sorted(added))}; ", "added set ok; "))


def compose_rows() -> None:
    g = "compose (B1)"
    tm = "    tmpfs:\n      - /tmp:mode=1777\n"
    run(g, "tmpfs /tmp (U4 GREEN)", True, TMPFS + NOWARN + OFF, compose=sub(D, tm, "    tmpfs:\n      - /tmp\n"))
    run(g, "tmpfs /tmp:mode=1777,exec", True, TMPFS, compose=sub(D, tm, "    tmpfs:\n      - /tmp:mode=1777,exec\n"))
    run(g, "tmpfs /tmp:mode=0755", True, TMPFS + NOWARN, compose=sub(D, tm, "    tmpfs:\n      - /tmp:mode=0755\n"))
    run(g, "tmpfs /tmp:mode=1777,size=64m", True, TMPFS, compose=sub(D, tm, "    tmpfs:\n      - /tmp:mode=1777,size=64m\n"))
    run(g, "XDG_CACHE_HOME dropped (cache on the read-only root)", True, NOWARN + OFF,
        compose=sub(D, "      XDG_CACHE_HOME: /tmp/cache\n", ""))
    g = "fake syft model (harness)"
    script = fake_docker._SCRIPT  # noqa: SLF001
    never = sub(script, "        if _cache3:\n", "        if False:\n")
    with mock.patch.object(fake_docker, "_SCRIPT", never):
        run(g, "fake never warns: the self-test fails", True, MODEL)
        run(g, "fake never warns + tmpfs /tmp: the no-warning test alone passes (why MODEL exists)", False, NOWARN,
            compose=sub(D, "      - /tmp:mode=1777\n", "      - /tmp\n"))
    always = sub(script, "        reason = None if root_user or attr & 0o002 else \"permission denied\"\n",
                 "        reason = \"permission denied\"\n")
    with mock.patch.object(fake_docker, "_SCRIPT", always):
        run(g, "fake warns on every tmpfs: the self-test fails", True, MODEL)


def policy_rows() -> None:
    import json
    g = "source-policy.json (M-1, M-2, L-1)"
    data = json.loads(P)

    def without(image: str, match: str) -> str:
        d = json.loads(P)
        d["always"] = [e for e in d["always"] if (e["image"], e["match"]) != (image, match)]
        assert len(d["always"]) == len(data["always"]) - 1, (image, match)
        return json.dumps(d)

    def plus(entry: dict[str, str]) -> str:
        d = json.loads(P)
        d["always"].append(entry)
        return json.dumps(d)
    for image, match in [*tso.R1_ENTRIES, ("neo4j", "pkg:maven/jrt-fs/jrt-fs")]:
        run(g, f"drop {image} {match}", True, POL, policy=without(image, match))
    run(g, "jrt-fs entry widened to pkg:maven/jrt-fs", True, POL,
        policy=json.dumps({"always": [e if e["match"] != "pkg:maven/jrt-fs/jrt-fs" else {**e, "match": "pkg:maven/jrt-fs"}
                                      for e in data["always"]]}))
    run(g, "a dead entry (upstream=gcc-13 in ke-app)", True, POL,
        policy=plus({"image": "ke-app", "match": "upstream=gcc-13", "why": "mutant"}))
    run(g, "U4 GREEN policy (u4/target-source-policy.json, 16 entries)", True, POL,
        policy=(HERE / "target-source-policy.json").read_text(encoding="utf-8"))


def offline_rows() -> None:
    g = "offline_check.sh (N7)"
    lab = '--label "com.docker.compose.project=${project}-sbomcheck" '
    run(g, "no label (U4 GREEN)", True, OFF, offline=sub(O, lab, ""))
    run(g, "label of another project", True, OFF, offline=sub(O, lab, '--label "com.docker.compose.project=ke-other" '))
    run(g, "label key not the compose project", True, OFF, offline=sub(O, lab, '--label "ke.project=${project}" '))


def floor_rows() -> None:
    g = "bundle.sh (N5 floor)"
    second = 'if [ "$parent_probe" != "$out_probe" ]; then\n  check_floor "$out_parent" "$parent_probe"\nfi\n'
    run(g, "no floor on dirname(--out) (U4 GREEN)", True, FPARENT + FBOTH, bundle=sub(B, second, ""))
    run(g, "no same-probe skip (df twice)", True, FONE, bundle=sub(B, second, 'check_floor "$out_parent" "$parent_probe"\n'))
    run(g, "parent refusal names --out", True, FPARENT,
        bundle=sub(B, 'die "need 7 GiB free on $1, found', 'die "need 7 GiB free on $out, found'))
    run(g, "parent probe measured at --out", True, FPARENT + FBOTH,
        bundle=sub(B, 'parent_probe="$(floor_probe "$out_parent")"', 'parent_probe="$(floor_probe "$out")"'))
    run(g, "--out floor dropped (parent only)", True, FOUT + FBOTH,
        bundle=sub(B, 'check_floor "$out" "$out_probe"\n', ""))
    run(g, "U4 GREEN bundle.sh (u4/target-bundle.sh)", True, FPARENT + FBOTH,
        bundle=(HERE / "target-bundle.sh").read_text(encoding="utf-8"))


def main() -> int:
    check_rows()
    compose_rows()
    policy_rows()
    offline_rows()
    floor_rows()
    bad = [r for r in rows if not r[3]]
    width = max(len(r[1]) for r in rows)
    print(f"U4 rework round 1 controls ({'base repo' if u4c.BASE_REPO else 'r1 targets'}): {len(rows)} rows, "
          f"{sum(1 for r in rows if r[2] == 'must fail')} must-fail, "
          f"{sum(1 for r in rows if r[2] == 'must pass')} must-pass, {len(bad)} unexpected")
    for group, name, want, ok, detail in rows:
        print(f"{'ok ' if ok else 'BAD'} [{group}] {name.ljust(width)} {want:9} | {detail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
