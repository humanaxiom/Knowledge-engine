"""platform-sbom U9a: the source-set checks, the source index and the "Source
code" section in `scripts/sbom_check.py` (PSC-15, PSC-22, PSC-24;
requirements "U9 precision" U9-2..U9-7 and U9-14; design-notes "N9
amendment, U9" items 1, 3, 5, 6, 7 and 14; orchestrator rulings Q78-Q80 and
O-9..O-12 at the end of that amendment). Tester, U9a RED, 2026-10-29.

Interface pinned (design item 1; pure, no I/O; the CLI wrappers read):
- `fetch_record_problems(record_text, lock_text, policy, arch, which) ->
  list[str]` (item 3 a-d, in that order; the first failing stage stops);
- `listing_problems(listing, plan, record) -> list[str]`: `listing` is
  `{name: (kind, size)}`, kind one of `file`, `link`, `dir`, `other`;
  `plan` is `fetch_plan(lock, arch, set)`; `record` True when `fetch.json`
  belongs in the listing (`--sources`), False for `app/sources/files/`;
- `exempt_matches` adds the multi-match problem (item 6), flags unchanged;
- `source_index(docs, lock_text, policy, arch, which, git_sha, listing) ->
  (index | None, problems)` (item 5; `None` whenever problems is non-empty,
  the tester's reading of "index | None");
- `source_section(index) -> (text | None, problems)` (item 7);
- subcommands `sources-check`, `index`, `notices` (item 1: exit 0, 1 on
  problems or any exception as one line and never a traceback, 2 on a bad
  argument).

The tester's U9a RED readings were ruled by the orchestrator (O-13, at the
end of design-notes "N9 amendment, U9"), and the rulings are pinned here:
- (1) `sources-check`'s ok line counts distinct files and distinct bytes,
  as `bundle_fetch.sh` does;
- (2) the oversize refusal reads `fetch.json is <n> bytes, over 4 MiB`;
- (3) the multi-match problem lists SPDXIDs in document order;
- (4) in a sample bundle the do-not-distribute banner is the first line
  after the section heading and the I-3 sentence follows it (U9-7 "starts
  with" wins over item 7's order);
- (6) a malformed `--git-sha` exits 2 for `index`;
- (7) `index`'s exempt lines on stderr are `index: <image>: <package>:
  <listing>`.
`test_full_bundle_refuses_not_shipped` still reaches item 5 stage 6 by
patching the module's `fetch_plan` (the design says the stage cannot follow
stages 3 and 5 and is asserted anyway).

U9a rework round 1 (orchestrator O-14; review B-1, B-2, N-3, N-4, N-7, N-9;
security L-1, L-2, L-3, I-3) adds: escaped record text in refusals; a
non-object policy is a problem; a FIFO or link swapped in after the listing
is refused without a hang; `notices --index` refuses a FIFO, a device and a
file over 16 MiB; the pure path's listing failure names `--files`; index
stages 3, 4 and 5 stop in order; `[ ] ( ) ! * _ #` refused in every printed
field except the URL; a deeply nested record is a problem, never a
RecursionError.

The synthetic fetched set (item 14): `tests.test_sources_fetch.wide()` (real
bytes, every sha256 and size true; two shared sha256 values; an arm64-only
entry), a synthetic policy (the committed `hosts`, `always` and `exempt` as
each row needs) and syft-shaped SBOMs that need exactly the lock's amd64
keys. Files are named by their computed sha256 and `fetch.json` is the U8a
client's own form. No network; no test reads docs/evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any, Callable
from unittest import mock

from tests import sbom_support as ss
from tests.engine_support import ROOT
from tests.test_sbom_bundle import load_sbom_check
from tests.test_sources_fetch import LockBuilder, load_fetch, plan_of, wide
from tests.test_sources_lock import canon, fixture_docs, miss, policy, stale

CHECK = ROOT / "scripts" / "sbom_check.py"
NOTICE = ROOT / "NOTICE.md"
COMMITTED_LOCK = ROOT / "docker" / "sources.lock.json"
ARCH = "amd64"
GIT_SHA = "0123456789abcdef0123456789abcdef01234567"
REVIEWED = "security 2026-10-25"
JNA = "pkg:maven/com.sun.jna/jna@5.15.0"
JAVASSIST = "pkg:maven/org.javassist/javassist@3.30.2-GA"
NOT_SAMPLE = "pypi:psycopg@3.3.6"  # a wide() amd64 key outside the sample
SHARED_IN_SAMPLE, SHARED_OUT = "deb:bash@5.2.15-2", "deb:bash@5.2.15-2+deb12u1"  # one orig tarball, one sha256
ALP = "?arch=x86_64&distro=alpine-3.23.3"
HEX64 = re.compile(r"[0-9a-f]{64}")
I3 = "Paths here are relative to the bundle's `app/` directory, which install publishes as the install directory."
BANNER = "Verification bundle: this source set is a sample and is not complete; do not distribute this bundle."
SHIPPED_CELL = "source in `sources/` (see `sources/index.json`)"
TOP_KEYS = {"format", "set", "arch", "git_sha", "lock_sha256", "components", "unparsed", "unidentified", "unlicensed"}
LOCK_COMPONENT_KEYS = {"key", "kind", "status", "packages", "files"}
EXEMPT_COMPONENT_KEYS = LOCK_COMPONENT_KEYS | {"exempt", "listing"}
PACKAGE_KEYS = {"image", "spdxid", "purl", "name", "always", "licence", "expression"}
FILE_KEYS = {"name", "url", "sha256", "size", "upstream", "path"}
FLAG_ROW_KEYS = {"image", "spdxid", "purl", "name", "needs"}


def fn(module: ModuleType, name: str) -> Callable[..., Any]:
    got = getattr(module, name, None)
    if not callable(got):
        raise AssertionError(f"scripts/sbom_check.py has no {name}() (U9a interface, design-notes \"N9 amendment, "
                             "U9\" item 1; tests/test_source_index.py)")
    return got


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# The synthetic set
# --------------------------------------------------------------------------

def syn_docs(**extra_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """SBOMs whose `needs` rows map to exactly wide()'s amd64 keys, plus a
    row needing nothing (zlib), an unparsed row with needs false (httpx), an
    unidentified row with needs true (psycopg), an unlicensed row (six) and
    jna (cleared by the synthetic exemption)."""
    rows: dict[str, list[dict[str, Any]]] = {
        "postgres": [
            {"purl": ss.deb("bash", "5.2.15-2+b13", upstream="bash@5.2.15-2"), "declared": "GPL-3.0-or-later"},
            {"purl": ss.deb("bash", "5.2.15-2+deb12u1"), "declared": "GPL-3.0-or-later"},
            {"purl": ss.deb("postgresql-common", "293.pgdg12+1"), "declared": "GPL-2.0-or-later"},
            {"purl": ss.deb("zlib1g", "1:1.2.13.dfsg-1", upstream="zlib"), "declared": "Zlib"}],
        "valkey": [{"purl": f"pkg:apk/alpine/readline@8.2.13-r1{ALP}", "declared": "GPL-3.0-or-later"}],
        "ke-gateway": [{"purl": f"pkg:apk/alpine/readline@8.2.13-r0{ALP}", "declared": "GPL-3.0-or-later"}],
        "ke-neo4j": [
            {"purl": "pkg:maven/org.neo4j/neo4j@5.26.32", "declared": "GPL-3.0-only"},
            {"purl": "pkg:generic/oracle/openjdk@21.0.12.1%2B1-LTS",
             "declared": "GPL-2.0-only WITH Classpath-exception-2.0"},
            {"purl": "pkg:maven/javax.xml.bind/jaxb-api@2.2.12", "declared": "GPL-2.0-only"},
            {"purl": JNA, "declared": "Apache-2.0 AND LGPL-2.1-or-later"}],
        "ke-app": [
            {"purl": "pkg:pypi/psycopg@3.3.6", "declared": "LicenseRef-" + "a" * 64},
            {"purl": "pkg:pypi/psycopg-c@3.3.6", "declared": "LGPL-3.0-only"},
            {"purl": "pkg:pypi/httpx@0.28.1", "declared": "MIT AND ("},
            {"purl": "pkg:pypi/six@1.16.0", "declared": None, "concluded": None}],
    }
    for image, more in extra_rows.items():
        rows.setdefault(image.replace("_", "-"), []).extend(more)
    return {image: ss.spdx_doc(image, r) for image, r in rows.items()}


def exempt_entry(package: str = JNA, image: str = "ke-neo4j", reviewed: str = REVIEWED) -> dict[str, str]:
    return {"image": image, "package": package, "reason": "Apache-2.0 elected (synthetic \"quoted\" reason)",
            "reviewed": reviewed}


def syn_policy(always: list[dict[str, str]] | None = None,
               exempt: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"hosts": list(policy()["hosts"]), "always": list(always or []),
            "exempt": [exempt_entry()] if exempt is None else list(exempt)}


def body_of(b: LockBuilder, f: dict[str, Any]) -> bytes:
    return b.bodies[f["url"]]


def record_text(b: LockBuilder, which: str, arch: str = ARCH, text: str | None = None) -> str:
    """fetch.json as `sources_fetch._write_record` writes it (A76)."""
    lock_t = text if text is not None else b.text()
    comps: dict[str, list[dict[str, Any]]] = {}
    for key, f in plan_of(b, arch, which):
        comps.setdefault(key, []).append({"name": f["name"], "sha256": f["sha256"], "size": f["size"]})
    return canon({"format": 1, "set": which, "arch": arch, "components": comps,
                  "lock_sha256": sha(lock_t.encode("utf-8"))})


def distinct(b: LockBuilder, which: str, arch: str = ARCH) -> dict[str, int]:
    return {f["sha256"]: f["size"] for _, f in plan_of(b, arch, which)}


def listing_of(b: LockBuilder, which: str, *, record: bool) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {s: ("file", n) for s, n in distinct(b, which).items()}
    if record:
        out["fetch.json"] = ("file", len(record_text(b, which).encode("utf-8")))
    return out


def write_fetched(directory: Path, b: LockBuilder, which: str, *, record: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for _, f in plan_of(b, ARCH, which):
        (directory / f["sha256"]).write_bytes(body_of(b, f))
    if record:
        (directory / "fetch.json").write_bytes(record_text(b, which).encode("utf-8"))


def snapshot(directory: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in sorted(directory.rglob("*")):
        rel = p.relative_to(directory).as_posix()
        if p.is_symlink():
            out[rel] = ("link", os.readlink(p))
        elif p.is_file():
            out[rel] = ("file", p.read_bytes())
        else:
            out[rel] = ("dir",)
    return out


def run_check(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(CHECK), *args], capture_output=True, text=True, timeout=120)


RAW_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
HANG_SECONDS = 10
MEMORY_CAP = 768 << 20  # address-space cap for the hang rows: a read of /dev/zero ends, never fills the gates host
INDEX_MAX = 16 * 1024 * 1024  # security L-3, orchestrator O-14

# A child that runs sbom_check.main(argv) with os.lstat reporting, for each
# target path, the stat of a decoy regular file: the state the listing saw
# before the target was swapped for a FIFO or a link (security L-1, review N-4).
SWAP_DRIVER = r'''
import importlib.util, json, os, sys
check, swaps, argv = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3:]
real_lstat = os.lstat
def lstat(path, *args, **kwargs):
    decoy = swaps.get(os.path.abspath(os.fspath(path)))
    return real_lstat(decoy) if decoy is not None else real_lstat(path, *args, **kwargs)
os.lstat = lstat
spec = importlib.util.spec_from_file_location("ke_sbom_check_swapped", check)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.exit(module.main(argv))
'''


def _cap_memory() -> None:
    import resource  # POSIX only; the rows that use this skip where os.mkfifo is unavailable
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP, MEMORY_CAP))


def run_bounded(argv: list[str]) -> subprocess.CompletedProcess | None:
    """Run argv with a wall-clock and memory bound; None when it did not finish."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=HANG_SECONDS, preexec_fn=_cap_memory)
    except subprocess.TimeoutExpired:
        return None


