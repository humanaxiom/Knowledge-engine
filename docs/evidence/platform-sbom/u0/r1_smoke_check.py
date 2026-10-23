"""platform-sbom U0 rework round 1 RED: drive SmokePsycopgTest against
scratch copies of scripts/smoke.sh. Runs inside the ke-gates image (Linux
bash, the fake docker); never writes the repository.

Variants:
- CURRENT: the repo's scripts/smoke.sh as is (want: every new rework case
  fails, every older case passes).
- TARGET: the repo's smoke.sh with its psycopg block (from the
  "# PSC-25 (N0): the api runs" comment to the closing
  `echo "smoke: psycopg c on Debian libpq5 ..."` line) replaced by
  r1-target-smoke-block.sh (want: every case passes).
- T1..T6: mutants of TARGET; each must turn at least one case red.

Prints one row per (variant, test, subtest) and a summary per variant.

Usage (in ke-gates, repo at /work read-only, /tmp tmpfs):
  python docs/evidence/platform-sbom/u0/r1_smoke_check.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from tests import test_psycopg_c as t  # noqa: E402

HERE = Path(__file__).resolve().parent
smoke = (REPO / "scripts" / "smoke.sh").read_text(encoding="utf-8")
block = (HERE / "r1-target-smoke-block.sh").read_text(encoding="utf-8")
START = "# PSC-25 (N0): the api runs psycopg-c on Debian's libpq5, not a vendored libpq.\n"
END = 'echo "smoke: psycopg c on Debian libpq5 $deb ($libpq)"\n'
assert smoke.count(START) == 1 and smoke.count(END) == 1
target = smoke[:smoke.index(START)] + block + smoke[smoke.index(END) + len(END):]


def sub(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


OLD_ARITH = '''deb_major="${deb%%.*}"
deb_minor="$(printf '%s' "$deb" | sed -E 's/^[0-9]+\\.([0-9]+).*/\\1/')"
old_want=$((10#$deb_major * 10000 + 10#$deb_minor))
'''
VALIDATE = "# M-1: container output never reaches $(( )) unvalidated.\n"
DPKG_W = '''deb="$(compose exec -T api dpkg-query -W -f='${Version}' libpq5)" || {
  echo "smoke: FAIL (libpq: dpkg-query libpq5 failed in api)" >&2
  exit 1
}
'''
WALK = '''b = sorted(os.path.relpath(os.path.join(d, n), sys.prefix) for d, ds, fs in os.walk(sys.prefix)
           for n in ds + fs if n.startswith("psycopg_binary"))
'''
OWNER_RX = r"^libpq5(:[a-z0-9]+)?:\ (.+)$"
OWNER_IF = 'if ! [[ "$libpq_owner" =~ ' + OWNER_RX + ' ]] || [ "${BASH_REMATCH[2]}" != "$libpq_real" ]; then\n'
OWNER_S = 'libpq_owner="$(compose exec -T api dpkg-query -S "$libpq_real")" || {'
VARIANTS = {
    "CURRENT repo smoke.sh": (smoke, "new cases fail"),
    "TARGET (r1-target-smoke-block.sh)": (target, "all pass"),
    "T1 owner matched as a prefix (libpq5*)": (sub(target, OWNER_RX, r"^libpq5[^:]*(:[a-z0-9]+)?:\ (.+)$"), "some fail"),
    "T2 find_spec only, no venv scan": (sub(target, WALK, "b = []\n"), "some fail"),
    "T3 arithmetic on raw $deb before validation": (sub(target, VALIDATE, OLD_ARITH + VALIDATE), "some fail"),
    "T4 dpkg -S on the ldd path, no realpath": (
        sub(target, 'libpq_real="$(compose exec -T api realpath -e "$libpq")" || {',
            'libpq_real="$libpq"; true || {'), "some fail"),
    "T5a owner name never checked (dpkg -S must only succeed)": (
        sub(target, OWNER_IF, "if false; then\n"), "some fail"),
    "T5b dpkg -S result ignored": (
        sub(sub(target, OWNER_IF, "if false; then\n"), OWNER_S, OWNER_S.replace("|| {", "|| true || {")),
        "some fail"),
    "T6 dpkg-query -W failure branch removed": (
        sub(target, DPKG_W, '''deb="$(compose exec -T api dpkg-query -W -f='${Version}' libpq5)"\n'''), "some fail"),
}
NEW_TESTS = {"test_smoke_fails_when_psycopg_binary_is_beside_psycopg_c",
             "test_smoke_checks_dpkg_libpq5_owns_the_loaded_libpq",
             "test_smoke_never_evaluates_the_libpq5_version",
             "test_smoke_fails_closed_on_dpkg_query_errors"}
TESTS = ["test_smoke_checks_psycopg_c_impl_in_api", *sorted(NEW_TESTS)]


class Rec(unittest.TestResult):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str, str, str]] = []

    def addSubTest(self, test, subtest, err):  # noqa: N802
        super().addSubTest(test, subtest, err)
        case = subtest.params.get("case", subtest._subDescription())
        why = ""
        if err is not None:
            why = [l for l in self._exc_info_to_string(err, test).strip().splitlines() if l.strip()]
            why = next((l for l in why if "Error:" in l), why[-1])[:170]
        self.rows.append((test._testMethodName, str(case), "fail" if err else "pass", why))


def run(text: str) -> Rec:
    class Case(t.SmokePsycopgTest):
        def setUp(self) -> None:
            super().setUp()
            (self.tmp / "scripts" / "smoke.sh").write_text(text, encoding="utf-8", newline="\n")

    rec = Rec()
    for name in TESTS:
        Case(name).run(rec)
    for test, tb in rec.errors:
        rec.rows.append((getattr(test, "_testMethodName", str(test)), "(error)", "fail", tb.strip().splitlines()[-1][:170]))
    return rec


bad = 0
for vname, (text, want) in VARIANTS.items():
    rec = run(text)
    new_fail = [r for r in rec.rows if r[0] in NEW_TESTS and r[2] == "fail"]
    old_fail = [r for r in rec.rows if r[0] not in NEW_TESTS and r[2] == "fail"]
    if want == "all pass":
        ok = not new_fail and not old_fail
    elif want == "new cases fail":
        ok = not old_fail
    else:
        ok = bool(new_fail or old_fail)
    bad += not ok
    print(f"\n### {vname}  (want: {want}; new-case fails {len(new_fail)}, older-case fails {len(old_fail)})"
          f"{'' if ok else '  UNEXPECTED'}")
    for test, case, outcome, why in rec.rows:
        if vname.startswith(("CURRENT", "TARGET")) or outcome == "fail":
            short = test.replace("test_smoke_", "")
            print(f"  {outcome:<4}  {short[:44]:<44}  {case[:66]:<66}  {why}")
print(f"\nunexpected variant results: {bad}")
raise SystemExit(1 if bad else 0)
