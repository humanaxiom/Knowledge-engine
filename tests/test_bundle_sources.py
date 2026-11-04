"""platform-sbom U9b: `scripts/bundle.sh` ships the fetched source set
(PSC-15, PSC-24; requirements "U9 precision" U9-1, U9-6, U9-8..U9-13, with
the Q78, O-10 and O-11 amendments; design-notes "N9 amendment, U9" items 2, 4,
7, 8, 9, 11-14 and the orchestrator rulings at its end: Q78 `--sources`
mandatory, O-10 removal on failure, O-13 (7) `index:` exempt lines, the
carried reviewer N-9 and security I-4). Tester, U9b RED, 2026-10-29.

Every row runs the real bundle.sh against the fake docker and fake df of
tests/fake_docker.py, in tests/test_offline_bundle.py `_BundleBase`'s
throwaway repository, whose synthetic `docker/sources.lock.json`,
`docker/source-policy.json` and fetched directory (one file per distinct
planned sha256 plus `fetch.json`, outside --out) cover exactly what the fake
syft's documents need. The three new stages (`sources-check`, `index`,
`notices`) run the real scripts/sbom_check.py through the fake's `run ...
sbom_check.py` model, as `finish` does; no fake change was needed. No
network; no test reads docs/evidence.

Orchestrator rulings these rows pin (design-notes, end of "N9 amendment, U9"):
- O-15 (at U9b RED): A2 the marker is item 12's form, `bundle: sources: check
  <a> s, copy <b> s, index <c> s, notices <d> s`, pinned by a fullmatch
  (MARKER_RE); A3 `docker info` (the arch) may precede the `--sources` shell
  checks and no other docker call may: every item-2 shell refusal (absent,
  symlink, not a directory, unlistable, no or non-regular fetch.json, overlap)
  asserts that every recorded docker call is `info`; A4 each refusal at a
  named stage is one `bundle: FAIL (stage <stage>: <why>)` line, the stage
  being sources-check, copy, index, notices, manifest or out, pinned per row by
  a fullmatch of that form (A4_RE); A8 `--sources ""` exits 2 with the usage
  line and no docker call.
- O-16 (U9b rework 1, on reviewer B-1..B-3, N-1, N-2, N-7 and security L-4):
  (1) after --out and --sources are made absolute every trailing slash is
  stripped, and a path holding an empty, `.` or `..` segment is refused before
  any check (`stage sources-check` or `stage out`, exit 1), never resolved;
  the overlap check is segment-wise and resolves links; (2) --out is claimed
  with a plain `mkdir` at the first write, so a missing parent is `stage out`
  with nothing written; (3) the release record is written under noclobber;
  (4) tag, save and the `app/` copies end in one `bundle:` line, and SIGTERM
  after the first write removes the run's output; (6) the manifest stage's
  refusals (a non-regular file, the path pattern) are `stage manifest`;
  (7) `_strip_messages` strips `stage_die` text, every stage line goes
  through `stage_die`, and the `app/` copies come from the bundle-root copies
  in --out (N-2). Rows that make symlinks skip on Windows (the gates image
  runs them); no symlink is made on the Windows host.
- O-17 (U9b rework 2, on reviewer rework-1 B-1 and N-1, security I-13 and
  I-14): (1) `created` is decided once, at the early --out check; an --out
  that appears after it (a directory, or a link to one) and a given --out
  replaced by a link before the first write are refused as `stage out` with
  nothing written; the trailing `..` segment, the N-4 cleanup warning and the
  N-5 empty sources-check output each get a row; (2) a link to a non-regular
  file at the record path is never removed by the cleanup, and a failed
  `chmod` of the record ends in a `bundle:` line.

Readings the tester pinned where the rulings leave a choice:
- the index and notices failure lines have no fixed text beyond A4 (U9-10:
  "one `bundle:` line naming the stage");
- tag and save failures (O-16 (4): `die "... no bundle written"`): a `bundle:`
  line naming the image's bundle name and saying "no bundle written";
- the noclobber row (O-16 (3)) pins non-zero, the record's bytes and the
  removal of --out (O-10), not a message (none is ruled);
- `--sources //` (empty once every trailing slash goes): exit 1 or 2, no
  docker call but `info`, nothing written (O-16 does not say which exit);
- README's sample warning has no fixed wording (U9-12): pinned as a
  paragraph naming `sample` and "verification only" (or "only for
  verification");
- O-17 (1), a given --out replaced by a link before the first write: the
  ruling says "refused"; pinned as `bundle: FAIL (stage out: ...)`, the stage
  it names for an --out that appeared since the check;
- O-16 (7) N-5: the empty-output refusal is pinned as a `stage sources-check`
  line saying no source file was listed ("no source file", "listed nothing"
  or "empty"), so that the not-a-sha256 refusal of an empty line does not
  stand in for it;
- O-17 (2), I-14: the `chmod` failure's `bundle:` line names the record
  ("record" or its path); no text is ruled;
- "CLAUDE.md unchanged by U9b": pinned as the lock row's U9 sentence, verbatim
  (a whole-file hash pin would fail every later, approved CLAUDE.md change);
  the file's sha256 before and after is in u9/u9b-controls.txt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests import fake_docker
from tests.engine_support import ROOT
from tests.test_offline_bundle import (ENGINE_OK, SHARED_SOURCE, _BundleBase, _default_source_keys, _rel,
                                       _synthetic_lock, _synthetic_policy, _write_fetched)

BUNDLE_SH = ROOT / "scripts" / "bundle.sh"
CHECK = ROOT / "scripts" / "sbom_check.py"
README_MD = ROOT / "README.md"
NOTICE_MD = ROOT / "NOTICE.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
NOTICES = "THIRD_PARTY_NOTICES.md"
REVIEWED = "security 2026-10-25"
HEX64 = re.compile(r"[0-9a-f]{64}")
# The generated section's fixed lines (pinned by U9a, tests/test_source_index.py).
I3 = "Paths here are relative to the bundle's `app/` directory, which install publishes as the install directory."
BANNER = "Verification bundle: this source set is a sample and is not complete; do not distribute this bundle."
USAGE_RE = re.compile(r"(?m)^usage: scripts/bundle\.sh\b.*--sources\b.*--sources-set\b")
# Any line that looks like the source-stage marker; MARKER_RE is O-15 A2's ruled form, matched whole.
MARKER_LOOSE_RE = re.compile(r"(?m)^.*\bsources:.*\bcheck \d+ ?s\b.*\bcopy \d+ ?s\b.*\bindex \d+ ?s\b.*\bnotices \d+ ?s\b.*$")
MARKER_RE = re.compile(r"bundle: sources: check \d+ s, copy \d+ s, index \d+ s, notices \d+ s")
# O-15 A4: the one refusal line of a named stage.
STAGES = ("sources-check", "copy", "index", "notices", "manifest", "out")
SYMLINK_SKIP = "POSIX symlinks; the gates image is Linux (no symlink is made on the Windows host)"
SIGNAL_SKIP = "POSIX signals; the gates image is Linux"
MANIFEST_CAP = 1024 * 1024
# U9-9 and design item 7, with security's R7 record (u9/libffi-provenance.md, read by the tester
# only to take the text; no test reads docs/evidence): the file, its source and its sha256.
LIBFFI_FILE = "licenses/libffi-jna-5.15.0.txt"
LIBFFI_URL = "https://raw.githubusercontent.com/java-native-access/jna/5.15.0/native/libffi/LICENSE"
LIBFFI_SHA256 = "2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388"
LIBFFI_SIZE = 1132
LIBFFI_HEADER = ["libffi 3.4.4 (vendored by JNA 5.15.0): native/libffi/LICENSE", f"Source: {LIBFFI_URL}",
                 f"Source sha256: {LIBFFI_SHA256}"]
LIBFFI_FIRST = "libffi - Copyright (c) 1996-2022  Anthony Green, Red Hat, Inc and others."
LIBFFI_PARAGRAPH = (
    "`/var/lib/neo4j/lib/jna-5.15.0.jar` (Java Native Access 5.15.0) carries native `libjnidispatch` "
    "libraries that include libffi 3.4.4, the copy JNA vendors in its `native/libffi` directory. "
    "libffi is under an MIT-style licence (\"libffi - Copyright (c) 1996-2022 Anthony Green, Red Hat, "
    "Inc and others.\"), and its copyright and permission notice is not in Neo4j's notices. The full "
    "text is `licenses/libffi-jna-5.15.0.txt`: JNA's `native/libffi/LICENSE` at tag 5.15.0, "
    "unmodified, fetched over HTTPS from "
    "https://raw.githubusercontent.com/java-native-access/jna/5.15.0/native/libffi/LICENSE "
    "(sha256 `2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388`); its header gives "
    "the same sha256.")
CLAUDE_LOCK_ROW_U9 = "from U9, `bundle.sh` (`sbom_check.py index`) refuses a package with no entry"


def A4_RE(stage: str) -> re.Pattern[str]:
    """O-15 A4: `bundle: FAIL (stage <stage>: <why>)`, to be matched whole."""
    assert stage in STAGES, stage
    return re.compile(rf"bundle: FAIL \(stage {re.escape(stage)}: .+\)")


def _a4_lines(stderr: str, stage: str) -> list[str]:
    return [ln for ln in stderr.splitlines() if A4_RE(stage).fullmatch(ln)]


def _flat(text: str) -> str:
    return " ".join(text.split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section(text: str, heading: str) -> str:
    """The body of the `## <heading>` section, up to the next `## `."""
    m = re.search(rf"(?ms)^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)", text)
    return m.group(1) if m else ""


def _header(text: str) -> str:
    """The leading comment block of a shell script (after the shebang)."""
    lines = text.splitlines()[1:]
    out = []
    for ln in lines:
        if not ln.startswith("#"):
            break
        out.append(ln[1:].strip())
    return " ".join(out)


def _code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def _manifest(out: Path) -> dict[str, str]:
    listed: dict[str, str] = {}
    for line in (out / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        digest, _, rel = line.partition("  ")
        listed[rel] = digest
    return listed


def _subcommand(argv: list[str]) -> str | None:
    at = [i for i, a in enumerate(argv) if a.replace("\\", "/").rsplit("/", 1)[-1] == "sbom_check.py"]
    return argv[at[-1] + 1] if at and at[-1] + 1 < len(argv) else None


def _run_check(*args: str) -> subprocess.CompletedProcess:
    import sys
    return subprocess.run([sys.executable, "-I", str(CHECK), *args], capture_output=True, text=True, timeout=120)


def _snapshot(directory: Path) -> dict[str, Any]:
    """Every entry under `directory`: kind, mode and, for a file, its bytes."""
    out: dict[str, Any] = {}
    for p in sorted(directory.rglob("*")):
        st = os.lstat(p)
        rel = p.relative_to(directory).as_posix()
        if stat.S_ISLNK(st.st_mode):
            out[rel] = ("link", os.readlink(p))
        elif stat.S_ISREG(st.st_mode):
            out[rel] = ("file", stat.S_IMODE(st.st_mode), p.read_bytes())
        else:
            out[rel] = ("dir", stat.S_IMODE(st.st_mode))
    return out


class _SourcesBase(_BundleBase, unittest.TestCase):
    """bundle.sh with `--sources` (fake docker), plus the helpers the U9b rows share."""

    # ---- the plan -------------------------------------------------------
    def _plan(self, which: str = "full", arch: str = "amd64") -> list[tuple[str, dict[str, Any]]]:
        from tests.test_sources_fetch import plan_of
        return plan_of(self.src_lock, arch, which)

    def _distinct(self, which: str = "full", arch: str = "amd64") -> dict[str, int]:
        return {f["sha256"]: f["size"] for _, f in self._plan(which, arch)}

    # ---- calls ------------------------------------------------------------
    @staticmethod
    def _writes(calls: list[list[str]]) -> list[list[str]]:
        return [c for c in calls if c[:1] in (["tag"], ["save"]) or c[:2] in (["image", "tag"], ["image", "save"])]

    @staticmethod
    def _checker_runs(calls: list[list[str]], sub: str) -> list[int]:
        return [i for i, c in enumerate(calls) if c[:1] == ["run"] and _subcommand(c) == sub]

    def _record(self, out: Path) -> Path:
        return out.parent / f"{out.name}.manifest.sha256"

    def _assert_info_only(self, calls: list[list[str]], what: str) -> None:
        """O-15 A3: before an item-2 shell refusal, no docker call but `info`."""
        self.assertEqual([c for c in calls if c[:1] != ["info"]], [],
                         f"a docker call other than `info` ran before {what} (O-15 A3)")

    def _assert_a4(self, result: subprocess.CompletedProcess, stage: str) -> None:
        self.assertTrue(_a4_lines(result.stderr, stage),
                        f"no `bundle: FAIL (stage {stage}: <why>)` line (O-15 A4):\n{result.stderr[-2000:]}")

    def _assert_refused_untouched(self, result: subprocess.CompletedProcess, calls: list[list[str]], out: Path,
                                  *names: str, code: int = 1, out_existed: bool = False,
                                  stage: str = "sources-check", info_only: bool = False) -> None:
        """A refusal before the first write: exit `code`, one `bundle:` line,
        `names` in the output, no tag or save, --out as it was, no record.
        U9b rework 1 (O-15 A3/A4, O-16 (5)): at exit 1 the line is
        `bundle: FAIL (stage <stage>: ...)`; `info_only` (the item-2 shell
        refusals) also asserts that every recorded docker call is `info`."""
        text = self._out(result)
        self.assertEqual(result.returncode, code, text[-3000:])
        if code == 1:
            self.assertTrue([ln for ln in result.stderr.splitlines() if ln.startswith("bundle: ")],
                            f"no `bundle:` line names the refusal:\n{result.stderr[-2000:]}")
            self._assert_a4(result, stage)
        if info_only:
            self._assert_info_only(calls, "the --sources shell refusal")
        for name in names:
            self.assertIn(name, text, f"the refusal does not name {name!r}")
        self.assertEqual(self._writes(calls), [], "a tag or save ran before the refusal (U9-2: before any write)")
        if out_existed:
            self.assertTrue(out.is_dir() and not any(out.iterdir()), "--out was written to")
        else:
            self.assertFalse(out.exists(), "--out was created before the refusal (item 2: only at the first write)")
        self.assertFalse(self._record(out).exists(), "a release record was written")
        self.assertNotIn("bundle written", result.stdout)

    def _assert_no_partial_bundle(self, result: subprocess.CompletedProcess, out: Path, *, given: bool,
                                  stage: str, a4: str | None = None) -> None:
        """U9-10 and O-10: non-zero, a `bundle:` line matching `stage`, no
        manifest, no record, no `bundle written`, and the run's output removed
        (the directory if the run created it, its contents if it was given).
        U9b rework 1 (O-15 A4, O-16 (5)): with `a4`, that line is also
        `bundle: FAIL (stage <a4>: ...)`, matched whole."""
        text = self._out(result)
        self.assertNotEqual(result.returncode, 0, "bundle.sh passed:\n" + text[-3000:])
        named = [ln for ln in result.stderr.splitlines() if ln.startswith("bundle: ") and re.search(stage, ln)]
        self.assertTrue(named, f"no `bundle:` line matching {stage!r} names the failing stage:\n{result.stderr[-2500:]}")
        if a4 is not None:
            self.assertTrue([ln for ln in named if A4_RE(a4).fullmatch(ln)],
                            f"the line naming the failure is not `bundle: FAIL (stage {a4}: <why>)` (O-15 A4): "
                            f"{named}")
        self.assertNotIn("bundle written", result.stdout)
        self.assertFalse(self._record(out).exists(), "a release record was written")
        if given:
            self.assertTrue(out.is_dir(), "the given --out was removed (O-10: only its contents go)")
            self.assertEqual(sorted(os.listdir(out)), [], "the given --out was not emptied after the failure (O-10)")
        else:
            self.assertFalse(out.exists(), "--out, created by this run, was left after the failure (O-10)")
        left = [p.name for p in out.parent.iterdir() if p.name.startswith(".ke-sbom.")]
        self.assertEqual(left, [], "the SBOM work dir was left beside --out")

    def _ok_bundle(self, **kw: Any) -> tuple[subprocess.CompletedProcess, list[list[str]], Path]:
        result, calls, out = self._bundle(**kw)
        self.assertEqual(result.returncode, 0, "bundle.sh failed on a fit build host with a fetched set:\n"
                         + self._out(result)[-4000:])
        return result, calls, out

    def _sbom_args(self, out: Path) -> list[str]:
        data = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        args: list[str] = []
        for e in data["images"]:
            name = Path(e["file"]).stem
            args += ["--sbom", f"{name}={out / 'app' / 'sboms' / f'{name}.spdx.json'}"]
        return args


# --------------------------------------------------------------------------
# Item 2 / U9-1: the command line
# --------------------------------------------------------------------------

class BundleSourcesCommandLineTest(_SourcesBase):

    def _usage(self, result: subprocess.CompletedProcess, calls: list[list[str]], out: Path) -> None:
        self.assertEqual(result.returncode, 2, self._out(result)[-2000:])
        self.assertRegex(result.stderr, USAGE_RE, "the usage line must name --sources and --sources-set (U9-1)")
        self.assertEqual(calls, [], "a docker call ran before the argument check (U9-1: before any docker call)")
        self.assertFalse(out.exists(), "--out was created")
        self.assertFalse(self._record(out).exists())

    def test_bundle_requires_sources(self):
        """Q78 option 1 (U9-1 amended): `--sources` absent, without a value,
        empty (O-15 A8) or repeated exits 2 with the usage line, before any
        docker call or write."""
        d = self._fetched()
        cases: dict[str, dict[str, Any]] = {
            "--sources absent": {"sources": None},
            "--sources without a value": {"sources": None, "tail": ("--sources",)},
            "--sources empty (O-15 A8)": {"sources": ""},
            "--sources repeated": {"sources": None, "args": ("--sources", str(d), "--sources", str(d))},
        }
        for case, kw in cases.items():
            with self.subTest(case=case):
                result, calls, out = self._bundle(**kw)
                self._usage(result, calls, out)

    def test_bundle_refuses_a_bad_sources_set(self):
        """U9-1: `--sources-set` with no value, a value other than `full` or
        `sample`, or repeated exits 2 with the usage line, before any docker
        call or write."""
        d = str(self._fetched())
        cases: dict[str, dict[str, Any]] = {
            "--sources-set without a value": {"sources": d, "tail": ("--sources-set",)},
            "--sources-set partial": {"sources": d, "args": ("--sources-set", "partial")},
            "--sources-set FULL": {"sources": d, "args": ("--sources-set", "FULL")},
            "--sources-set empty": {"sources": d, "args": ("--sources-set", "")},
            "--sources-set repeated": {"sources": d, "args": ("--sources-set", "full", "--sources-set", "full")},
        }
        for case, kw in cases.items():
            with self.subTest(case=case):
                result, calls, out = self._bundle(**kw)
                self._usage(result, calls, out)

    def test_bundle_sources_set_defaults_to_full(self):
        """U9-1: the expected set is `full` unless `--sources-set sample` is
        given; a set that differs from the record's is refused before any
        write (U9-3), naming both."""
        with self.subTest(case="no --sources-set, a full fetch: bundled as full"):
            _, _, out = self._ok_bundle()
            index = json.loads((out / "app" / "sources" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index.get("set"), "full")
        with self.subTest(case="--sources-set full, a full fetch"):
            self._ok_bundle(sources_set="full")
        with self.subTest(case="no --sources-set, a sample fetch: refused"):
            result, calls, out = self._bundle(sources=self._fetched("amd64", "sample"))
            self._assert_refused_untouched(result, calls, out, "fetch.json: set is sample, this bundle needs full")
        with self.subTest(case="--sources-set sample, a full fetch: refused"):
            result, calls, out = self._bundle(sources=self._fetched("amd64", "full"), args=("--sources-set", "sample"))
            self._assert_refused_untouched(result, calls, out, "fetch.json: set is full, this bundle needs sample")


# --------------------------------------------------------------------------
# Items 2-3 / U9-2, U9-3: refusals before any write
# --------------------------------------------------------------------------

class BundleSourcesRefusalTest(_SourcesBase):

    def _copy_fetched(self, name: str, which: str = "full") -> Path:
        d = self.tmp / name
        shutil.copytree(self._fetched("amd64", which), d)
        return d

    def test_bundle_refuses_a_bad_sources_dir(self):
        """U9-2 and design item 2 (shell checks) and item 3 e (the listing, in
        `sources-check`): each shape is refused with exit 1 and one `bundle:`
        line naming it, before any tag, save or write; --out and the record
        stay as they were, and --sources is unchanged."""
        good = self._fetched()
        planned = sorted(self._distinct())
        absent = self.tmp / "no-such-fetch"
        link = self.tmp / "linked-fetch"
        link.symlink_to(good, target_is_directory=True)
        afile = self.tmp / "a-file"
        afile.write_text("not a directory\n", encoding="utf-8")
        no_record = self._copy_fetched("no-record")
        (no_record / "fetch.json").unlink()
        record_dir = self._copy_fetched("record-dir")
        (record_dir / "fetch.json").unlink()
        (record_dir / "fetch.json").mkdir()
        record_link = self._copy_fetched("record-link")
        outside = self.tmp / "outside-record.json"
        shutil.copyfile(record_link / "fetch.json", outside)
        (record_link / "fetch.json").unlink()
        (record_link / "fetch.json").symlink_to(outside)
        part = self._copy_fetched("with-part")
        (part / f"{planned[0]}.part").write_bytes(b"partial\n")
        flipped = self._copy_fetched("flipped")
        data = bytearray((flipped / planned[0]).read_bytes())
        data[0] ^= 0x01
        (flipped / planned[0]).write_bytes(bytes(data))
        missing = self._copy_fetched("missing-file")
        (missing / planned[-1]).unlink()
        cases: dict[str, tuple[Path, tuple[str, ...]]] = {
            "absent": (absent, (str(absent),)),
            "a symlink to a good fetch": (link, (str(link),)),
            "not a directory": (afile, (str(afile),)),
            "no fetch.json": (no_record, ("fetch.json", "scripts/bundle_fetch.sh")),
            "fetch.json is a directory": (record_dir, ("fetch.json",)),
            "fetch.json is a symlink": (record_link, ("fetch.json",)),
            "a .part file beside the planned files": (part, (f"{planned[0]}.part",)),
            "a planned file with one byte flipped": (flipped, (planned[0],)),
            "a planned file missing": (missing, (planned[-1],)),
        }
        # O-15 A3: the item-2 shell refusals; the other three are the container's sources-check.
        shell = {"absent", "a symlink to a good fetch", "not a directory", "no fetch.json", "fetch.json is a directory",
                 "fetch.json is a symlink"}
        for case, (src, names) in cases.items():
            with self.subTest(case=case):
                before = _snapshot(src) if src.is_dir() and not src.is_symlink() else None
                result, calls, out = self._bundle(sources=src)
                self._assert_refused_untouched(result, calls, out, *names, info_only=case in shell)
                if before is not None:
                    self.assertEqual(_snapshot(src), before, "--sources changed (U9-1)")

    def test_bundle_refuses_an_unlistable_sources_dir(self):
        """U9-10 *N-9*: "the same rule holds for every listing bundle.sh makes
        of --sources": a --sources it cannot list (mode 0300) is refused before
        any write, never read as empty."""
        if not hasattr(os, "geteuid"):
            self.skipTest("mode bits on a directory need POSIX (the gates image runs this row)")
        if os.geteuid() == 0:
            self.skipTest("uid 0 lists any directory whatever its mode (the gates image runs as uid 10001)")
        d = self.tmp / "unlistable-fetch"
        shutil.copytree(self._fetched(), d)
        os.chmod(d, 0o300)
        self.addCleanup(os.chmod, d, 0o700)
        result, calls, out = self._bundle(sources=d)
        mode = stat.S_IMODE(d.stat().st_mode)
        os.chmod(d, 0o700)
        self._assert_refused_untouched(result, calls, out, str(d), info_only=True)
        self.assertEqual(mode, 0o300, "--sources' mode was changed")
        self.assertEqual(_snapshot(d), _snapshot(self._fetched()), "--sources changed")

    def test_bundle_refuses_a_mismatched_fetch_record(self):
        """U9-3 at the bundle: a record for another arch, or made before a
        re-lock, is refused by `sources-check` before any write, naming the
        field and both values."""
        with self.subTest(case="arch: an arm64 fetch on an amd64 daemon"):
            result, calls, out = self._bundle(sources=self._fetched("arm64", "full"))
            self._assert_refused_untouched(result, calls, out, "fetch.json", "arch", "arm64")
        with self.subTest(case="lock_sha256: a fetch made before a re-lock"):
            # The re-lock changes one sdist's bytes (and so the lock text); the old fetch stays.
            from tests.test_sources_fetch import blob
            old = self.tmp / "fetched-before-relock"
            shutil.copytree(self._fetched(), old)
            lock = self.repo / "docker" / "sources.lock.json"
            key = next(k for k in _default_source_keys() if k.startswith("pypi:psycopg-c@"))
            b2 = _synthetic_lock(_default_source_keys())
            f = b2.components[key]["files"][0]
            del b2.bodies[f["url"]]
            data = blob("psycopg-c sdist, relocked", f["size"] + 7)
            f.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
            f["upstream"]["value"] = f["sha256"]
            b2.bodies[f["url"]] = data
            self._relock(b2)
            new_sha = hashlib.sha256(lock.read_bytes()).hexdigest()
            result, calls, out = self._bundle(sources=old)
            self._assert_refused_untouched(result, calls, out, "lock_sha256", new_sha,
                                           "fetch again after the re-lock")

    def test_bundle_refuses_sources_overlapping_out(self):
        """Design item 2: `--sources` equal to, inside or containing `--out`
        is refused before any write, so no write can land under --sources
        (U9-1)."""
        holder = self.tmp / "holder"
        holder.mkdir()
        src_named_out = holder / "bundle-amd64"
        _write_fetched(src_named_out, self.src_lock, "full", "amd64")
        nested_out = self.tmp / "nested-out" / "bundle-amd64"
        nested_out.mkdir(parents=True)
        inner_src = nested_out / "fetch"
        _write_fetched(inner_src, self.src_lock, "full", "amd64")
        good = self._fetched()
        cases: dict[str, tuple[Path, Path, bool]] = {
            "--out inside --sources (absent)": (good, good / "bundle-amd64", False),
            "--out equal to --sources": (src_named_out, src_named_out, True),
            "--sources inside --out": (inner_src, nested_out, True),
        }
        for case, (src, out, exists) in cases.items():
            with self.subTest(case=case):
                before = _snapshot(src)
                out_before = _snapshot(out) if exists else None
                result, calls, out = self._bundle(out, sources=src)
                text = self._out(result)
                self.assertEqual(result.returncode, 1, text[-2000:])
                self.assertTrue([ln for ln in result.stderr.splitlines() if ln.startswith("bundle: ")], text[-2000:])
                if not exists:
                    # O-15 A4 where the overlap check refuses; an existing --out is refused first by the
                    # pre-U9 "--out is not empty" check, whose `die` text O-16 (6) keeps.
                    self._assert_a4(result, "sources-check")
                self._assert_info_only(calls, "the overlap refusal")
                self.assertEqual(self._writes(calls), [], "a tag or save ran")
                self.assertEqual(_snapshot(src), before, "--sources changed (U9-1)")
                if exists:
                    self.assertEqual(_snapshot(out), out_before, "--out changed")
                else:
                    self.assertFalse(out.exists(), "--out was created inside --sources")
                self.assertFalse(self._record(out).exists())

    def test_bundle_refuses_an_empty_sources_check_listing(self):
        """O-16 (7), reviewer N-5 (U9b rework-1 review N-1; O-17 (1) asks
        the row): a `sources-check` run that exits 0 and prints nothing is
        refused as `bundle: FAIL (stage sources-check: ...)` saying the check
        listed no source file, before the first write: no tag or save, no
        copy, --out never created, no record."""
        hooks = [{"on": r"sbom_check\.py sources-check", "exit": 0}]
        result, calls, out = self._bundle(FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertEqual(len(self._checker_runs(calls, "sources-check")), 1, "precondition: the check ran once")
        self._assert_refused_untouched(result, calls, out, stage="sources-check")
        named = [ln for ln in _a4_lines(result.stderr, "sources-check")
                 if re.search(r"\bno source file\b|\blisted nothing\b|\bempty\b", ln)]
        self.assertTrue(named, "the empty check output is not refused as `bundle: FAIL (stage sources-check: ...)` "
                        f"saying no source file was listed (O-16 (7), N-5):\n{result.stderr[-2000:]}")


# --------------------------------------------------------------------------
# O-16 (1), (2) / reviewer B-1, security L-4, I-8..I-10: the path rule and
# the claim of --out
# --------------------------------------------------------------------------

class BundleSourcesPathRuleTest(_SourcesBase):

    def _assert_path_refused(self, result: subprocess.CompletedProcess, calls: list[list[str]], stage: str, *,
                             absent: tuple[Path, ...] = (), watched: dict[Path, Any] | None = None) -> None:
        """O-16 (1): exit 1, a `bundle: FAIL (stage <stage>: ...)` line, no
        docker call but `info` (the path is refused before any check runs),
        each `absent` path never created, each watched tree unchanged."""
        text = self._out(result)
        self.assertEqual(result.returncode, 1, text[-2500:])
        self._assert_a4(result, stage)
        self._assert_info_only(calls, "the path refusal (O-16 (1): before any check runs)")
        for path in absent:
            self.assertFalse(os.path.lexists(path), f"{path} was created")
        for path, before in (watched or {}).items():
            self.assertEqual(_snapshot(path), before, f"{path} changed")
        self.assertNotIn("bundle written", result.stdout)

    def test_bundle_refuses_an_out_path_with_a_dot_dot_dot_or_empty_segment(self):
        """O-16 (1), reviewer B-1, security L-4: an --out holding a `..`, `.`
        or empty segment is refused as `stage out` before any check runs (no
        docker call but `info`), never resolved: nothing is created, the
        directory it would reach (--sources, an earlier bundle) is unchanged
        and no record is written beside it."""
        t = self.tmp.as_posix()
        src = self.tmp / "dotdot-src"
        shutil.copytree(self._fetched(), src)
        earlier = self.tmp / "earlier-amd64"
        earlier.mkdir()
        (earlier / "keep.txt").write_text("an earlier bundle\n", encoding="utf-8")
        holders = [self.tmp / f"seg-holder-{i}" for i in range(3)]
        for h in holders:
            (h / "x").mkdir(parents=True)
        good = self._fetched()
        cases: dict[str, tuple[str, Path, tuple[Path, ...]]] = {
            "`<missing>/../<--sources>/x-amd64` (lands in --sources)": (
                f"{t}/missing-a/../dotdot-src/x-amd64", src, (self.tmp / "missing-a", src / "x-amd64")),
            "`<missing>/../<existing non-empty>-amd64` (an earlier bundle)": (
                f"{t}/missing-b/../earlier-amd64", good,
                (self.tmp / "missing-b", self.tmp / "earlier-amd64.manifest.sha256")),
            "`<existing>/x/../bundle-amd64` (a `..` after an existing directory)": (
                f"{holders[0].as_posix()}/x/../bundle-amd64", good, (holders[0] / "bundle-amd64",)),
            "`<existing>/./bundle-amd64` (a `.` segment)": (
                f"{holders[1].as_posix()}/./bundle-amd64", good, (holders[1] / "bundle-amd64",)),
            "`<existing>//bundle-amd64` (an empty segment)": (
                f"{holders[2].as_posix()}//bundle-amd64", good, (holders[2] / "bundle-amd64",)),
        }
        for case, (raw, sources, absent) in cases.items():
            with self.subTest(case=case):
                watched = {sources: _snapshot(sources), earlier: _snapshot(earlier)}
                result, calls, _ = self._bundle(raw_out=raw, sources=sources)
                self._assert_path_refused(result, calls, "out", absent=absent, watched=watched)

    def test_bundle_refuses_a_sources_path_with_a_dot_dot_dot_or_empty_segment(self):
        """O-16 (1), reviewer B-1: a --sources holding a `..`, `.` or empty
        segment is refused as `stage sources-check` before any check runs (no
        docker call but `info`), even where it would resolve to a good fetch;
        --out is never created. `--sources //` (empty once every trailing
        slash goes) is refused, exit 1 or 2 (not ruled), with no docker call
        but `info`. U9b rework 2 (O-17 (1), reviewer rework-1 N-1): a
        trailing `..` (`<fetch copy>/sub/..`, which would resolve to the
        fetch) is refused the same way."""
        good = self._fetched()
        holder = self.tmp / "src-holder"
        holder.mkdir()
        t = self.tmp.as_posix()
        cases = {
            "`<existing>/../<fetch>` (a `..` segment)": f"{holder.as_posix()}/../{good.name}",
            "`<parent>/./<fetch>` (a `.` segment)": f"{t}/./{good.name}",
            "`<parent>//<fetch>` (an empty segment)": f"{t}//{good.name}",
            "`<fetch>/.` (a trailing `.` segment)": f"{good.as_posix()}/.",
        }
        for case, raw in cases.items():
            with self.subTest(case=case):
                before = _snapshot(good)
                result, calls, out = self._bundle(sources=raw)
                self._assert_path_refused(result, calls, "sources-check", absent=(out, self._record(out)),
                                          watched={good: before})
        with self.subTest(case="`//`"):
            result, calls, out = self._bundle(sources="//")
            self.assertIn(result.returncode, (1, 2), self._out(result)[-2500:])
            self._assert_info_only(calls, "the refusal of `--sources //`")
            self.assertFalse(out.exists(), "--out was created")
            self.assertFalse(self._record(out).exists(), "a release record was written")
        trailing = self.tmp / "dotdot-trailing-fetch"
        shutil.copytree(good, trailing)
        (trailing / "sub").mkdir()
        with self.subTest(case="`<fetch copy>/sub/..` (a trailing `..` segment)"):
            before = _snapshot(trailing)
            result, calls, out = self._bundle(sources=f"{trailing.as_posix()}/sub/..")
            self._assert_path_refused(result, calls, "sources-check", absent=(out, self._record(out)),
                                      watched={trailing: before})

    def test_bundle_refuses_a_symlinked_sources_given_with_trailing_slashes_or_a_dot(self):
        """O-16 (1), reviewer B-1, security I-9: `--sources <link>//`,
        `<link>///` and `<link>/.` (a link to a good fetch) are refused as
        `stage sources-check` with no docker call but `info`: every trailing
        slash is stripped before the link test, and a `.` segment is
        refused."""
        if os.name == "nt":
            self.skipTest(SYMLINK_SKIP)
        good = self._fetched()
        link = self.tmp / "linked-fetch-r1"
        link.symlink_to(good, target_is_directory=True)
        cases = {"`<link>//`": f"{link.as_posix()}//", "`<link>///`": f"{link.as_posix()}///",
                 "`<link>/.`": f"{link.as_posix()}/."}
        for case, raw in cases.items():
            with self.subTest(case=case):
                before = _snapshot(good)
                result, calls, out = self._bundle(sources=raw)
                self._assert_path_refused(result, calls, "sources-check", absent=(out, self._record(out)),
                                          watched={good: before})

    def test_bundle_refuses_an_out_under_a_link_into_sources(self):
        """Reviewer B-1 (pins `cd -P` in the overlap check): --out under a
        symlink whose target is --sources is inside --sources once links are
        resolved, and is refused as `stage sources-check` with no docker call
        but `info`; --sources gets no write."""
        if os.name == "nt":
            self.skipTest(SYMLINK_SKIP)
        good = self._fetched()
        alias = self.tmp / "alias-into-fetch"
        alias.symlink_to(good, target_is_directory=True)
        before = _snapshot(good)
        result, calls, _ = self._bundle(alias / "bundle-amd64", sources=good)
        self._assert_path_refused(result, calls, "sources-check", absent=(good / "bundle-amd64",),
                                  watched={good: before})

    def test_bundle_overlap_check_is_segment_wise(self):
        """Reviewer B-1 control (pins the trailing `/` of both overlap
        patterns): a name that is only a string prefix of the other is no
        overlap. --out `<t>/fetch2/bundle-amd64` beside --sources `<t>/fetch`,
        and --sources `<t>/bundle-amd64-fetch` beside --out
        `<t>/bundle-amd64`, both bundle."""
        base = self.tmp / "segwise"
        fetch = base / "fetch"
        shutil.copytree(self._fetched(), fetch)
        with self.subTest(case="--out `<t>/fetch2/bundle-amd64`, --sources `<t>/fetch`"):
            self._ok_bundle(out=base / "fetch2" / "bundle-amd64", sources=fetch)
        with self.subTest(case="--out `<t>/bundle-amd64`, --sources `<t>/bundle-amd64-fetch`"):
            src2 = base / "bundle-amd64-fetch"
            shutil.copytree(self._fetched(), src2)
            self._ok_bundle(out=base / "bundle-amd64", sources=src2)

    def test_bundle_strips_every_trailing_slash(self):
        """O-16 (1), security I-8/I-9: every trailing slash of --out and
        --sources is stripped: `--out <dir>//` with `--sources <fetch>//`
        bundles into <dir>, prints `bundle written: <dir>`, writes the record
        beside <dir> naming `<name>/MANIFEST.sha256`, and binds --sources into
        sources-check by its stripped path."""
        good = self._fetched()
        parent = self.tmp / "slashes"
        parent.mkdir()
        out = parent / "bundle-amd64"
        result, calls, _ = self._bundle(raw_out=f"{out.as_posix()}//", sources=f"{good.as_posix()}//")
        self.assertEqual(result.returncode, 0, self._out(result)[-3000:])
        self.assertTrue((out / "MANIFEST.sha256").is_file(), "no bundle at --out with its trailing slashes stripped")
        self.assertIn(f"bundle written: {out.as_posix()}", result.stdout.splitlines())
        record = parent / "bundle-amd64.manifest.sha256"
        self.assertTrue(record.is_file(), "the release record is not beside --out")
        self.assertRegex(record.read_text(encoding="utf-8"), r"\A[0-9a-f]{64}  bundle-amd64/MANIFEST\.sha256\n\Z")
        self.assertFalse(os.path.lexists(out / ".manifest.sha256"), "the record was written inside --out")
        checks = self._checker_runs(calls, "sources-check")
        self.assertEqual(len(checks), 1)
        argv = calls[checks[0]]
        mounts = [b for a, b in zip(argv, argv[1:]) if a in ("-v", "--volume") and b.endswith(":/sources:ro")]
        self.assertEqual(mounts, [f"{good.as_posix()}:/sources:ro"],
                         "--sources is not bound by its path with every trailing slash stripped")

    def test_bundle_refuses_an_out_whose_parent_is_missing(self):
        """O-16 (2), reviewer N-3, security L-4 fix 2 and I-10: --out is
        claimed with a plain `mkdir` (never `-p`) at the first write, so an
        --out whose parent does not exist is refused as `stage out`, exit 1,
        with nothing written: no tag or save, no ancestor created, no record,
        no SBOM work dir."""
        t = self.tmp.as_posix()
        cases = {
            "one missing parent": (f"{t}/no-parent/bundle-amd64", self.tmp / "no-parent"),
            "two missing ancestors": (f"{t}/no-anc/deeper/bundle-amd64", self.tmp / "no-anc"),
        }
        for case, (raw, top) in cases.items():
            with self.subTest(case=case):
                result, calls, out = self._bundle(raw_out=raw)
                self.assertEqual(result.returncode, 1, self._out(result)[-2500:])
                self._assert_a4(result, "out")
                self.assertEqual(self._writes(calls), [], "a tag or save ran")
                self.assertFalse(os.path.lexists(top), f"{top} was created (O-16 (2): a plain mkdir, never -p)")
                self.assertNotIn("bundle written", result.stdout)
                self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".ke-sbom.")], [])


# --------------------------------------------------------------------------
# Item 2: stage order and the hardened runs in ke-app
# --------------------------------------------------------------------------

class BundleSourcesStagesTest(_SourcesBase):

    def test_bundle_checks_sources_in_ke_app_before_the_first_write(self):
        """Design items 2, 3, 5 and 7: `sources-check` runs in the ke-app
        image (no network, read-only, no capabilities, the caller's uid:gid,
        its own label, --pull never, every mount :ro, --sources bound) before
        the first tag or save, while --out does not exist yet; `index` runs
        after every `finish` and `notices` after `index`, hardened the same."""
        from tests.test_sbom_bundle import finish_run_problems
        probe = self.tmp / "out-at-check.jsonl"
        out = self.tmp / f"stages{self.n + 1}" / "bundle-amd64"
        out.parent.mkdir(parents=True)
        hooks = [{"on": r"sbom_check\.py sources-check", "list": [str(out.parent), str(probe), out.name]}]
        from tests.test_sbom_bundle import PROJECT
        result, calls, out = self._ok_bundle(out=out, FAKE_DOCKER_HOOKS=json.dumps(hooks), COMPOSE_PROJECT_NAME=PROJECT)
        checks = self._checker_runs(calls, "sources-check")
        indexes = self._checker_runs(calls, "index")
        notices = self._checker_runs(calls, "notices")
        finishes = self._checker_runs(calls, "finish")
        writes = [i for i, c in enumerate(calls) if c in self._writes(calls)]
        self.assertEqual((len(checks), len(indexes), len(notices)), (1, 1, 1),
                         "one sources-check, one index and one notices run")
        self.assertTrue(writes and checks[0] < min(writes), "sources-check ran after the first tag or save")
        self.assertTrue(finishes and indexes[0] > max(finishes), "index ran before every SBOM was finished")
        self.assertGreater(notices[0], indexes[0], "notices ran before index")
        seen = probe.read_text(encoding="utf-8").splitlines() if probe.exists() else []
        self.assertEqual([json.loads(ln) for ln in seen], [[]],
                         "--out existed when sources-check ran (item 2: created only at the first write)")
        user = subprocess.run(["bash", "-c", 'printf "%s:%s" "$(id -u)" "$(id -g)"'],
                              capture_output=True, text=True, check=True).stdout
        sources = self._fetched()
        for sub, at in (("sources-check", checks[0]), ("index", indexes[0]), ("notices", notices[0])):
            argv = calls[at]
            with self.subTest(run=sub):
                app_refs = {r for r in self.stack.values() if r.split("@")[0].rsplit(":", 1)[0].endswith("ke-app")}
                problems = [p for p in finish_run_problems(argv, app_refs | {f"ke-app:bundle-{self.sha[:12]}"},
                                                            self.repo)
                            if "subcommand" not in p]
                self.assertEqual(problems, [], f"{sub}: {argv}")
                pairs = set(zip(argv, argv[1:]))
                self.assertIn(("--user", user), pairs, f"{sub} does not run as the caller's uid:gid")
        argv = calls[checks[0]]
        mounts = [b for a, b in zip(argv, argv[1:]) if a in ("-v", "--volume")]
        bound = [m for m in mounts if os.path.realpath(m.rsplit(":", 2)[0]) == os.path.realpath(sources)]
        self.assertEqual(len(bound), 1, f"--sources is not bound (read-only) into sources-check: {mounts}")
        self.assertTrue(bound[0].endswith(":ro"), bound[0])
        pairs = set(zip(argv, argv[1:]))
        self.assertIn(("--set", "full"), pairs)
        self.assertIn(("--arch", "amd64"), pairs)

    def test_bundle_prints_the_sources_marker(self):
        """U9-13 and design item 12 with O-15 A2: one line naming `sources:`
        with the seconds of the check, copy, index and notices stages, and it
        is exactly `bundle: sources: check <a> s, copy <b> s, index <c> s,
        notices <d> s`."""
        result, _, _ = self._ok_bundle()
        lines = MARKER_LOOSE_RE.findall(self._out(result))
        self.assertEqual(len(lines), 1, f"want one source-stage marker line, got {lines}")
        self.assertTrue(MARKER_RE.fullmatch(lines[0]),
                        f"the marker is not O-15 A2's form `bundle: sources: check <a> s, copy <b> s, index <c> s, "
                        f"notices <d> s`: {lines[0]!r}")

    def test_bundle_prints_the_exempt_listing(self):
        """U9-5 and design item 6 with O-13 (7): an exempt component's line
        `index: <image>: <package>: <listing>` reaches the bundle output, and
        the index lists the component as `exempt` (synthetic policy)."""
        psycopg = next(k for k in _default_source_keys() if k.startswith("pypi:psycopg@"))
        purl = "pkg:pypi/psycopg@" + psycopg.rsplit("@", 1)[1]
        entry = {"image": "ke-app", "package": purl, "reason": "synthetic exemption for the U9b listing row",
                 "reviewed": REVIEWED}
        self._relock(_synthetic_lock(set(_default_source_keys()) - {psycopg}), _synthetic_policy(exempt=[entry]))
        result, _, out = self._ok_bundle()
        self.assertIn(f"index: ke-app: {purl}: exempt, reviewed {REVIEWED}", result.stderr.splitlines(),
                      "the exempt listing line did not reach the bundle output")
        index = json.loads((out / "app" / "sources" / "index.json").read_text(encoding="utf-8"))
        exempt = [c for c in index["components"] if c.get("status") == "exempt"]
        self.assertEqual([c["exempt"]["package"] for c in exempt], [purl])


# --------------------------------------------------------------------------
# Item 4 / U9-6: the content-addressed copy
# --------------------------------------------------------------------------

class BundleSourcesCopyTest(_SourcesBase):

    def _assert_copy(self, out: Path, which: str) -> None:
        sources = out / "app" / "sources"
        self.assertEqual(sorted(os.listdir(sources)), ["files", "index.json"],
                         "app/sources/ holds exactly index.json and files/ (U9-6)")
        want = self._distinct(which)
        files = sources / "files"
        self.assertEqual(sorted(os.listdir(files)), sorted(want),
                         f"app/sources/files/ holds one file per distinct {which} sha256, nothing else")
        src_dir = self._fetched("amd64", which)
        for sha, size in want.items():
            with self.subTest(set=which, file=sha[:12]):
                p = files / sha
                st = os.lstat(p)
                self.assertTrue(stat.S_ISREG(st.st_mode), "not a regular file (cp -P, item 4)")
                self.assertEqual(st.st_nlink, 1, "a hard link (item 4: never -l)")
                src = os.lstat(src_dir / sha)
                self.assertNotEqual((st.st_dev, st.st_ino), (src.st_dev, src.st_ino), "the same inode as --sources")
                self.assertEqual(st.st_size, size)
                self.assertEqual(_sha256(p), sha, "the shipped bytes do not hash to the name")
        self.assertEqual([_rel(p, out) for p in (out / "app").rglob("fetch.json")], [],
                         "fetch.json is shipped (item 4: index.json replaces it)")
        self.assertEqual([_rel(p, out) for p in out.rglob("*") if p.name == "fetch.json"], [])

    def test_sources_are_copied_not_linked(self):
        """U9-6, design item 4: one regular file per distinct sha256 a shipped
        component names, copied (never linked) from --sources, named by its
        sha256; no fetch.json, no upstream name on disk."""
        plan = self._plan("full")
        self.assertGreater(len(plan), len(self._distinct("full")),
                           f"precondition: two planned files share one sha256 ({SHARED_SOURCE})")
        _, _, out = self._ok_bundle()
        self._assert_copy(out, "full")
        names = {f["name"] for _, f in plan}
        self.assertEqual(sorted(p.name for p in out.rglob("*") if p.name in names), [],
                         "an upstream file name is on disk in the bundle")

    def test_sample_bundle_ships_exactly_the_sample(self):
        """U9-5, U9-6 (bundle level): with `--sources-set sample`, files/ is
        exactly the sample's distinct sha256 set and the index says sample."""
        self.assertLess(len(self._distinct("sample")), len(self._distinct("full")), "precondition")
        _, _, out = self._ok_bundle(sources_set="sample")
        self._assert_copy(out, "sample")
        index = json.loads((out / "app" / "sources" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index.get("set"), "sample")
        from tests.test_sbom_bundle import load_sbom_check
        sample = set(load_sbom_check().sample_keys(self.src_lock.lock(), "amd64"))
        status = {c["key"]: c["status"] for c in index["components"] if c.get("key")}
        self.assertEqual({k for k, s in status.items() if s == "shipped"}, sample)
        self.assertTrue(all(s == "not-shipped" for k, s in status.items() if k not in sample), status)

    def test_source_archive_hashes_in_manifest(self):
        """PSC-15/24, U9-6, design item 8: every app/sources/files/<sha256>
        line of MANIFEST.sha256 carries that same sha256, their count is the
        check's list, and index.json is listed."""
        _, _, out = self._ok_bundle()
        listed = _manifest(out)
        source_lines = {rel: d for rel, d in listed.items() if rel.startswith("app/sources/files/")}
        self.assertEqual(sorted(rel.rsplit("/", 1)[1] for rel in source_lines), sorted(self._distinct()),
                         "the manifest's source lines are not the distinct planned sha256 set")
        for rel, digest in source_lines.items():
            self.assertEqual(digest, rel.rsplit("/", 1)[1], f"{rel}: the manifest's sha256 is not the name")
        self.assertIn("app/sources/index.json", listed)
        self.assertEqual(listed["app/sources/index.json"], _sha256(out / "app" / "sources" / "index.json"))

    def test_a_source_file_changed_after_the_check_is_refused(self):
        """Security I-4, closed by design item 8: a file in --sources whose
        bytes change between `sources-check` and the copy (same size) ships
        bytes that do not hash to the name; the manifest step refuses, naming
        it, and no bundle is left (O-10)."""
        src = self.tmp / "swapped-fetch"
        shutil.copytree(self._fetched(), src)
        sha = sorted(self._distinct())[0]
        size = (src / sha).stat().st_size
        changed = ("X" * size)
        self.assertEqual(len(changed.encode("utf-8")), size)
        hooks = [{"on": r"^(?:image )?tag ", "once": str(self.tmp / "swap-once"), "write": {str(src / sha): changed}}]
        result, _, out = self._bundle(sources=src, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertTrue((self.tmp / "swap-once").exists(), "precondition: the swap ran (at the first tag)")
        self._assert_no_partial_bundle(result, out, given=False, stage=re.escape(f"app/sources/files/{sha}"),
                                       a4="manifest")


# --------------------------------------------------------------------------
# Items 5 and 7 / U9-5, U9-7: the index and the notices section
# --------------------------------------------------------------------------

class BundleSourcesIndexNoticesTest(_SourcesBase):

    def _index_cli(self, out: Path, which: str) -> subprocess.CompletedProcess:
        data = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        return _run_check("index", "--lock", str(self.repo / "docker" / "sources.lock.json"),
                          "--policy", str(self.repo / "docker" / "source-policy.json"), "--arch", "amd64",
                          "--set", which, "--git-sha", data["git_sha"],
                          "--files", str(out / "app" / "sources" / "files"), *self._sbom_args(out))

    def test_index_json_is_the_checkers_index(self):
        """Design item 5: app/sources/index.json is byte-identical to
        `sbom_check.py index` over the bundle's own SBOMs, lock, policy and
        copied files (full and sample)."""
        for which in ("full", "sample"):
            with self.subTest(set=which):
                _, _, out = self._ok_bundle(**({"sources_set": "sample"} if which == "sample" else {}))
                want = self._index_cli(out, which)
                self.assertEqual(want.returncode, 0, want.stderr[-2000:])
                self.assertEqual((out / "app" / "sources" / "index.json").read_text(encoding="utf-8"), want.stdout,
                                 "app/sources/index.json is not the checker's index")

    def test_third_party_notices_end_with_the_source_code_section(self):
        """U9-7, design item 7: THIRD_PARTY_NOTICES.md keeps its sections and
        ends with `sbom_check.py notices` over the shipped index, once; a full
        bundle's section has no sample banner; a sample bundle's starts with
        it, then the I-3 sentence (O-13 (4))."""
        for which in ("full", "sample"):
            with self.subTest(set=which):
                _, _, out = self._ok_bundle(**({"sources_set": "sample"} if which == "sample" else {}))
                text = (out / NOTICES).read_text(encoding="utf-8")
                section = _run_check("notices", "--index", str(out / "app" / "sources" / "index.json"))
                self.assertEqual(section.returncode, 0, section.stderr)
                self.assertEqual(text.count("## Source code"), 1, "want one `## Source code` section")
                self.assertIn(section.stdout, text, "the section is not the checker's `notices` output")
                self.assertEqual(text[text.index(section.stdout) + len(section.stdout):].strip(), "",
                                 "the Source code section is not the last part of THIRD_PARTY_NOTICES.md")
                for heading in ("## Python packages in the ke-app image", "## Stack images"):
                    self.assertIn(heading, text, "an earlier section was lost")
                    self.assertLess(text.index(heading), text.index("## Source code"))
                body = [ln for ln in _section(text, "Source code").splitlines() if ln.strip()]
                if which == "sample":
                    self.assertEqual(body[:2], [BANNER, I3])
                else:
                    self.assertNotIn(BANNER, text)
                    self.assertEqual(body[:1], [I3])


# --------------------------------------------------------------------------
# Item 9 / U9-10, O-10, N-9: no partial bundle
# --------------------------------------------------------------------------

class BundleSourcesNoPartialTest(_SourcesBase):

    def _out_for(self, given: bool) -> Path:
        out = self.tmp / f"late{self.n + 1}-{'given' if given else 'created'}" / "bundle-amd64"
        out.parent.mkdir(parents=True)
        if given:
            out.mkdir()
        return out

    def _cp_shim(self, pattern: str = "*app/sources/files/*", name: str = "cpbin") -> str:
        """A `cp` ahead of the real one that fails a copy whose arguments match
        the shell `pattern` (default: into app/sources/files/; a disk-full
        stand-in). Returns the PATH that puts it first."""
        real = shutil.which("cp")
        self.assertIsNotNone(real, "cp is not on PATH")
        d = self.tmp / name
        d.mkdir(exist_ok=True)
        shim = d / "cp"
        shim.write_text("#!/bin/sh\n"
                        f'case "$*" in {pattern}) echo "cp: write error: No space left on device" >&2; '
                        "exit 1 ;; esac\n"
                        f'exec "{real}" "$@"\n', encoding="utf-8", newline="\n")
        shim.chmod(0o755)
        return f"{d}{os.pathsep}{self.path}"

    def _long_config(self) -> None:
        """Tracked config files on a deep path, so MANIFEST.sha256 passes
        install's 1 MiB cap by a margin (only the manifest's size changes)."""
        deep = self.repo / "config" / Path(*(["d" * 200] * 17))
        deep.mkdir(parents=True)
        for i in range(320):
            (deep / f"f{i:03d}{'x' * 96}").write_text(f"{i}\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture: long config paths")
        self.sha = self._git("rev-parse", "HEAD").strip()

    def test_bundle_writes_no_manifest_when_sbom_or_source_fails(self):
        """PSC-24, U9-10 with O-10, design item 9: a failure at any stage
        after the first write exits non-zero with one `bundle:` line naming
        the stage, writes no MANIFEST.sha256 and no release record, prints no
        `bundle written`, and removes the run's output: --out itself when the
        run created it, its contents when it was given."""
        stale = "deb:zlib-fixture@1.0-1"
        cases: dict[str, tuple[dict[str, Any], str, Any]] = {
            "SBOM generation fails (ke-neo4j)": ({"FAKE_DOCKER_FAIL": "docker-archive:/in/ke-neo4j.tar"},
                                                 r"\bke-neo4j\b", None),
            "copying a source file fails (disk full)": ({}, r"copying source file [0-9a-f]{64} failed", "cp"),
            "the index stage fails": ({"FAKE_DOCKER_FAIL": "sbom_check.py index"}, r"\bindex\b", None),
            "index refuses a lock key no image needs": ({}, r"\bindex\b", "stale"),
            "the notices stage fails": ({"FAKE_DOCKER_FAIL": "sbom_check.py notices"}, r"\bnotices\b", None),
            "MANIFEST.sha256 would pass install's 1 MiB cap": (
                {}, r"MANIFEST\.sha256 would be \d+ bytes, over install's 1 MiB cap", "cap"),
        }
        # O-15 A4: the named stage of each case (SBOM generation is not one of A4's stages).
        a4_of = {"copying a source file fails (disk full)": "copy", "the index stage fails": "index",
                 "index refuses a lock key no image needs": "index", "the notices stage fails": "notices",
                 "MANIFEST.sha256 would pass install's 1 MiB cap": "manifest"}
        for case, (env, stage, setup) in cases.items():
            if setup == "stale":
                self._relock(_synthetic_lock(set(_default_source_keys()) | {stale}))
            elif setup == "cap":
                self._relock(_synthetic_lock(_default_source_keys()))
                self._long_config()
            else:
                self._relock(_synthetic_lock(_default_source_keys()))
            run_env = dict(env)
            if setup == "cp":
                run_env["PATH"] = self._cp_shim()
            for given in (False, True):
                with self.subTest(case=case, out="given empty" if given else "created by the run"):
                    out = self._out_for(given)
                    result, _, out = self._bundle(out, **run_env)
                    self._assert_no_partial_bundle(result, out, given=given, stage=stage, a4=a4_of.get(case))
                    if setup == "stale":
                        self.assertIn(stale, self._out(result), "the index refusal names the key")
                    if setup == "cap":
                        self.assertFalse(list(out.parent.glob("**/MANIFEST.sha256*")), "a manifest file was left")

    # ---- U9b rework 1: O-16 (3), (4), (6), N-7 -------------------------------

    def _assert_removed(self, out: Path, given: bool, text: str) -> None:
        if given:
            self.assertTrue(out.is_dir(), "the given --out was removed (O-10: only its contents go)")
            self.assertEqual(sorted(os.listdir(out)), [], "the given --out was not emptied (O-10):\n" + text[-2000:])
        else:
            self.assertFalse(out.exists(), "--out, created by this run, was left (O-10):\n" + text[-2000:])
        self.assertEqual([p.name for p in out.parent.iterdir() if p.name.startswith(".ke-sbom.")], [],
                         "the SBOM work dir was left beside --out")

    def test_bundle_names_the_image_when_tag_or_save_fails(self):
        """Reviewer B-3, O-16 (4), U9-10: a failing `docker tag` or `docker
        save` ends the run with one `bundle:` line naming the image and
        saying no bundle was written; nothing is left (O-10), with --out
        created by the run and given empty."""
        cases = {"docker tag fails": r"^(?:image )?tag ", "docker save fails": r"^(?:image )?save "}
        for case, rx in cases.items():
            for given in (False, True):
                with self.subTest(case=case, out="given empty" if given else "created by the run"):
                    out = self._out_for(given)
                    result, calls, out = self._bundle(out, FAKE_DOCKER_FAIL_NTH=f"{rx}#1")
                    failed = [c for c in calls if re.search(rx, " ".join(c))]
                    self.assertEqual(len(failed), 1, f"precondition: one call ran and failed: {failed}")
                    argv = failed[0]
                    if "save" in argv[:2]:
                        name = Path(argv[argv.index("-o") + 1]).stem
                    else:
                        name = argv[-1].split("@")[0].rsplit(":", 1)[0].rsplit("/", 1)[-1]
                    self._assert_no_partial_bundle(result, out, given=given, stage=re.escape(name))
                    self.assertTrue([ln for ln in result.stderr.splitlines() if ln.startswith("bundle: ")
                                     and name in ln and "no bundle written" in ln],
                                    f"no `bundle:` line names {name} and says no bundle was written "
                                    f"(O-16 (4)):\n{result.stderr[-2000:]}")

    def test_bundle_names_the_file_when_an_app_notice_copy_fails(self):
        """Reviewer B-3, O-16 (4), U9-10: a failing copy into app/ of
        NOTICE.md or of licenses/ ends the run with `bundle: FAIL (stage
        copy: ...)` naming the file; nothing is left (O-10), with --out
        created by the run and given empty."""
        cases = {"app/NOTICE.md": ("*/app/NOTICE.md*|*NOTICE.md*/app*", r"NOTICE\.md", "cpbin-notice"),
                 "app/licenses/": ("*/app/licenses*|*licenses*/app*", r"licenses", "cpbin-licenses")}
        for case, (pattern, named, shim) in cases.items():
            path = self._cp_shim(pattern, name=shim)
            for given in (False, True):
                with self.subTest(case=case, out="given empty" if given else "created by the run"):
                    out = self._out_for(given)
                    result, _, out = self._bundle(out, PATH=path)
                    self._assert_no_partial_bundle(result, out, given=given, stage=named, a4="copy")

    def test_bundle_removes_its_output_on_sigterm(self):
        """Reviewer B-3, O-16 (4), O-10: SIGTERM to bundle.sh's own pid
        after the first write (while the fake `docker save` runs) ends the
        run non-zero and removes what it wrote: --out itself when the run
        created it, its contents when it was given; no record, no `bundle
        written`."""
        if os.name == "nt":
            self.skipTest(SIGNAL_SKIP)
        import signal
        import time
        for given in (False, True):
            with self.subTest(out="given empty" if given else "created by the run"):
                tag = f"{self.n + 1}-{'given' if given else 'created'}"
                marker = self.tmp / f"saving-{tag}"
                hooks = [{"on": r"^(?:image )?save ", "once": str(self.tmp / f"save-once-{tag}"),
                          "touch": str(marker), "sleep": 3}]
                out = self._out_for(given)
                argv, env, out = self._bundle_cmd(out, FAKE_DOCKER_HOOKS=json.dumps(hooks))
                proc = subprocess.Popen(argv, cwd=self.repo, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, start_new_session=True)
                try:
                    for _ in range(1800):
                        if marker.exists() or proc.poll() is not None:
                            break
                        time.sleep(0.1)
                    self.assertTrue(marker.exists(), "the run never reached docker save (after the first write)")
                    self.assertTrue((out / "images").is_dir(), "precondition: the first write came before the signal")
                    os.kill(proc.pid, signal.SIGTERM)  # bundle.sh alone; the fake docker runs on
                    stdout, stderr = proc.communicate(timeout=120)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                text = stdout + stderr
                self.assertNotEqual(proc.returncode, 0, "bundle.sh exited 0 after SIGTERM:\n" + text[-2000:])
                self.assertNotIn("bundle written", stdout)
                self.assertFalse(self._record(out).exists(), "a release record was written")
                self._assert_removed(out, given, text)

    def test_bundle_never_overwrites_a_record_that_appears_during_the_run(self):
        """O-16 (3), security L-4 (c) and M-3: a release record that appears
        beside --out after the run's start (here while `notices` runs) is
        never overwritten (noclobber): the run ends non-zero, the record keeps
        its bytes, no `bundle written`, and the run's output is removed
        (O-10)."""
        planted = "an operator's record, made while the run was going\n"
        for given in (False, True):
            with self.subTest(out="given empty" if given else "created by the run"):
                out = self._out_for(given)
                record = self._record(out)
                hooks = [{"on": r"sbom_check\.py notices", "write": {str(record): planted}}]
                result, _, out = self._bundle(out, FAKE_DOCKER_HOOKS=json.dumps(hooks))
                text = self._out(result)
                self.assertTrue(record.is_file(), "precondition: the hook planted the record")
                self.assertNotEqual(result.returncode, 0, "bundle.sh passed over a record it did not write:\n"
                                    + text[-2000:])
                self.assertEqual(record.read_bytes(), planted.encode("utf-8"),
                                 "the record was overwritten (O-16 (3): noclobber)")
                self.assertNotIn("bundle written", result.stdout)
                self._assert_removed(out, given, text)

    def test_a_source_file_changed_after_the_check_is_refused_in_a_given_out(self):
        """Security I-4 with a given --out (reviewer B-3): the bytes changed
        between `sources-check` and the copy fail name == hash as
        `bundle: FAIL (stage manifest: ...)` naming the file; the given --out
        is emptied, not removed (O-10)."""
        src = self.tmp / "swapped-fetch-given"
        shutil.copytree(self._fetched(), src)
        sha = sorted(self._distinct())[0]
        size = (src / sha).stat().st_size
        once = self.tmp / "swap-once-given"
        hooks = [{"on": r"^(?:image )?tag ", "once": str(once), "write": {str(src / sha): "X" * size}}]
        out = self._out_for(True)
        result, _, out = self._bundle(out, sources=src, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertTrue(once.exists(), "precondition: the swap ran (at the first tag)")
        self._assert_no_partial_bundle(result, out, given=True, stage=re.escape(f"app/sources/files/{sha}"),
                                       a4="manifest")

    def test_a_source_file_swapped_for_a_link_after_the_check_is_refused(self):
        """Reviewer N-7 (security I-4, the link variant), O-16 (7): a checked
        file in --sources replaced, after `sources-check` (at the first tag),
        by a symlink to a copy of the same bytes is copied as a link by
        `cp -P` (a followed link would ship the same bytes and pass) and
        refused by one `bundle: FAIL (stage <stage>: ...)` line, the stage
        being `index` (U9a's `index` opens each copied file with O_NOFOLLOW,
        and runs before the manifest) or `manifest` (its non-regular check);
        nothing is left (O-10), with --out created and given. O-16 (7) said
        `stage manifest`; the RED run showed `index` refuses first (named in
        the U9b rework-1 RED report)."""
        if os.name == "nt":
            self.skipTest(SYMLINK_SKIP)
        sha = sorted(self._distinct())[0]
        for given in (False, True):
            tag = "given" if given else "created"
            with self.subTest(out="given empty" if given else "created by the run"):
                src = self.tmp / f"link-swapped-fetch-{tag}"
                shutil.copytree(self._fetched(), src)
                same = self.tmp / f"same-bytes-{tag}"
                shutil.copyfile(src / sha, same)
                log = self.tmp / f"replace-{tag}.log"
                hooks = [{"on": r"^(?:image )?tag ", "once": str(self.tmp / f"link-once-{tag}"),
                          "replace": [str(src / sha), "symlink", str(same), str(log)]}]
                out = self._out_for(given)
                result, _, out = self._bundle(out, sources=src, FAKE_DOCKER_HOOKS=json.dumps(hooks))
                self.assertEqual(log.read_text(encoding="utf-8").split() if log.exists() else [], ["replaced"],
                                 "precondition: the link swap ran")
                named = [ln for ln in result.stderr.splitlines()
                         if A4_RE("index").fullmatch(ln) or A4_RE("manifest").fullmatch(ln)]
                self.assertTrue(named, "no `bundle: FAIL (stage index|manifest: ...)` line:\n" + result.stderr[-2000:])
                self._assert_no_partial_bundle(result, out, given=given, stage=r"\(stage (?:index|manifest): ")

    def test_bundle_path_pattern_refusal_is_stage_manifest(self):
        """O-16 (6), reviewer N-6: a bundle path that fails the manifest's
        path pattern (a tracked config file whose name holds a space) is
        refused as `bundle: FAIL (stage manifest: ...)` naming it; nothing is
        left (O-10), with --out created and given."""
        (self.repo / "config").mkdir(exist_ok=True)
        (self.repo / "config" / "bad name.txt").write_text("x\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture: a config file name with a space")
        self.sha = self._git("rev-parse", "HEAD").strip()
        for given in (False, True):
            with self.subTest(out="given empty" if given else "created by the run"):
                out = self._out_for(given)
                result, _, out = self._bundle(out)
                self._assert_no_partial_bundle(result, out, given=given, stage=r"app/config/bad", a4="manifest")

    def test_bundle_non_regular_file_refusal_is_stage_manifest(self):
        """O-16 (6), reviewer N-6: an entry of the bundle that is neither a
        file nor a directory (a tracked config symlink, copied by `cp -P`) is
        refused by the manifest's non-regular check as `bundle: FAIL (stage
        manifest: ...)`; nothing is left (O-10), with --out created and
        given."""
        if os.name == "nt":
            self.skipTest(SYMLINK_SKIP)
        cfg = self.repo / "config"
        cfg.mkdir(exist_ok=True)
        (cfg / "linked-target.txt").write_text("x\n", encoding="utf-8")
        (cfg / "a-link.txt").symlink_to("linked-target.txt")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture: a tracked config symlink")
        self.sha = self._git("rev-parse", "HEAD").strip()
        for given in (False, True):
            with self.subTest(out="given empty" if given else "created by the run"):
                out = self._out_for(given)
                result, _, out = self._bundle(out)
                self._assert_no_partial_bundle(result, out, given=given, stage=r".", a4="manifest")

    def test_bundle_refuses_an_unlistable_out(self):
        """Reviewer U8b N-9 (U9-10, design item 9): an --out that exists, is
        non-empty and cannot be listed (mode 0300) is refused with exit 1
        naming it, before any write, and left untouched."""
        if not hasattr(os, "geteuid"):
            self.skipTest("mode bits on a directory need POSIX (the gates image runs this row)")
        if os.geteuid() == 0:
            self.skipTest("uid 0 lists any directory whatever its mode (the gates image runs as uid 10001)")
        out = self.tmp / "unlistable" / "bundle-amd64"
        out.mkdir(parents=True)
        (out / "operator.txt").write_text("keep\n", encoding="utf-8")
        os.chmod(out, 0o300)
        self.addCleanup(os.chmod, out, 0o700)
        result, calls, out = self._bundle(out)
        mode = stat.S_IMODE(out.stat().st_mode)
        os.chmod(out, 0o700)
        text = self._out(result)
        self.assertEqual(result.returncode, 1, text[-2000:])
        self.assertTrue([ln for ln in result.stderr.splitlines() if ln.startswith("bundle: ") and str(out) in ln
                         and "list" in ln], f"no `bundle:` line says --out cannot be listed:\n{result.stderr[-2000:]}")
        self._assert_a4(result, "out")
        self.assertEqual(self._writes(calls), [], "a tag or save ran")
        self.assertEqual(mode, 0o300, "--out's mode was changed")
        self.assertEqual(sorted(os.listdir(out)), ["operator.txt"], "--out was written to or emptied")
        self.assertFalse(self._record(out).exists())

    # ---- U9b rework 2: O-17 (1), (2); O-16 (7) N-4 -----------------------------

    LATE_TEXT = "an operator's file, in a directory that appeared while the run was going\n"

    def _assert_late_out_refused(self, result: subprocess.CompletedProcess, calls: list[list[str]], out: Path,
                                 what: str) -> None:
        """O-17 (1): exit 1, exactly one `bundle: FAIL` line, it being
        `stage out`; no tag or save, no record, no SBOM work dir, no `bundle
        written`."""
        text = self._out(result)
        self.assertEqual(result.returncode, 1, f"{what} was adopted as --out (O-17 (1)):\n" + text[-2500:])
        fails = [ln for ln in result.stderr.splitlines() if ln.startswith("bundle: FAIL")]
        self.assertEqual(len(fails), 1, f"want one `bundle: FAIL` line:\n{result.stderr[-2000:]}")
        self._assert_a4(result, "out")
        self.assertEqual(self._writes(calls), [], "a tag or save ran")
        self.assertFalse(os.path.lexists(self._record(out)), "a release record was written")
        self.assertEqual([p.name for p in out.parent.iterdir() if p.name.startswith(".ke-sbom.")], [],
                         "an SBOM work dir was made beside --out")
        self.assertNotIn("bundle written", result.stdout)

    def _late_target(self, name: str) -> tuple[Path, dict[str, Any]]:
        target = self.tmp / name
        target.mkdir()
        (target / "operator.txt").write_text(self.LATE_TEXT, encoding="utf-8", newline="\n")
        return target, _snapshot(target)

    def test_bundle_refuses_an_out_that_appears_after_its_check(self):
        """O-17 (1), reviewer rework-1 B-1, security I-13: `created` is
        decided once, at the early --out check. A directory holding an
        operator's file, planted at an absent --out while `sources-check`
        runs (after that check), is refused as one `bundle: FAIL (stage out:
        ...)` line, exit 1: the file is untouched and the only entry, and no
        tag, save, record or SBOM work dir is made. (Re-testing `[ ! -e
        "$out" ]` at the first write adopts it as a given --out.)"""
        out = self._out_for(False)
        log = self.tmp / "late-dir.log"
        hooks = [{"on": r"sbom_check\.py sources-check", "replace": [str(out), "dir", "", str(log)],
                  "write": {str(out / "operator.txt"): self.LATE_TEXT}}]
        result, calls, out = self._bundle(out, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertEqual(log.read_text(encoding="utf-8").split() if log.exists() else [], ["replaced"],
                         "precondition: the hook planted the directory")
        self._assert_late_out_refused(result, calls, out, "a directory that appeared at --out after its check")
        self.assertTrue(out.is_dir() and not out.is_symlink(), "the planted directory was removed")
        self.assertEqual(sorted(os.listdir(out)), ["operator.txt"], "the planted directory was written to or emptied")
        self.assertEqual((out / "operator.txt").read_bytes(), self.LATE_TEXT.encode("utf-8"),
                         "the operator's file was changed")

    def test_bundle_refuses_a_link_that_appears_at_an_absent_out(self):
        """O-17 (1), security I-13 (the link variant): a symlink to a
        directory holding an operator's file, planted at an absent --out
        while `sources-check` runs, is refused as one `bundle: FAIL (stage
        out: ...)` line, exit 1: nothing is written through the link, the
        link stays, and no tag, save, record or SBOM work dir is made."""
        if os.name == "nt":
            self.skipTest(SYMLINK_SKIP)
        target, before = self._late_target("late-link-target-absent")
        out = self._out_for(False)
        log = self.tmp / "late-link-absent.log"
        hooks = [{"on": r"sbom_check\.py sources-check", "replace": [str(out), "symlink", str(target), str(log)]}]
        result, calls, out = self._bundle(out, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertEqual(log.read_text(encoding="utf-8").split() if log.exists() else [], ["replaced"],
                         "precondition: the hook planted the link")
        self._assert_late_out_refused(result, calls, out, "a link to a directory that appeared at --out")
        self.assertTrue(out.is_symlink() and os.readlink(out) == str(target), "the planted link was removed")
        self.assertEqual(_snapshot(target), before, "something was written through the link")

    def test_bundle_refuses_a_given_out_replaced_by_a_link_before_the_first_write(self):
        """O-17 (1): a given (empty) --out is re-checked to be a real
        directory, not a link, right before the first write. Replaced by a
        symlink to a directory holding an operator's file while
        `sources-check` runs, it is refused as one `bundle: FAIL (stage out:
        ...)` line (the tester's reading of "refused"), exit 1: nothing is
        written through the link, the link stays, and no tag, save, record or
        SBOM work dir is made."""
        if os.name == "nt":
            self.skipTest(SYMLINK_SKIP)
        target, before = self._late_target("late-link-target-given")
        out = self._out_for(True)
        log = self.tmp / "late-link-given.log"
        hooks = [{"on": r"sbom_check\.py sources-check", "replace": [str(out), "symlink", str(target), str(log)]}]
        result, calls, out = self._bundle(out, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        self.assertEqual(log.read_text(encoding="utf-8").split() if log.exists() else [], ["replaced"],
                         "precondition: the hook replaced the given --out by a link")
        self._assert_late_out_refused(result, calls, out, "a given --out replaced by a link to a directory")
        self.assertTrue(out.is_symlink() and os.readlink(out) == str(target), "the planted link was removed")
        self.assertEqual(_snapshot(target), before, "something was written through the link")

    def test_bundle_leaves_a_non_regular_record_link_in_place(self):
        """O-17 (2), security I-14: a symlink to a non-regular file
        (/dev/null) planted at the release record path while `notices` runs
        is opened by the noclobber write (bash's exception for an existing
        non-regular file), and the record's `chmod` then fails. The run ends
        with exit 1 and a `bundle:` line naming the record (`chmod ... ||
        die`); the cleanup never removes the link (`record_made=1` only
        after the `chmod`); --out is removed (created by the run) or emptied
        (given)."""
        if os.name == "nt":
            self.skipTest(SYMLINK_SKIP)
        if not hasattr(os, "geteuid") or os.geteuid() == 0:
            self.skipTest("uid 0 may chmod /dev/null itself (the gates image runs this row as uid 10001)")
        for given in (False, True):
            tag = "given" if given else "created"
            with self.subTest(out="given empty" if given else "created by the run"):
                out = self._out_for(given)
                record = self._record(out)
                marker = self.tmp / f"devnull-planted-{tag}"
                hooks = [{"on": r"sbom_check\.py notices", "symlink": [str(record), os.devnull],
                          "touch": str(marker)}]
                result, _, out = self._bundle(out, FAKE_DOCKER_HOOKS=json.dumps(hooks))
                text = self._out(result)
                self.assertTrue(marker.exists(), "precondition: the hook planted the link")
                self.assertEqual(result.returncode, 1, text[-2000:])
                self.assertTrue([ln for ln in result.stderr.splitlines() if ln.startswith("bundle: ")
                                 and ("record" in ln or str(record) in ln)],
                                f"no `bundle:` line names the record (O-17 (2): chmod || die):\n{result.stderr[-2000:]}")
                self.assertTrue(os.path.islink(record) and os.readlink(record) == os.devnull,
                                "the cleanup removed a record link this run did not write (O-17 (2), I-14)")
                self.assertNotIn("bundle written", result.stdout)
                self._assert_removed(out, given, text)

    def _rm_shim(self, needle: str, name: str) -> str:
        """An `rm` ahead of the real one that fails, removing nothing, when
        its arguments hold `needle` (a stand-in for an entry the cleanup
        cannot remove). Returns the PATH that puts it first."""
        real = shutil.which("rm")
        self.assertIsNotNone(real, "rm is not on PATH")
        d = self.tmp / name
        d.mkdir(exist_ok=True)
        shim = d / "rm"
        shim.write_text("#!/bin/sh\n"
                        f'case "$*" in *"{needle}"*) echo "rm: cannot remove: Permission denied" >&2; exit 1 ;; esac\n'
                        f'exec "{real}" "$@"\n', encoding="utf-8", newline="\n")
        shim.chmod(0o755)
        return f"{d}{os.pathsep}{self.path}"

    def test_bundle_cleanup_warns_and_carries_on_when_a_removal_fails(self):
        """O-16 (7), reviewer N-4 (U9b rework-1 review N-1; O-17 (1) asks
        the row): when the O-10 cleanup cannot remove what the run wrote (an
        `rm` that fails on --out; for a given --out, the one `find -exec`
        runs), it prints `bundle: warning: could not remove ...` naming --out
        and carries on, with no `set -e` abort inside the trap: the run keeps
        its status (exit 1, the notices failure), the SBOM project's `compose
        ... down` still runs and the SBOM work dir is still removed. With
        --out created by the run and given empty."""
        if os.name == "nt":
            self.skipTest("an `rm` shim run by GNU find's -exec; the gates image runs this row")
        for given in (False, True):
            tag = "given" if given else "created"
            with self.subTest(out="given empty" if given else "created by the run"):
                out = self._out_for(given)
                path = self._rm_shim(str(out), f"rmbin-{tag}")
                result, calls, out = self._bundle(out, PATH=path, FAKE_DOCKER_FAIL="sbom_check.py notices")
                text = self._out(result)
                self.assertTrue(out.is_dir(), "precondition: the `rm` shim kept --out")
                self.assertEqual(result.returncode, 1, "the cleanup changed the run's status:\n" + text[-2000:])
                self._assert_a4(result, "notices")
                warned = [ln for ln in result.stderr.splitlines()
                          if ln.startswith("bundle: warning: could not remove") and str(out) in ln]
                self.assertTrue(warned, "no `bundle: warning: could not remove ...` line names --out (O-16 (7), "
                                f"N-4):\n{result.stderr[-2000:]}")
                self.assertTrue([c for c in calls if c[:1] == ["compose"] and "down" in c],
                                "the cleanup stopped before the SBOM project's `compose ... down` (N-4)")
                self.assertEqual([p.name for p in out.parent.iterdir() if p.name.startswith(".ke-sbom.")], [],
                                 "the cleanup stopped before removing the SBOM work dir (N-4)")
                self.assertNotIn("bundle written", result.stdout)
                self.assertFalse(os.path.lexists(self._record(out)), "a release record was written")

    def test_bundle_leaves_sources_dir_unchanged(self):
        """U9-1: bundle.sh never writes, deletes or renames under --sources:
        its listing, modes and bytes are unchanged after a run that passes, a
        run refused before any write and a run that fails after the first."""
        src = self.tmp / "watched-fetch"
        shutil.copytree(self._fetched(), src)
        before = _snapshot(src)
        runs: dict[str, dict[str, Any]] = {
            "a run that passes": {},
            "a run refused before any write (sample set asked)": {"args": ("--sources-set", "sample")},
            "a run that fails after the first write": {"FAKE_DOCKER_FAIL": "docker-archive:/in/ke-neo4j.tar"},
        }
        for case, kw in runs.items():
            with self.subTest(case=case):
                result, _, _ = self._bundle(sources=src, **kw)
                if case == "a run that passes":
                    self.assertEqual(result.returncode, 0, self._out(result)[-3000:])
                else:
                    self.assertNotEqual(result.returncode, 0)
                self.assertEqual(_snapshot(src), before, "--sources changed")


# --------------------------------------------------------------------------
# Item 7 / U9-8, U9-9: the notice copies under app/, I-3 resolution, libffi
# --------------------------------------------------------------------------

class BundleSourcesNoticeCopiesTest(_SourcesBase):

    def _install(self, out: Path, target: Path, kind: str) -> subprocess.CompletedProcess:
        data = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        load = {Path(e["file"]).name: f"Loaded image: {e['as']}" for e in data["images"]}
        for f in (self.log, self.json):
            f.write_text("", encoding="utf-8")
        env = {"PATH": self.path, "HOME": str(self.tmp), "FAKE_DOCKER_LOG": str(self.log),
               "FAKE_DOCKER_JSON": str(self.json), "FAKE_DOCKER_ENGINE": ENGINE_OK,
               "FAKE_COMPOSE_IMAGES": json.dumps(self.stack), "FAKE_DOCKER_LOAD": json.dumps(load)}
        if kind == "sh":
            argv = ["bash", str(out / "install.sh"), str(target)]
        else:
            argv = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(out / "install.ps1"), "-Target", str(target)]
        return subprocess.run(argv, env=env, cwd=out, capture_output=True, text=True, timeout=300)

    def test_app_carries_the_notice_copies(self):
        """U9-8, design item 7: app/ carries NOTICE.md,
        THIRD_PARTY_NOTICES.md, LICENSE and licenses/, each byte-identical to
        the bundle-root copy, which stays; all are in the manifest; the libffi
        text ships in both, equal to the committed file."""
        _, _, out = self._ok_bundle()
        root_licences = sorted(p.relative_to(out).as_posix() for p in (out / "licenses").rglob("*") if p.is_file())
        self.assertTrue(root_licences, "precondition: licenses/ ships at the root")
        listed = _manifest(out)
        for rel in ["NOTICE.md", NOTICES, "LICENSE", *root_licences]:
            with self.subTest(file=rel):
                self.assertTrue((out / rel).is_file(), f"the root copy of {rel} is gone (it stays, U9-8)")
                copy = out / "app" / rel
                self.assertTrue(copy.is_file() and not copy.is_symlink(), f"app/{rel} is missing")
                self.assertEqual(copy.read_bytes(), (out / rel).read_bytes(), f"app/{rel} differs from the root copy")
                self.assertIn(f"app/{rel}", listed, f"app/{rel} is not in MANIFEST.sha256")
        app_licences = sorted(p.relative_to(out / "app").as_posix()
                              for p in (out / "app" / "licenses").rglob("*") if p.is_file())
        self.assertEqual(app_licences, root_licences, "app/licenses/ is not the root licenses/")
        with self.subTest(file=LIBFFI_FILE):
            committed = ROOT / LIBFFI_FILE
            self.assertTrue(committed.is_file(), f"{LIBFFI_FILE} is not committed (U9-9)")
            for where in (out / LIBFFI_FILE, out / "app" / LIBFFI_FILE):
                self.assertTrue(where.is_file(), f"{_rel(where, out)} is not in the bundle")
                if committed.is_file() and where.is_file():
                    self.assertEqual(where.read_bytes(), committed.read_bytes(), f"{_rel(where, out)} differs")

    def test_app_notice_copies_are_taken_from_the_bundle_root(self):
        """Reviewer N-2, O-16 (7), U9-8: the app/ copies of NOTICE.md,
        LICENSE and licenses/ are taken from the bundle-root copies in
        --out, so byte-identity holds by construction: files changed in the
        tree after the root copies were made (here while `notices` runs) do
        not reach app/."""
        changed = "changed in the tree after the bundle-root copy was made\n"
        lic = sorted(p.relative_to(self.repo).as_posix() for p in (self.repo / "licenses").rglob("*") if p.is_file())
        self.assertTrue(lic, "precondition: the fixture has licences")
        targets = ["NOTICE.md", "LICENSE", lic[0]]
        hooks = [{"on": r"sbom_check\.py notices", "write": {str(self.repo / rel): changed for rel in targets}}]
        _, _, out = self._ok_bundle(FAKE_DOCKER_HOOKS=json.dumps(hooks))
        for rel in targets:
            with self.subTest(file=rel):
                root = (out / rel).read_bytes()
                self.assertNotEqual(root, changed.encode("utf-8"), "precondition: the root copy predates the change")
                self.assertEqual((out / "app" / rel).read_bytes(), root,
                                 f"app/{rel} is not the bundle-root copy (N-2: copy from --out, not the tree)")

    def _assert_resolves(self, notices: Path, app_root: Path, label: str) -> None:
        text = notices.read_text(encoding="utf-8")
        body = [ln for ln in _section(text, "Source code").splitlines() if ln.strip()]
        self.assertIn(I3, body, f"{label}: the Source code section lacks the I-3 path sentence")
        index_path = app_root / "sources" / "index.json"
        self.assertTrue(index_path.is_file(), f"{label}: sources/index.json does not resolve from {app_root}")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        paths = sorted({f["path"] for c in index["components"] for f in c.get("files", []) if f.get("path")})
        self.assertTrue(paths, f"{label}: the index names no shipped file")
        for rel in paths:
            p = app_root / rel
            self.assertTrue(p.is_file(), f"{label}: {rel} does not resolve from {app_root}")
            self.assertEqual(_sha256(p), rel.rsplit("/", 1)[1], f"{label}: {rel} is not its sha256's bytes")

    def test_sources_paths_resolve_from_every_notice_copy(self):
        """Security I-3, U9-7, U9-8: for the root copy, the app/ copy and the
        installed copy of THIRD_PARTY_NOTICES.md, `<app root>/sources/index.json`
        and every `sources/files/<sha256>` path the index names resolve, the
        app root being <bundle>/app for both bundle copies and the install
        directory for the installed one."""
        _, _, out = self._ok_bundle()
        self._assert_resolves(out / NOTICES, out / "app", "the bundle-root copy")
        self._assert_resolves(out / "app" / NOTICES, out / "app", "the app/ copy")
        target = self.tmp / "installed"
        done = self._install(out, target, "sh")
        self.assertEqual(done.returncode, 0, done.stdout[-1500:] + done.stderr[-2500:])
        self._assert_resolves(target / NOTICES, target, "the installed copy")

    def _assert_installs(self, kind: str) -> None:
        if kind == "ps1" and shutil.which("pwsh") is None:
            self.fail("pwsh is not on PATH: the gates image must carry pwsh (PS-3.1)")
        for which in ("sample", "full"):
            with self.subTest(installer=kind, set=which):
                _, _, out = self._ok_bundle(**({"sources_set": "sample"} if which == "sample" else {}))
                target = self.tmp / f"installed-{kind}-{which}"
                done = self._install(out, target, kind)
                self.assertEqual(done.returncode, 0, done.stdout[-1500:] + done.stderr[-2500:])
                listed = _manifest(out)
                for rel, digest in listed.items():
                    if rel.startswith("app/sources/") or rel in (f"app/{NOTICES}", "app/NOTICE.md", "app/LICENSE",
                                                                  f"app/{LIBFFI_FILE}"):
                        installed = target / rel[len("app/"):]
                        self.assertTrue(installed.is_file() and not installed.is_symlink(), f"{installed} missing")
                        self.assertEqual(_sha256(installed), digest, f"{installed}: not the manifest's bytes")
                self.assertEqual(sorted(os.listdir(target / "sources" / "files")), sorted(self._distinct(which)))

    def test_bundle_with_sources_installs_under_install_sh(self):
        """Item 9 of the U9b brief, U9-11's control on a real bundle.sh
        bundle: a sample and a full bundle built by the fake flow install
        under install.sh, and the target holds sources/ and the notice copies
        with the manifest's sha256."""
        self._assert_installs("sh")

    def test_bundle_with_sources_installs_under_install_ps1(self):
        """The same under install.ps1 (pwsh, in the gates image)."""
        self._assert_installs("ps1")


# --------------------------------------------------------------------------
# U9-9: NOTICE.md (I-3 sentence, libffi) and the libffi text
# --------------------------------------------------------------------------

class NoticeSourcesTextTest(unittest.TestCase):

    def test_notice_source_code_section_starts_with_the_i3_sentence(self):
        """U9-9, design item 7: NOTICE.md's "Source code" section gains the
        I-3 path sentence as its first line, identical to the generated
        section's, and keeps the pointer and the L-6 sentence."""
        text = NOTICE_MD.read_text(encoding="utf-8")
        body = _section(text, "Source code")
        self.assertTrue(body, "NOTICE.md has no `## Source code` section")
        lines = [ln for ln in body.splitlines() if ln.strip()]
        self.assertEqual(lines[:1], [I3], "the I-3 sentence is not the section's first line")
        flat = _flat(body)
        self.assertIn('A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has no `sources/`', flat)
        self.assertIn("`THIRD_PARTY_NOTICES.md` says, in its \"Source code\" section", flat)

    def test_notice_names_libffi_in_ke_neo4j_section(self):
        """U9-9 (security U6 exempt review L-1, orchestrator ruling
        2026-10-25), design item 7, security R7: the "Base image of
        `ke-neo4j`" section names libffi in jna 5.15.0's `libjnidispatch`,
        names licenses/libffi-jna-5.15.0.txt, and carries security's
        recommended paragraph (whitespace-normalised)."""
        text = NOTICE_MD.read_text(encoding="utf-8")
        section = _flat(_section(text, "Base image of `ke-neo4j`"))
        self.assertTrue(section, "NOTICE.md has no `## Base image of `ke-neo4j`` section")
        for needle in ("libffi", "libjnidispatch", "5.15.0", f"`{LIBFFI_FILE}`", LIBFFI_URL, LIBFFI_SHA256):
            with self.subTest(needle=needle):
                self.assertIn(needle, section, f"the ke-neo4j section does not name {needle}")
        self.assertIn(LIBFFI_PARAGRAPH, section, "the ke-neo4j section does not carry the libffi paragraph (R7)")
        self.assertNotRegex(text, r"(?i)docs[/\\]evidence", "NOTICE.md cites a docs/evidence path")

    def test_libffi_licence_file_is_the_fetched_text(self):
        """U9-9, security R7: licenses/libffi-jna-5.15.0.txt has the Q48
        header (three lines, then a blank line) and then the fetched 1132
        bytes unmodified, whose sha256 is the header's; LF only; tracked."""
        path = ROOT / LIBFFI_FILE
        self.assertTrue(path.is_file(), f"{LIBFFI_FILE} is missing (U9-9)")
        raw = path.read_bytes()
        self.assertNotIn(b"\r", raw, "CR in the file (LF only)")
        head, sep, body = raw.partition(b"\n\n")
        self.assertTrue(sep, "no blank line after the header")
        self.assertEqual(head.decode("ascii").split("\n"), LIBFFI_HEADER, "the header is not the Q48 form")
        self.assertEqual(len(body), LIBFFI_SIZE, "the fetched text is not 1132 bytes")
        self.assertEqual(hashlib.sha256(body).hexdigest(), LIBFFI_SHA256, "the text is not the fetched bytes")
        self.assertEqual(body.decode("ascii").split("\n", 1)[0], LIBFFI_FIRST)
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", LIBFFI_FILE], capture_output=True,
                                 text=True, check=False)
        self.assertEqual(tracked.returncode, 0, tracked.stderr)
        self.assertEqual(tracked.stdout.strip(), LIBFFI_FILE, f"{LIBFFI_FILE} is not tracked (git ls-files)")


# --------------------------------------------------------------------------
# O-16 (4), (7): bundle.sh's shell form (static)
# --------------------------------------------------------------------------

class BundleSourcesShellFormTest(unittest.TestCase):

    def test_bundle_cleanup_ignores_signals_before_clearing_exit_trap(self):
        """Reviewer B-3, O-16 (4) (as bundle_fetch.sh and scan.sh): in the
        EXIT-trap function, INT, TERM and HUP are ignored (`trap '' INT TERM
        HUP`) before the EXIT trap is cleared (`trap - EXIT`), and the
        function never resets INT, TERM or HUP to their default, so a second
        signal cannot cut the removal short."""
        from tests.test_image_scan import _function_body, _trap_words
        lines = _code_lines(BUNDLE_SH.read_text(encoding="utf-8"))
        handlers = [w[1] for w in (_trap_words(line) for line in lines if not line[:1].isspace())
                    if w and len(w) >= 3 and "EXIT" in w[2:] and w[1] not in ("", "-")]
        self.assertEqual(len(handlers), 1, "harness: bundle.sh installs one EXIT trap function at top level")
        body = _function_body(lines, handlers[0]) if handlers else []
        self.assertTrue(body, f"harness: the body of the EXIT trap function {handlers[:1]} was not found")
        traps = [w for w in (_trap_words(line) for line in body) if w]
        self.assertTrue(traps, "the EXIT trap function sets no trap")
        if traps:
            first = traps[0]
            self.assertTrue(first[1] == "" and {"INT", "TERM", "HUP"} <= set(first[2:]),
                            f"the first trap in {handlers[0]}() is `{' '.join(first)}`: it must be "
                            "`trap '' INT TERM HUP`, before `trap - EXIT`")
        self.assertTrue([w for w in traps if w[1] in ("", "-") and "EXIT" in w[2:]],
                        f"{handlers[:1]}() never clears the EXIT trap (`trap - EXIT`)")
        reset = [" ".join(w) for w in traps if w[1] == "-" and {"INT", "TERM", "HUP"} & set(w[2:])]
        self.assertEqual(reset, [], f"{handlers[:1]}() resets a signal to its default during the removal")

    def test_bundle_turns_int_term_and_hup_into_a_non_zero_exit(self):
        """Reviewer B-3, O-10: INT, TERM and HUP each have a top-level trap
        that exits non-zero, so the EXIT trap runs with a non-zero status and
        removes the run's output (with the EXIT trap alone, SIGTERM and
        SIGHUP run it with status 0 and nothing is removed)."""
        from tests.test_image_scan import _trap_words
        lines = _code_lines(BUNDLE_SH.read_text(encoding="utf-8"))
        top = [w for w in (_trap_words(line) for line in lines if not line[:1].isspace()) if w]
        for sig in ("INT", "TERM", "HUP"):
            with self.subTest(signal=sig):
                actions = [w[1] for w in top if sig in w[2:]]
                self.assertEqual(len(actions), 1, f"want one top-level trap for {sig}, got {actions}")
                self.assertTrue(actions and re.fullmatch(r"exit ([1-9][0-9]*)", actions[0].strip()),
                                f"the {sig} trap does not exit non-zero: {actions}")

    def test_every_stage_refusal_goes_through_stage_die(self):
        """O-16 (7), reviewer N-1, O-15 A4: every `bundle: FAIL (stage ...)`
        line comes from `stage_die`; no other code line prints the form (the
        no-fetch.json refusal used `echo` because `_strip_messages` did not
        strip `stage_die` text)."""
        code = _code_lines(BUNDLE_SH.read_text(encoding="utf-8"))
        defs = [ln for ln in code if re.match(r"\s*stage_die\s*\(\)", ln)]
        self.assertEqual(len(defs), 1, "harness: bundle.sh defines stage_die once")
        stray = [ln.strip() for ln in code if "FAIL (stage" in ln and ln not in defs]
        self.assertEqual(stray, [], "a stage line is printed outside stage_die (O-16 (7))")

    def test_strip_messages_strips_the_text_of_stage_die(self):
        """O-16 (7), reviewer N-1: tests/test_sbom_generator.py
        `_strip_messages` strips the message of `stage_die <stage> "..."` as
        it does for die, echo and printf, and keeps the code around it."""
        from tests.test_sbom_generator import _strip_messages
        sample = ('  [ -f "$s/fetch.json" ] || stage_die sources-check "--sources $s has no fetch.json; run '
                  'scripts/bundle_fetch.sh --set $set first"\n'
                  '  die "the generator is not present; pull it first"\n'
                  '  scripts/bundle_fetch.sh --set full\n')
        lines = _strip_messages(sample).splitlines()
        self.assertEqual(len(lines), 3, lines)
        self.assertNotIn("bundle_fetch", lines[0], "the stage_die message was not stripped")
        self.assertIn('[ -f "$s/fetch.json" ] ||', lines[0], "the code before the message was stripped too")
        self.assertNotIn("pull", lines[1], "control: a die message is stripped")
        self.assertIn("scripts/bundle_fetch.sh --set full", lines[2], "control: code that is not a message stays")


# --------------------------------------------------------------------------
# U9-12: header, README, CLAUDE.md; design item 4: the copy form
# --------------------------------------------------------------------------

class BundleSourcesDocsTest(unittest.TestCase):

    def test_bundle_header_names_the_sources_step(self):
        """U9-1, U9-12 (N13): bundle.sh's header names --sources and
        --sources-set in its command line, says the bundle ships app/sources/
        from the set scripts/bundle_fetch.sh fetched, and still says it makes
        no network call."""
        head = _header(BUNDLE_SH.read_text(encoding="utf-8"))
        for phrase in ("--sources", "--sources-set", "app/sources/", "scripts/bundle_fetch.sh",
                       "makes no network call"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, head, f"bundle.sh's header does not name {phrase!r}")
        self.assertRegex(head, r"scripts/bundle\.sh --out \S+ .*--sources\b", "the header's command line lacks --sources")

    def test_bundle_copies_sources_with_cp_dash_p_only(self):
        """Design item 4: the copy into app/sources/files is `cp -P --`, never
        a hard link, reflink or attribute-preserving copy."""
        code = _code_lines(BUNDLE_SH.read_text(encoding="utf-8"))
        copies = [ln for ln in code if re.search(r"\bcp\b", ln) and "sources/files" in ln]
        self.assertTrue(copies, "no cp into .../sources/files in bundle.sh")
        for ln in copies:
            with self.subTest(line=ln.strip()):
                self.assertRegex(ln, r"\bcp\s+-P\s+--\s", "the source copy is not `cp -P --`")
                self.assertNotRegex(ln, r"\bcp\b[^|;&]*\s(?:-[A-Za-z]*[alp][A-Za-z]*|--link|--reflink\S*|"
                                        r"--archive|--preserve\S*)\s", "a link, reflink or preserving copy")

    def test_readme_gives_the_operator_order_with_sources(self):
        """U9-12 (documenter): README gives the operator order build.sh, then
        bundle_fetch.sh --set full, then bundle.sh --sources <dir>; says a
        sample bundle is for verification only; and no longer says bundle.sh
        does not read the fetched set."""
        text = README_MD.read_text(encoding="utf-8")
        paras = [_flat(p) for p in re.split(r"\n\s*\n", text)]
        ordered = [p for p in paras
                   if re.search(r"scripts/build\.sh.*scripts/bundle_fetch\.sh --set full.*scripts/bundle\.sh\b.{0,80}?"
                                r"--sources\b", p)]
        self.assertTrue(ordered, "no README paragraph gives build.sh, then bundle_fetch.sh --set full, then "
                                 "bundle.sh --sources")
        sample = [p for p in paras if re.search(r"\bsample\b", p)
                  and re.search(r"(?i)\bverification only\b|\bonly for verification\b|\bfor verification only\b", p)]
        self.assertTrue(sample, "no README paragraph says a sample bundle is for verification only")
        self.assertNotIn("does not read it yet", _flat(text), "README still says bundle.sh does not read the set")
        self.assertIn("app/sources/", text, "README does not say the bundle carries app/sources/")

    def test_claude_md_lock_row_is_unchanged(self):
        """U9-12: U9 makes CLAUDE.md's lock row true and changes no CLAUDE.md
        text (control: green from the start)."""
        self.assertIn(CLAUDE_LOCK_ROW_U9, CLAUDE_MD.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Control: the synthetic set matches the fake syft (green from the start)
# --------------------------------------------------------------------------

class FakeSyftNeedsTest(_SourcesBase):

    def _fake_syft_docs(self) -> dict[str, Any]:
        """Raw documents from the fake syft, one per stack image name."""
        from tests import compose_support as cs
        from tests.test_offline_bundle import _expected_as
        names = sorted({_expected_as(ref, self.sha)[1] for ref in self.stack.values()})
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        (d / "in").mkdir()
        shutil.copyfile(ROOT / cs.SBOM_COMPOSE_NAME, d / cs.SBOM_COMPOSE_NAME)
        shutil.copyfile(ROOT / ".env.example", d / ".env.example")
        docs = {}
        for name in names:
            (d / "in" / f"{name}.tar").write_bytes(b"not a real tar\n")
            work = d / f"out-{name}"
            (work / "tmp").mkdir(parents=True)
            env = {"PATH": self.path, "HOME": str(self.tmp),
                   "FAKE_COMPOSE_FILE_IMAGES": json.dumps({cs.SBOM_COMPOSE_NAME: {"sbom": self.sbom_ref}}),
                   "FAKE_IMAGE_PATHS": json.dumps({"/opt/venv": str(self.venv), "/app": str(ROOT)}),
                   "KE_SBOM_IN": str(d / "in"), "KE_SBOM_OUT": str(work), "KE_SBOM_USER": "1000:1000"}
            done = subprocess.run([str(self.tmp / "fakebin" / "docker"), "compose", "--env-file", ".env.example",
                                   "-f", cs.SBOM_COMPOSE_NAME, "run", "--rm", "--pull", "never", "sbom",
                                   f"docker-archive:/in/{name}.tar", "--scope", "all-layers", "-o",
                                   "spdx-json=/out/raw.spdx.json"], cwd=d, env=env, capture_output=True, text=True,
                                  timeout=60)
            self.assertEqual(done.returncode, 0, done.stderr)
            docs[name] = json.loads((work / "raw.spdx.json").read_text(encoding="utf-8"))
        return docs

    def test_synthetic_lock_covers_exactly_the_fake_syft_needs(self):
        """Harness control (green on arrival): the default synthetic lock's
        keys are exactly what the fake syft's documents need, with no lock
        problem for either arch, and `sources-check` passes on each fetched
        directory the harness writes."""
        from tests.test_sbom_bundle import load_sbom_check
        S = load_sbom_check()
        docs = self._fake_syft_docs()
        needs, problems = S.lock_needs(self.src_policy, docs)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(needs), _default_source_keys())
        for arch in ("amd64", "arm64"):
            with self.subTest(arch=arch):
                self.assertEqual(S.lock_problems(self.src_lock.text(), self.src_policy, docs, arch), [])
            for which in ("full", "sample"):
                with self.subTest(arch=arch, set=which):
                    done = _run_check("sources-check", "--lock", str(self.repo / "docker" / "sources.lock.json"),
                                      "--policy", str(self.repo / "docker" / "source-policy.json"),
                                      "--dir", str(self._fetched(arch, which)), "--arch", arch, "--set", which)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual(done.stdout.split(), sorted(self._distinct(which, arch)))


if __name__ == "__main__":
    unittest.main()