class _CliAsserts(unittest.TestCase):
    command = ""

    def assertKnown(self, r: subprocess.CompletedProcess) -> None:
        self.assertNotIn(f"invalid choice: '{self.command}'", r.stderr,
                         f"sbom_check.py has no `{self.command}` subcommand (U9a, design item 1)")

    def assertRefused(self, r: subprocess.CompletedProcess, *names: str) -> None:
        self.assertKnown(r)
        self.assertEqual(r.returncode, 1, r.stdout[-500:] + r.stderr[-1500:])
        self.assertNotIn("Traceback", r.stderr, "never a traceback (U7b rework round 1 form)")
        for name in names:
            self.assertIn(name, r.stderr, f"the refusal does not name {name!r}: {r.stderr[-1500:]}")

    def assertOneFailLine(self, r: subprocess.CompletedProcess) -> None:
        self.assertRefused(r)
        lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, r.stderr[-1500:])
        self.assertIn("FAIL", lines[0])
        self.assertNotRegex(r.stderr, r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "the message is printed raw")

    def assertBadArgument(self, r: subprocess.CompletedProcess) -> None:
        self.assertKnown(r)
        self.assertEqual(r.returncode, 2, r.stdout[-500:] + r.stderr[-1500:])
        self.assertNotIn("Traceback", r.stderr)


# --------------------------------------------------------------------------
# Item 3 a-d: fetch_record_problems
# --------------------------------------------------------------------------

class FetchRecordProblemsTest(unittest.TestCase):
    """U9-2 (the record's text) and U9-3 (it matches this bundle)."""

    def setUp(self) -> None:
        self.S = load_sbom_check()
        self.check = fn(self.S, "fetch_record_problems")
        self.b = wide()
        self.pol = syn_policy()

    def problems(self, record: str, which: str = "full", arch: str = ARCH, lock: str | None = None) -> list[str]:
        got = self.check(record, lock if lock is not None else self.b.text(), self.pol, arch, which)
        self.assertIsInstance(got, list)
        return got

    def edited(self, change: Callable[[dict[str, Any]], Any], which: str = "full") -> str:
        rec = json.loads(record_text(self.b, which))
        change(rec)
        return canon(rec)

    def assertNamed(self, problems: list[str], *parts: str) -> None:
        self.assertTrue(problems, "no problem")
        self.assertTrue(any(all(p in line for p in parts) for line in problems),
                        f"no problem names {parts}: {problems}")

    def test_control_the_fetch_clients_record_passes(self):
        for which in ("full", "sample"):
            with self.subTest(which=which):
                self.assertEqual(self.problems(record_text(self.b, which), which), [])
        with self.subTest(case="the U8a client's own _write_record output"):
            F = load_fetch()
            tmp = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, tmp, True)
            F._write_record(str(tmp), "full", ARCH, self.b.text(), plan_of(self.b, ARCH, "full"))
            self.assertEqual(self.problems((tmp / "fetch.json").read_bytes().decode("utf-8")), [])

    def test_bundle_refuses_a_mismatched_fetch_record(self):
        rec = json.loads(record_text(self.b, "full"))
        key = "deb:bash@5.2.15-2+deb12u1"
        f0 = rec["components"][key][1]
        lock_sha = sha(self.b.text().encode("utf-8"))
        cases: dict[str, tuple[str, tuple[str, ...]]] = {
            "not JSON": ("{not json\n", ("fetch.json",)),
            "not an object": (canon([rec]), ("fetch.json",)),
            "not canonical (compact)": (json.dumps(rec, sort_keys=True) + "\n", ("fetch.json", "canonical")),
            "not canonical (no final newline)": (canon(rec)[:-1], ("fetch.json", "canonical")),
            "an extra top-level key": (self.edited(lambda r: r.update(note="x")), ("fetch.json", "note")),
            "format 2": (self.edited(lambda r: r.update(format=2)), ("fetch.json", "format")),
            "format true": (self.edited(lambda r: r.update(format=True)), ("fetch.json", "format")),
            "set differs": (record_text(self.b, "sample"),
                            ("fetch.json: set is sample, this bundle needs full",)),
            "arch differs": (self.edited(lambda r: r.update(arch="arm64")), ("fetch.json", "arch", "arm64")),
            "lock_sha256 differs": (self.edited(lambda r: r.update(lock_sha256="0" * 64)),
                                    (f"fetch.json: lock_sha256 {'0' * 64} is not the lock's {lock_sha}: "
                                     "fetch again after the re-lock",)),
            "a key missing": (self.edited(lambda r: r["components"].pop(NOT_SAMPLE)), ("fetch.json", NOT_SAMPLE)),
            "a key extra": (self.edited(lambda r: r["components"].update({"deb:dash@0.5.12-2": [f0]})),
                            ("fetch.json", "deb:dash@0.5.12-2")),
            "a file missing": (self.edited(lambda r: r["components"][key].pop(1)), ("fetch.json", key)),
            "a file extra": (self.edited(lambda r: r["components"][key].append(dict(f0, name="extra.tar.xz"))),
                             ("fetch.json", key)),
            "two files swapped": (self.edited(lambda r: r["components"][key].reverse()), ("fetch.json", key)),
            "a name differs": (self.edited(lambda r: r["components"][key][1].update(name="other.tar.xz")),
                               ("fetch.json", key, "name", "other.tar.xz", f0["name"])),
            "a sha256 differs": (self.edited(lambda r: r["components"][key][1].update(sha256="e" * 64)),
                                 ("fetch.json", key, "sha256", "e" * 64, f0["sha256"])),
            "a size differs": (self.edited(lambda r: r["components"][key][1].update(size=f0["size"] + 1)),
                               (f"fetch.json: {key}: size is {f0['size'] + 1}, the lock's full plan says "
                                f"{f0['size']}",)),
        }
        for k in ("format", "set", "arch", "lock_sha256", "components"):
            cases[f"the {k} key missing"] = (self.edited(lambda r, k=k: r.pop(k)), ("fetch.json", k))
        for case, (text, parts) in cases.items():
            with self.subTest(case=case):
                self.assertNamed(self.problems(text), *parts)

    def test_the_first_failing_stage_stops_the_run(self):
        # Item 3: a (the text) before b (this bundle): a non-canonical record
        # for the wrong set names the form, not the set.
        rec = json.loads(record_text(self.b, "sample"))
        got = self.problems(json.dumps(rec) + "\n", "full")
        self.assertNamed(got, "canonical")
        self.assertFalse([p for p in got if "set is sample" in p], got)

    def test_a_lock_failing_lock_entry_problems_is_named(self):
        # Item 3 c (security U7a I-4): before fetch_plan; the record binds the
        # same (bad) lock text, so only the lock's own rule can refuse it.
        bad = copy.deepcopy(self.b.components)
        bad[NOT_SAMPLE]["files"][0]["url"] = bad[NOT_SAMPLE]["files"][0]["url"].replace(
            "files.pythonhosted.org", "evil.example")
        text = canon({"format": 1, "components": bad})
        first = self.S.lock_entry_problems(text, self.pol)
        self.assertTrue(first, "the probe lock must fail lock_entry_problems")
        got = self.problems(record_text(self.b, "full", text=text), lock=text)
        self.assertNamed(got, first[0])

    def test_wrong_types_are_problems_never_exceptions(self):
        rec = json.loads(record_text(self.b, "full"))
        key = next(iter(rec["components"]))
        hostile = {
            "components a list": lambda r: r.update(components=[]),
            "a component not a list": lambda r: r["components"].update({key: "x"}),
            "a file not an object": lambda r: r["components"].update({key: ["x"]}),
            "a size as a string": lambda r: r["components"][key][0].update(size=str(r["components"][key][0]["size"])),
            "a sha256 as a number": lambda r: r["components"][key][0].update(sha256=5),
            "set a number": lambda r: r.update(set=1),
            "arch null": lambda r: r.update(arch=None),
            "a file with an extra field": lambda r: r["components"][key][0].update(url="https://x"),
        }
        for case, change in hostile.items():
            with self.subTest(case=case):
                text = self.edited(change)
                try:
                    got = self.problems(text)
                except Exception as exc:  # noqa: BLE001 - the row under test
                    self.fail(f"{case}: raised {type(exc).__name__}: {exc}")
                self.assertTrue(got, case)

    def test_record_text_in_a_refusal_is_escaped(self):
        # U9-2 "escaped as PSC-22 L-3" (review B-2): a C0 or C1 byte from the
        # record reaches the problem as \xNN text, never raw.
        key = "deb:bash@5.2.15-2+deb12u1"
        cases = {
            "an ESC in set": (lambda r: r.update(set="full\x1b[31m"), "set is full\\x1b[31m"),
            "a C1 CSI in a file name": (lambda r: r["components"][key][1].update(name="evil\x9bname.tar.xz"),
                                        "name is evil\\x9bname.tar.xz"),
            "a BEL in an extra component key": (
                lambda r: r["components"].update({"deb:dash\x07@0.5.12-2": r["components"][key]}),
                "deb:dash\\x07@0.5.12-2"),
        }
        for case, (change, escaped) in cases.items():
            with self.subTest(case=case):
                got = self.problems(self.edited(change))
                self.assertNamed(got, "fetch.json", escaped)
                for line in got:
                    self.assertNotRegex(line, RAW_CONTROL_RE, f"a raw control byte in {line!r}")

    def test_a_non_object_policy_is_a_problem(self):
        # Review N-3: as source_index, a policy that is not an object is a
        # problem from the pure function, never an exception.
        rec = record_text(self.b, "full")
        for case, pol in {"a list": [], "null": None, "a string": "x", "a number": 5}.items():
            with self.subTest(case=case):
                try:
                    got = self.check(rec, self.b.text(), pol, ARCH, "full")
                except Exception as exc:  # noqa: BLE001 - the row under test
                    self.fail(f"{case}: raised {type(exc).__name__}: {exc}")
                self.assertIsInstance(got, list)
                self.assertTrue(got, f"{case}: a non-object policy passed")

    def test_a_deeply_nested_record_is_a_problem(self):
        # Security I-3: json.loads accepts the record, the canonical re-dump
        # recurses; the pure function returns a problem, never RecursionError.
        loaded = 0
        for depth in (1000, 2000, 5000):
            text = '{"format": ' + "[" * depth + "]" * depth + "}\n"
            self.assertLess(len(text.encode("utf-8")), 4 * 1024 * 1024, "the row stays under the 4 MiB cap")
            try:
                json.loads(text)
                loaded += 1
            except RecursionError:
                pass
            with self.subTest(depth=depth):
                try:
                    got = self.problems(text)
                except RecursionError as exc:
                    self.fail(f"{depth} deep: RecursionError escaped: {exc}")
                self.assertTrue(got, f"{depth} deep: no problem")
        self.assertTrue(loaded, "no depth parsed: the row never reaches the canonical compare")


