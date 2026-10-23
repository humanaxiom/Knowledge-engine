"""platform-sbom U0 RED: drive SmokePsycopgTest (test 7) against scratch
copies of scripts/smoke.sh. Runs inside the ke-gates image (Linux bash, the
fake docker), never writes the repository.

TARGET = the repo's smoke.sh with target_smoke_block.sh inserted after the
first `/readyz ready` line. Each mutant changes the block; the test must fail
on every mutant and pass on the target.

Usage (in ke-gates, repo at /work read-only, /tmp tmpfs):
  python docs/evidence/platform-sbom/u0/u0_smoke_mutants.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from tests import test_psycopg_c as t  # noqa: E402

HERE = Path(__file__).resolve().parent
ANCHOR = 'echo "smoke: /readyz ready"\n'
smoke = (REPO / "scripts" / "smoke.sh").read_text(encoding="utf-8")
block = (HERE / "target_smoke_block.sh").read_text(encoding="utf-8")
assert smoke.count(ANCHOR) == 1


def sub(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


IMPL_CHECK = '''if [ "$pq_impl" != c ]; then
  echo "smoke: FAIL (psycopg: api uses the '$pq_impl' implementation, want c)" >&2
  exit 1
fi
'''
VERSION_COND = 'if [ "$pq_version" != "$want" ] || [ "$pq_build" != "$want" ]; then'
PATH_COND = ('if ! [[ "$libpq" =~ ^(/usr)?/lib/(x86_64|aarch64)-linux-gnu/libpq\\.so\\.5 ]] '
             '|| [[ "$ldd_out" == *psycopg_binary* ]]; then')
LDD_START = 'ldd_out="$(compose exec -T api ldd "$pq_ext")" || {'
LDD_END = 'echo "smoke: psycopg c on Debian libpq5 $deb ($libpq)"\n'

VARIANTS = {
    "repo smoke.sh as is (RED)": (None, "fail"),
    "TARGET (block per N0)": (block, "pass"),
    "S1 no impl check": (sub(block, IMPL_CHECK, ""), "fail"),
    "S2 version()==__build_version__ only, no pin/libpq5 compare": (
        sub(block, VERSION_COND, 'if [ "$pq_version" != "$pq_build" ]; then'), "fail"),
    "S3 no libpq path check": (sub(block, PATH_COND, "if false; then"), "fail"),
    "S4 over-strict: /usr/lib only (rejects bookworm's /lib alias)": (
        sub(block, "^(/usr)?/lib/", "^/usr/lib/"), "fail"),
    "S5 check runs in worker, not api": (block.replace("exec -T api", "exec -T worker"), "fail"),
    "S6 no ldd step (and no libpq path)": (block[:block.index(LDD_START)] + 'echo "smoke: psycopg c"\n', "fail"),
    # Equivalent mutant: with `|| true` an empty reply still fails the impl
    # check (impl '' != c), so smoke stays fail-closed and the test passes.
    "S7 (equivalent) python check failure ignored (|| true)": (
        sub(block, ''')" || {
  echo "smoke: FAIL (psycopg: the check in api failed)" >&2
  exit 1
}
read -r''', ''')" || true
read -r'''), "pass"),
}


def run(variant: str | None) -> list[str]:
    class Case(t.SmokePsycopgTest):
        def setUp(self) -> None:
            super().setUp()
            if variant is not None:
                text = sub(smoke, ANCHOR, ANCHOR + variant)
                (self.tmp / "scripts" / "smoke.sh").write_text(text, encoding="utf-8", newline="\n")

    result = unittest.TestResult()
    Case("test_smoke_checks_psycopg_c_impl_in_api").run(result)
    out = []
    for test, tb in result.failures + result.errors:
        last = [l for l in tb.strip().splitlines() if l.strip()][-1][:150]
        out.append(f"{test}: {last}")
    return out


bad = 0
for name, (variant, want) in VARIANTS.items():
    fails = run(variant)
    got = "fail" if fails else "pass"
    ok = got == want
    bad += not ok
    print(f"{name:<64} want={want} got={got}{'' if ok else '  UNEXPECTED'}")
    for f in fails[:3]:
        print(f"    {f.split('(case=')[-1][:200]}")
    if len(fails) > 3:
        print(f"    ... {len(fails) - 3} more failing subtests")
print(f"\nunexpected results: {bad}")
raise SystemExit(1 if bad else 0)
