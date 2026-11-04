"""platform-sbom U7d S7 RED: controls for tests/test_sources_lock_committed.py.

Never writes the repository (no docker/sources.lock.json is written). It
builds a stand-in lock in a temp dir from the U7d fake-network coverage run
(tests/test_sources_resolve.py fixtures: all 182 fixture keys through the
resolver, plus the manual neo4j entry with security's second-fetch values),
then runs the committed-lock tests with `LOCK` and `GITATTRIBUTES` pointed at:
the stand-in and u7d/s7-target-gitattributes (must pass), the repository as it
is (must fail: no lock, no eol line), and mutants of each (must fail, naming
the test).

Usage (in the gates image, from the repo root, on the U7d GREEN tree):
  COMPOSE_FILE=docker-compose.yml docker compose --env-file .env.example \\
    --profile gates run --rm gates \\
    uv run --locked python docs/evidence/platform-sbom/u7d/s7_controls.py [--base repo]
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests import test_sources_lock as tsl  # noqa: E402
from tests import test_sources_lock_committed as tsc  # noqa: E402
from tests import test_sources_resolve as tsr  # noqa: E402
from tests.test_sbom_bundle import load_sbom_check  # noqa: E402

HERE = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="u7d-s7-controls-"))
rows: list[tuple[str, str, str, bool]] = []
NEO_FROM = "second fetch: security 2026-10-25, docs/evidence/platform-sbom/sources-provenance.md"


def standin() -> dict[str, Any]:
    """The U7dCoverageTest run, kept: 181 resolved entries plus the manual
    neo4j entry as sources-provenance.md records it."""
    mod = tsr.load_resolver()
    check = load_sbom_check()
    docs = tsl.fixture_docs()
    needs_all, problems = check.lock_needs(tsl.policy(), docs)
    assert not problems and len(needs_all) == 182, (problems, len(needs_all))
    needs: dict[str, Any] = {}
    routes: dict[str, Any] = {}
    pg = tsr.PgdgFixture(tuple(k for k in needs_all if k.startswith("pgdg:")))
    routes.update(pg.routes())
    routes.update(tsr.maven_routes())
    routes.update(tsr.temurin_routes())
    routes[tsr.NEO_URL] = tsr.ok(tsr.NEO_BODY)
    for key, e in sorted(needs_all.items()):
        kind = key.split(":", 1)[0]
        name, _, ver = key.split(":", 1)[1].rpartition("@")
        route: dict[str, Any] = {}
        if kind == "deb":
            route = {"src": name, "ver": ver}
            routes.update(tsr.DebFixture(key).routes())
        elif kind == "pgdg":
            route = {"src": name, "ver": ver, "suite": tsr.SUITE}
        elif kind == "apk":
            distro = {unquote(q.partition("=")[2]) for p in e["packages"]
                      for q in str(p["purl"]).partition("?")[2].split("&") if q.startswith("distro=")}
            x, y, _ = distro.pop().split("-", 1)[1].split(".")
            fx = tsr.ApkFixture(key, commit=tsr.aports_commit(name, ver), branch=f"v{x}.{y}")
            route = {"origin": name, "ver": ver, "commit": fx.commit, "branch": fx.branch}
            routes.update(fx.routes())
        elif kind == "temurin":
            route = {"sbom_version": "21.0.12.1+1-LTS", "release": tsr.RELEASE}
        elif kind == "neo4j":
            route = {"ver": ver}
        elif kind == "maven":
            g, _, a = name.partition(":")
            route = {"g": g, "a": a, "v": ver}
        elif kind == "pypi":
            route = {"name": name, "ver": ver}
            body = f"sdist of {key}".encode()
            url = "https://files.pythonhosted.org/packages/ab/cd/" + tsr.sha("sha256", body)[:60] + f"/{name}-{ver}.tar.gz"
            routes[f"https://pypi.org/pypi/{name}/{ver}/json"] = tsr.ok(json.dumps({
                "info": {"name": name, "version": ver},
                "urls": [{"packagetype": "sdist", "url": url, "digests": {"sha256": tsr.sha("sha256", body)},
                          "size": len(body)}]}))
            routes[url] = tsr.ok(body)
        needs[key] = {"kind": kind, "packages": e["packages"], "route": route}
    uv = (REPO / "uv.lock").read_text(encoding="utf-8")
    with tsr.network(mod, routes), mock.patch.object(mod, "SNAPSHOT_PAUSE", 0), \
            mock.patch.object(mod, "SLEEP", lambda s: None), contextlib.redirect_stderr(io.StringIO()):
        lock, cands, skipped = mod.resolve(needs, tsr.EMPTY_LOCK, tsl.policy(), uv, "amd64", False)
    assert not skipped and [c["key"] for c in cands] == [tsc.NEO4J_KEY], (skipped, cands)
    lock["components"][tsc.NEO4J_KEY] = {
        "kind": "neo4j", "origin": "manual", "arches": ["amd64"],
        "files": [{"name": "5.26.32.tar.gz", "url": tsr.NEO_URL, "sha256": tsc.NEO4J_SHA256, "size": tsc.NEO4J_SIZE,
                   "upstream": {"alg": "sha256", "value": tsc.NEO4J_SHA256, "from": NEO_FROM}}]}
    return lock


def write(name: str, text: str) -> Path:
    p = WORK / name
    p.write_bytes(text.encode("utf-8"))
    return p


def run(lock: Path, attrs: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for m in unittest.defaultTestLoader.getTestCaseNames(tsc.CommittedLockTest):
        result = unittest.TestResult()
        with mock.patch.object(tsc, "LOCK", lock), mock.patch.object(tsc, "GITATTRIBUTES", attrs):
            unittest.TestSuite([tsc.CommittedLockTest(m)]).run(result)
        out[m] = [str(b[1]).strip().splitlines()[-1] for b in result.failures + result.errors]
    return out


def row(group: str, name: str, must_fail: bool, problems: list[str]) -> None:
    ok = bool(problems) == must_fail
    rows.append((group, name, "must fail" if must_fail else "must pass", ok))
    print(f"{'ok ' if ok else 'BAD'} [{group}] {name:<66} {'must fail' if must_fail else 'must pass'} | "
          f"{problems[0][:120] if problems else 'no problem'}", flush=True)


check = load_sbom_check()
# --base repo (U7d item 13 brief): the target is the repository's lock and
# .gitattributes as they are; otherwise the stand-in and the target line.
BASE_REPO = "--base" in sys.argv and sys.argv[sys.argv.index("--base") + 1] == "repo"
if BASE_REPO:
    good_text = (REPO / "docker" / "sources.lock.json").read_bytes().decode("utf-8")
    base = json.loads(good_text)
    attrs = REPO / ".gitattributes"
    label = "repo lock + repo .gitattributes"
else:
    base = standin()
    good_text = check.lock_text(base)
    attrs = HERE / "s7-target-gitattributes"
    label = "stand-in + target .gitattributes"
good = write("sources.lock.json", good_text)
# The "no lock, no eol line" state is built here, never read from the repo
# (attempt 1 read the repo's current state: u7d/s7-green-controls-attempt1.txt).
no_eol = write("gitattributes-no-eol", "".join(
    ln for ln in attrs.read_text(encoding="utf-8").splitlines(keepends=True) if "docker/sources.lock.json" not in ln))
assert tsc.EOL_LINE not in no_eol.read_text(encoding="utf-8")
print(f"{label}: {len(base['components'])} entries, {len(good_text)} bytes; kinds "
      f"{sorted({k.split(':', 1)[0] for k in base['components']})}")

for m, problems in run(good, attrs).items():
    row("target", f"{label}: {m}", False, problems)
for m, problems in run(WORK / "absent.json", no_eol).items():
    row("baseline", f"no lock, no eol line (temp copy): {m}", True, problems)
missing = run(WORK / "absent.json", attrs)["test_no_lock_problems"]
row("repo", "a missing lock is a named failure, not an error", True,
    missing if missing and "is not committed" in missing[0] else [])
if missing and "is not committed" not in missing[0]:
    rows[-1] = rows[-1][:3] + (False,)


def mutate(change: Callable[[dict[str, Any]], Any]) -> str:
    d = json.loads(good_text)
    change(d)
    return check.lock_text(d)


def wrong_sha(d: dict[str, Any]) -> None:
    f = d["components"][tsc.NEO4J_KEY]["files"][0]
    f["sha256"] = f["upstream"]["value"] = "0" * 64


stale_key = "deb:zzz-unneeded@1.0-1"
MUTANTS: dict[str, tuple[str, Path, str]] = {
    "a stale entry": (mutate(lambda d: d["components"].update({stale_key: tsl.good_entry(stale_key)})), attrs,
                      "test_no_lock_problems"),
    "a missing key": (mutate(lambda d: d["components"].pop("deb:bash@5.2.15-2")), attrs, "test_no_lock_problems"),
    "a missing key (key set)": (mutate(lambda d: d["components"].pop("deb:bash@5.2.15-2")), attrs,
                                "test_every_needed_key_and_nothing_else"),
    "CRLF line endings": (good_text.replace("\n", "\r\n"), attrs, "test_canonical_lf_and_format"),
    "non-canonical spacing": (json.dumps(json.loads(good_text), indent=2, sort_keys=True) + "\n", attrs,
                              "test_canonical_lf_and_format"),
    "a wrong neo4j sha256": (mutate(wrong_sha), attrs, "test_the_manual_neo4j_entry"),
    "the neo4j entry generated, not manual": (mutate(lambda d: d["components"][tsc.NEO4J_KEY].update(origin="generated")),
                                              attrs, "test_the_manual_neo4j_entry"),
    "format 2": (mutate(lambda d: d.update(format=2)), attrs, "test_canonical_lf_and_format"),
    "no pgdg entries (six kinds)": (mutate(lambda d: [d["components"].pop(k) for k in list(d["components"])
                                                      if k.startswith("pgdg:")]), attrs, "test_the_sample"),
    "the .gitattributes line missing": (good_text, no_eol, "test_gitattributes_pins_lf"),
    # U7d round 1, item 13: what the hardcoded scan's whole-file skip could hide.
    "a port key in an entry": (mutate(lambda d: d["components"]["deb:bash@5.2.15-2"].update(port=8080)), attrs,
                               "test_nothing_the_hardcoded_scan_would_miss"),
    "an http key at the top": (mutate(lambda d: d.update(http_proxy="x")), attrs,
                               "test_nothing_the_hardcoded_scan_would_miss"),
    "a Port key in a file (case)": (mutate(lambda d: d["components"]["deb:bash@5.2.15-2"]["files"][0].update(
        Port="x")), attrs, "test_nothing_the_hardcoded_scan_would_miss"),
    "an integer in arches": (mutate(lambda d: d["components"]["deb:bash@5.2.15-2"]["arches"].append(8080)), attrs,
                             "test_nothing_the_hardcoded_scan_would_miss"),
    "an integer under another key": (mutate(lambda d: d["components"]["deb:bash@5.2.15-2"].update(listen=8080)),
                                     attrs, "test_nothing_the_hardcoded_scan_would_miss"),
    "a float under another key": (mutate(lambda d: d["components"]["deb:bash@5.2.15-2"].update(listen=8080.0)),
                                  attrs, "test_nothing_the_hardcoded_scan_would_miss"),
}
for name, (text, attr_path, method) in MUTANTS.items():
    path = write(f"mutant-{abs(hash(name))}.json", text)
    row("mutant", f"{name} -> {method}", True, run(path, attr_path)[method])

bad = [r for r in rows if not r[3]]
print(f"\nU7d S7 controls: {len(rows)} rows, {sum(r[2] == 'must fail' for r in rows)} must-fail, "
      f"{sum(r[2] == 'must pass' for r in rows)} must-pass, {len(bad)} unexpected")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if bad else 0)