# --------------------------------------------------------------------------
# Item 3 e, item 5 stage 5: listing_problems
# --------------------------------------------------------------------------

class ListingProblemsTest(unittest.TestCase):
    """U9-2 (nothing extra; links named), U9-3 (every planned sha256 present
    at the lock's size), U9-6 (`app/sources/files/` is exactly the shipped
    set)."""

    def setUp(self) -> None:
        self.S = load_sbom_check()
        self.check = fn(self.S, "listing_problems")
        self.b = wide()

    def problems(self, listing: dict[str, tuple[str, int]], which: str = "full", *, record: bool = True) -> list[str]:
        got = self.check(listing, plan_of(self.b, ARCH, which), record=record)
        self.assertIsInstance(got, list)
        return got

    def assertNamed(self, problems: list[str], *parts: str) -> None:
        self.assertTrue(problems, "no problem")
        self.assertTrue(any(all(p in line for p in parts) for line in problems),
                        f"no problem names {parts}: {problems}")

    def test_control_exactly_the_planned_files(self):
        for which in ("full", "sample"):
            for record in (True, False):
                with self.subTest(which=which, record=record):
                    self.assertEqual(self.problems(listing_of(self.b, which, record=record), which, record=record), [])
        full = plan_of(self.b, ARCH, "full")
        self.assertLess(len(distinct(self.b, "full")), len(full), "the control needs a shared sha256 (one file each)")

    def test_bundle_refuses_a_bad_sources_dir(self):
        good = listing_of(self.b, "full", record=True)
        s0 = sorted(distinct(self.b, "full"))[0]
        unplanned = "f" * 64
        self.assertNotIn(unplanned, good)
        self.assertNotEqual(s0.upper(), s0, "the probe sha256 needs a letter")
        extra = {
            "a .part file": (f"{s0}.part", ("file", 3)),
            "the .fetch.json.part file": (".fetch.json.part", ("file", 3)),
            "an upper-case name": (s0.upper(), ("file", good[s0][1])),
            "a short name": (s0[:63], ("file", 3)),
            "an unplanned 64-hex file": (unplanned, ("file", 3)),
            "a subdirectory": ("sub", ("dir", 0)),
            "an unplanned 64-hex directory": (unplanned, ("dir", 0)),
            "a fifo": ("pipe", ("other", 0)),
            "a dangling link": ("alias", ("link", 0)),
        }
        for case, (name, entry) in extra.items():
            with self.subTest(case=case):
                self.assertNamed(self.problems(dict(good, **{name: entry})), name)
        for case, kind in {"a planned file that is a link": "link", "a planned file that is a fifo": "other",
                           "a planned file that is a directory": "dir"}.items():
            with self.subTest(case=case):
                got = self.problems(dict(good, **{s0: (kind, good[s0][1])}))
                self.assertNamed(got, s0)
                if kind == "link":
                    self.assertNamed(got, s0, "link")
        with self.subTest(case="fetch.json is a link"):
            self.assertNamed(self.problems(dict(good, **{"fetch.json": ("link", 10)})), "fetch.json")
        with self.subTest(case="fetch.json missing from --sources"):
            self.assertNamed(self.problems({k: v for k, v in good.items() if k != "fetch.json"}), "fetch.json")
        with self.subTest(case="fetch.json in app/sources/files"):
            self.assertNamed(self.problems(good, record=False), "fetch.json")
        with self.subTest(case="a sample directory holding a full set's extra file"):
            sample = listing_of(self.b, "sample", record=True)
            other = next(s for s in distinct(self.b, "full") if s not in sample)
            self.assertNamed(self.problems(dict(sample, **{other: good[other]}), "sample"), other)

    def test_a_missing_or_resized_planned_file_is_named(self):
        good = listing_of(self.b, "full", record=True)
        key, f = next((k, f) for k, f in plan_of(self.b, ARCH, "full") if k == NOT_SAMPLE)
        with self.subTest(case="missing: its key and upstream name"):
            self.assertNamed(self.problems({k: v for k, v in good.items() if k != f["sha256"]}),
                             f["sha256"], key, f["name"])
        with self.subTest(case="short: both sizes"):
            got = self.problems(dict(good, **{f["sha256"]: ("file", f["size"] - 1)}))
            self.assertNamed(got, f["sha256"], str(f["size"]), str(f["size"] - 1))
        with self.subTest(case="long: both sizes"):
            got = self.problems(dict(good, **{f["sha256"]: ("file", f["size"] + 7)}))
            self.assertNamed(got, f["sha256"], str(f["size"]), str(f["size"] + 7))
        with self.subTest(case="an empty listing is a refusal, never a pass"):
            self.assertTrue(self.problems({}))
            self.assertTrue(self.problems({}, record=False))


# --------------------------------------------------------------------------
# Item 3: the `sources-check` subcommand
# --------------------------------------------------------------------------

class SourcesCheckCliTest(_CliAsserts):
    """`sbom_check.py sources-check --lock L --policy P --dir D --arch A --set S`
    (U9-2, U9-3; item 3): before any write, re-hashes every planned file."""

    command = "sources-check"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)
        self.b = wide()
        self.lock = self.tmp / "sources.lock.json"
        self.lock.write_bytes(self.b.text().encode("utf-8"))
        self.pol = ss.write_json(self.tmp / "source-policy.json", syn_policy())
        self.dir = self.tmp / "fetch"
        write_fetched(self.dir, self.b, "full")

    def _rmtree(self) -> None:
        for p in [self.tmp, *self.tmp.rglob("*")]:
            if p.is_dir() and not p.is_symlink():
                try:
                    os.chmod(p, 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, True)

    def run_cli(self, which: str = "full", arch: str = ARCH, directory: Path | None = None,
                lock: Path | None = None, pol: Path | None = None) -> subprocess.CompletedProcess:
        return run_check("sources-check", "--lock", str(lock or self.lock), "--policy", str(pol or self.pol),
                         "--dir", str(directory or self.dir), "--arch", arch, "--set", which)

    def assertNoList(self, r: subprocess.CompletedProcess) -> None:
        self.assertFalse(HEX64.search(r.stdout), "a refused check printed sha256 lines on stdout")

    def test_sources_check_prints_the_sorted_sha256_list(self):
        for which in ("full", "sample"):
            with self.subTest(which=which):
                d = self.tmp / f"ok-{which}"
                write_fetched(d, self.b, which)
                r = self.run_cli(which, directory=d)
                self.assertKnown(r)
                self.assertEqual(r.returncode, 0, r.stderr[-1500:])
                want = distinct(self.b, which)
                self.assertEqual(r.stdout.splitlines(), sorted(want))
                keys = {k for k, _ in plan_of(self.b, ARCH, which)}
                self.assertIn(f"sources-check: ok {len(want)} files, {sum(want.values())} bytes, {len(keys)} "
                              f"components ({which}, {ARCH})", r.stderr.splitlines())

    def test_bundle_refuses_a_bad_sources_dir(self):
        s0 = sorted(distinct(self.b, "full"))[0]
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "copy").write_bytes((self.dir / s0).read_bytes())
        (outside / "fetch.json").write_bytes((self.dir / "fetch.json").read_bytes())

        def put(name: str, data: bytes = b"x") -> Callable[[Path], None]:
            return lambda d: (d / name).write_bytes(data)

        def subdir(d: Path) -> None:
            (d / "sub").mkdir()

        def link_in_place(d: Path) -> None:
            (d / s0).unlink()
            os.symlink(outside / "copy", d / s0)

        def record_link(d: Path) -> None:
            (d / "fetch.json").unlink()
            os.symlink(outside / "fetch.json", d / "fetch.json")

        def record_dir(d: Path) -> None:
            (d / "fetch.json").unlink()
            (d / "fetch.json").mkdir()

        cases: dict[str, tuple[Callable[[Path], None], str]] = {
            "a .part file": (put(f"{s0}.part"), f"{s0}.part"),
            "the .fetch.json.part file": (put(".fetch.json.part"), ".fetch.json.part"),
            "an upper-case name": (put(s0.upper()), s0.upper()),
            "a short name": (put(s0[:63]), s0[:63]),
            "an unplanned 64-hex file": (put("f" * 64), "f" * 64),
            "a subdirectory": (subdir, "sub"),
            "a planned file replaced by a link to the same bytes": (link_in_place, s0),
            "fetch.json absent": (lambda d: (d / "fetch.json").unlink(), "fetch.json"),
            "fetch.json a link to a good record": (record_link, "fetch.json"),
            "fetch.json a directory": (record_dir, "fetch.json"),
        }
        if hasattr(os, "mkfifo"):
            cases["a fifo"] = (lambda d: os.mkfifo(d / "pipe"), "pipe")
        for case, (tamper, name) in cases.items():
            with self.subTest(case=case):
                d = self.tmp / f"case-{len(list(self.tmp.iterdir()))}"
                write_fetched(d, self.b, "full")
                tamper(d)
                r = self.run_cli(directory=d)
                self.assertRefused(r, name)
                self.assertNoList(r)
        with self.subTest(case="control: the unchanged directory"):
            r = self.run_cli()
            self.assertKnown(r)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        with self.subTest(case="--dir absent"):
            self.assertRefused(self.run_cli(directory=self.tmp / "nope"))
        with self.subTest(case="--dir a file"):
            self.assertRefused(self.run_cli(directory=self.dir / "fetch.json"))

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "root (or Windows) bypasses the mode bits; the gates image runs as uid 10001")
    def test_a_failed_listing_is_a_refusal_never_an_empty_listing(self):
        os.chmod(self.dir, 0o300)  # writable, searchable, not listable
        r = self.run_cli()
        self.assertRefused(r)
        self.assertNoList(r)
        self.assertNotIn("sources-check: ok", r.stderr)

    def test_bundle_refuses_a_mismatched_fetch_record(self):
        plan = plan_of(self.b, ARCH, "full")
        key, f = next((k, f) for k, f in plan if k == NOT_SAMPLE)
        data = body_of(self.b, f)
        flipped = bytes([data[0] ^ 0x01]) + data[1:]

        def rewrite(d: Path, b: bytes) -> None:
            (d / f["sha256"]).write_bytes(b)

        cases: dict[str, tuple[Callable[[Path], None], tuple[str, ...]]] = {
            "a planned file missing": (lambda d: (d / f["sha256"]).unlink(), (f["sha256"], key, f["name"])),
            "a planned file short": (lambda d: rewrite(d, data[:-1]), (f["sha256"], str(f["size"]))),
            "a planned file changed, same size (re-hash, item 3 f)": (
                lambda d: rewrite(d, flipped),
                (f"--sources: {f['sha256']} ({key} {f['name']}): sha256 mismatch: got {sha(flipped)}",)),
            "an extra 64-hex file": (lambda d: (d / ("e" * 64)).write_bytes(b"extra"), ("e" * 64,)),
        }
        for case, (tamper, parts) in cases.items():
            with self.subTest(case=case):
                d = self.tmp / f"case-{len(list(self.tmp.iterdir()))}"
                write_fetched(d, self.b, "full")
                tamper(d)
                r = self.run_cli(directory=d)
                self.assertRefused(r, *parts)
                self.assertNoList(r)
        with self.subTest(case="a sample directory for a full bundle"):
            d = self.tmp / "sample"
            write_fetched(d, self.b, "sample")
            self.assertRefused(self.run_cli("full", directory=d), "fetch.json: set is sample, this bundle needs full")
        with self.subTest(case="a full directory for a sample bundle"):
            self.assertRefused(self.run_cli("sample"), "fetch.json: set is full, this bundle needs sample")
        with self.subTest(case="arch differs from --arch"):
            self.assertRefused(self.run_cli(arch="arm64"), "fetch.json", "arch")
        with self.subTest(case="a fetch made before a re-lock"):
            relocked = LockBuilder()
            relocked.components = {k: v for k, v in self.b.components.items() if k != "deb:dash@0.5.12-2"}
            lock2 = self.tmp / "relocked.json"
            lock2.write_bytes(relocked.text().encode("utf-8"))
            self.assertRefused(self.run_cli(lock=lock2), "fetch.json: lock_sha256",
                               "fetch again after the re-lock")
        with self.subTest(case="fetch.json over 4 MiB"):
            d = self.tmp / "big"
            write_fetched(d, self.b, "full")
            (d / "fetch.json").write_bytes(b" " * (4 * 1024 * 1024 + 1))
            r = self.run_cli(directory=d)
            self.assertRefused(r, "fetch.json")
            self.assertRegex(r.stderr, r"4 MiB|4194304|too large|size")
        with self.subTest(case="fetch.json not UTF-8"):
            d = self.tmp / "latin"
            write_fetched(d, self.b, "full")
            (d / "fetch.json").write_bytes(b"\xff\xfe{}")
            self.assertRefused(self.run_cli(directory=d), "fetch.json")

    def test_sources_check_never_writes_under_dir(self):
        before = snapshot(self.dir)
        ok = self.run_cli()
        self.assertKnown(ok)
        self.assertEqual(ok.returncode, 0, ok.stderr[-1500:])
        bad = self.run_cli("sample")
        self.assertEqual(bad.returncode, 1, bad.stderr[-1500:])
        self.assertEqual(snapshot(self.dir), before, "sources-check changed --dir (U9-1)")

    def test_sources_check_exit_2_on_a_bad_argument(self):
        base = ["--lock", str(self.lock), "--policy", str(self.pol), "--dir", str(self.dir)]
        cases = {
            "an unknown arch": base + ["--arch", "x86_64", "--set", "full"],
            "an unknown set": base + ["--arch", ARCH, "--set", "most"],
            "no --set": base + ["--arch", ARCH],
            "no --dir": ["--lock", str(self.lock), "--policy", str(self.pol), "--arch", ARCH, "--set", "full"],
            "no --lock": ["--policy", str(self.pol), "--dir", str(self.dir), "--arch", ARCH, "--set", "full"],
        }
        for case, args in cases.items():
            with self.subTest(case=case):
                self.assertBadArgument(run_check("sources-check", *args))

    def test_sources_check_never_shows_a_traceback(self):
        nested = "[" * 100000 + "]" * 100000
        (self.tmp / "deep.json").write_text('{"components": ' + nested + ', "format": 1}\n', encoding="utf-8")
        (self.tmp / "bad-policy.json").write_text("{not json", encoding="utf-8")
        cases = {
            "a missing lock file": dict(lock=self.tmp / "nope.json"),
            "a 100000-deep nested lock": dict(lock=self.tmp / "deep.json"),
            "a policy that is not JSON": dict(pol=self.tmp / "bad-policy.json"),
        }
        for case, kw in cases.items():
            with self.subTest(case=case):
                self.assertOneFailLine(self.run_cli(**kw))  # type: ignore[arg-type]

    def test_oversize_record_refusal_reads_as_ruled(self):
        # Orchestrator O-13 (2), review B-1.
        n = 4 * 1024 * 1024 + 1
        (self.dir / "fetch.json").write_bytes(b" " * n)
        r = self.run_cli()
        self.assertRefused(r)
        self.assertTrue([ln for ln in r.stderr.splitlines() if ln.endswith(f"fetch.json is {n} bytes, over 4 MiB")],
                        f"no line ends with the ruled text: {r.stderr[-1500:]}")
        self.assertNoList(r)

    def test_record_text_in_a_cli_refusal_is_escaped(self):
        # U9-2 "escaped as PSC-22 L-3" (review B-2), through the CLI.
        key = "deb:bash@5.2.15-2+deb12u1"
        cases = {
            "an ESC in set": (lambda r: r.update(set="full\x1b[31m"), "set is full\\x1b[31m"),
            "a C1 CSI in a file name": (lambda r: r["components"][key][1].update(name="evil\x9bname.tar.xz"),
                                        "name is evil\\x9bname.tar.xz"),
        }
        for case, (change, escaped) in cases.items():
            with self.subTest(case=case):
                rec = json.loads(record_text(self.b, "full"))
                change(rec)
                d = self.tmp / f"case-{len(list(self.tmp.iterdir()))}"
                write_fetched(d, self.b, "full")
                (d / "fetch.json").write_bytes(canon(rec).encode("utf-8"))
                r = self.run_cli(directory=d)
                self.assertRefused(r, "fetch.json", escaped)
                self.assertNotRegex(r.stderr, RAW_CONTROL_RE, "a record byte was printed raw")
                self.assertNoList(r)


@unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "symlink") and os.name == "posix",
                     "os.mkfifo is unavailable here (Windows); the gates image runs these rows")
class SwappedAfterListingTest(_CliAsserts):
    """Security L-1, review N-4, orchestrator O-14: `fetch.json` and every
    planned file are opened without following a link and without blocking
    on a FIFO, and the open fd must be a regular file. The listing is made to
    see a regular file (os.lstat reports a decoy), so only the open can
    refuse; a hang is a failure after HANG_SECONDS."""

    command = "sources-check"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.b = wide()
        self.lock = self.tmp / "sources.lock.json"
        self.lock.write_bytes(self.b.text().encode("utf-8"))
        self.pol = ss.write_json(self.tmp / "source-policy.json", syn_policy())
        self.dir = self.tmp / "fetch"
        write_fetched(self.dir, self.b, "full")
        self.decoys = self.tmp / "decoys"
        self.decoys.mkdir()
        self.driver = self.tmp / "swap_driver.py"
        self.driver.write_text(SWAP_DRIVER, encoding="utf-8")
        self.s0 = sorted(distinct(self.b, "full"))[0]

    def swap(self, name: str, how: str) -> dict[str, str]:
        target = self.dir / name
        decoy = self.decoys / name
        decoy.write_bytes(target.read_bytes())
        target.unlink()
        if how == "fifo":
            os.mkfifo(target)
        else:
            os.symlink(decoy, target)
        return {os.path.abspath(target): str(decoy)}

    def run_swapped(self, swaps: dict[str, str]) -> subprocess.CompletedProcess:
        r = run_bounded([sys.executable, "-I", str(self.driver), str(CHECK), json.dumps(swaps), "sources-check",
                         "--lock", str(self.lock), "--policy", str(self.pol), "--dir", str(self.dir),
                         "--arch", ARCH, "--set", "full"])
        if r is None:
            self.fail(f"sources-check did not finish within {HANG_SECONDS} s: the read blocked on what was "
                      "swapped in after the listing (security L-1)")
        return r

    def test_control_the_decoy_driver_passes_an_untouched_dir(self):
        r = self.run_swapped({})
        self.assertKnown(r)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])

    def test_fetch_record_swapped_for_a_fifo_is_refused(self):
        r = self.run_swapped(self.swap("fetch.json", "fifo"))
        self.assertRefused(r, "fetch.json")
        self.assertFalse(HEX64.search(r.stdout))

    def test_planned_file_swapped_for_a_fifo_is_refused(self):
        r = self.run_swapped(self.swap(self.s0, "fifo"))
        self.assertRefused(r, self.s0)
        self.assertFalse(HEX64.search(r.stdout))

    def test_fetch_record_swapped_for_a_link_is_refused(self):
        r = self.run_swapped(self.swap("fetch.json", "link"))
        self.assertRefused(r, "fetch.json")
        self.assertFalse(HEX64.search(r.stdout))

    def test_planned_file_swapped_for_a_link_is_refused(self):
        r = self.run_swapped(self.swap(self.s0, "link"))
        self.assertRefused(r, self.s0)
        self.assertFalse(HEX64.search(r.stdout))


# --------------------------------------------------------------------------
# Items 5 and 6: source_index and the multi-match exempt rule
# --------------------------------------------------------------------------

class _IndexCase(unittest.TestCase):

    def setUp(self) -> None:
        self.S = load_sbom_check()
        self.index_fn = fn(self.S, "source_index")
        self.b = wide()

    def build(self, which: str = "full", *, docs: dict[str, Any] | None = None, pol: dict[str, Any] | None = None,
              listing: dict[str, tuple[str, int]] | None = None, text: str | None = None
              ) -> tuple[dict[str, Any] | None, list[str]]:
        got = self.index_fn(docs if docs is not None else syn_docs(), text if text is not None else self.b.text(),
                            pol if pol is not None else syn_policy(), ARCH, which, GIT_SHA,
                            listing if listing is not None else listing_of(self.b, which, record=False))
        self.assertIsInstance(got, tuple)
        index, problems = got
        self.assertIsInstance(problems, list)
        if problems:
            self.assertIsNone(index, "an index with problems is never returned (item 5: index | None)")
        return index, problems

    def ok(self, which: str = "full", **kw: Any) -> dict[str, Any]:
        index, problems = self.build(which, **kw)
        self.assertEqual(problems, [])
        self.assertIsInstance(index, dict)
        assert index is not None
        return index

    def refused(self, *parts: str, which: str = "full", **kw: Any) -> list[str]:
        index, problems = self.build(which, **kw)
        self.assertIsNone(index)
        self.assertTrue(problems, "no problem")
        self.assertTrue(any(all(p in line for p in parts) for line in problems), f"no problem names {parts}: {problems}")
        return problems

    @staticmethod
    def lock_components(index: dict[str, Any]) -> list[dict[str, Any]]:
        return [c for c in index["components"] if c.get("status") != "exempt"]

    @staticmethod
    def exempt_components(index: dict[str, Any]) -> list[dict[str, Any]]:
        return [c for c in index["components"] if c.get("status") == "exempt"]


class SourceIndexSchemaTest(_IndexCase):
    """U9-5, item 5 schema and rules (full and sample)."""

    def test_index_schema_and_order(self):
        docs = syn_docs()
        index = self.ok(docs=docs)
        lock = self.b.lock()
        self.assertEqual(set(index), TOP_KEYS)
        self.assertEqual((index["format"], index["set"], index["arch"], index["git_sha"]), (1, "full", ARCH, GIT_SHA))
        self.assertIs(type(index["format"]), int)
        self.assertEqual(index["lock_sha256"], sha(self.b.text().encode("utf-8")))
        amd64 = sorted(k for k, e in lock["components"].items() if ARCH in e["arches"])
        comps = self.lock_components(index)
        self.assertEqual([c["key"] for c in comps], amd64, "one component per needed key, sorted by key")
        self.assertEqual(index["components"][:len(comps)], comps, "lock-key components come first")
        always, exempt = [], syn_policy()["exempt"]
        rows = {image: self.S.classify_document(image, docs[image], always, exempt) for image in docs}
        for c in comps:
            with self.subTest(key=c["key"]):
                self.assertEqual(set(c), LOCK_COMPONENT_KEYS)
                self.assertEqual(c["kind"], c["key"].split(":", 1)[0])
                self.assertEqual(c["status"], "shipped")
                entry = lock["components"][c["key"]]
                self.assertEqual([{k: v for k, v in f.items() if k != "path"} for f in c["files"]], entry["files"],
                                 "files are the lock entry's, upstream verbatim")
                for f in c["files"]:
                    self.assertEqual(set(f), FILE_KEYS)
                    self.assertEqual(f["path"], f"sources/files/{f['sha256']}")
                self.assertTrue(c["packages"])
                for p in c["packages"]:
                    self.assertEqual(set(p), PACKAGE_KEYS)
                    self.assertEqual(set(p["licence"]), {"declared", "concluded"})
        with self.subTest(case="packages: image then document order, the classifier's rows"):
            bash = next(c for c in comps if c["key"] == "deb:bash@5.2.15-2")
            row = next(r for r in rows["postgres"] if r["purl"].startswith("pkg:deb/debian/bash@5.2.15-2%2Bb13"))
            self.assertEqual(bash["packages"], [{"image": "postgres", "spdxid": row["spdxid"], "purl": row["purl"],
                                                 "name": "bash", "always": False,
                                                 "licence": {"declared": "GPL-3.0-or-later", "concluded": "NOASSERTION"},
                                                 "expression": row["expression"]}])
            psy = next(c for c in comps if c["key"] == "pypi:psycopg@3.3.6")
            self.assertEqual(psy["packages"][0]["licence"], {"declared": "LicenseRef-" + "a" * 64,
                                                             "concluded": "NOASSERTION"})
        with self.subTest(case="the exempt component"):
            ex = self.exempt_components(index)
            self.assertEqual(index["components"][len(comps):], ex, "exempt components come after the lock keys")
            self.assertEqual(len(ex), 1, ex)
            c = ex[0]
            self.assertEqual(set(c), EXEMPT_COMPONENT_KEYS)
            jna = next(r for r in rows["ke-neo4j"] if r["purl"] == JNA)
            self.assertEqual((c["key"], c["kind"], c["status"], c["files"]), (None, None, "exempt", []))
            self.assertEqual([p["spdxid"] for p in c["packages"]], [jna["spdxid"]])
            self.assertEqual(c["packages"][0]["image"], "ke-neo4j")
            self.assertEqual(c["exempt"], {"image": "ke-neo4j", "package": JNA,
                                           "reason": exempt_entry()["reason"], "reviewed": REVIEWED},
                             "reason and reviewed verbatim")
            self.assertEqual(c["listing"], f"exempt, reviewed {REVIEWED}")
        with self.subTest(case="unparsed and unidentified: every flagged row, needs true or false"):
            want_unparsed = [{"image": im, "spdxid": r["spdxid"], "purl": r["purl"], "name": r["name"],
                              "needs": r["needs"]} for im in sorted(docs) for r in rows[im] if r["unparsed"]]
            want_unident = [{"image": im, "spdxid": r["spdxid"], "purl": r["purl"], "name": r["name"],
                             "needs": r["needs"]} for im in sorted(docs) for r in rows[im] if r["unidentified"]]
            self.assertTrue([r for r in want_unparsed if r["needs"] is False], "the probe needs a needs-false row")
            self.assertTrue([r for r in want_unident if r["needs"] is True], "the probe needs a needs-true row")
            self.assertEqual(index["unparsed"], want_unparsed)
            self.assertEqual(index["unidentified"], want_unident)
            for r in index["unparsed"] + index["unidentified"]:
                self.assertEqual(set(r), FLAG_ROW_KEYS)
        with self.subTest(case="unlicensed: unlicensed_report per image"):
            self.assertEqual(index["unlicensed"], {im: self.S.unlicensed_report(docs[im]) for im in docs})

    def test_a_non_string_licence_is_null(self):
        docs = syn_docs()
        for p in docs["ke-app"]["packages"]:
            if p.get("name") == "psycopg-c":
                p["licenseConcluded"] = ["LGPL-3.0-only"]
        index = self.ok(docs=docs)
        psyc = next(c for c in index["components"] if c["key"] == "pypi:psycopg-c@3.3.6")
        self.assertEqual(psyc["packages"][0]["licence"], {"declared": "LGPL-3.0-only", "concluded": None})

    def test_index_is_byte_identical_across_runs(self):
        a, b = self.ok(), self.ok()
        self.assertEqual(self.S.lock_text(a), self.S.lock_text(b))
        self.assertEqual(json.loads(self.S.lock_text(a)), a, "the index is plain JSON data")

    def test_sample_bundle_ships_exactly_the_sample(self):
        index = self.ok("sample")
        lock = self.b.lock()
        sample = set(self.S.sample_keys(lock, ARCH))
        comps = self.lock_components(index)
        self.assertEqual({c["key"] for c in comps if c["status"] == "shipped"}, sample)
        self.assertEqual({c["key"] for c in comps if c["status"] == "not-shipped"},
                         {k for k, e in lock["components"].items() if ARCH in e["arches"]} - sample)
        self.assertIn(NOT_SAMPLE, {c["key"] for c in comps if c["status"] == "not-shipped"})
        for c in comps:
            for f in c["files"]:
                with self.subTest(key=c["key"], file=f["name"]):
                    if c["status"] == "shipped":
                        self.assertEqual(f["path"], f"sources/files/{f['sha256']}")
                    else:
                        self.assertIsNone(f["path"], "path is null exactly when not shipped")
        with self.subTest(case="a sha256 shared by a shipped and a not-shipped key"):
            byk = {c["key"]: c for c in comps}
            shared = {f["sha256"] for f in byk[SHARED_IN_SAMPLE]["files"]} & {f["sha256"] for f in byk[SHARED_OUT]["files"]}
            self.assertEqual(len(shared), 1)
            s = shared.pop()
            self.assertEqual([f["path"] for f in byk[SHARED_IN_SAMPLE]["files"] if f["sha256"] == s], [f"sources/files/{s}"])
            self.assertEqual([f["path"] for f in byk[SHARED_OUT]["files"] if f["sha256"] == s], [None])
        with self.subTest(case="a full listing in a sample bundle is refused (nothing extra)"):
            self.refused(which="sample", listing=listing_of(self.b, "full", record=False))

    def test_full_bundle_refuses_not_shipped(self):
        with self.subTest(case="a planned file absent from app/sources/files"):
            listing = listing_of(self.b, "full", record=False)
            gone = next(f["sha256"] for k, f in plan_of(self.b, ARCH, "full") if k == NOT_SAMPLE)
            self.refused(gone, listing={k: v for k, v in listing.items() if k != gone})
        with self.subTest(case="item 5 stage 6, asserted although stages 3 and 5 cover it"):
            real = self.S.fetch_plan

            def short_plan(lock: Any, arch: str, which: str) -> Any:
                return [(k, f) for k, f in real(lock, arch, which) if k != NOT_SAMPLE]

            listing = {f["sha256"]: ("file", f["size"]) for _, f in short_plan(self.b.lock(), ARCH, "full")}
            with mock.patch.object(self.S, "fetch_plan", side_effect=short_plan):
                self.refused(f"index: {NOT_SAMPLE} is not shipped in a full bundle", listing=listing)

    def test_index_refuses_a_bad_files_listing(self):
        good = listing_of(self.b, "full", record=False)
        s0 = sorted(good)[0]
        cases = {
            "an extra 64-hex file": dict(good, **{"e" * 64: ("file", 3)}),
            "fetch.json copied": dict(good, **{"fetch.json": ("file", 3)}),
            "a link in place of a file": dict(good, **{s0: ("link", good[s0][1])}),
            "a size other than the lock's": dict(good, **{s0: ("file", good[s0][1] + 1)}),
            "an empty listing": {},
        }
        for case, listing in cases.items():
            with self.subTest(case=case):
                self.refused(listing=listing)

    def test_source_file_names_pass_the_manifest_rule(self):
        # U9-6, item 10: the installers' path rule, unchanged ([A-Za-z0-9._-]
        # per segment; no `.`/`..`, no trailing dot or space, no Windows
        # reserved device name).
        seg = re.compile(r"[A-Za-z0-9._-]+")
        reserved = re.compile(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?")
        for which in ("full", "sample"):
            index = self.ok(which)
            paths = {f["path"] for c in index["components"] for f in c["files"] if f["path"] is not None}
            self.assertTrue(paths)
            for p in sorted(paths):
                with self.subTest(which=which, path=p):
                    bundle_path = f"app/{p}"
                    for s in bundle_path.split("/"):
                        self.assertRegex(s, seg)
                        self.assertTrue(seg.fullmatch(s), s)
                        self.assertNotIn(s, (".", ".."))
                        self.assertFalse(s.endswith((".", " ")), s)
                        self.assertIsNone(reserved.fullmatch(s), s)
                    self.assertRegex(p, r"^sources/files/[0-9a-f]{64}$")

    def test_index_never_raises_on_hostile_input(self):
        cases = {
            "a lock that is not JSON": dict(text="{not json\n"),
            "an SBOM that is not an object": dict(docs=dict(syn_docs(), valkey=[])),
            "a listing entry of an unknown kind": dict(listing=dict(listing_of(self.b, "full", record=False),
                                                                    **{"x": ("socket", 0)})),
            "a policy whose exempt is not a list": dict(pol=dict(syn_policy(), exempt="x")),
        }
        for case, kw in cases.items():
            with self.subTest(case=case):
                try:
                    index, problems = self.build(**kw)
                except Exception as exc:  # noqa: BLE001 - the row under test
                    self.fail(f"{case}: raised {type(exc).__name__}: {exc}")
                self.assertIsNone(index)
                self.assertTrue(problems)


def multi_match_doc() -> tuple[dict[str, Any], list[str], str]:
    """ke-neo4j holding jna twice (its purl, and the same purl with
    `?type=jar`), the SPDXIDs in document order and the pinned problem."""
    docs = syn_docs(ke_neo4j=[{"purl": JNA + "?type=jar", "declared": "Apache-2.0 AND LGPL-2.1-or-later"}])
    neo = docs["ke-neo4j"]
    sids = [p["SPDXID"] for p in neo["packages"]
            if str((p.get("externalRefs") or [{}])[0].get("referenceLocator", "")).startswith(JNA)]
    assert len(sids) == 2, sids
    return docs, sids, (f"ke-neo4j: exempt entry matches 2 packages: {JNA} ({sids[0]}, {sids[1]}); "
                        "an exemption clears exactly one package: review again")


class ExemptMultiMatchTest(unittest.TestCase):
    """Item 6 (security U6 L-1, the U6 carried row): an exempt entry matching
    more than one package in its image is a problem naming every SPDXID; the
    SPDXIDs are still flagged, so classify_document is unchanged."""

    def setUp(self) -> None:
        self.S = load_sbom_check()

    def test_exempt_entry_matching_more_than_one_package_is_a_problem(self):
        docs, sids, want = multi_match_doc()
        flagged, problems = self.S.exempt_matches("ke-neo4j", docs["ke-neo4j"], [exempt_entry()])
        self.assertEqual(flagged, sids, "both packages stay flagged")
        self.assertEqual(problems, [want])

    def test_classify_document_is_unchanged(self):
        docs, sids, _ = multi_match_doc()
        rows = self.S.classify_document("ke-neo4j", docs["ke-neo4j"], [], [exempt_entry()])
        self.assertEqual([(r["exempt"], r["needs"]) for r in rows if r["spdxid"] in sids], [(True, False)] * 2)

    def test_control_the_committed_policy_matches_one_package_per_entry(self):
        fx = fixture_docs()
        for e in policy()["exempt"]:
            with self.subTest(package=e["package"]):
                flagged, problems = self.S.exempt_matches(e["image"], fx[e["image"]], [e])
                self.assertEqual((len(flagged), problems), (1, []))


class SourceIndexGateTest(_IndexCase):
    """U9-4: `index` gates the bundle (items 5 stages 2-4, item 6)."""

    def test_index_validates_first(self):
        docs = syn_docs()
        neo = docs["ke-neo4j"]
        jna_sid = next(p["SPDXID"] for p in neo["packages"] if p.get("name") == "jna")
        gpl = next(p for p in neo["packages"] if p.get("name") == "jaxb-api")
        old = gpl["SPDXID"]
        gpl["SPDXID"] = jna_sid  # a GPL package reusing the exempted package's SPDXID
        for r in neo["relationships"]:
            if r["relatedSpdxElement"] == old:
                r["relatedSpdxElement"] = jna_sid
        with mock.patch.object(self.S, "classify_document",
                               side_effect=AssertionError("classified before validate")) as classify:
            index, problems = self.build(docs=docs)
        self.assertFalse(classify.called, "classify_document ran before every SBOM passed validate (security U6 L-2)")
        self.assertIsNone(index)
        self.assertIn(f"ke-neo4j: package SPDXID {jna_sid} is not unique", problems)
        self.assertFalse([p for p in problems if "needs source" in p], "validate is a stage of its own")
        with self.subTest(case="any validate problem, in any image"):
            docs = syn_docs()
            docs["valkey"]["spdxVersion"] = "SPDX-2.2"
            self.refused("valkey: spdxVersion is 'SPDX-2.2', want SPDX-2.3", docs=docs)

    def test_index_fails_on_coverage_gaps_both_ways(self):
        dash = ss.deb("dash", "0.5.12-2")
        with self.subTest(case="a needed key the lock lacks for the arch"):
            docs = syn_docs(postgres=[{"purl": dash, "declared": "GPL-2.0-or-later"}])
            self.refused(miss("postgres", dash, "deb:dash@0.5.12-2"), docs=docs)
        with self.subTest(case="a lock key no image needs"):
            docs = syn_docs()
            del docs["ke-gateway"]
            self.refused(stale("apk:readline@8.2.13-r0"), docs=docs)
        with self.subTest(case="a needs row that maps to no lock kind"):
            docs = syn_docs(postgres=[{"purl": None, "name": "mystery", "declared": "GPL-2.0-only"}])
            self.refused("mystery (no purl) needs source and maps to no lock kind", docs=docs)
        with self.subTest(case="the jrt-fs version rule"):
            docs = syn_docs(ke_neo4j=[{"purl": "pkg:maven/jrt-fs/jrt-fs@21.0.11", "declared": "GPL-2.0-only"}])
            self.refused("ke-neo4j: jrt-fs 21.0.11 is not the image's Temurin build", docs=docs)

    def test_index_fails_on_always_and_exempt_problems(self):
        with self.subTest(case="an always entry with no match"):
            pol = syn_policy(always=[{"image": "valkey", "match": "pkg:apk/alpine/busybox", "why": "synthetic"}])
            self.refused("valkey: expected component not catalogued: pkg:apk/alpine/busybox (synthetic)", pol=pol)
        with self.subTest(case="an exempt entry that is not a versioned purl"):
            pol = syn_policy(exempt=[exempt_entry(), exempt_entry("pkg:maven/com.sun.jna/jna")])
            self.refused("ke-neo4j: exempt entry is not a versioned purl: pkg:maven/com.sun.jna/jna", pol=pol)
        with self.subTest(case="an exempt entry that matches nothing at its version"):
            pol = syn_policy(exempt=[exempt_entry(), exempt_entry("pkg:maven/org.example/absent@1.0")])
            self.refused("ke-neo4j: exempt entry matches nothing: pkg:maven/org.example/absent@1.0", pol=pol)

    def test_index_refuses_a_multi_match_exempt_entry(self):
        docs, _, want = multi_match_doc()
        self.refused(want, docs=docs)

    def test_index_lists_always_cleared_by_exemption(self):
        # U9-5, item 6: a synthetic policy (no real entry is both at U9;
        # tests/test_sbom_classifier.py l.1134 keeps its assertion).
        pol = syn_policy(always=[{"image": "ke-neo4j", "match": "pkg:maven/com.sun.jna/jna", "why": "synthetic"}])
        index = self.ok(pol=pol)
        ex = self.exempt_components(index)
        self.assertEqual(len(ex), 1, ex)
        self.assertEqual(ex[0]["listing"], f"always, cleared by exemption {REVIEWED}")
        self.assertIs(ex[0]["packages"][0]["always"], True)
        self.assertNotIn("maven:com.sun.jna:jna@5.15.0", [c["key"] for c in index["components"]])
        with self.subTest(case="otherwise: exempt, reviewed <reviewed>"):
            other = self.exempt_components(self.ok(pol=syn_policy(exempt=[exempt_entry(reviewed="security 2031-01-02")])))
            self.assertEqual(other[0]["listing"], "exempt, reviewed security 2031-01-02")
            self.assertIs(other[0]["packages"][0]["always"], False)

    def test_exempt_components_sorted_by_image_then_package(self):
        docs = syn_docs(ke_neo4j=[{"purl": JAVASSIST, "declared": "LGPL-2.1-only"}],
                        postgres=[{"purl": "pkg:deb/debian/aaa@1.0?arch=amd64", "declared": "GPL-2.0-only"}])
        pol = syn_policy(exempt=[exempt_entry(), exempt_entry(JAVASSIST),
                                 exempt_entry("pkg:deb/debian/aaa@1.0", image="postgres")])
        ex = self.exempt_components(self.ok(docs=docs, pol=pol))
        self.assertEqual([(c["exempt"]["image"], c["exempt"]["package"]) for c in ex],
                         [("ke-neo4j", JNA), ("ke-neo4j", JAVASSIST), ("postgres", "pkg:deb/debian/aaa@1.0")])

    def test_every_gpl_package_has_source(self):
        # Item 14 row 7, on the real data: the six U3 fixtures, the committed
        # lock and policy, `full`, a listing supplied as data.
        S = self.S
        text = COMMITTED_LOCK.read_bytes().decode("utf-8")
        plan = S.fetch_plan(json.loads(text), ARCH, "full")
        listing = {f["sha256"]: ("file", f["size"]) for _, f in plan}
        docs = fixture_docs()
        for image, doc in docs.items():
            self.assertEqual(S.validate(doc), [], f"{image}: the fixture document fails validate")
        index, problems = self.index_fn(docs, text, policy(), ARCH, "full", GIT_SHA, listing)
        self.assertEqual(problems, [])
        assert index is not None
        comps = self.lock_components(index)
        self.assertEqual({c["key"] for c in comps}, set(json.loads(text)["components"]))
        self.assertEqual({c["status"] for c in comps}, {"shipped"})
        ex = self.exempt_components(index)
        self.assertEqual(sorted((c["exempt"]["image"], c["exempt"]["package"], c["listing"]) for c in ex),
                         [("ke-neo4j", JNA, f"exempt, reviewed {REVIEWED}"),
                          ("ke-neo4j", JAVASSIST, f"exempt, reviewed {REVIEWED}")])
        needs = [(im, r["spdxid"]) for im in sorted(docs)
                 for r in S.classify_document(im, docs[im], policy()["always"], policy()["exempt"]) if r["needs"]]
        covered = [(p["image"], p["spdxid"]) for c in comps for p in c["packages"]]
        self.assertEqual(sorted(covered), sorted(needs), "every package that needs source is in a shipped component")

    def test_index_coverage_exempt_and_listing_stages_stop_in_order(self):
        # Item 5 (review N-9): stage 3 (coverage, lock_problems) stops before
        # stage 4 (always/exempt), stage 4 before stage 5 (the copied listing).
        dash = ss.deb("dash", "0.5.12-2")
        gap = miss("postgres", dash, "deb:dash@0.5.12-2")
        absent = "pkg:maven/org.example/absent@1.0"
        exempt_problem = f"ke-neo4j: exempt entry matches nothing: {absent}"
        extra = "e" * 64
        bad_pol = syn_policy(exempt=[exempt_entry(), exempt_entry(absent)])
        bad_listing = dict(listing_of(self.b, "full", record=False), **{extra: ("file", 3)})
        with self.subTest(case="a coverage gap, an exempt problem and a bad listing: the gap only"):
            got = self.refused(gap, docs=syn_docs(postgres=[{"purl": dash, "declared": "GPL-2.0-or-later"}]),
                               pol=bad_pol, listing=bad_listing)
            self.assertFalse([p for p in got if "exempt entry" in p], f"stage 4 ran after stage 3 failed: {got}")
            self.assertFalse([p for p in got if extra in p], f"stage 5 ran after stage 3 failed: {got}")
        with self.subTest(case="an exempt problem and a bad listing: the exempt problem only"):
            got = self.refused(exempt_problem, pol=bad_pol, listing=bad_listing)
            self.assertFalse([p for p in got if extra in p], f"stage 5 ran after stage 4 failed: {got}")
        with self.subTest(case="control: a bad listing alone reaches stage 5"):
            self.refused(extra, listing=bad_listing)

    def test_index_names_files_when_the_listing_cannot_be_read(self):
        # Review N-7, orchestrator O-14: the pure path's listing failure names
        # the --files directory, not `.`.
        class Unreadable(Mapping):  # type: ignore[type-arg]
            def __getitem__(self, key: Any) -> Any:
                raise OSError("unreadable")

            def __iter__(self) -> Any:
                raise OSError("unreadable")

            def __len__(self) -> int:
                raise OSError("unreadable")

        got = self.refused("--files: cannot list", listing=Unreadable())
        self.assertFalse([p for p in got if p.startswith(".:")], got)


# --------------------------------------------------------------------------
# Item 7: source_section, the "Source code" section
# --------------------------------------------------------------------------

class SourceSectionTest(_IndexCase):
    """U9-7: the section's rows and banner; refuse, never escape."""

    def setUp(self) -> None:
        super().setUp()
        self.section = fn(self.S, "source_section")

    def text_of(self, index: dict[str, Any]) -> str:
        got = self.section(index)
        self.assertIsInstance(got, tuple)
        text, problems = got
        self.assertEqual(problems, [])
        self.assertIsInstance(text, str)
        return text

    @staticmethod
    def images(c: dict[str, Any]) -> str:
        return ", ".join(sorted({p["image"] for p in c["packages"]}))

    def test_notices_source_code_section_rows(self):
        for which in ("full", "sample"):
            with self.subTest(which=which):
                index = self.ok(which)
                text = self.text_of(index)
                lines = text.splitlines()
                self.assertEqual(lines[0], "## Source code")
                self.assertEqual(text.count(I3), 1, "the I-3 sentence, once")
                self.assertLess(text.index(I3), text.index("sources/"), "the I-3 sentence comes before any path")
                self.assertIn("sources/index.json", text)
                self.assertEqual(lines.count("| Component | Images | Source |"), 1)
                head = lines.index("| Component | Images | Source |")
                self.assertEqual(lines[head + 1], "|---|---|---|")
                rows = [ln for ln in lines[head + 2:] if ln.startswith("| ")]
                want = []
                for c in index["components"]:
                    if c["status"] == "shipped":
                        want.append(f"| `{c['key']}` | {self.images(c)} | {SHIPPED_CELL} |")
                    elif c["status"] == "not-shipped":
                        want.append(f"| `{c['key']}` | {self.images(c)} | Upstream source: {c['files'][0]['url']} |")
                    else:
                        want.append(f"| `{c['exempt']['package']}` | {c['exempt']['image']} | no source in this "
                                    f"bundle: cleared by a reviewed exemption ({c['listing']}) |")
                self.assertEqual(rows, want, "one row per index component, in index order")
                self.assertEqual(len([c for c in index["components"] if c["status"] == "not-shipped"]) > 0,
                                 which == "sample")
                for row in rows:
                    if "Upstream source:" in row or "no source in this bundle" in row:
                        self.assertNotIn("source in `sources/`", row, "a source claim only for shipped components")

    def test_sample_bundle_notices_say_do_not_distribute(self):
        sample = self.text_of(self.ok("sample"))
        self.assertEqual(sample.count(BANNER), 1)
        self.assertIn(BANNER, sample.splitlines(), "the banner is a line of its own")
        self.assertLess(sample.index(BANNER), sample.index("| Component | Images | Source |"))
        full = self.text_of(self.ok("full"))
        self.assertNotIn("Verification bundle", full)
        self.assertNotIn("do not distribute", full)

    def test_notice_section_refuses_rather_than_escapes(self):
        base = self.ok("sample")
        shipped = next(i for i, c in enumerate(base["components"]) if c["status"] == "shipped")
        out = next(i for i, c in enumerate(base["components"]) if c["status"] == "not-shipped")
        ex = next(i for i, c in enumerate(base["components"]) if c["status"] == "exempt")

        def key(v: str) -> Callable[[dict[str, Any]], None]:
            return lambda ix: ix["components"][shipped].update(key=v)

        def url(v: str) -> Callable[[dict[str, Any]], None]:
            return lambda ix: ix["components"][out]["files"][0].update(url=v)

        def image(v: str) -> Callable[[dict[str, Any]], None]:
            return lambda ix: [p.update(image=v) for p in ix["components"][shipped]["packages"]]

        def package(v: str) -> Callable[[dict[str, Any]], None]:
            return lambda ix: ix["components"][ex]["exempt"].update(package=v)

        def reviewed(v: str) -> Callable[[dict[str, Any]], None]:
            def apply(ix: dict[str, Any]) -> None:
                ix["components"][ex]["exempt"]["reviewed"] = v
                ix["components"][ex]["listing"] = f"exempt, reviewed {v}"
            return apply

        k0 = base["components"][shipped]["key"]
        u0 = base["components"][out]["files"][0]["url"]
        cases = {}
        for ch, label in (("|", "pipe"), ("`", "backtick"), ("<", "lt"), (">", "gt"), ("\\", "backslash"),
                          ("\n", "newline"), ("\r", "carriage return"), ("\x07", "C0 control"),
                          ("\x85", "C1 control"), ("\x7f", "DEL")):
            cases[f"a key with a {label}"] = key(k0 + ch + "x")
            cases[f"a URL with a {label}"] = url(u0 + ch + "x")
            cases[f"an image with a {label}"] = image("postgres" + ch + "x")
            cases[f"an exempt package with a {label}"] = package(JNA + ch + "x")
            cases[f"a reviewed value with a {label}"] = reviewed("security" + ch + "x")
        cases["a key with a space"] = key(k0 + " x")
        cases["a URL with a space"] = url(u0 + " x")
        cases["a key with a non-ASCII letter"] = key(k0 + "é")
        for case, change in cases.items():
            with self.subTest(case=case):
                ix = copy.deepcopy(base)
                change(ix)
                got = self.section(ix)
                self.assertIsInstance(got, tuple)
                text, problems = got
                self.assertIsNone(text, f"{case}: a section was produced")
                self.assertTrue(problems, case)
        with self.subTest(case="control: a space inside reviewed is printable"):
            ix = copy.deepcopy(base)
            reviewed("security team 2026-10-25")(ix)
            self.assertIn("exempt, reviewed security team 2026-10-25", self.text_of(ix))

    def test_generator_text_never_reaches_the_section(self):
        docs = syn_docs()
        for p in docs["ke-app"]["packages"]:
            if p.get("name") == "psycopg-c":
                p["name"] = "evil|name\n| injected | row |"
                p["licenseDeclared"] = "LGPL-3.0-only"
                p["licenseConcluded"] = "GPL-3.0-only|<b>evil</b>"
        text = self.text_of(self.ok(docs=docs))
        for bad in ("evil", "injected", "<b>"):
            self.assertNotIn(bad, text)

    def test_sample_banner_is_the_first_line_after_the_heading(self):
        # U9-7 "starts with", orchestrator O-13 (4) (review B-1): heading,
        # banner, then the I-3 sentence; without a banner the I-3 sentence
        # comes first (item 7).
        sample = [ln for ln in self.text_of(self.ok("sample")).splitlines() if ln.strip()]
        self.assertEqual(sample[:3], ["## Source code", BANNER, I3])
        full = [ln for ln in self.text_of(self.ok("full")).splitlines() if ln.strip()]
        self.assertEqual(full[:2], ["## Source code", I3])

    def test_notice_section_refuses_markdown_syntax_outside_the_url(self):
        # Security L-2, orchestrator O-14 and "O-14 precision": `[ ] ( ) ! * _ #`
        # are refused in every printed free-text field, but not in the
        # lock-key column (a code span) nor the URL column; the item-7 set
        # stays refused there (keys: this row; URLs: the row above).
        base = self.ok("sample")
        shipped = next(i for i, c in enumerate(base["components"]) if c["status"] == "shipped")
        out = next(i for i, c in enumerate(base["components"]) if c["status"] == "not-shipped")
        ex = next(i for i, c in enumerate(base["components"]) if c["status"] == "exempt")
        k0, k1 = base["components"][shipped]["key"], base["components"][out]["key"]

        def setter(*path: Any) -> Callable[[str], Callable[[dict[str, Any]], None]]:
            def make(v: str) -> Callable[[dict[str, Any]], None]:
                def apply(ix: dict[str, Any]) -> None:
                    node: Any = ix
                    for step in path[:-1]:
                        node = node[step]
                    node[path[-1]] = v
                return apply
            return make

        def images(v: str) -> Callable[[dict[str, Any]], None]:
            return lambda ix: [p.update(image=v) for p in ix["components"][shipped]["packages"]]

        def reviewed(v: str) -> Callable[[dict[str, Any]], None]:
            def apply(ix: dict[str, Any]) -> None:
                ix["components"][ex]["exempt"]["reviewed"] = v
                ix["components"][ex]["listing"] = f"exempt, reviewed {v}"
            return apply

        fields: dict[str, tuple[Callable[[str], Callable[[dict[str, Any]], None]], str]] = {
            "an image": (images, "postgres"),
            "an exempt package": (setter("components", ex, "exempt", "package"), JNA),
            "an exempt image": (setter("components", ex, "exempt", "image"), "ke-neo4j"),
            "a reviewed value": (reviewed, "security"),
            "a listing": (setter("components", ex, "listing"), f"exempt, reviewed {REVIEWED}"),
        }
        cases = {f"{field} with {ch!r}": make(value + ch + "x")
                 for field, (make, value) in fields.items() for ch in "[]()!*_#"}
        cases["the probe: a Markdown link in reviewed"] = reviewed("security [x](javascript:alert(1))")
        for case, change in cases.items():
            with self.subTest(case=case):
                ix = copy.deepcopy(base)
                change(ix)
                got = self.section(ix)
                self.assertIsInstance(got, tuple)
                text, problems = got
                self.assertIsNone(text, f"{case}: a section was produced")
                self.assertTrue(problems, case)
        keys = {"a shipped key": (shipped, k0), "a not-shipped key": (out, k1)}
        for field, (i, k) in keys.items():
            for ch in "_!":
                with self.subTest(case=f"control: {field} with {ch!r} still prints (a code span)"):
                    ix = copy.deepcopy(base)
                    ix["components"][i]["key"] = k + ch + "x"
                    self.assertIn(f"| `{k + ch}x` |", self.text_of(ix))
            for ch in "`|":
                with self.subTest(case=f"{field} with {ch!r} is still refused (item 7)"):
                    ix = copy.deepcopy(base)
                    ix["components"][i]["key"] = k + ch + "x"
                    text, problems = self.section(ix)
                    self.assertIsNone(text, f"{field} with {ch!r}: a section was produced")
                    self.assertTrue(problems)
        with self.subTest(case="control: a URL with ( and _ in its path still prints"):
            ix = copy.deepcopy(base)
            u = ix["components"][out]["files"][0]["url"] + "_(1)"
            ix["components"][out]["files"][0]["url"] = u
            self.assertIn(f"Upstream source: {u} |", self.text_of(ix))

    def test_notice_source_code_heading_matches_generated(self):
        # PSC-15: NOTICE.md names the section the bundle's generated text heads.
        notice = NOTICE.read_text(encoding="utf-8")
        named = set(re.findall(r'in its "([^"]+)" section', notice))
        self.assertEqual(named, {"Source code"}, "NOTICE.md's pointer names one section")
        heading = self.text_of(self.ok()).splitlines()[0]
        self.assertEqual(heading, "## " + named.pop())


# --------------------------------------------------------------------------
# Items 1 and 5: the `index` subcommand
# --------------------------------------------------------------------------

class IndexCliTest(_CliAsserts):
    """`sbom_check.py index --lock L --policy P --arch A --set S --git-sha G
    --files DIR --sbom IMAGE=PATH [...]`; stdout is index.json."""

    command = "index"

    def setUp(self) -> None:
        self.S = load_sbom_check()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.b = wide()
        self.lock = self.tmp / "sources.lock.json"
        self.lock.write_bytes(self.b.text().encode("utf-8"))

    def setup_set(self, which: str = "full", pol: dict[str, Any] | None = None,
                  docs: dict[str, Any] | None = None) -> list[str]:
        d = self.tmp / f"files-{which}"
        if not d.exists():
            write_fetched(d, self.b, which, record=False)
        ss.write_json(self.tmp / "source-policy.json", pol or syn_policy())
        args = []
        for image, doc in (docs or syn_docs()).items():
            p = ss.write_json(self.tmp / "sboms" / f"{image}.spdx.json", doc)
            args += ["--sbom", f"{image}={p}"]
        return ["--lock", str(self.lock), "--policy", str(self.tmp / "source-policy.json"), "--arch", ARCH,
                "--set", which, "--git-sha", GIT_SHA, "--files", str(d)] + args

    def test_index_cli_prints_the_canonical_index(self):
        for which in ("full", "sample"):
            with self.subTest(which=which):
                args = self.setup_set(which)
                r1, r2 = run_check("index", *args), run_check("index", *args)
                self.assertKnown(r1)
                self.assertEqual(r1.returncode, 0, r1.stderr[-1500:])
                self.assertEqual(r1.stdout, r2.stdout, "two runs on the same inputs are byte-identical")
                data = json.loads(r1.stdout)
                self.assertEqual(r1.stdout, self.S.lock_text(data), "the lock_text form")
                index, problems = fn(self.S, "source_index")(syn_docs(), self.b.text(), syn_policy(), ARCH, which,
                                                             GIT_SHA, listing_of(self.b, which, record=False))
                self.assertEqual(problems, [])
                self.assertEqual(r1.stdout, self.S.lock_text(index), "the subcommand prints source_index's index")
                self.assertIn(f"ke-neo4j: {JNA}: exempt, reviewed {REVIEWED}", r1.stderr)

    def test_index_cli_prints_always_cleared_by_exemption(self):
        pol = syn_policy(always=[{"image": "ke-neo4j", "match": "pkg:maven/com.sun.jna/jna", "why": "synthetic"}])
        r = run_check("index", *self.setup_set(pol=pol))
        self.assertKnown(r)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn(f"ke-neo4j: {JNA}: always, cleared by exemption {REVIEWED}", r.stderr)

    def test_index_cli_refuses(self):
        with self.subTest(case="an extra file in --files"):
            args = self.setup_set()
            (self.tmp / "files-full" / ("e" * 64)).write_bytes(b"extra")
            r = run_check("index", *args)
            self.assertRefused(r, "e" * 64)
            self.assertEqual(r.stdout, "", "no index on stdout when refused")
            (self.tmp / "files-full" / ("e" * 64)).unlink()
        with self.subTest(case="an SBOM failing validate"):
            docs = syn_docs()
            docs["valkey"]["dataLicense"] = "MIT"
            r = run_check("index", *self.setup_set(docs=docs))
            self.assertRefused(r, "valkey: dataLicense")
            self.assertEqual(r.stdout, "")
        with self.subTest(case="a multi-match exempt entry"):
            docs = syn_docs(ke_neo4j=[{"purl": JNA + "?type=jar", "declared": "Apache-2.0 AND LGPL-2.1-or-later"}])
            r = run_check("index", *self.setup_set(docs=docs))
            self.assertRefused(r, "exempt entry matches 2 packages")
            self.assertEqual(r.stdout, "")

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "root (or Windows) bypasses the mode bits; the gates image runs as uid 10001")
    def test_index_cli_a_failed_listing_is_a_refusal(self):
        args = self.setup_set()
        d = self.tmp / "files-full"
        os.chmod(d, 0o300)
        self.addCleanup(os.chmod, d, 0o700)
        r = run_check("index", *args)
        self.assertRefused(r)
        self.assertEqual(r.stdout, "")

    def test_index_cli_exit_2_on_a_bad_argument(self):
        args = self.setup_set()

        def swap(opt: str, value: str) -> list[str]:
            out = list(args)
            out[out.index(opt) + 1] = value
            return out

        cases = {
            "an unknown arch": swap("--arch", "x86_64"),
            "an unknown set": swap("--set", "most"),
            "an --sbom without IMAGE=": swap("--sbom", str(self.tmp / "x.json")),
            "no --sbom": [a for a in args[:args.index("--sbom")]],
            "no --files": args[:args.index("--files")] + args[args.index("--files") + 2:],
        }
        for case, argv in cases.items():
            with self.subTest(case=case):
                self.assertBadArgument(run_check("index", *argv))

    def test_index_cli_exit_2_on_a_malformed_git_sha(self):
        # Orchestrator O-13 (6) (review B-1).
        args = self.setup_set()
        at = args.index("--git-sha") + 1
        cases = {
            "upper-case hex": GIT_SHA.upper(),
            "39 hex digits": GIT_SHA[:-1],
            "41 hex digits": GIT_SHA + "0",
            "a trailing newline": GIT_SHA + "\n",
            "a non-hex letter": "g" + GIT_SHA[1:],
            "an ESC": "\x1b" + GIT_SHA[1:],
            "empty": "",
        }
        for case, value in cases.items():
            with self.subTest(case=case):
                argv = list(args)
                argv[at] = value
                r = run_check("index", *argv)
                self.assertBadArgument(r)
                self.assertEqual(r.stdout, "", "no index on stdout")
                self.assertNotRegex(r.stderr, RAW_CONTROL_RE, "the value is echoed raw")

    def test_index_cli_exempt_lines_carry_the_index_prefix(self):
        # Orchestrator O-13 (7) (review B-1): `index: <image>: <package>: <listing>`.
        r = run_check("index", *self.setup_set())
        self.assertKnown(r)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn(f"index: ke-neo4j: {JNA}: exempt, reviewed {REVIEWED}", r.stderr.splitlines())
        pol = syn_policy(always=[{"image": "ke-neo4j", "match": "pkg:maven/com.sun.jna/jna", "why": "synthetic"}])
        r = run_check("index", *self.setup_set(pol=pol))
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn(f"index: ke-neo4j: {JNA}: always, cleared by exemption {REVIEWED}", r.stderr.splitlines())

    def test_index_cli_never_shows_a_traceback(self):
        args = self.setup_set()
        (self.tmp / "not-json.spdx.json").write_text("{not json", encoding="utf-8")
        nested = "[" * 100000 + "]" * 100000
        (self.tmp / "deep.spdx.json").write_text(nested, encoding="utf-8")

        def swap_sbom(image: str, path: Path) -> list[str]:
            out = list(args)
            out[out.index(next(a for a in out if a.startswith(f"{image}=")))] = f"{image}={path}"
            return out

        cases = {
            "a missing SBOM": swap_sbom("valkey", self.tmp / "nope.json"),
            "an SBOM that is not JSON": swap_sbom("valkey", self.tmp / "not-json.spdx.json"),
            "a 100000-deep nested SBOM": swap_sbom("valkey", self.tmp / "deep.spdx.json"),
        }
        for case, argv in cases.items():
            with self.subTest(case=case):
                self.assertOneFailLine(run_check("index", *argv))
        with self.subTest(case="--files absent"):
            out = list(args)
            out[out.index("--files") + 1] = str(self.tmp / "nope")
            r = run_check("index", *out)
            self.assertRefused(r)
            self.assertEqual(r.stdout, "")


# --------------------------------------------------------------------------
# Items 1 and 7: the `notices` subcommand
# --------------------------------------------------------------------------

class NoticesCliTest(_CliAsserts):
    """`sbom_check.py notices --index PATH` prints the "Source code" section."""

    command = "notices"

    def setUp(self) -> None:
        self.S = load_sbom_check()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.b = wide()

    def index(self, which: str = "sample") -> dict[str, Any]:
        index, problems = fn(self.S, "source_index")(syn_docs(), self.b.text(), syn_policy(), ARCH, which,
                                                     GIT_SHA, listing_of(self.b, which, record=False))
        self.assertEqual(problems, [])
        assert index is not None
        return index

    def write(self, data: Any) -> Path:
        p = self.tmp / "index.json"
        p.write_text(data if isinstance(data, str) else self.S.lock_text(data), encoding="utf-8", newline="")
        return p

    def test_notices_prints_the_section(self):
        for which in ("full", "sample"):
            with self.subTest(which=which):
                ix = self.index(which)
                r = run_check("notices", "--index", str(self.write(ix)))
                self.assertKnown(r)
                self.assertEqual(r.returncode, 0, r.stderr[-1500:])
                text, problems = fn(self.S, "source_section")(ix)
                self.assertEqual(problems, [])
                self.assertEqual(r.stdout.rstrip("\n"), text.rstrip("\n"))
                self.assertTrue(r.stdout.startswith("## Source code\n"))

    def test_notices_refuses_and_prints_no_section(self):
        ix = self.index()
        ix["components"][0]["key"] += "|x"
        r = run_check("notices", "--index", str(self.write(ix)))
        self.assertRefused(r)
        self.assertNotIn("## Source code", r.stdout)
        self.assertNotIn("|x", r.stdout)

    def test_notices_never_shows_a_traceback(self):
        for case, path in {"an index that is not JSON": self.write("{not json\n"),
                           "a missing index": self.tmp / "nope.json"}.items():
            with self.subTest(case=case):
                self.assertOneFailLine(run_check("notices", "--index", str(path)))
        with self.subTest(case="an index that is not an object"):
            r = run_check("notices", "--index", str(self.write("[]\n")))
            self.assertRefused(r)
            self.assertNotIn("## Source code", r.stdout)

    def test_notices_exit_2_on_a_bad_argument(self):
        self.assertBadArgument(run_check("notices"))


@unittest.skipUnless(hasattr(os, "mkfifo") and os.name == "posix" and os.path.exists("/dev/zero"),
                     "os.mkfifo or /dev/zero is unavailable here (Windows); the gates image runs these rows")
class NoticesIndexReadTest(_CliAsserts):
    """Security L-3, orchestrator O-14: `notices --index` opens a regular
    file only (a FIFO or a device is refused without a read) and refuses a
    file over 16 MiB by its size before reading it. Each run is bounded in
    time and memory; running out of memory is not a refusal."""

    command = "notices"

    def setUp(self) -> None:
        self.S = load_sbom_check()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.b = wide()
        index, problems = fn(self.S, "source_index")(syn_docs(), self.b.text(), syn_policy(), ARCH, "sample",
                                                     GIT_SHA, listing_of(self.b, "sample", record=False))
        self.assertEqual(problems, [])
        self.text = self.S.lock_text(index)

    def notices(self, path: Path | str) -> subprocess.CompletedProcess:
        r = run_bounded([sys.executable, "-I", str(CHECK), "notices", "--index", str(path)])
        if r is None:
            self.fail(f"notices --index {path} did not finish within {HANG_SECONDS} s (security L-3)")
        return r

    def assertRefusedWithoutReading(self, r: subprocess.CompletedProcess) -> None:
        self.assertRefused(r)
        self.assertNotIn("## Source code", r.stdout)
        self.assertNotIn("MemoryError", r.stderr, "refused by running out of memory, not by the check")

    def padded(self, size: int) -> Path:
        data = self.text.encode("utf-8")
        p = self.tmp / f"index-{size}.json"
        p.write_bytes(data + b" " * (size - len(data)))
        return p

    def test_notices_refuses_a_fifo_index(self):
        fifo = self.tmp / "index.json"
        os.mkfifo(fifo)
        self.assertRefusedWithoutReading(self.notices(fifo))

    def test_notices_refuses_a_device_index(self):
        self.assertRefusedWithoutReading(self.notices("/dev/zero"))

    def test_notices_refuses_an_index_over_the_size_cap(self):
        with self.subTest(case="one byte over 16 MiB"):
            r = self.notices(self.padded(INDEX_MAX + 1))
            self.assertRefusedWithoutReading(r)
            self.assertRegex(r.stderr, r"16 MiB|16777217")
        with self.subTest(case="a sparse 1 GiB file: refused by its size, never read"):
            sparse = self.tmp / "sparse.json"
            with open(sparse, "wb") as fh:
                fh.truncate(1 << 30)
            self.assertRefusedWithoutReading(self.notices(sparse))
        with self.subTest(case="control: exactly 16 MiB is read"):
            ok = self.notices(self.padded(INDEX_MAX))
            self.assertEqual(ok.returncode, 0, ok.stderr[-1500:])
            self.assertTrue(ok.stdout.startswith("## Source code\n"))


if __name__ == "__main__":
    unittest.main()
