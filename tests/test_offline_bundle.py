"""platform-offline PS-3.1: the offline bundle (`scripts/bundle.sh`) and its
installers (`scripts/install.sh`, `scripts/install.ps1`), driven against the
fake `docker` and fake `df` in tests/fake_docker.py. All fast; nothing here
talks to a daemon.

Design: docs/architecture.md §2.5 (Bundle, Install) and §2.6 platform-offline
items 2-6. Criteria and test names: docs/requirements.md PS-3.1 and its
"PS-3.1 additions". Rulings: docs/handoffs/platform-offline.md (R1 no
bundle.ps1; R2 store-independent per-image tars, `bundle.json` file/ref/as/
services, compose override; R6 10 GB floor; R7 stack images only).

The installers are tested on a tiny fixture bundle: two "image" tars
(`ke-app`, serving api and worker; `postgres`, a vendor image), an `app/`
tree with a small compose file, `bundle.json` in the §2.5 one-entry-per-line
form, and a `MANIFEST.sha256` over every other file. Each installer case runs
under bash and under pwsh (the gates image carries pwsh).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests import compose_support as cs
from tests import fake_docker
from tests.engine_support import ROOT

ENGINE_OK = "29.5.2"
PWSH_MISSING = ("pwsh is not on PATH: the gates image must carry pwsh (PS-3.1: the PowerShell "
                "installer is tested under pwsh in the gates image)")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SERVICE_NAME = re.compile(r"^[a-z0-9_-]+$")
GIB_KB = 1024 * 1024  # df -Pk reports 1024-byte blocks

# The fixture bundle (installer tests).
GIT_SHA = "0123456789abcdef0123456789abcdef01234567"
PG_DIGEST = hashlib.sha256(b"fixture postgres").hexdigest()
PG_REF = f"postgres:16-bookworm@sha256:{PG_DIGEST}"
AS_APP = f"ke-app:bundle-{GIT_SHA[:12]}"
AS_PG = f"ke-vendor/postgres:{PG_DIGEST[:12]}"
# A `Loaded image: <name>` line (classic/named load). A genuine tar is saved
# from `as`, so the name it prints is `as` (security L-5; rework round 1 in
# docs/handoffs/platform-offline.md). Any other name is refused.
LOADED_APP_NAME = AS_APP
WRONG_LOADED_NAME = "ke-app:loaded-by-fake"
FIXTURE_COMPOSE = f"""services:
  api:
    image: ke-app:local
  worker:
    image: ke-app:local
  postgres:
    image: {PG_REF}
  gates:
    image: ke-gates:local
    profiles: ["gates"]
"""
FIXTURE_STACK_IMAGES = {"api": "ke-app:local", "worker": "ke-app:local", "postgres": PG_REF}
# PS-3.1 Arch normalisation: `docker info` Architecture -> bundle arch.
ARCH_OF = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
# The bundle.json header line, as both installers match it (architecture §2.5).
HEADER_RE = re.compile(r'^\{"format": 1, "git_sha": "[0-9a-f]{40}", "dirty": (?:true|false), '
                       r'"created": "\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", "arch": "(amd64|arm64)", "images": \[$')
MUTATING = ("rm", "rmi", "pull", "push", "build", "untag", "prune", "save", "commit")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _regular_files(root: Path) -> list[str]:
    return sorted((_rel(p, root) for p in root.rglob("*") if p.is_file() and not p.is_symlink()),
                  key=lambda s: s.encode("utf-8"))


def _write_manifest(root: Path) -> None:
    lines = [f"{_sha256(root / rel)}  {rel}" for rel in _regular_files(root)
             if rel != "MANIFEST.sha256"]
    (root / "MANIFEST.sha256").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _entry(file: str, ref: str, as_: str, services: str) -> dict[str, str]:
    return {"file": file, "ref": ref, "as": as_, "services": services}


def _bundle_json(entries: list[dict[str, str]], dirty: bool = False, arch: str = "amd64") -> str:
    """The §2.5 form: one header line, one image per line, closing line.
    The header carries `"arch": "amd64|arm64"` in place of the old
    `"platform": "linux/amd64"` (PS-3.1 per-arch bundles, *Arch recorded*)."""
    head = ('{"format": 1, "git_sha": "%s", "dirty": %s, "created": "2026-10-19T00:00:00Z", '
            '"arch": "%s", "images": [' % (GIT_SHA, "true" if dirty else "false", arch))
    body = ",\n".join(json.dumps(e) for e in entries)
    return head + "\n" + body + "\n]}\n"


FIXTURE_ENTRIES = [
    _entry("images/ke-app.tar", "ke-app:local", AS_APP, "api worker"),
    _entry("images/postgres.tar", PG_REF, AS_PG, "postgres"),
]


def _case_sensitive(directory: Path) -> bool:
    probe = directory / "case-probe"
    probe.write_text("x", encoding="utf-8")
    try:
        return not (directory / "CASE-PROBE").exists()
    finally:
        probe.unlink()


# Rule names a refusal must carry (architecture §2.5 Install: "a message names
# the rule and the path"; review B1).
RULE_HASH = r"hash mismatch"
RULE_MISSING = r"listed file is missing"
RULE_UNLISTED = r"not listed"
RULE_LINK = r"\b(?:sym)?link\b|reparse point|junction"
RULE_HARDLINK = r"hard ?link|link count"
RULE_FIFO = r"\bfifo\b|named pipe"
RULE_DOT = r"(?:'\.'|'\.\.'|\bdot(?:-dot)?) segment"
RULE_LEADING = r"leading|absolute"
RULE_BACKSLASH = r"backslash"
RULE_MALFORMED = r"<64 hex>|malformed"
RULE_DUPLICATE = r"duplicate"
RULE_RESERVED = r"reserved"
RULE_TRAILING = r"trailing (?:dot|'\.')|ends? (?:with|in) (?:a )?(?:dot|'\.')"
RULE_CHARACTER = r"character"
RULE_CASE = r"\bcase\b"
RULE_TRAILING_SPACE = r"character|trailing (?:space|' ')|ends? (?:with|in) (?:a )?space"
STAGING_PREFIX = ".ke-install."  # architecture §2.5 Install: private staging in the target's parent
RULE_SIZE = r"\b1 mib\b|too (?:large|big)|\bsize\b|\bcap\b"
MANIFEST_CAP = 1024 * 1024  # architecture §2.5: MANIFEST.sha256 is at most 1 MiB


def _pad_manifest(path: Path, size: int) -> None:
    """Append well-formed lines naming absent `app/pad/*` files until the
    manifest is exactly `size` bytes."""
    data = path.read_bytes()
    h = "0" * 64
    lines, i = [], 0
    used = len(data)
    while True:
        line = f"{h}  app/pad/{i:08d}.txt\n"
        if used + len(line) * 2 > size:
            break
        lines.append(line)
        used += len(line)
        i += 1
    base = f"{h}  app/pad/z"
    rest = size - used - len(base) - len(".txt\n")
    assert 1 <= rest <= 200, rest
    lines.append(f"{base}{'z' * rest}.txt\n")
    out = data + "".join(lines).encode("ascii")
    assert len(out) == size, len(out)
    path.write_bytes(out)


def _make_fixture(root: Path, entries: list[dict[str, str]] | None = None, arch: str = "amd64") -> None:
    root.mkdir(parents=True)
    for name in ("install.sh", "install.ps1"):
        src = ROOT / "scripts" / name
        if src.is_file():
            shutil.copyfile(src, root / name)
    (root / "images").mkdir()
    (root / "images" / "ke-app.tar").write_bytes(b"fixture ke-app image tar\n")
    (root / "images" / "postgres.tar").write_bytes(b"fixture postgres image tar\n")
    (root / "app" / "scripts").mkdir(parents=True)
    (root / "app" / "docker-compose.yml").write_text(FIXTURE_COMPOSE, encoding="utf-8", newline="\n")
    (root / "app" / ".env.example").write_text("KE_ENV=dev\n", encoding="utf-8", newline="\n")
    (root / "app" / "scripts" / "launch.sh").write_text("#!/usr/bin/env bash\nexit 0\n",
                                                        encoding="utf-8", newline="\n")
    (root / "bundle.json").write_text(_bundle_json(FIXTURE_ENTRIES if entries is None else entries,
                                                   arch=arch),
                                      encoding="utf-8", newline="\n")
    _write_manifest(root)


# --------------------------------------------------------------------------
# The installers: install.sh (bash) and install.ps1 (pwsh)
# --------------------------------------------------------------------------

class _InstallBase:
    """Shared installer cases. Subclasses set `script` and `argv(bundle, target)`."""

    script: str

    def argv(self, bundle: Path, target: Path) -> list[str]:
        raise NotImplementedError

    def setUp(self) -> None:  # noqa: D401 - unittest hook
        t: Any = self
        t.assertTrue((ROOT / self.script).is_file(),
                     f"{self.script} is missing (PS-3.1: the installer is copied to the bundle root, "
                     "architecture §2.5 Bundle root)")
        self.tmp = Path(tempfile.mkdtemp())
        t.addCleanup(shutil.rmtree, self.tmp, True)
        fake_docker.install(self.tmp / "fakebin")
        self.log = self.tmp / "docker.log"
        self.json = self.tmp / "docker.jsonl"
        self.path = f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
        self.n = 0

    def _fresh(self, entries: list[dict[str, str]] | None = None, arch: str = "amd64"
               ) -> tuple[Path, Path]:
        """A new fixture bundle (header `arch`) and a target path that does not exist yet."""
        self.n += 1
        bundle = self.tmp / f"bundle{self.n}"
        _make_fixture(bundle, entries, arch)
        return bundle, self.tmp / f"target{self.n}"

    def argv_expect(self, bundle: Path, target: Path, sha: str) -> list[str]:
        """The installer asked to accept only a manifest whose sha256 is `sha` (security M-3)."""
        raise NotImplementedError

    def _env(self, **env: str) -> dict[str, str]:
        """Fresh fake-docker logs and the run environment."""
        for f in (self.log, self.json):
            f.write_text("", encoding="utf-8")
        run_env = {
            "PATH": self.path, "HOME": str(self.tmp),
            "FAKE_DOCKER_LOG": str(self.log), "FAKE_DOCKER_JSON": str(self.json),
            "FAKE_DOCKER_ENGINE": ENGINE_OK,
            "FAKE_COMPOSE_IMAGES": json.dumps(FIXTURE_STACK_IMAGES),
            "FAKE_DOCKER_LOAD": json.dumps({"ke-app.tar": f"Loaded image: {LOADED_APP_NAME}"}),
        }
        run_env.update(env)
        return run_env

    def _install(self, bundle: Path, target: Path, *, argv: list[str] | None = None,
                 umask: int | None = None, timeout: int = 120, **env: str
                 ) -> tuple[subprocess.CompletedProcess, list[list[str]], str]:
        run_env = self._env(**env)
        cmd = argv if argv is not None else self.argv(bundle, target)
        if umask is not None:
            cmd = ["bash", "-c", f"umask {umask:03o}; exec \"$@\"", "umask", *cmd]
        try:
            result = subprocess.run(cmd, env=run_env, cwd=bundle,
                                    capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            t: Any = self
            t.fail(f"the installer hung for {timeout}s (it read something it should have refused "
                   f"first, e.g. a fifo): {exc}")
        calls = [r["argv"] for r in fake_docker.records(self.json)]
        return result, calls, self.log.read_text(encoding="utf-8")

    @staticmethod
    def _out(result: subprocess.CompletedProcess) -> str:
        return (result.stdout or "") + (result.stderr or "")

    def _assert_refused_before_docker(self, result: subprocess.CompletedProcess, log: str,
                                      target: Path, name: str | None = None,
                                      rule: str | None = None) -> None:
        t: Any = self
        t.assertNotEqual(result.returncode, 0, "the installer accepted a tampered bundle:\n"
                         + self._out(result))
        t.assertEqual(log, "", "a docker command ran before the manifest check passed "
                      "(architecture §2.5 Install: until step 1 passes no docker command runs)")
        if name is not None:
            t.assertIn(name, self._out(result), "the refusal must name the bundle-relative path")
        if rule is not None:
            t.assertRegex(self._out(result).lower(), rule,
                          "the refusal must name its rule (architecture §2.5 Install, review B1); "
                          "a refusal by some other rule means the rule under test is not enforced")
        t.assertFalse(target.exists() and any(target.iterdir()),
                      "the installer wrote into the target after refusing")

    @staticmethod
    def _loads(calls: list[list[str]]) -> list[list[str]]:
        return [c for c in calls if c[:1] == ["load"] or c[:2] == ["image", "load"]]

    def _outside_dir(self) -> Path:
        d = self.tmp / f"outside{self.n}"
        d.mkdir(exist_ok=True)
        return d

    def _tamper_cases(self) -> dict[str, tuple[Any, str | None, str | None]]:
        """case -> (tamper(bundle), path the refusal names, rule regex it names)."""
        def changed(b: Path) -> None:
            p = b / "images" / "ke-app.tar"
            data = bytearray(p.read_bytes())
            data[0] ^= 0x01
            p.write_bytes(bytes(data))

        def missing(b: Path) -> None:
            (b / "app" / ".env.example").unlink()

        def unlisted(b: Path) -> None:
            (b / "app" / "extra.txt").write_text("not in the manifest\n", encoding="utf-8")

        def listed_symlink(b: Path) -> None:
            os.symlink("../images/ke-app.tar", b / "app" / "alias.tar")
            with open(b / "MANIFEST.sha256", "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"{_sha256(b / 'images' / 'ke-app.tar')}  app/alias.tar\n")

        def unlisted_dir_symlink(b: Path) -> None:
            # Review B1 / mutant m4: `find -type f` does not descend into a
            # linked directory, so only the link rule refuses this.
            outside = self._outside_dir()
            (outside / "secret.txt").write_text("outside the bundle\n", encoding="utf-8")
            os.symlink(str(outside), b / "app" / "evil")

        def unlisted_file_symlink(b: Path) -> None:
            os.symlink("../install.sh", b / "app" / "alias.sh")

        def fifo(b: Path) -> None:
            os.mkfifo(b / "app" / "pipe")

        def manifest_line(line: str) -> Any:
            def apply(b: Path) -> None:
                with open(b / "MANIFEST.sha256", "a", encoding="utf-8", newline="\n") as fh:
                    fh.write(line + "\n")
            return apply

        def duplicate(b: Path) -> None:
            first = (b / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()[0]
            manifest_line(first)(b)

        def listed_genuine(rel: str) -> Any:
            # A real file, listed with its real hash: only the name rule can refuse it.
            def apply(b: Path) -> None:
                (b / rel).write_text("genuine bytes\n", encoding="utf-8")
                _write_manifest(b)
            return apply

        h = _sha256(ROOT / "pyproject.toml")
        cases: dict[str, tuple[Any, str | None, str | None]] = {
            # PS-3.1 Tamper cases (a), (b), (c): each names the file.
            "a_changed_file": (changed, "images/ke-app.tar", RULE_HASH),
            "b_listed_file_missing": (missing, "app/.env.example", RULE_MISSING),
            "c_file_not_in_manifest": (unlisted, "app/extra.txt", RULE_UNLISTED),
            # Architecture §2.6 item 2: the other manifest rules (review B1:
            # each refusal names its rule and the bundle-relative path, N2).
            "symlink": (listed_symlink, "app/alias.tar", RULE_LINK),
            "unlisted_dir_symlink": (unlisted_dir_symlink, "app/evil", RULE_LINK),
            "unlisted_file_symlink": (unlisted_file_symlink, "app/alias.sh", RULE_LINK),
            "dotdot_path": (manifest_line(f"{h}  ../outside.txt"), "../outside.txt", RULE_DOT),
            "dot_path": (manifest_line(f"{h}  app/./extra.txt"), "app/./extra.txt", RULE_DOT),
            "leading_slash": (manifest_line(f"{h}  /etc/passwd"), "/etc/passwd", RULE_LEADING),
            "backslash": (manifest_line(f"{h}  app\\scripts\\launch.sh"), None, RULE_BACKSLASH),
            "malformed_line": (manifest_line(f"{h[:40]} app/docker-compose.yml"), None, RULE_MALFORMED),
            "duplicate_path": (duplicate, "app/.env.example", RULE_DUPLICATE),
            # Security I-1: names that resolve differently on Windows.
            "reserved_name_con": (listed_genuine("app/CON"), "app/CON", RULE_RESERVED),
            "reserved_name_nul_ext": (listed_genuine("app/nul.txt"), "app/nul.txt", RULE_RESERVED),
            "reserved_name_com1_mixed_case": (listed_genuine("app/Com1.log"), "app/Com1.log", RULE_RESERVED),
            "reserved_name_lpt9": (listed_genuine("app/lpt9"), "app/lpt9", RULE_RESERVED),
            "trailing_dot": (listed_genuine("app/notes."), "app/notes.", RULE_TRAILING),
            "colon": (listed_genuine("app/a:b"), None, RULE_CHARACTER),
            # Architecture §2.5: a segment ending in a space (Windows strips it).
            "trailing_space": (listed_genuine("app/notes "), "app/notes", RULE_TRAILING_SPACE),
        }
        if os.name == "nt":  # these names cannot be created on Windows; the gates image is Linux
            for k in [k for k in cases if k.startswith(("reserved_name", "trailing_dot", "trailing_space", "colon"))]:
                del cases[k]
        if hasattr(os, "mkfifo"):
            # Review N1: a fifo is refused by its own rule, in ps1 as in sh.
            cases["unlisted_fifo"] = (fifo, "app/pipe", RULE_FIFO)
        return cases

    # ---- PS-3.1 Tamper cases ------------------------------------------------

    def test_bundle_manifest_rejects_tamper(self):
        t: Any = self
        for case, (tamper, name, rule) in self._tamper_cases().items():
            with t.subTest(case=case):
                bundle, target = self._fresh()
                tamper(bundle)
                result, _, log = self._install(bundle, target, timeout=60)
                self._assert_refused_before_docker(result, log, target, name, rule)
        with t.subTest(case="control_untouched_bundle"):
            bundle, target = self._fresh()
            result, calls, _ = self._install(bundle, target)
            t.assertEqual(result.returncode, 0, self._out(result))
            t.assertTrue(calls, "the control install ran no docker command")
            t.assertEqual(calls[0][:1], ["info"], f"docker info must answer first; calls: {calls}")
            steps = [c for c in calls if c[:1] in (["load"], ["tag"]) or c[:2] == ["image", "inspect"]]
            expected_shape = []
            for entry in FIXTURE_ENTRIES:
                expected_shape += [("load", entry["file"]), ("tag", entry["as"]), ("inspect", entry["as"])]
            got_shape = []
            for c in steps:
                if c[0] == "load":
                    got_shape.append(("load", "images/" + c[-1].replace("\\", "/").rsplit("/", 1)[-1]))
                elif c[0] == "tag":
                    got_shape.append(("tag", c[-1]))
                else:
                    got_shape.append(("inspect", c[-1]))
            t.assertEqual(got_shape, expected_shape,
                          "per image, in bundle.json order: load -i <tar>, tag <loaded> <as>, "
                          f"image inspect <as> (architecture §2.6 item 2); calls: {calls}")

    def test_install_loads_nothing_when_manifest_fails(self):
        t: Any = self
        for case, (tamper, _, _) in self._tamper_cases().items():
            with t.subTest(case=case):
                bundle, target = self._fresh()
                tamper(bundle)
                result, calls, _ = self._install(bundle, target, timeout=60)
                t.assertNotEqual(result.returncode, 0, self._out(result))
                t.assertEqual(self._loads(calls), [], "docker load ran on a bundle that failed its manifest")
        with t.subTest(case="control_loads_each_tar_once"):
            bundle, target = self._fresh()
            result, calls, _ = self._install(bundle, target)
            t.assertEqual(result.returncode, 0, self._out(result))
            t.assertEqual(len(self._loads(calls)), len(FIXTURE_ENTRIES), calls)

    # ---- PS-3.1 bundle.json entries (install side) --------------------------

    def test_install_rejects_bundle_json_missing_field(self):
        t: Any = self
        for field in ("file", "ref", "as", "services"):
            with t.subTest(missing=field):
                entries = [dict(e) for e in FIXTURE_ENTRIES]
                del entries[1][field]
                bundle, target = self._fresh(entries)
                result, calls, _ = self._install(bundle, target)
                t.assertNotEqual(result.returncode, 0,
                                 f"accepted a bundle.json entry without `{field}`:\n{self._out(result)}")
                t.assertEqual(self._loads(calls), [], "rejected only after a docker load")
        for label, services in (("empty", ""), ("upper", "Postgres"), ("shell", "postgres;id"),
                                ("quote", 'postgres"')):
            with t.subTest(services=label):
                entries = [dict(e) for e in FIXTURE_ENTRIES]
                entries[1]["services"] = services
                bundle, target = self._fresh(entries)
                result, calls, _ = self._install(bundle, target)
                t.assertNotEqual(result.returncode, 0,
                                 f"accepted services={services!r}:\n{self._out(result)}")
                t.assertEqual(self._loads(calls), [], "rejected only after a docker load")

    # ---- architecture §2.6 item 3: target, daemon, bundle.json patterns -----

    def test_install_refuses_unfit_target_or_daemon(self):
        t: Any = self
        with t.subTest(case="non_empty_target"):
            bundle, target = self._fresh()
            target.mkdir()
            (target / "keep.txt").write_text("operator file\n", encoding="utf-8")
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertEqual(self._loads(calls), [])
            t.assertEqual(sorted(p.name for p in target.iterdir()), ["keep.txt"])
        with t.subTest(case="docker_info_fails"):
            bundle, target = self._fresh()
            result, calls, _ = self._install(bundle, target, FAKE_DOCKER_ENGINE_EXIT="1")
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertEqual(self._loads(calls), [])
        # Review N3 / security L-1: a target that is a link (a junction on
        # Windows) is refused, never followed; sh already refuses it.
        with t.subTest(case="target_is_link_to_empty_dir"):
            bundle, target = self._fresh()
            elsewhere = self._outside_dir()
            os.symlink(str(elsewhere), target)
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0, "installed through a linked target:\n" + self._out(result))
            t.assertEqual(self._loads(calls), [], "the target is checked before any load")
            t.assertEqual(list(elsewhere.iterdir()), [], "files landed in the link's destination")
        with t.subTest(case="target_is_dangling_link"):
            bundle, target = self._fresh()
            elsewhere = self.tmp / f"never{self.n}"
            os.symlink(str(elsewhere), target)
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0, "installed through a dangling link:\n" + self._out(result))
            t.assertEqual(self._loads(calls), [])
            t.assertFalse(elsewhere.exists(), "the dangling link's destination was created")
        # Review N7: first-party `as` must carry the header's git_sha[:12].
        with t.subTest(case="first_party_as_not_from_git_sha"):
            entries = [dict(e) for e in FIXTURE_ENTRIES]
            entries[0]["as"] = f"ke-app:bundle-{'f' * 12}"
            bundle, target = self._fresh(entries)
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0,
                             "accepted a first-party `as` whose sha12 is not the header git_sha:\n"
                             + self._out(result))
            t.assertIn(f"ke-app:bundle-{'f' * 12}", self._out(result), "the refusal names the `as`")
            t.assertEqual(self._loads(calls), [])
        # Review N7: the "names a service the stack does not have" path.
        with t.subTest(case="bundle_json_names_unknown_service"):
            entries = [dict(e) for e in FIXTURE_ENTRIES]
            entries[1]["services"] = "postgres ghost"
            bundle, target = self._fresh(entries)
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertIn("ghost", self._out(result), "the refusal names the service")
            t.assertEqual(self._loads(calls), [])
        bad_values = {
            "as_with_digest": ("as", f"{AS_PG}@sha256:{PG_DIGEST}"),
            "as_with_registry": ("as", f"registry.example.invalid:5000/{AS_PG}"),
            "ref_with_space": ("ref", "postgres:16 --help"),
            "as_with_dollar": ("as", "ke-vendor/postgres:$(id)"),
            "file_outside_images": ("file", "../postgres.tar"),
        }
        for case, (field, value) in bad_values.items():
            with t.subTest(case=case):
                entries = [dict(e) for e in FIXTURE_ENTRIES]
                entries[1][field] = value
                bundle, target = self._fresh(entries)
                result, calls, _ = self._install(bundle, target)
                t.assertNotEqual(result.returncode, 0, f"accepted {field}={value!r}:\n{self._out(result)}")
                t.assertEqual(self._loads(calls), [])
        with t.subTest(case="tar_not_in_bundle_json"):
            bundle, target = self._fresh()
            (bundle / "images" / "extra.tar").write_bytes(b"an image nobody listed\n")
            _write_manifest(bundle)
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertIn("extra.tar", self._out(result))
            t.assertEqual(self._loads(calls), [])
        with t.subTest(case="bundle_json_entry_without_tar"):
            bundle, target = self._fresh()
            (bundle / "images" / "postgres.tar").unlink()
            _write_manifest(bundle)
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertIn("postgres.tar", self._out(result))
            t.assertEqual(self._loads(calls), [])
        with t.subTest(case="malformed_bundle_json_line"):
            bundle, target = self._fresh()
            text = (bundle / "bundle.json").read_text(encoding="utf-8")
            (bundle / "bundle.json").write_text(text.replace('{"file": "images/postgres.tar"',
                                                             '{"file":"images/postgres.tar"'),
                                                encoding="utf-8", newline="\n")
            _write_manifest(bundle)
            result, calls, _ = self._install(bundle, target)
            t.assertNotEqual(result.returncode, 0,
                             "bundle.json lines must match the fixed §2.5 pattern:\n" + self._out(result))
            t.assertEqual(self._loads(calls), [])

    # ---- PS-3.1 Store-independent install (R2) ------------------------------

    def test_install_tags_loaded_image_as_bundle_name(self):
        t: Any = self
        with t.subTest(load="name_line_and_id_line"):
            bundle, target = self._fresh()
            result, calls, _ = self._install(bundle, target)
            t.assertEqual(result.returncode, 0, self._out(result))
            tags = [c for c in calls if c[:1] == ["tag"]]
            pg_id = hashlib.sha256((bundle / "images" / "postgres.tar").read_bytes()).hexdigest()
            t.assertIn(["tag", LOADED_APP_NAME, AS_APP], tags,
                       "a `Loaded image: <name>` line: tag that name as the entry's `as`")
            t.assertTrue(any(c[-1] == AS_PG and c[-2] in (f"sha256:{pg_id}", pg_id) for c in tags),
                         f"a `Loaded image ID: sha256:<id>` line: tag that id as `as`; tags: {tags}")
            t.assertIn(["image", "inspect", AS_APP], [c[:2] + c[-1:] for c in calls])
            t.assertIn(["image", "inspect", AS_PG], [c[:2] + c[-1:] for c in calls])
            joined = [" ".join(c) for c in calls]
            t.assertFalse([j for j in joined if ":local" in j],
                          "the installer never creates or moves a `:local` tag")
            t.assertFalse([c for c in calls if c[:1] in [[m] for m in MUTATING]
                           or c[:2] in (["image", "rm"], ["image", "prune"])],
                          f"no rm/rmi/pull/save is ever run by install; calls: {calls}")
            t.assertFalse([c for c in calls if c[:1] == ["inspect"] or
                           (c[:2] == ["image", "inspect"] and c[-1] not in (AS_APP, AS_PG))],
                          "image IDs are never compared: only `image inspect <as>` is run")
        for label, text in (("no_line", "Loaded: nothing useful\n"),
                            ("two_lines", f"Loaded image: {LOADED_APP_NAME}\n"
                                          f"Loaded image ID: sha256:{'b' * 64}\n")):
            with t.subTest(load=label):
                bundle, target = self._fresh()
                result, _, _ = self._install(bundle, target,
                                             FAKE_DOCKER_LOAD=json.dumps({"ke-app.tar": text}))
                t.assertNotEqual(result.returncode, 0, self._out(result))
                t.assertIn("ke-app.tar", self._out(result), "the failure must name the tar")
        # Security L-5: a genuine tar is saved from `as`, so a name line must
        # name `as`; a tar that names any other image is refused.
        with t.subTest(load="name_line_is_not_as"):
            bundle, target = self._fresh()
            result, calls, _ = self._install(
                bundle, target, FAKE_DOCKER_LOAD=json.dumps({"ke-app.tar": f"Loaded image: {WRONG_LOADED_NAME}"}))
            t.assertNotEqual(result.returncode, 0,
                             f"accepted a tar that loaded as {WRONG_LOADED_NAME}, not {AS_APP}:\n"
                             + self._out(result))
            t.assertIn("ke-app.tar", self._out(result), "the failure must name the tar")
            t.assertFalse([c for c in calls if c[:1] == ["tag"] and WRONG_LOADED_NAME in c],
                          "the wrongly named image was tagged as `as`")
            t.assertFalse(target.exists() and any(target.iterdir()), "wrote the target after refusing")
        with t.subTest(load="inspect_of_as_fails"):
            bundle, target = self._fresh()
            result, _, _ = self._install(bundle, target,
                                         FAKE_DOCKER_FAIL_NTH=f"inspect.*{re.escape(AS_PG)}#1")
            t.assertNotEqual(result.returncode, 0, self._out(result))

    # ---- PS-3.1 Compose override (R2) ---------------------------------------

    def test_install_override_maps_every_service_to_as_tag(self):
        import yaml

        t: Any = self
        bundle, target = self._fresh()
        result, _, _ = self._install(bundle, target)
        t.assertEqual(result.returncode, 0, self._out(result))
        for rel in ("docker-compose.yml", ".env.example", "scripts/launch.sh"):
            t.assertTrue((target / rel).is_file(), f"app/{rel} was not copied to the target")
        override = target / "docker-compose.override.yml"
        t.assertTrue(override.is_file(), "no docker-compose.override.yml in the target (§2.5 Install 7)")
        data = yaml.safe_load(override.read_text(encoding="utf-8"))
        t.assertEqual(data, {"services": {
            "api": {"image": AS_APP, "pull_policy": "never"},
            "worker": {"image": AS_APP, "pull_policy": "never"},
            "postgres": {"image": AS_PG, "pull_policy": "never"},
        }}, "every service in `services` maps to its `as` with pull_policy never, and nothing else")
        t.assertNotIn("@sha256:", override.read_text(encoding="utf-8"))

    def test_install_fails_when_service_has_no_bundle_entry(self):
        t: Any = self
        bundle, target = self._fresh([FIXTURE_ENTRIES[0]])
        (bundle / "images" / "postgres.tar").unlink()
        _write_manifest(bundle)
        result, calls, _ = self._install(bundle, target)
        t.assertNotEqual(result.returncode, 0,
                         "stack service postgres has no bundle.json entry, but install passed:\n"
                         + self._out(result))
        t.assertIn("postgres", self._out(result), "the failure must name the service")
        t.assertEqual(self._loads(calls), [], "review N7: refused only after a docker load")

    # ---- review N6: a failing `compose config --services` is fatal -----------

    def test_install_fails_when_compose_config_fails(self):
        t: Any = self
        bundle, target = self._fresh()
        result, calls, _ = self._install(bundle, target, FAKE_DOCKER_EXIT_AFTER="config --services")
        t.assertNotEqual(result.returncode, 0,
                         "`compose config --services` printed the services and exited 3, and the "
                         "installer carried on:\n" + self._out(result))
        t.assertEqual(self._loads(calls), [])
        t.assertFalse(target.exists() and any(target.iterdir()))

    # ---- security L-4: the manifest itself is checked before it is read ----

    def test_install_refuses_manifest_link_or_fifo(self):
        t: Any = self
        with t.subTest(case="manifest_is_symlink"):
            bundle, target = self._fresh()
            real = self._outside_dir() / "MANIFEST.sha256"
            shutil.move(str(bundle / "MANIFEST.sha256"), real)
            os.symlink(str(real), bundle / "MANIFEST.sha256")
            result, _, log = self._install(bundle, target, timeout=60)
            self._assert_refused_before_docker(result, log, target, "MANIFEST.sha256", RULE_LINK)
        # Architecture §2.5 (amended): MANIFEST.sha256 is a regular file of at
        # most 1 MiB, checked before it is read.
        with t.subTest(case="manifest_over_1_mib"):
            bundle, target = self._fresh()
            _pad_manifest(bundle / "MANIFEST.sha256", MANIFEST_CAP + 1)
            result, _, log = self._install(bundle, target, timeout=60)
            self._assert_refused_before_docker(result, log, target, "MANIFEST.sha256", RULE_SIZE)
        with t.subTest(case="manifest_exactly_1_mib_not_refused_by_cap"):
            bundle, target = self._fresh()
            _pad_manifest(bundle / "MANIFEST.sha256", MANIFEST_CAP)
            result, _, log = self._install(bundle, target, timeout=60)
            # Valid lines naming absent pad files: the missing-file rule refuses, not the cap.
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertEqual(log, "")
            t.assertNotRegex(self._out(result).lower(), RULE_SIZE,
                             "a manifest of exactly 1 MiB is within the cap")
            t.assertRegex(self._out(result).lower(), RULE_MISSING)
        if hasattr(os, "mkfifo"):
            with t.subTest(case="manifest_is_fifo"):
                bundle, target = self._fresh()
                (bundle / "MANIFEST.sha256").unlink()
                os.mkfifo(bundle / "MANIFEST.sha256")
                result, _, log = self._install(bundle, target, timeout=30)
                self._assert_refused_before_docker(result, log, target, "MANIFEST.sha256", RULE_FIFO)

    # ---- security M-2 / review N5: paths compare as ordinal strings ---------

    def test_install_refuses_case_variant_paths(self):
        t: Any = self
        probe = self.tmp / "case-dir"
        probe.mkdir()
        if not _case_sensitive(probe):
            t.skipTest("the filesystem under the temp dir is case-insensitive, so a case variant "
                       "cannot sit beside its original (the gates image is Linux, where it can)")
        with t.subTest(case="unlisted_case_variant_of_listed_file"):
            bundle, target = self._fresh()
            (bundle / "app" / "scripts" / "LAUNCH.sh").write_text("echo EVIL\n", encoding="utf-8")
            result, _, log = self._install(bundle, target)
            # Review P2 (rework round 2, docs/handoffs/platform-offline.md): a
            # present file that differs from a listed one only by case may be
            # refused by the case rule instead (sh now must, see
            # InstallShTest.test_install_sh_names_case_rule_for_present_case_variant).
            self._assert_refused_before_docker(result, log, target, "app/scripts/LAUNCH.sh",
                                               f"{RULE_UNLISTED}|{RULE_CASE}")
        with t.subTest(case="manifest_lists_case_variant_of_present_file"):
            bundle, target = self._fresh()
            m = bundle / "MANIFEST.sha256"
            m.write_text(m.read_text(encoding="utf-8").replace("  app/docker-compose.yml\n",
                                                               "  App/docker-compose.yml\n"),
                         encoding="utf-8", newline="\n")
            result, _, log = self._install(bundle, target)
            self._assert_refused_before_docker(result, log, target, None,
                                               f"{RULE_UNLISTED}|{RULE_MISSING}")
            t.assertRegex(self._out(result), r"(?:app|App)/docker-compose\.yml")
        if self.refuses_case_collisions:
            with t.subTest(case="two_listed_paths_equal_ignoring_case"):
                # The Windows target is case-insensitive: one would overwrite the other.
                bundle, target = self._fresh()
                (bundle / "app" / "scripts" / "LAUNCH.sh").write_text("echo OTHER\n", encoding="utf-8")
                _write_manifest(bundle)
                result, _, log = self._install(bundle, target)
                self._assert_refused_before_docker(result, log, target, None, RULE_CASE)
                t.assertRegex(self._out(result), r"app/scripts/(?:launch|LAUNCH)\.sh")

    refuses_case_collisions = False

    # ---- security M-1 / L-3: what is loaded and copied is what was verified -

    def _assert_verified_bytes_only(self, bundle: Path, target: Path, hooks: list[dict],
                                    evil: str) -> None:
        t: Any = self
        originals = {name: _sha256(bundle / "images" / name) for name in ("ke-app.tar", "postgres.tar")}
        launch = (bundle / "app" / "scripts" / "launch.sh").read_bytes()
        loaded_log = self.tmp / f"loaded{self.n}.log"
        result, _, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks),
                                     FAKE_DOCKER_LOADED_LOG=str(loaded_log))
        loaded = [ln.split() for ln in (loaded_log.read_text(encoding="utf-8").splitlines()
                                        if loaded_log.exists() else [])]
        evil_sha = hashlib.sha256(evil.encode("utf-8")).hexdigest()
        t.assertFalse([b for b, h in loaded if h == evil_sha],
                      "docker load read bytes changed after the manifest check (security M-1):\n"
                      + self._out(result))
        copied = target / "scripts" / "launch.sh"
        if copied.exists():
            t.assertEqual(copied.read_bytes(), launch,
                          "the target got app/ bytes changed after the manifest check (security M-1)")
        if result.returncode == 0:
            t.assertEqual(sorted(loaded), sorted([[n, h] for n, h in originals.items()]),
                          "an accepted install loads exactly the verified tars")
            t.assertTrue(copied.exists(), "an accepted install copies app/")

    def test_install_loads_and_copies_verified_bytes_only(self):
        t: Any = self
        evil = "EVIL bytes swapped in after the manifest check\n"
        with t.subTest(case="bundle_changed_after_info"):
            bundle, target = self._fresh()
            hooks = [{"on": r"^info\b", "write": {str(bundle / "images" / "ke-app.tar"): evil,
                                                    str(bundle / "app" / "scripts" / "launch.sh"): evil}}]
            self._assert_verified_bytes_only(bundle, target, hooks, evil)
        with t.subTest(case="hardlink_partner_changed_after_info"):
            # Security L-3: a hardlink lets someone outside the bundle change it.
            bundle, target = self._fresh()
            outside = self._outside_dir()
            for rel in ("images/ke-app.tar", "app/scripts/launch.sh"):
                partner = outside / rel.replace("/", "_")
                os.link(bundle / rel, partner)
            hooks = [{"on": r"^info\b", "write": {str(outside / "images_ke-app.tar"): evil,
                                                    str(outside / "app_scripts_launch.sh"): evil}}]
            self._assert_verified_bytes_only(bundle, target, hooks, evil)

    # ---- security L-2: the target is not followed if a link appears later --

    def test_install_does_not_follow_target_planted_during_load(self):
        t: Any = self
        bundle, target = self._fresh()
        elsewhere = self._outside_dir()
        hooks = [{"on": r"^(?:image )?load\b", "symlink": [str(target), str(elsewhere)]}]
        result, _, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        t.assertEqual(list(elsewhere.iterdir()), [],
                      "the installer followed a link planted at the target after its check:\n"
                      + self._out(result))
        if result.returncode == 0:
            t.assertFalse(target.is_symlink(), "an accepted install leaves a real directory")
            t.assertTrue((target / "docker-compose.override.yml").is_file())

    # ---- security L-6: no half-installed target ------------------------------

    def test_install_leaves_no_partial_target(self):
        t: Any = self
        bundle, target = self._fresh()
        # app/ ships a directory where the override goes: writing the override fails
        # after app/ was copied, unless the installer stages and renames.
        (bundle / "app" / "docker-compose.override.yml").mkdir()
        (bundle / "app" / "docker-compose.override.yml" / "x").write_text("x\n", encoding="utf-8")
        _write_manifest(bundle)
        result, _, _ = self._install(bundle, target)
        if result.returncode == 0:
            override = target / "docker-compose.override.yml"
            t.assertTrue(override.is_file(), "accepted, but no override file in the target")
        else:
            t.assertFalse(target.exists() and any(target.iterdir()),
                          "a failed install left a target with app/ but no override (security L-6): "
                          f"{sorted(p.name for p in target.iterdir()) if target.exists() else []}\n"
                          + self._out(result))

    # ---- security M-3: the accepted manifest hash, and --expect-manifest ----

    def test_install_prints_and_checks_manifest_hash(self):
        t: Any = self
        with t.subTest(case="prints_accepted_hash"):
            bundle, target = self._fresh()
            result, _, _ = self._install(bundle, target)
            t.assertEqual(result.returncode, 0, self._out(result))
            t.assertIn(_sha256(bundle / "MANIFEST.sha256"), result.stdout,
                       "the installer prints the sha256 of the manifest it accepted")
        with t.subTest(case="expect_manifest_matches"):
            bundle, target = self._fresh()
            sha = _sha256(bundle / "MANIFEST.sha256")
            result, _, _ = self._install(bundle, target, argv=self.argv_expect(bundle, target, sha))
            t.assertEqual(result.returncode, 0, self._out(result))
            t.assertTrue((target / "docker-compose.override.yml").is_file())
        with t.subTest(case="expect_manifest_mismatch"):
            bundle, target = self._fresh()
            sha = _sha256(bundle / "MANIFEST.sha256")
            wrong = ("0" if sha[0] != "0" else "1") + sha[1:]
            result, _, log = self._install(bundle, target, argv=self.argv_expect(bundle, target, wrong))
            self._assert_refused_before_docker(result, log, target, None, r"expect")
            t.assertIn(sha, self._out(result), "the refusal prints the actual manifest hash")
            t.assertIn(wrong, self._out(result),
                       "the refusal prints the expected value too (architecture §2.5 Install)")
        with t.subTest(case="expect_manifest_not_hex"):
            bundle, target = self._fresh()
            result, _, log = self._install(bundle, target, argv=self.argv_expect(bundle, target, "abc;id"))
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertEqual(log, "", "a docker command ran with a malformed --expect-manifest")

    # ---- security I-2: the override's mode does not come from the umask -----

    def test_install_writes_override_0644(self):
        t: Any = self
        if os.name == "nt":
            t.skipTest("POSIX file modes; the gates image is Linux")
        bundle, target = self._fresh()
        result, _, _ = self._install(bundle, target, umask=0o077)
        t.assertEqual(result.returncode, 0, self._out(result))
        mode = (target / "docker-compose.override.yml").stat().st_mode & 0o777
        t.assertEqual(oct(mode), oct(0o644),
                      "docker-compose.override.yml is written 0644 explicitly (security I-2)")

    # ---- finding F6 (smoke-gate loop 1): target modes ignore the build host --

    def _loosen_like_build_host(self, bundle: Path, variant: str) -> None:
        """Give the bundle the modes a build host leaves: `umask0002` is a
        umask-0002 Linux host (dirs 0775, files 0664, scripts 0775, image tars
        0600, as recorded on aria-gb10); `ntfs` is a tree copied off NTFS
        (every file 0755, as recorded on run 1); `umask0077` is a umask-0077
        host (dirs and scripts 0700, files 0600). Only `umask0077` is too
        tight for the copy's umask to fix, so under install umask 0022 it is
        the variant that tells the F6 chmods from none (audit-d1.md I-1)."""
        (bundle / "app" / "docs").mkdir(exist_ok=True)
        (bundle / "app" / "docs" / "quickstart.md").write_text("# Quickstart\n", encoding="utf-8", newline="\n")
        (bundle / "app" / "config").mkdir(exist_ok=True)
        (bundle / "app" / "config" / "settings.toml").write_text("x = 1\n", encoding="utf-8", newline="\n")
        (bundle / "app" / "scripts" / "teardown.sh").write_text("#!/usr/bin/env bash\nexit 0\n",
                                                                encoding="utf-8", newline="\n")
        _write_manifest(bundle)
        for p in sorted(bundle.rglob("*")):
            rel = _rel(p, bundle)
            if variant == "umask0077":
                p.chmod(0o700 if p.is_dir() or rel.startswith("app/scripts/") else 0o600)
            elif p.is_dir():
                p.chmod(0o775 if variant == "umask0002" else 0o755)
            elif variant == "ntfs":
                p.chmod(0o755)
            elif rel.startswith("images/"):
                p.chmod(0o600)
            elif rel.startswith("app/scripts/"):
                p.chmod(0o775)
            else:
                p.chmod(0o664)

    def test_install_target_modes_ignore_build_host_umask(self):
        """F6 (docs/evidence/platform-offline/recorded-runs.md): after install
        every directory of the target and every file under scripts/ is 0755
        and every other file 0644, whatever modes the bundle came with
        (aria-gb10, umask 0002: config/, docs/, scripts/ were installed 0775;
        run 1, off NTFS: docker-compose.yml and .env.example were 0755). Run
        under the install host's umask 0002 (aria-gb10 built and installed on
        one host) and 0022."""
        t: Any = self
        if os.name == "nt":
            t.skipTest("POSIX file modes; the gates image is Linux")
        for variant in ("umask0002", "ntfs", "umask0077"):
            for umask in (0o002, 0o022):
                with t.subTest(bundle=variant, install_umask=oct(umask)):
                    bundle, target = self._fresh()
                    self._loosen_like_build_host(bundle, variant)
                    result, _, _ = self._install(bundle, target, umask=umask)
                    t.assertEqual(result.returncode, 0, self._out(result))
                    wrong = []
                    for p in [target, *sorted(target.rglob("*"))]:
                        rel = "." if p == target else _rel(p, target)
                        mode = p.lstat().st_mode
                        if stat.S_ISDIR(mode):
                            want = 0o755
                        elif rel.startswith("scripts/"):
                            want = 0o755
                        else:
                            want = 0o644
                        if stat.S_IMODE(mode) != want:
                            wrong.append(f"{rel}: {oct(stat.S_IMODE(mode))} (want {oct(want)})")
                    t.assertEqual(wrong, [], "the installed target's modes must not come from the build host "
                                             "or the umask: directories and scripts 0755, other files 0644 (F6)")

    # ---- smoke-gate loop 2, F9: the `next:` line names the .env step -----------

    # The launch command the `next:` line ends with, and the .env copy it must
    # name first. Subclasses override.
    next_launch_rx: str = r"bash scripts/launch\.sh"
    next_env_copy_rx: str = r"\bcp\s+['\"]?\.env\.example['\"]?\s+['\"]?\.env\b"
    # Security L-L2e: the step that restricts .env to its owner. install.sh
    # says `chmod 600 .env`; install.ps1 overrides it.
    next_env_restrict_rx: str = r"\bchmod\s+0?600\s+['\"]?\.env\b"

    def test_install_next_line_creates_env_before_launch(self):
        """Smoke-gate loop 2, F9 (docs/evidence/platform-offline/recorded2-runs.md):
        the installer's closing `next:` line went straight to launch, skipping
        the `.env` step the quickstart requires (F1), so an operator who
        follows it runs with placeholder secrets and KE_ENV=dev. The one
        `next:` line must name creating `.env` from `.env.example` and setting
        real secrets in it, before the launch command."""
        t: Any = self
        bundle, target = self._fresh()
        result, _, _ = self._install(bundle, target)
        out = self._out(result)
        t.assertEqual(result.returncode, 0, out)
        nxt = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("next:")]
        t.assertEqual(len(nxt), 1, f"{self.script} prints one `next:` line:\n{out}")
        line = nxt[0]
        env_copy = re.search(self.next_env_copy_rx, line)
        t.assertIsNotNone(env_copy, f"the `next:` line must say to create .env from .env.example "
                                    f"(/{self.next_env_copy_rx}/) before launch (F9): {line!r}")
        t.assertRegex(line, r"(?i)\bsecrets?\b|\bpasswords?\b",
                      f"the `next:` line must say to set real secrets in .env before launch (F9): {line!r}")
        launch = [m.start() for m in re.finditer(self.next_launch_rx, line)]
        t.assertTrue(launch, f"the `next:` line must still name the launch command /{self.next_launch_rx}/: "
                             f"{line!r}")
        assert env_copy is not None
        t.assertLess(env_copy.start(), launch[-1],
                     f"the `next:` line must name the .env step before the launch command (F9): {line!r}")

    def test_install_next_line_restricts_env_before_launch(self):
        """Security L-L2e (docs/evidence/platform-offline/audit-l2.md): the
        `next:` line of install.sh names `chmod 600 .env`, but install.ps1's
        named only `Copy-Item`, so its operator puts real secrets into a file
        every local user may read. The one `next:` line names restricting
        `.env` to its owner (install.ps1: icacls in the `*<SID>` form, `chmod
        600 .env`, or a pointer to the quickstart step that does it), after
        the copy and before the launch command."""
        t: Any = self
        bundle, target = self._fresh()
        result, _, _ = self._install(bundle, target)
        out = self._out(result)
        t.assertEqual(result.returncode, 0, out)
        nxt = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("next:")]
        t.assertEqual(len(nxt), 1, f"{self.script} prints one `next:` line:\n{out}")
        line = nxt[0]
        restrict = re.search(self.next_env_restrict_rx, line)
        t.assertIsNotNone(restrict, f"the `next:` line must say to restrict .env to its owner "
                                    f"(/{self.next_env_restrict_rx}/) before secrets go in (L-L2e): {line!r}")
        assert restrict is not None
        t.assertNotIn("USERNAME", line.upper(), "an icacls grant names the SID, not the user name (L-L2c/e)")
        env_copy = re.search(self.next_env_copy_rx, line)
        launch = [m.start() for m in re.finditer(self.next_launch_rx, line)]
        t.assertIsNotNone(env_copy, f"precondition (F9): the `next:` line names the .env copy: {line!r}")
        t.assertTrue(launch, f"precondition (F9): the `next:` line names the launch command: {line!r}")
        assert env_copy is not None
        t.assertLess(env_copy.start(), restrict.start(),
                     f"the restriction must come after the .env copy (L-L2e): {line!r}")
        t.assertLess(restrict.start(), launch[-1],
                     f"the restriction must come before the launch command (L-L2e): {line!r}")

    # ---- architecture §2.5 Install: private staging, removed on every exit --

    def _staging_left(self, parent: Path) -> list[str]:
        return sorted(p.name for p in parent.iterdir() if p.name.startswith(STAGING_PREFIX))

    def test_install_stages_privately_in_target_parent(self):
        t: Any = self
        if os.name == "nt":
            t.skipTest("POSIX file modes; the gates image is Linux (the Windows ACL path is untested here)")
        bundle, target = self._fresh()
        snap = self.tmp / "staging-snapshot.jsonl"
        hooks = [{"on": r"^info\b", "list": [str(target.parent), str(snap), STAGING_PREFIX]}]
        # A permissive umask: 0700 must come from the installer, not the caller.
        result, _, _ = self._install(bundle, target, umask=0o022, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        t.assertEqual(result.returncode, 0, self._out(result))
        seen = [json.loads(ln) for ln in snap.read_text(encoding="utf-8").splitlines()] if snap.exists() else []
        t.assertEqual(len(seen), 1, "docker info ran once")
        t.assertEqual(len(seen[0]), 1,
                      f"exactly one {STAGING_PREFIX}* directory sits in the target's parent while docker "
                      f"runs (architecture §2.5 Install); found {seen[0]}")
        entry = seen[0][0]
        t.assertTrue(entry["dir"], f"the staging entry is a directory: {entry}")
        t.assertEqual(oct(entry["mode"]), oct(0o700), f"the staging directory is 0700: {entry}")

    def test_install_removes_staging_on_every_exit(self):
        t: Any = self
        cases = {
            "success": ({}, True),
            "manifest_refusal": ({}, False),
            "failed_load": ({"FAKE_DOCKER_FAIL": "load -i"}, False),
            "failed_info": ({"FAKE_DOCKER_ENGINE_EXIT": "1"}, False),
        }
        for case, (env, ok) in cases.items():
            with t.subTest(case=case):
                bundle, target = self._fresh()
                if case == "manifest_refusal":
                    (bundle / "app" / "extra.txt").write_text("unlisted\n", encoding="utf-8")
                result, _, _ = self._install(bundle, target, **env)
                t.assertEqual(result.returncode == 0, ok, self._out(result))
                t.assertEqual(self._staging_left(target.parent), [],
                              f"a {STAGING_PREFIX}* directory was left behind after {case}")
        if os.name == "nt":
            return
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            with t.subTest(case=f"interrupted_by_{sig.name}_during_load"):
                bundle, target = self._fresh()
                marker = self.tmp / f"loading{self.n}"
                hooks = [{"on": r"^load\b", "touch": str(marker), "sleep": 20}]
                proc = subprocess.Popen(self.argv(bundle, target), cwd=bundle,
                                        env=self._env(FAKE_DOCKER_HOOKS=json.dumps(hooks)),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        start_new_session=True)
                try:
                    for _ in range(600):
                        if marker.exists() or proc.poll() is not None:
                            break
                        import time
                        time.sleep(0.1)
                    t.assertTrue(marker.exists(), "the install never reached docker load")
                    t.assertTrue(self._staging_left(target.parent), "no staging directory during load")
                    os.killpg(proc.pid, sig)  # what a terminal sends: the whole process group
                    out, err = proc.communicate(timeout=60)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                t.assertEqual(self._staging_left(target.parent), [],
                              f"a {STAGING_PREFIX}* directory was left behind after {sig.name}:\n{out}{err}")
                t.assertFalse(target.exists(), "an interrupted install published the target")
                t.assertNotEqual(proc.returncode, 0,
                                 f"an install interrupted by {sig.name} exited 0 (success):\n{out}{err}")

    # ---- rework 2: review RB1 / security L-10 (+ P1): a signal to the pid ----

    def _wait_for(self, path: Path, proc: subprocess.Popen, seconds: int = 90) -> bool:
        import time
        for _ in range(seconds * 10):
            if path.exists() or proc.poll() is not None:
                break
            time.sleep(0.1)
        return path.exists()

    def test_install_stops_on_signal_to_its_own_pid(self):
        """SIGTERM or SIGHUP sent to the installer's pid only (not its group,
        so the docker child runs on) during load: the install stops, exits
        with a non-zero status of its own, publishes nothing and removes
        staging (review RB1, security L-10, nit P1). Also kills mutant i1
        (`[KeInterrupt]::Install()` removed), which leaves staging behind."""
        t: Any = self
        if os.name == "nt":
            t.skipTest("POSIX signals; the gates image is Linux")
        import signal

        for sig in (signal.SIGTERM, signal.SIGHUP):
            with t.subTest(signal=sig.name):
                bundle, target = self._fresh()
                marker = self.tmp / f"loading{self.n}"
                hooks = [{"on": r"^load\b", "touch": str(marker), "sleep": 3}]
                proc = subprocess.Popen(self.argv(bundle, target), cwd=bundle,
                                        env=self._env(FAKE_DOCKER_HOOKS=json.dumps(hooks)),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        start_new_session=True)
                try:
                    t.assertTrue(self._wait_for(marker, proc), "the install never reached docker load")
                    os.kill(proc.pid, sig)  # the installer alone
                    out, err = proc.communicate(timeout=90)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                t.assertFalse(target.exists(),
                              f"the install went on and published the target after {sig.name} to its pid "
                              f"(review RB1):\n{out}{err}")
                t.assertEqual(self._staging_left(target.parent), [],
                              f"a {STAGING_PREFIX}* directory was left behind after {sig.name} to the pid "
                              f"(review RB1; mutant i1):\n{out}{err}")
                t.assertGreater(proc.returncode, 0,
                                f"after {sig.name} the installer must clean up and exit with a non-zero "
                                f"status of its own, not 0 and not death by the signal (returncode "
                                f"{proc.returncode}; review RB1, nit P1):\n{out}{err}")

    # ---- rework 2: security H-1, staging swapped after verification --------

    def _lookalike(self) -> tuple[Path, str]:
        """A self-consistent bundle (its own manifest passes) with evil bytes."""
        evil = "EVIL tar planted in a lookalike staging dir\n"
        look = self.tmp / f"lookalike{self.n}"
        _make_fixture(look)
        (look / "images" / "ke-app.tar").write_text(evil, encoding="utf-8", newline="\n")
        (look / "images" / "postgres.tar").write_text(evil, encoding="utf-8", newline="\n")
        (look / "app" / "scripts" / "launch.sh").write_text("echo EVIL\n", encoding="utf-8", newline="\n")
        (look / "app" / "docker-compose.yml").write_text(
            FIXTURE_COMPOSE.replace("    image: ke-app:local\n", "    image: ke-app:local\n    privileged: true\n"),
            encoding="utf-8", newline="\n")
        _write_manifest(look)
        return look, evil

    def test_install_survives_staging_swap_after_verification(self):
        """Security H-1: someone who can rename entries in the target's parent
        renames the verified staging dir at `docker info` and plants a
        lookalike under its name. The installer must load and publish only
        the verified bytes, or refuse."""
        t: Any = self
        bundle, target = self._fresh()
        look, evil = self._lookalike()
        swaps = self.tmp / f"swaps{self.n}.log"
        loaded_log = self.tmp / f"loaded{self.n}.log"
        originals = {name: _sha256(bundle / "images" / name) for name in ("ke-app.tar", "postgres.tar")}
        launch = (bundle / "app" / "scripts" / "launch.sh").read_bytes()
        hooks = [{"on": r"^info\b", "swap": [str(target.parent), STAGING_PREFIX, str(look), str(swaps)]}]
        result, _, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks),
                                     FAKE_DOCKER_LOADED_LOG=str(loaded_log))
        out = self._out(result)
        did = swaps.read_text(encoding="utf-8") if swaps.exists() else ""
        if os.name != "nt":
            t.assertIn("swapped", did, f"the fake never swapped staging (no {STAGING_PREFIX}* at info?): {did}")
        loaded = [ln.split() for ln in (loaded_log.read_text(encoding="utf-8").splitlines()
                                        if loaded_log.exists() else [])]
        evil_sha = hashlib.sha256(evil.encode("utf-8")).hexdigest()
        t.assertFalse([b for b, h in loaded if h == evil_sha],
                      "docker load read the lookalike's tars: staging was reached again by its path "
                      "after verification (security H-1):\n" + out)
        copied = target / "scripts" / "launch.sh"
        if copied.exists():
            t.assertEqual(copied.read_bytes(), launch,
                          "the target got the lookalike's app/ (security H-1):\n" + out)
        compose = target / "docker-compose.yml"
        if compose.exists():
            t.assertNotIn("privileged", compose.read_text(encoding="utf-8"),
                          "the published compose file is the lookalike's (security H-1)")
        if result.returncode == 0:
            t.assertEqual(sorted(loaded), sorted([[n, h] for n, h in originals.items()]),
                          "an accepted install loads exactly the verified tars")
            t.assertTrue(copied.exists(), "an accepted install publishes app/")

    # ---- rework 2: security M-4, the script changed while it runs ----------

    appended_command: str = ""

    def test_install_ignores_script_changed_during_run(self):
        """Security M-4: a command appended to the bundle's installer while it
        runs (at `docker info`) must not execute."""
        t: Any = self
        bundle, target = self._fresh()
        injected = self.tmp / f"INJECTED{self.n}"
        name = Path(self.script).name
        hooks = [{"on": r"^info\b", "append": {str(bundle / name): self.appended_command % str(injected)}}]
        result, calls, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        t.assertTrue(calls and calls[0][:1] == ["info"], f"the run never reached docker info: {calls}")
        t.assertFalse(injected.exists(),
                      f"a command appended to {name} during the run executed: the script is read lazily "
                      "from the bundle dir (security M-4; wrap the body as main() {...}; main \"$@\"; exit)\n"
                      + self._out(result))

    # ---- rework 3: review RB3 / security M-4b, an in-place rewrite ---------

    inplace_prefix: str = ""

    def test_install_ignores_script_rewritten_in_place(self):
        """Review RB3, security M-4b: at `docker info` the bundle's installer
        is truncated and rewritten in place (same inode, same bytes up to its
        last line), with a command put in front of its last line. bash reads
        a script lazily, so a tail of `main "$@"` and `exit` on two lines
        runs the injected `touch ...; exit`; `main "$@"; exit` on ONE line is
        parsed whole before main runs. Also kills mutant unwrap (the main
        wrapper removed, the trailing `exit` kept)."""
        t: Any = self
        bundle, target = self._fresh()
        injected = self.tmp / f"INJECTED-INPLACE{self.n}"
        script = bundle / Path(self.script).name
        text = script.read_bytes().decode("utf-8")
        body = text.rstrip("\r\n")
        head, _, last = body.rpartition("\n")
        t.assertTrue(last.strip(), f"{script.name} has no last line")
        rewritten = f"{head}\n{self.inplace_prefix % str(injected)}{last}{text[len(body):] or chr(10)}"
        t.assertEqual(rewritten[:len(head)], text[:len(head)], "the rewrite keeps every byte before the last line")
        hooks = [{"on": r"^info\b", "write": {str(script): rewritten}}]
        result, calls, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        t.assertTrue(calls and calls[0][:1] == ["info"], f"the run never reached docker info: {calls}")
        t.assertEqual(script.read_text(encoding="utf-8"), rewritten, "the fake did not rewrite the script")
        t.assertFalse(injected.exists(),
                      f"a command written in place into the last line of {script.name} during the run executed "
                      f"(last line was {last!r}; review RB3, security M-4b: put `main \"$@\"; exit` on one line)\n"
                      + self._out(result))

    # ---- rework 2: security L-8, the target claimed with an exclusive mkdir -

    def test_install_claims_target_before_docker(self):
        """The target is claimed (an exclusive mkdir, 0700) before any docker
        call and stays a real directory throughout; a failed install removes
        the claim (security L-8, the mkdir-claim publish)."""
        t: Any = self
        if os.name == "nt":
            t.skipTest("POSIX file modes; the gates image is Linux")
        with t.subTest(case="claimed_at_info"):
            bundle, target = self._fresh()
            snap = self.tmp / f"claim{self.n}.jsonl"
            hooks = [{"on": r"^info\b", "list": [str(target.parent), str(snap), target.name]}]
            result, _, _ = self._install(bundle, target, umask=0o022, FAKE_DOCKER_HOOKS=json.dumps(hooks))
            t.assertEqual(result.returncode, 0, self._out(result))
            seen = [json.loads(ln) for ln in snap.read_text(encoding="utf-8").splitlines()] if snap.exists() else []
            mine = [e for row in seen for e in row if e["name"] == target.name]
            t.assertEqual(len(mine), 1, f"the target is not claimed while docker runs (security L-8): {seen}")
            t.assertTrue(mine[0]["dir"], f"the claim is a real directory: {mine[0]}")
            t.assertEqual(oct(mine[0]["mode"]), oct(0o700),
                          f"the claimed target is 0700 until publish: {mine[0]}")
            t.assertTrue(target.is_dir() and not target.is_symlink())
            t.assertTrue((target / "docker-compose.override.yml").is_file())
        with t.subTest(case="claim_removed_on_failure"):
            bundle, target = self._fresh()
            result, _, _ = self._install(bundle, target, FAKE_DOCKER_FAIL="load -i")
            t.assertNotEqual(result.returncode, 0, self._out(result))
            t.assertFalse(target.exists(), "a failed install left its claimed target behind")

    def test_install_refuses_target_replaced_during_load(self):
        """Security L-8: a directory or symlink planted at the target during
        load (the claim removed and replaced) is refused, and nothing lands in
        the planted directory or the link's destination."""
        t: Any = self
        for kind in ("dir", "symlink"):
            with t.subTest(planted=kind):
                bundle, target = self._fresh()
                victim = self._outside_dir()
                (victim / "sentinel").write_text("keep\n", encoding="utf-8")
                once = self.tmp / f"replaced-once{self.n}"
                done = self.tmp / f"replaced{self.n}.log"
                hook: dict[str, Any] = {"on": r"^(?:image )?load\b", "once": str(once),
                                        "replace": [str(target), kind, str(victim), str(done)]}
                planted = target / "planted-sentinel"
                if kind == "dir":
                    # Review N2: the planted directory holds a file of its owner's; cleanup must not
                    # remove a directory that lacks this run's claim marker (kills mutant clshc).
                    hook["write"] = {str(planted): "planted\n"}
                result, _, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps([hook]))
                out = self._out(result)
                t.assertIn("replaced", done.read_text(encoding="utf-8") if done.exists() else "",
                           "the fake could not plant at the target")
                t.assertNotEqual(result.returncode, 0,
                                 f"a {kind} planted at the target during load was accepted (security L-8):\n"
                                 + out)
                t.assertEqual(sorted(p.name for p in victim.iterdir()), ["sentinel"],
                              "something was written through the planted link (security L-8)")
                if kind == "dir":
                    t.assertTrue(planted.is_file() and planted.read_text(encoding="utf-8") == "planted\n",
                                 "the cleanup removed a directory planted at the target, with its owner's "
                                 "file: only the run's own claim (holding its marker) may be removed "
                                 "(review N2):\n" + out)
                    t.assertEqual(sorted(p.name for p in target.iterdir()), ["planted-sentinel"],
                                  "the app landed inside a directory planted at the target (security L-8)")
                t.assertFalse((target.parent / "app").exists())
                t.assertEqual(self._staging_left(target.parent), [])

    # ---- rework 2: security H-1 fix 3, a target parent others can write ----

    def test_install_flags_target_parent_others_can_write(self):
        """Security H-1 fix 3, round-4 ruling: a target parent that others can
        write (group-writable or world-writable, with or without the sticky
        bit) is REFUSED, by both installers on every platform, before any
        docker call, claim or staging; the refusal names the parent and the
        rule. An operator-only parent is not flagged.

        Amended in round 4 (orchestrator "unit-2 rework round 4/5" in
        docs/handoffs/platform-offline.md, POLICY CHANGE: refuse, which
        supersedes "warn, not refuse"; security H-2, review RB6). Before,
        install.sh warned and exited 0 here.

        Round 5 (review RB7 = security L-18): 0o1757 and 0o1703 are sticky,
        world-writable and NOT group-writable, so only the other-write rule
        can refuse them; install.ps1 off Windows exempted a sticky o+w
        parent and installed (1777 is refused anyway through group write)."""
        t: Any = self
        if os.name == "nt":
            t.skipTest("POSIX modes; the Windows ACL check is InstallPs1WindowsAclTest")
        rule = r"(?:others?|other users|group|world)[- ](?:can )?writ|writable by (?:others|group|other)"
        for mode in (0o777, 0o775, 0o770, 0o1757, 0o1703):
            with t.subTest(parent=oct(mode)):
                bundle, _ = self._fresh()
                parent = self.tmp / f"shared{self.n}"
                parent.mkdir()
                parent.chmod(mode)
                target = parent / "ke"
                result, _, log = self._install(bundle, target, argv=self.argv(bundle, target))
                out = self._out(result)
                t.assertRegex(out.lower(), rule,
                              f"a target parent with mode {oct(mode)} was used without naming the rule "
                              "(security H-1 fix 3, round-4 ruling)")
                t.assertNotEqual(result.returncode, 0,
                                 f"{self.script} installed under a parent with mode {oct(mode)}; it must refuse "
                                 "it (round-4 ruling: refuse, not warn):\n" + out)
                t.assertIn(str(parent), out, "the refusal names the parent")
                t.assertEqual(log, "", "docker ran under a refused parent (round-4 ruling)")
                t.assertFalse(target.exists(), "a refused parent got a claimed target (round-4 ruling)")
                t.assertEqual(self._staging_left(parent), [], "a refused parent got staging (round-4 ruling)")
        with t.subTest(parent="0o755"):
            bundle, _ = self._fresh()
            parent = self.tmp / f"private{self.n}"
            parent.mkdir()
            parent.chmod(0o755)
            target = parent / "ke"
            result, _, _ = self._install(bundle, target, argv=self.argv(bundle, target))
            t.assertEqual(result.returncode, 0, self._out(result))
            t.assertNotRegex(self._out(result).lower(), rule)

    # ---- rework 3: security I-7, a swapped staging is emptied ---------------

    def test_install_empties_swapped_staging(self):
        """Security I-7: after staging is renamed away and a lookalike planted
        under its name (the H-1 swap at `docker info`), the renamed original
        (the pinned working directory, holding the image tars) must be
        emptied from inside.

        Amended in round 5 (security M-7, orchestrator "escalated after
        round 4; human approved a SCOPED round 5/5" in
        docs/handoffs/platform-offline.md): staging is never removed
        recursively by name, so the lookalike under the staging name is no
        longer removed (whatever sits there is not this run's). Only the
        renamed original (`<staging>.swapped`) is checked; before, the
        lookalike had to be emptied too."""
        t: Any = self
        if os.name == "nt":
            t.skipTest("Windows refuses the rename of a pinned directory; the gates image is Linux")
        bundle, target = self._fresh()
        look, _ = self._lookalike()
        swaps = self.tmp / f"swaps{self.n}.log"
        hooks = [{"on": r"^info\b", "swap": [str(target.parent), STAGING_PREFIX, str(look), str(swaps)]}]
        result, _, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        out = self._out(result)
        did = swaps.read_text(encoding="utf-8") if swaps.exists() else ""
        t.assertIn("swapped", did, f"the fake never swapped staging: {did}")
        moved = [p for p in target.parent.iterdir()
                 if p.name.startswith(STAGING_PREFIX) and p.name.endswith(".swapped")]
        t.assertTrue(moved, f"no renamed original staging (*.swapped) in the parent: {did}")
        left = {p.name: sorted(str(q.relative_to(p)) for q in p.rglob("*")) for p in moved if p.is_dir()}
        t.assertEqual({k: v for k, v in left.items() if v}, {},
                      "the renamed original staging still holds the bundle (image tars, app/) after the run: "
                      "empty it from inside while it is still pinned (security I-7):\n" + out)

    # ---- rework 5: security M-7, staging is never removed recursively by name

    def test_install_never_removes_dir_renamed_into_staging_name(self):
        """Security M-7 (probes A2r/A10, W1r): at `docker info`, after the
        pin, staging is renamed away and a non-empty operator directory
        (a sibling, `notes/keep`) is renamed into the staging name. A
        fake-docker `rename` hook stands in for the racer (an ancestor
        writer in A10). Whatever the run's result, the cleanup must not
        delete that directory: the pinned staging is emptied from inside,
        and the name is removed only non-recursively (`rmdir` /
        `Directory.Delete(path, $false)`), never `rm -rf "$staging"` or
        `Remove-Item -Recurse`."""
        t: Any = self
        if os.name == "nt":
            t.skipTest("Windows refuses the rename of a pinned directory; the gates image is Linux")
        bundle, target = self._fresh()
        sibling = target.parent / f"operator-notes{self.n}"
        (sibling / "notes").mkdir(parents=True)
        (sibling / "notes" / "keep").write_text("operator data\n", encoding="utf-8")
        (sibling / "top.txt").write_text("top\n", encoding="utf-8")
        before = sorted(str(p.relative_to(sibling)) for p in sibling.rglob("*"))
        renames = self.tmp / f"renames{self.n}.log"
        hooks = [{"on": r"^info\b", "once": str(self.tmp / f"rename-once{self.n}"),
                  "rename": [str(target.parent), STAGING_PREFIX, str(sibling), str(renames)]}]
        result, _, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        out = self._out(result)
        did = renames.read_text(encoding="utf-8") if renames.exists() else ""
        m = re.search(r"^renamed (\S+)$", did, re.M)
        t.assertIsNotNone(m, f"the fake never renamed the sibling into the staging name (no {STAGING_PREFIX}* "
                             f"at info?): {did!r}\n{out}")
        assert m is not None
        landed = target.parent / m.group(1)
        t.assertTrue(landed.is_dir() and not landed.is_symlink(),
                     f"{self.script} deleted the operator directory renamed into the staging name {landed.name}: "
                     "the cleanup removes staging recursively by name (security M-7; use rmdir / "
                     "Directory.Delete(path, $false)):\n" + out)
        after = sorted(str(p.relative_to(landed)) for p in landed.rglob("*"))
        t.assertEqual(after, before, f"{self.script} emptied or changed the operator directory renamed into the "
                                     "staging name (security M-7):\n" + out)
        t.assertEqual((landed / "notes" / "keep").read_text(encoding="utf-8"), "operator data\n")

    # ---- rework 3: security L-12, the claim marker gone before publish ------

    def test_install_fails_when_claim_marker_deleted_before_publish(self):
        """Security L-12: the claim marker deleted after the last docker call
        (before publish) means the target is no longer this run's claim: the
        install exits non-zero and publishes nothing."""
        t: Any = self
        bundle, target = self._fresh()
        removed = self.tmp / f"removed{self.n}.log"
        hooks = [{"on": r"^image inspect\b", "remove": [str(target), ".ke-claim.", str(removed)]}]
        result, _, _ = self._install(bundle, target, FAKE_DOCKER_HOOKS=json.dumps(hooks))
        out = self._out(result)
        t.assertIn("removed .ke-claim.", removed.read_text(encoding="utf-8") if removed.exists() else "",
                   "the fake found no .ke-claim.* marker in the target at image inspect")
        t.assertNotEqual(result.returncode, 0,
                         "the install published into a target whose claim marker was deleted (security L-12):\n"
                         + out)
        t.assertFalse((target / "docker-compose.yml").exists(), "the app was published without the claim marker")

    # ---- PS-3.1 per-arch bundles (architecture §2.5 Arch, §2.6 item 5b) ----

    @staticmethod
    def _compose_configs(calls: list[list[str]]) -> list[list[str]]:
        return [c for c in calls if c[:1] == ["compose"] and "config" in c]

    def test_arch_normalisation(self):
        """`docker info` Architecture x86_64|amd64 -> amd64 and aarch64|arm64
        -> arm64; any other value is refused, naming it, before any load."""
        t: Any = self
        for daemon, arch in (("x86_64", "amd64"), ("amd64", "amd64"),
                             ("aarch64", "arm64"), ("arm64", "arm64")):
            with t.subTest(daemon=daemon, bundle=arch):
                bundle, target = self._fresh(arch=arch)
                result, calls, _ = self._install(bundle, target, FAKE_DOCKER_ARCH=daemon)
                t.assertEqual(result.returncode, 0,
                              f"a {arch} bundle on a daemon reporting {daemon} must install "
                              "(PS-3.1 Arch normalisation):\n" + self._out(result))
                t.assertEqual(len(self._loads(calls)), len(FIXTURE_ENTRIES), calls)
        for daemon in ("riscv64", "armv7l"):
            with t.subTest(daemon=daemon, bundle="amd64"):
                bundle, target = self._fresh(arch="amd64")
                result, calls, _ = self._install(bundle, target, FAKE_DOCKER_ARCH=daemon)
                t.assertNotEqual(result.returncode, 0,
                                 f"installed on a daemon whose arch is {daemon}:\n" + self._out(result))
                t.assertIn(daemon, self._out(result),
                           "the refusal names the unknown Architecture value (PS-3.1 Arch normalisation)")
                t.assertEqual(self._loads(calls), [], "a load ran on an unknown daemon arch")
                t.assertEqual(self._compose_configs(calls), [],
                              "compose config ran before the arch check (architecture §2.5 Install 5)")
                t.assertFalse(target.exists() and any(target.iterdir()))

    def test_install_refuses_arch_mismatch(self):
        """After `docker info` answers and before `compose config` or any
        load, the bundle's `arch` must equal the normalised daemon arch."""
        t: Any = self
        cases = {
            "amd64_bundle_on_aarch64": ("amd64", "aarch64", ("amd64",), ("arm64", "aarch64")),
            "arm64_bundle_on_x86_64": ("arm64", "x86_64", ("arm64",), ("amd64", "x86_64")),
        }
        for case, (arch, daemon, bundle_names, daemon_names) in cases.items():
            with t.subTest(case=case):
                bundle, target = self._fresh(arch=arch)
                result, calls, _ = self._install(bundle, target, FAKE_DOCKER_ARCH=daemon)
                out = self._out(result)
                t.assertNotEqual(result.returncode, 0,
                                 f"installed a {arch} bundle on a {daemon} daemon:\n" + out)
                t.assertTrue(any(n in out for n in bundle_names),
                             f"the refusal names the bundle's arch {arch}:\n{out}")
                t.assertTrue(any(n in out for n in daemon_names),
                             f"the refusal names the daemon's arch ({daemon}):\n{out}")
                t.assertTrue(calls and calls[0][:1] == ["info"], f"docker info answers first; calls: {calls}")
                t.assertEqual(self._loads(calls), [], "docker load ran on an arch mismatch")
                t.assertEqual(self._compose_configs(calls), [],
                              "compose config ran before the arch check (architecture §2.5 Install 5)")
                t.assertFalse(target.exists() and any(target.iterdir()),
                              "the installer wrote the target after an arch mismatch")
        with t.subTest(case="control_arm64_bundle_on_aarch64"):
            bundle, target = self._fresh(arch="arm64")
            result, calls, _ = self._install(bundle, target, FAKE_DOCKER_ARCH="aarch64")
            t.assertEqual(result.returncode, 0, self._out(result))
            t.assertEqual(len(self._loads(calls)), len(FIXTURE_ENTRIES), calls)
            t.assertTrue((target / "docker-compose.override.yml").is_file())


class InstallShTest(_InstallBase, unittest.TestCase):
    script = "scripts/install.sh"

    def argv(self, bundle: Path, target: Path) -> list[str]:
        return ["bash", str(bundle / "install.sh"), str(target)]

    def argv_expect(self, bundle: Path, target: Path, sha: str) -> list[str]:
        return ["bash", str(bundle / "install.sh"), "--expect-manifest", sha, str(target)]

    appended_command = "touch '%s'\n"
    inplace_prefix = "touch '%s'; "
    # The awk pass over MANIFEST.sha256 already refuses two listed paths equal
    # ignoring case (macOS APFS is case-insensitive too); pinned here.
    refuses_case_collisions = True

    # ---- rework 3: shims for one tool, ahead of the fake docker -------------

    def _shim(self, tool: str, body: str) -> Path:
        """A `#!/bin/sh` `tool` in its own directory; `REAL` in `body` is the real tool's path."""
        real = shutil.which(tool, path=os.environ.get("PATH", "/usr/bin:/bin"))
        self.assertIsNotNone(real, f"{tool} is not on PATH")
        d = self.tmp / f"shim-{tool}{self.n}"
        d.mkdir(exist_ok=True)
        shim = d / tool
        shim.write_text("#!/bin/sh\n" + body.replace("REAL", f"'{real}'"), encoding="utf-8", newline="\n")
        shim.chmod(0o755)
        return d

    # ---- rework 3: security L-11, staging checked after the cd --------------

    def test_install_sh_refuses_staging_loosened_before_cd(self):
        """Security L-11: between creating staging and the `cd` into it, a
        racer can loosen its mode. The installer must check the directory it
        is in after the `cd` (owner and mode 0700) and refuse before any
        docker call (round-3 ruling).

        Re-seated in round 4 (orchestrator "unit-2 rework round 4/5": no
        chmod of staging by name; mktemp -d creates it 0700). The old hook,
        a `chmod` shim on staging's name, is no longer reached. A `mktemp`
        shim now stands in for the racer: right after the real `mktemp -d`
        it loosens the SAME directory in place (no swap), so `pwd -P` equals
        staging and the directory is empty; only the owner/mode check after
        the cd can refuse it. Not covered by the H-2 test
        (`test_install_sh_never_empties_dir_swapped_in_for_staging`), whose
        swapped-in link is refused earlier by the `pwd -P` check."""
        if os.name == "nt":
            self.skipTest("POSIX modes; the gates image is Linux")
        for mode in ("0755", "0750", "0701"):
            with self.subTest(staging_mode=mode):
                bundle, target = self._fresh()
                racer = self.tmp / f"racer{self.n}.log"
                shimdir = self._shim("mktemp", f"""case " $* " in
  *" -d "*{STAGING_PREFIX}*)
    out="$(REAL "$@")" || exit $?
    if [ -d "$out" ] && [ ! -L "$out" ]; then chmod {mode} -- "$out" && echo "loosened $out" >> '{racer}'; fi
    printf '%s\\n' "$out"
    exit 0 ;;
esac
exec REAL "$@"
""")
                result, _, log = self._install(bundle, target, PATH=f"{shimdir}{os.pathsep}{self.path}")
                out = self._out(result)
                self.assertIn("loosened", racer.read_text(encoding="utf-8") if racer.exists() else "",
                              "the mktemp shim never saw `mktemp -d .../.ke-install.*`; update this test with "
                              "the code:\n" + out)
                self.assertNotEqual(result.returncode, 0,
                                    f"the installer worked inside a staging directory whose mode was {mode} after "
                                    "the cd: check `[ -O . ]` and mode 0700 right after `cd` (security L-11):\n"
                                    + out)
                self.assertEqual(log, "", f"docker ran from a staging directory that was {mode}, not 0700 "
                                          "(security L-11)")
                self.assertRegex(out.lower(), r"staging", "the refusal names staging")
                self.assertEqual(self._staging_left(target.parent), [])
                self.assertFalse(target.exists(), "the claimed target was left behind")

    # ---- rework 3: security L-13, a failed claim leaves no target -----------

    def test_install_sh_leaves_no_target_when_claim_mkdir_fails(self):
        """Security L-13: under Git Bash on NTFS, `mkdir -m 0700` creates the
        directory and then fails to set its mode ("cannot change
        permissions"). The install fails closed and must not leave an empty
        target behind. A `mkdir` shim does what Git Bash does."""
        if os.name == "nt":
            self.skipTest("the shim stands in for Git Bash; the gates image is Linux")
        bundle, target = self._fresh()
        seen = self.tmp / f"mkdir-m{self.n}.log"
        shimdir = self._shim("mkdir", f"""case " $* " in
  *" -m "*)
    for last in "$@"; do :; done
    REAL -- "$last" || exit 1
    echo "mkdir -m $last" >> '{seen}'
    echo "mkdir: cannot change permissions of '$last': Permission denied" >&2
    exit 1 ;;
esac
exec REAL "$@"
""")
        result, _, log = self._install(bundle, target, PATH=f"{shimdir}{os.pathsep}{self.path}")
        out = self._out(result)
        self.assertIn("mkdir -m", seen.read_text(encoding="utf-8") if seen.exists() else "",
                      "the claim no longer runs `mkdir -m`; update this test with the code:\n" + out)
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(log, "", "docker ran after the claim failed")
        self.assertFalse(target.exists(),
                         "a failed claim (`mkdir -m` created the directory, then failed) left an empty target "
                         "behind (security L-13)")
        self.assertEqual(self._staging_left(target.parent), [])

    # ---- rework 3b: security L-12, the target re-checked before chmod -----

    def test_install_sh_refuses_target_swapped_for_link_before_chmod(self):
        """Security L-12 (round-3 orchestrator item): `chmod 0755` on the
        target follows a symlink. An `rm` shim stands in for the racer: right
        after the real `rm` of the claim marker it renames the target away
        and puts a symlink to a 0700 victim directory in its place. The
        installer must re-check, right before the chmod, that the target is
        a real directory and not a link (`[ -d ] && [ ! -L ]`), exit
        non-zero, and leave the victim's mode alone. Behavioural: `rm` is an
        external tool, so a PATH shim reaches the marker-rm-to-chmod window."""
        if os.name == "nt":
            self.skipTest("POSIX modes and symlinks; the gates image is Linux")
        bundle, target = self._fresh()
        victim = self.tmp / f"victim{self.n}"
        victim.mkdir()
        victim.chmod(0o700)
        racer = self.tmp / f"rm-racer{self.n}.log"
        # Round 4 (security M-5): the marker may be removed by name or from inside the target
        # (`cd "$target"; rm -- "./$marker"`); the racer swaps the target's name either way.
        shimdir = self._shim("rm", f"""REAL "$@" || exit $?
for a in "$@"; do
  case "$a" in
    '{target}'/.ke-claim.* | ./.ke-claim.* | .ke-claim.*)
      if [ -d '{target}' ] && [ ! -L '{target}' ]; then
        mv -- '{target}' '{target}.swapped' && ln -s -- '{victim}' '{target}' && echo "swapped {target}" >> '{racer}'
      fi ;;
  esac
done
exit 0
""")
        result, _, _ = self._install(bundle, target, PATH=f"{shimdir}{os.pathsep}{self.path}")
        out = self._out(result)
        self.assertIn("swapped", racer.read_text(encoding="utf-8") if racer.exists() else "",
                      "the rm shim never saw the claim marker removed by name; update this test with the "
                      "code:\n" + out)
        self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o700,
                         "install.sh ran `chmod 0755` through a symlink that replaced the target after the "
                         "marker was removed: re-check `[ -d \"$target\" ] && [ ! -L \"$target\" ]` right "
                         "before the chmod (security L-12):\n" + out)
        self.assertNotEqual(result.returncode, 0,
                            "install.sh reported success although the target was a symlink at chmod time "
                            "(security L-12):\n" + out)
        self.assertTrue(target.is_symlink(), "the test's symlink should still be in place")

    # ---- rework 3: review N1, a parent owned by another user ----------------

    def test_install_sh_flags_parent_owned_by_another_user(self):
        """Review N1, architecture §2.5, round-4 ruling: install.sh REFUSES a
        target parent owned by neither the operator nor root, before any
        docker call, claim or staging, naming the parent and the rule. The
        gates run unprivileged, so no directory can be given to another
        user; an `id` shim reports the operator's uid as 4242 instead (§2.5
        names `find <parent> -prune ( -user <uid> -o -user 0 )`; the uid is
        read with `id -u`). Control: a root-owned 0755 parent is not flagged.

        Amended in round 4 (orchestrator "unit-2 rework round 4/5" in
        docs/handoffs/platform-offline.md, POLICY CHANGE: refuse, which
        supersedes "warn, not refuse"). Before, this warned and exited 0."""
        if os.name == "nt":
            self.skipTest("POSIX owners; the gates image is Linux")
        if os.geteuid() == 0:
            self.skipTest("running as root: the temp dir is root-owned, so it cannot stand for a parent "
                          "owned by another user (the gates run as uid 10001)")
        owner_rule = r"owned by|\bowner\b|writable by others|others? (?:can )?writ"
        asked = self.tmp / "id-u.log"
        shimdir = self._shim("id", f"""if [ "$*" = "-u" ]; then echo -u >> '{asked}'; echo 4242; exit 0; fi
exec REAL "$@"
""")
        path = f"{shimdir}{os.pathsep}{self.path}"
        with self.subTest(parent="owned by uid != operator, != root, mode 0755"):
            bundle, _ = self._fresh()
            parent = self.tmp / f"foreign{self.n}"
            parent.mkdir()
            parent.chmod(0o755)
            target = parent / "ke"
            result, _, log = self._install(bundle, target, argv=self.argv(bundle, target), PATH=path)
            out = self._out(result)
            self.assertTrue(asked.exists(), "install.sh never ran `id -u` for the operator's uid (§2.5):\n" + out)
            self.assertRegex(out.lower(), owner_rule,
                             "a target parent owned by neither the operator nor root was used without naming "
                             "the owner rule (review N1, architecture §2.5):\n" + out)
            self.assertIn(str(parent), out, "the refusal names the parent")
            self.assertNotEqual(result.returncode, 0,
                                "install.sh installed under a parent owned by another user; it must refuse it "
                                "(round-4 ruling: refuse, not warn):\n" + out)
            self.assertEqual(log, "", "docker ran under a refused parent (round-4 ruling)")
            self.assertFalse(target.exists(), "a refused parent got a claimed target (round-4 ruling)")
            self.assertEqual(self._staging_left(parent), [], "a refused parent got staging (round-4 ruling)")
        with self.subTest(parent="root-owned 0755 (control)"):
            root_dir = Path("/")
            self.assertEqual(root_dir.stat().st_uid, 0, "/ is not root-owned here")
            bundle, _ = self._fresh()
            target = root_dir / f"ke-n1-probe-{os.getpid()}-{self.n}"
            self.assertFalse(target.exists())
            self.addCleanup(lambda p=target: p.rmdir() if p.is_dir() else None)
            result, _, _ = self._install(bundle, target, argv=self.argv(bundle, target), PATH=path)
            self.assertNotRegex(self._out(result).lower(), owner_rule,
                                "a root-owned 0755 parent was flagged (§2.5: root is allowed)")

    # ---- rework 4: round-4 ruling, fail closed on an unreadable parent -----

    def test_install_sh_refuses_parent_it_cannot_check(self):
        """Round-4 ruling (orchestrator "unit-2 rework round 4/5"): any error
        reading the parent's owner or mode, or the operator's uid, means
        refusal (fail closed). Shims stand in for the failure: `ls`, `find`
        and `stat` fail when asked about the parent itself (whichever reads
        the owner/mode), and, separately, `id -u` fails. No docker call, no
        claim, no staging; the refusal names the parent."""
        if os.name == "nt":
            self.skipTest("POSIX owners and modes; the gates image is Linux")
        cannot = r"cannot|can't|could not|unable|failed"
        cases = {"owner_or_mode_unreadable": ("ls", "find", "stat"), "operator_uid_unreadable": ("id",)}
        for case, tools in cases.items():
            with self.subTest(case=case):
                bundle, _ = self._fresh()
                parent = self.tmp / f"unreadable{self.n}"
                parent.mkdir()
                parent.chmod(0o755)
                target = parent / "ke"
                failed = self.tmp / f"failed{self.n}.log"
                dirs = []
                for tool in tools:
                    if tool == "id":
                        body = f"""if [ "$*" = "-u" ]; then echo "id -u" >> '{failed}'; echo "id: failed" >&2; exit 1; fi
exec REAL "$@"
"""
                    else:
                        body = f"""for a in "$@"; do
  if [ "$a" = '{parent}' ] || [ "$a" = '{parent}/' ]; then
    echo "{tool} $*" >> '{failed}'; echo "{tool}: cannot access '$a': Input/output error" >&2; exit 1
  fi
done
exec REAL "$@"
"""
                    if shutil.which(tool, path=os.environ.get("PATH", "/usr/bin:/bin")) is None:
                        continue
                    dirs.append(str(self._shim(tool, body)))
                path = os.pathsep.join([*dict.fromkeys(dirs), self.path])
                result, _, log = self._install(bundle, target, argv=self.argv(bundle, target), PATH=path)
                out = self._out(result)
                self.assertTrue(failed.exists(),
                                f"install.sh never read the parent's owner/mode (or `id -u`) with {tools}; "
                                "update this test with the code:\n" + out)
                self.assertNotEqual(result.returncode, 0,
                                    f"install.sh went on although reading the parent ({case}) failed; it must "
                                    "refuse (round-4 ruling: fail closed):\n" + out)
                self.assertRegex(out.lower(), cannot, "the refusal says the check could not be made")
                self.assertIn(str(parent), out, "the refusal names the parent")
                self.assertEqual(log, "", "docker ran although the parent could not be checked")
                self.assertFalse(target.exists(), "a parent that could not be checked got a claimed target")
                self.assertEqual(self._staging_left(parent), [], "a parent that could not be checked got staging")

    # ---- rework 4: security H-2 / review RB6, staging swapped before the cd

    def test_install_sh_never_empties_dir_swapped_in_for_staging(self):
        """Security H-2, review RB6: right after `mktemp -d` creates staging,
        a racer renames it away and puts a symlink to a non-empty
        operator-owned directory under its name (`~/.ssh`). A `mktemp` shim
        stands in for the racer. The installer must not work in, copy into
        or empty that directory: pin staging only after `pwd -P` equals the
        staging path, the directory is empty, `-O`, mode 0700; never chmod
        staging by name. Two victims: 0700 (passes `-O`/drwx------ today)
        and 0755 (the chmod by name made it 0700 first, probe A2). The run
        exits non-zero, no docker command runs, and the victim keeps its
        files and its mode."""
        if os.name == "nt":
            self.skipTest("POSIX symlinks and modes; the gates image is Linux "
                          "(the Windows junction case is InstallPs1WindowsAclTest)")
        for mode in (0o700, 0o755):
            with self.subTest(victim=oct(mode)):
                bundle, target = self._fresh()
                victim = self.tmp / f"victim-ssh{self.n}"
                (victim / "sub").mkdir(parents=True)
                (victim / "id_ed25519").write_text("PRIVATE KEY\n", encoding="utf-8")
                (victim / "sub" / "keep").write_text("keep\n", encoding="utf-8")
                victim.chmod(mode)
                before = sorted(str(p.relative_to(victim)) for p in victim.rglob("*"))
                racer = self.tmp / f"mktemp-racer{self.n}.log"
                shimdir = self._shim("mktemp", f"""case " $* " in
  *" -d "*{STAGING_PREFIX}*)
    out="$(REAL "$@")" || exit $?
    mv -- "$out" "$out.moved" && ln -s -- '{victim}' "$out" && echo "swapped $out" >> '{racer}'
    printf '%s\\n' "$out"
    exit 0 ;;
esac
exec REAL "$@"
""")
                result, _, log = self._install(bundle, target, PATH=f"{shimdir}{os.pathsep}{self.path}")
                out = self._out(result)
                self.assertIn("swapped", racer.read_text(encoding="utf-8") if racer.exists() else "",
                              "the mktemp shim never saw `mktemp -d .../.ke-install.*`; update this test with "
                              "the code:\n" + out)
                after = sorted(str(p.relative_to(victim)) for p in victim.rglob("*"))
                self.assertEqual(after, before,
                                 "the operator's directory, swapped in under the staging name, was emptied or "
                                 "written into (security H-2, review RB6: pin only after pwd -P == staging, the "
                                 "directory is empty, -O and 0700):\n" + out)
                self.assertEqual((victim / "id_ed25519").read_text(encoding="utf-8"), "PRIVATE KEY\n")
                self.assertEqual(stat.S_IMODE(victim.stat().st_mode), mode,
                                 "the victim's mode changed: staging was chmod'ed by name through the link "
                                 "(security H-2 probe A2)")
                self.assertNotEqual(result.returncode, 0,
                                    "install.sh accepted a staging name that leads to another directory:\n" + out)
                self.assertEqual(log, "", "docker ran from a staging directory that was not the one created "
                                          "(security H-2)")
                self.assertFalse(target.exists(), "the claimed target was left behind")

    # ---- rework 4: security M-5, the target swapped right before chmod 0755

    def test_install_sh_never_chmods_a_target_swapped_at_publish(self):
        """Security M-5 (probe A6): at the `chmod 0755` that opens up the
        published target, a racer renames the target away and puts a
        symlink to a 0700 operator directory under its name. A `chmod` shim
        stands in for the racer: it swaps the name, then runs the real chmod
        on its arguments. The installer must open up the directory it
        published (cd into the target, check the marker and `-O .`, rm the
        marker, `chmod 0755 .`), leave the victim's mode alone, exit
        non-zero (the target's name no longer leads to what was published)
        and never print "installed to"."""
        if os.name == "nt":
            self.skipTest("POSIX symlinks and modes; the gates image is Linux")
        bundle, target = self._fresh()
        victim = self.tmp / f"victim-m5{self.n}"
        victim.mkdir()
        (victim / "private").write_text("keep\n", encoding="utf-8")
        victim.chmod(0o700)
        racer = self.tmp / f"chmod-racer{self.n}.log"
        shimdir = self._shim("chmod", f"""opening=0
for a in "$@"; do case "$a" in 0755 | 755 | a+rx | go+rx | u=rwx,go=rx) opening=1 ;; esac; done
if [ "$opening" = 1 ] && [ ! -e '{racer}' ]; then
  for a in "$@"; do
    hit=0
    case "$a" in
      '{target}' | '{target}/') hit=1 ;;
      . | ./) if [ "$(pwd -P)" = '{target}' ]; then hit=1; fi ;;
    esac
    if [ "$hit" = 1 ] && [ -d '{target}' ] && [ ! -L '{target}' ]; then
      mv -- '{target}' '{target}.swapped' && ln -s -- '{victim}' '{target}' && echo "swapped {target}" >> '{racer}'
    fi
  done
fi
exec REAL "$@"
""")
        result, _, _ = self._install(bundle, target, PATH=f"{shimdir}{os.pathsep}{self.path}")
        out = self._out(result)
        self.assertIn("swapped", racer.read_text(encoding="utf-8") if racer.exists() else "",
                      "the chmod shim never saw the target opened up (chmod 0755 of the target or of `.` inside "
                      "it); update this test with the code:\n" + out)
        self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o700,
                         "install.sh's `chmod 0755` followed a symlink swapped in for the target: the victim is "
                         "now 0755 (security M-5: cd into the target, check marker and -O ., chmod 0755 .):\n"
                         + out)
        self.assertNotEqual(result.returncode, 0,
                            "install.sh reported success although the target's name no longer leads to the "
                            "published directory (security M-5):\n" + out)
        self.assertNotIn("installed to", out, "a false success was printed (security M-5)")
        self.assertTrue(target.is_symlink(), "the test's symlink should still be in place")
        self.assertEqual(sorted(p.name for p in victim.iterdir()), ["private"], "the victim was written into")

    # ---- rework 5: review N11, the publish-time `-ef` check ------------------

    def test_install_sh_refuses_real_dir_swapped_in_at_publish(self):
        """Review N11 (probe dir_swap_at_publish): at `chmod 0755 .` inside
        the target, a racer renames the target away and makes a new, empty,
        REAL directory under its name. `pwd -P` of the name still equals the
        expected path, so only `[ "$target" -ef . ]` tells the published
        directory from the new one. A `chmod` shim stands in for the racer.
        The run exits non-zero and never prints "installed to". Pins the
        single `-ef` check that remains once the duplicate is dropped."""
        if os.name == "nt":
            self.skipTest("POSIX chmod and inodes; the gates image is Linux")
        bundle, target = self._fresh()
        racer = self.tmp / f"chmod-dir-racer{self.n}.log"
        shimdir = self._shim("chmod", f"""opening=0
for a in "$@"; do case "$a" in 0755 | 755 | a+rx | go+rx | u=rwx,go=rx) opening=1 ;; esac; done
if [ "$opening" = 1 ] && [ ! -e '{racer}' ]; then
  for a in "$@"; do
    hit=0
    case "$a" in
      '{target}' | '{target}/') hit=1 ;;
      . | ./) if [ "$(pwd -P)" = '{target}' ]; then hit=1; fi ;;
    esac
    if [ "$hit" = 1 ] && [ -d '{target}' ] && [ ! -L '{target}' ]; then
      mv -- '{target}' '{target}.away' && mkdir -- '{target}' && echo "swapped {target}" >> '{racer}'
    fi
  done
fi
exec REAL "$@"
""")
        result, _, _ = self._install(bundle, target, PATH=f"{shimdir}{os.pathsep}{self.path}")
        out = self._out(result)
        self.assertIn("swapped", racer.read_text(encoding="utf-8") if racer.exists() else "",
                      "the chmod shim never saw the target opened up (chmod 0755 of the target or of `.` inside "
                      "it); update this test with the code:\n" + out)
        self.assertNotEqual(result.returncode, 0,
                            "install.sh reported success although a different real directory now sits at the "
                            "target's name: keep `[ \"$target\" -ef . ]` after `chmod 0755 .` (review N11):\n" + out)
        self.assertNotIn("installed to", out, "a false success was printed (review N11)")
        self.assertRegex(out.lower(), r"no longer leads|replaced",
                         "the refusal says the target's name no longer leads to what was published:\n" + out)
        self.assertTrue(target.is_dir() and not target.is_symlink(), "the test's new directory should be in place")
        self.assertEqual(list(target.iterdir()), [], "install.sh wrote into the directory swapped in at publish")

    # ---- rework 5: security M-7, no recursive removal of staging by name -----

    def test_install_sh_never_removes_staging_recursively_by_name(self):
        """Security M-7: `rm -rf -- "$staging"` deletes whatever directory sits
        at the staging name at exit (an operator folder renamed in by an
        ancestor writer, probe A10). The pinned staging is emptied from
        inside; its name is removed with `rmdir` only. Static: no code line
        runs `rm` with a recursive flag (or `find ... -delete`) on
        `$staging`."""
        rx = re.compile(r"\brm\s+(?:-\w+\s+)*(?:-\w*[rR]\w*|--recursive)\b[^\n]*\$\{?staging\b"
                        r"|\bfind\s+[^\n]*\$\{?staging\b[^\n]*-delete\b")
        bad = [f"install.sh:{n}: {code.strip()}" for n, code in _code_lines((ROOT / self.script).read_text(
            encoding="utf-8")) if rx.search(code)]
        self.assertEqual(bad, [], "install.sh removes staging recursively by its name (security M-7): empty the "
                                  "pinned staging from inside, then `rmdir -- \"$staging\"`")

    # ---- rework 5: review N10, the stale sticky-parent comment ---------------

    def test_install_sh_comments_never_allow_a_sticky_parent(self):
        """Review N10 / security L-19: the round-4 rule refuses a sticky
        world-writable parent (1777, /tmp); no comment in install.sh may say
        such a parent is allowed. Consecutive comment lines are read as one
        text, since the stale sentence spans two lines."""
        blocks, cur = [], []
        for line in (ROOT / self.script).read_text(encoding="utf-8").splitlines():
            s = line.lstrip()
            if s.startswith("#") and not s.startswith("#!"):
                cur.append(s.lstrip("#").strip())
            else:
                m = re.search(r"\s#\s?(.*)$", line)
                if m and not cur:
                    blocks.append(m.group(1))
                if cur:
                    blocks.append(" ".join(cur))
                    cur = []
        if cur:
            blocks.append(" ".join(cur))
        rx = re.compile(r"(?i)\bsticky\b[^.;]{0,160}?\b(?:is|are|stays?|remains?)\s+(?:still\s+)?"
                        r"(?:allowed|accepted|permitted|exempt(?:ed)?|fine|ok(?:ay)?)\b"
                        r"|\b(?:allow|accept|permit|exempt)s?\b[^.;]{0,80}\bsticky\b")
        bad = [b for b in blocks if rx.search(b)]
        self.assertEqual(bad, [], "an install.sh comment says a sticky parent is allowed; the round-4 rule "
                                  "refuses it (review N10)")

    # ---- rework 4: review N6, the `next:` line --------------------------------

    def test_install_sh_next_line_runs_launch_with_bash(self):
        """Review N6: the quickstart says `bash scripts/launch.sh` so the
        file mode does not matter; install.sh's closing `next:` line says
        the same."""
        bundle, target = self._fresh()
        result, _, _ = self._install(bundle, target)
        out = self._out(result)
        self.assertEqual(result.returncode, 0, out)
        nxt = [ln for ln in (result.stdout or "").splitlines() if ln.startswith("next:")]
        self.assertEqual(len(nxt), 1, f"install.sh prints one `next:` line:\n{out}")
        # Smoke-gate loop 2, F9 (recorded2-runs.md; orchestrator ruling in the
        # platform-offline handoff, 2026-10-19: F9 gets fixed): the line now
        # names the .env step between `cd` and launch, so `&& bash` right after
        # the cd no longer holds. N6's point is kept: it ends by running
        # `bash scripts/launch.sh`, never `./scripts/launch.sh`.
        self.assertRegex(nxt[0], r"^next: cd .+\bbash scripts/launch\.sh\s*$",
                         "install.sh's next: line must run `bash scripts/launch.sh` (review N6)")

    # ---- security L-OC1b-a (audit-oc1b.md): an exported CDPATH ---------------

    def test_install_sh_ignores_exported_cdpath(self):
        """Security L-OC1b-a: install.sh's `unset CDPATH` survived every test.
        Run as `bash <relative>/install.sh` with `CDPATH=<decoy>:.` exported,
        where the decoy holds a valid lookalike bundle under the same relative
        name: the install passes and loads and copies its own bundle's bytes,
        never the decoy's (a relative `cd` would otherwise search CDPATH and
        print the directory it found)."""
        bundle, target = self._fresh()
        decoy_root = self.tmp / f"decoy{self.n}"
        decoy = decoy_root / bundle.name
        _make_fixture(decoy)
        (decoy / "images" / "ke-app.tar").write_bytes(b"DECOY ke-app image tar\n")
        (decoy / "app" / "scripts" / "launch.sh").write_text("#!/usr/bin/env bash\necho decoy\n",
                                                            encoding="utf-8", newline="\n")
        _write_manifest(decoy)
        loaded_log = self.tmp / f"loaded{self.n}.log"
        argv = ["bash", "-c", 'cd -- "$0" && exec bash "$@"', str(bundle.parent),
                f"{bundle.name}/install.sh", str(target)]
        result, calls, _ = self._install(bundle, target, argv=argv, CDPATH=f"{decoy_root}:.",
                                         FAKE_DOCKER_LOADED_LOG=str(loaded_log))
        out = self._out(result)
        self.assertEqual(result.returncode, 0, "install.sh failed under an exported CDPATH:\n" + out)
        loaded = sorted(ln.split() for ln in (loaded_log.read_text(encoding="utf-8").splitlines()
                                              if loaded_log.exists() else []))
        self.assertEqual(loaded, sorted([n, _sha256(bundle / "images" / n)] for n in ("ke-app.tar", "postgres.tar")),
                         "install.sh loaded tars that are not its own bundle's")
        copied = target / "scripts" / "launch.sh"
        self.assertTrue(copied.is_file(), "the install copied no app/")
        self.assertEqual(copied.read_bytes(), (bundle / "app" / "scripts" / "launch.sh").read_bytes(),
                         "install.sh copied the decoy's app/, not its own")
        self.assertNotIn(str(decoy_root), out, "install.sh entered the CDPATH decoy")

    # ---- review P2: a case collision is refused by the case rule ------------

    def test_install_sh_names_case_rule_for_present_case_variant(self):
        """Review P2: on a case-insensitive staging volume (macOS APFS) the
        copy of `LAUNCH.sh` beside `launch.sh` fails with a raw `cp` error.
        The bundle's own names are checked first (an awk tolower pass), so the
        refusal names the case rule, here on any filesystem."""
        probe = self.tmp / "case-dir"
        probe.mkdir()
        if not _case_sensitive(probe):
            self.skipTest("the filesystem under the temp dir is case-insensitive, so a case variant "
                          "cannot sit beside its original (the gates image is Linux, where it can)")
        bundle, target = self._fresh()
        (bundle / "app" / "scripts" / "LAUNCH.sh").write_text("echo EVIL\n", encoding="utf-8")
        result, _, log = self._install(bundle, target)
        self._assert_refused_before_docker(result, log, target, None, RULE_CASE)
        self.assertRegex(self._out(result), r"app/scripts/(?:launch|LAUNCH)\.sh")

    # ---- security L-9: relative or empty PATH entries ------------------------

    def test_install_sh_refuses_relative_or_empty_path_entries(self):
        """Security L-9: with an empty, `.` or relative PATH entry, a `mktemp`
        (or any tool) shipped in the bundle would run from the operator's cwd
        before the manifest check. install.sh refuses such a PATH before it
        runs anything."""
        if os.name == "nt":
            self.skipTest("POSIX PATH search; the gates image is Linux")
        bash = shutil.which("bash")
        self.assertIsNotNone(bash, "bash is not on PATH")
        tools = ("mktemp", "dirname", "ls", "find", "cp", "chmod", "awk", "wc", "tr", "rm", "df",
                 "sha256sum", "mv", "rmdir", "mkdir", "cat", "sed", "grep", "sort", "head")
        cases = {
            "leading_empty": lambda p: ":" + p,
            "trailing_empty": lambda p: p + ":",
            "middle_empty": lambda p: p.replace(os.pathsep, "::", 1) if os.pathsep in p else p + "::/bin",
            "dot": lambda p: "." + os.pathsep + p,
            "relative": lambda p: "bin" + os.pathsep + p,
        }
        for case, make in cases.items():
            with self.subTest(case=case):
                bundle, target = self._fresh()
                ran = self.tmp / f"bundle-tool-ran{self.n}"
                (bundle / "bin").mkdir()
                for d in (bundle, bundle / "bin"):
                    for tool in tools:
                        real = shutil.which(tool, path=os.environ.get("PATH", "/usr/bin:/bin"))
                        shim = d / tool
                        shim.write_text(f"#!/bin/sh\necho {tool} >> '{ran}'\n"
                                        + (f"exec '{real}' \"$@\"\n" if real else "exit 1\n"),
                                        encoding="utf-8", newline="\n")
                        shim.chmod(0o755)
                path = make(self.path)
                assert bash is not None
                result, _, log = self._install(bundle, target, argv=[bash, str(bundle / "install.sh"), str(target)],
                                               PATH=path)
                out = self._out(result)
                self.assertFalse(ran.exists(),
                                 f"a tool shipped in the bundle ran through PATH={path!r} "
                                 f"({sorted(set(ran.read_text(encoding='utf-8').split())) if ran.exists() else ''}; "
                                 "security L-9):\n" + out)
                self.assertNotEqual(result.returncode, 0, out)
                self.assertEqual(log, "", "docker ran with a relative or empty PATH entry")
                self.assertIn("PATH", out, "the refusal names PATH (security L-9)")
                self.assertRegex(out.lower(), r"relative|empty", "the refusal names the rule")
                self.assertEqual(self._staging_left(target.parent), [])
                self.assertFalse(target.exists() and any(target.iterdir()))

    # ---- security I-5: the piped unlisted-file check -------------------------

    def test_install_sh_piped_checks_exit_explicitly(self):
        """Security I-5: a `die` inside a `... | { ...; }` group runs in a
        subshell; the group's closing line carries `|| exit 1` (or `|| die`)
        so the refusal does not rest on errexit + pipefail alone."""
        lines = (ROOT / self.script).read_text(encoding="utf-8").splitlines()
        opened = [i for i, ln in enumerate(lines) if re.search(r"\|\s*\{\s*$", ln.split(" #")[0])]
        self.assertTrue(opened, "install.sh has no `| {` group; update this test with the code")
        for i in opened:
            indent = len(lines[i]) - len(lines[i].lstrip())
            end = next((j for j in range(i + 1, len(lines))
                        if lines[j].strip().startswith("}") and len(lines[j]) - len(lines[j].lstrip()) == indent),
                       None)
            with self.subTest(line=i + 1):
                self.assertIsNotNone(end, f"line {i + 1}: no closing brace")
                assert end is not None
                self.assertRegex(lines[end].strip(), r"^\}\s*\|\|\s*(?:exit\s+1|die\b)",
                                 f"line {end + 1}: the piped group at line {i + 1} must end `}} || exit 1` "
                                 "(security I-5)")


class InstallPs1Test(_InstallBase, unittest.TestCase):
    script = "scripts/install.ps1"

    def argv(self, bundle: Path, target: Path) -> list[str]:
        return ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(bundle / "install.ps1"),
                "-Target", str(target)]

    def argv_expect(self, bundle: Path, target: Path, sha: str) -> list[str]:
        return ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(bundle / "install.ps1"),
                "-Target", str(target), "-ExpectManifest", sha]

    # Security M-2: the Windows target is case-insensitive, so ps1 also refuses
    # two listed paths that are equal under OrdinalIgnoreCase.
    refuses_case_collisions = True
    appended_command = "New-Item -ItemType File -Path '%s' | Out-Null\n"
    inplace_prefix = "New-Item -ItemType File -Path '%s' | Out-Null; "
    # F9: install.ps1's `next:` line names launch.ps1, and `Copy-Item` (or cp)
    # for the .env step.
    next_launch_rx = r"launch\.ps1"
    next_env_copy_rx = (r"(?i)(?:\bCopy-Item|\bcp)\s+(?:-Path\s+)?['\"]?\.env\.example['\"]?\s+"
                        r"(?:-Destination\s+)?['\"]?\.env\b")
    # Security L-L2e: icacls by SID (L-L2c), chmod 600 off Windows, or a
    # pointer to the quickstart step that restricts .env.
    next_env_restrict_rx = (r"(?i)\bicacls(?:\.exe)?\s+['\"]?\.env\b[^;]*?/grant:r\s+['\"]?\*"
                            r"|\bchmod\s+0?600\s+['\"]?\.env\b"
                            r"|\bquickstart\b")

    def setUp(self) -> None:
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        super().setUp()

    # ---- rework 3: review RB5a, the ps1 PATH rule (security L-9) -----------

    def test_install_ps1_refuses_relative_or_empty_path_entries(self):
        """Review RB5a, security L-9 (twin of the sh test; kills mutant
        pspath): a relative or `.` PATH entry is refused, and so is an empty
        entry off Windows (on Windows an empty entry is dropped; see
        InstallPs1WindowsAclTest). The refusal names PATH and its rule, and
        no tool shipped in the bundle, and no docker, runs."""
        if os.name == "nt":
            self.skipTest("POSIX PATH search (the empty-entry refusal is the non-Windows rule); "
                          "the gates image is Linux")
        pwsh = shutil.which("pwsh")
        assert pwsh is not None
        tools = ("find", "df", "docker", "mktemp", "chmod", "ls")
        cases = {
            "relative": (lambda p: "bin" + os.pathsep + p, r"relative"),
            "dot": (lambda p: "." + os.pathsep + p, r"relative"),
            "leading_empty": (lambda p: os.pathsep + p, r"empty"),
            "trailing_empty": (lambda p: p + os.pathsep, r"empty"),
            "middle_empty": (lambda p: p.replace(os.pathsep, os.pathsep * 2, 1), r"empty"),
        }
        for case, (make, rule) in cases.items():
            with self.subTest(case=case):
                bundle, target = self._fresh()
                ran = self.tmp / f"bundle-tool-ran{self.n}"
                (bundle / "bin").mkdir()
                for d in (bundle, bundle / "bin"):
                    for tool in tools:
                        shim = d / tool
                        shim.write_text(f"#!/bin/sh\necho {tool} >> '{ran}'\nexit 1\n", encoding="utf-8",
                                        newline="\n")
                        shim.chmod(0o755)
                path = make(self.path)
                argv = [pwsh, *self.argv(bundle, target)[1:]]
                result, _, log = self._install(bundle, target, argv=argv, PATH=path)
                out = self._out(result)
                self.assertFalse(ran.exists(), f"a tool shipped in the bundle ran through PATH={path!r} "
                                               "(security L-9):\n" + out)
                self.assertNotEqual(result.returncode, 0,
                                    f"install.ps1 accepted PATH={path!r} (review RB5a, security L-9):\n" + out)
                self.assertEqual(log, "", "docker ran with a relative or empty PATH entry")
                self.assertIn("PATH", out, "the refusal names PATH (security L-9)")
                self.assertRegex(out.lower(), rule, "the refusal names the rule")
                self.assertEqual(self._staging_left(target.parent), [])
                self.assertFalse(target.exists(), "a refused PATH left a claimed target")

    # ---- rework 3: security L-12, the marker checked right before delete ---

    def test_install_ps1_checks_marker_exists_right_before_delete(self):
        """Security L-12: `[IO.File]::Delete` is silent when the file is
        missing, so a marker removed (or the target swapped) after the
        publish check went unnoticed and the run exited 0. The marker's
        existence is asserted in the few lines right before it is deleted.
        Static: the gap between the check and the delete cannot be hit from
        a docker hook (no docker call runs there)."""
        lines = (ROOT / self.script).read_text(encoding="utf-8").splitlines()
        deletes = [i for i, ln in enumerate(lines)
                   if re.search(r"File\]::Delete\(\s*\$markerPath\s*\)", ln) and not ln.lstrip().startswith("#")]
        self.assertEqual(len(deletes), 1, "install.ps1 should delete the claim marker once, as "
                                          "[System.IO.File]::Delete($markerPath); update this test with the code")
        window = "\n".join(lines[max(0, deletes[0] - 6):deletes[0]])
        self.assertRegex(window, r"(?:File\]::Exists|Get-EntryKind|Test-Path)\s*\(?\s*(?:-LiteralPath\s+)?\$markerPath",
                         "install.ps1 deletes the claim marker without checking, in the six lines before, that it "
                         "is still there (security L-12: File.Delete is silent on a missing file)")

    def test_install_ps1_rechecks_target_is_dir_right_before_chmod(self):
        """Security L-12: `[IO.File]::SetUnixFileMode($targetPath, ...)`
        follows a symlink, so a target swapped for a link after the publish
        check gets the link's destination set to 0755 and the run exits 0.
        The last SetUnixFileMode on the target must be preceded, within the
        six code lines before it, by `Get-EntryKind $targetPath` compared
        with 'dir' (Get-EntryKind reports a link as 'link', never 'dir').
        Static: between the marker delete and the chmod there are only .NET
        calls, so no docker hook or PATH shim can reach that window."""
        lines = (ROOT / self.script).read_text(encoding="utf-8").splitlines()
        code = [(i, ln) for i, ln in enumerate(lines) if ln.strip() and not ln.lstrip().startswith("#")]
        chmods = [k for k, (_, ln) in enumerate(code)
                  if re.search(r"SetUnixFileMode\(\s*\$targetPath\b", ln)]
        self.assertTrue(chmods, "install.ps1 no longer sets the target's mode with "
                                "[System.IO.File]::SetUnixFileMode($targetPath, ...); update this test with the code")
        last = chmods[-1]
        window = "\n".join(ln for _, ln in code[max(0, last - 6):last])
        self.assertRegex(window,
                         r"Get-EntryKind\s+\(?\s*\$targetPath\s*\)?\s*\)?\s*-(?:eq|ne)\s*'dir'",
                         "install.ps1 sets the target's mode without re-checking, in the six code lines before, "
                         "that the target is still a real directory and not a link "
                         "(Get-EntryKind $targetPath -eq 'dir'; security L-12: SetUnixFileMode follows links)")

    # ---- rework 3: review N1, GenericWrite / GenericAll on Windows ---------

    def test_install_ps1_counts_generic_write_rights(self):
        """Review N1, architecture §2.5: the Windows parent check counts
        GenericWrite and GenericAll as write rights. Static: NTFS maps a
        generic right to specific rights on an ACE that applies to the
        directory itself (probe: docs/evidence/platform-offline/
        tester-u2r3-generic-rights-probe.txt), so a Windows host cannot
        build such a parent; the check is pinned on the source.

        Round 4 (re-seated by the tester): the check now refuses rather than
        warns, so it is found by content, not by name. The parent check is
        the function that reads an ACL's access rules and builds an integer
        write mask (security M-6) holding a generic right; whatever it is
        called (e.g. `Assert-SafeParent`), that mask must hold both."""
        code = "\n".join(ln for ln in (ROOT / self.script).read_text(encoding="utf-8").splitlines()
                         if not ln.lstrip().startswith("#"))
        rights = (("GenericWrite", 0x40000000), ("GenericAll", 0x10000000))

        def holds(value: int, text: str) -> bool:
            return re.search(rf"(?i)\b0x{value:08x}L?\b|\b{value}L?\b", text) is not None

        functions: dict[str, str] = {}
        for m in re.finditer(r"(?m)^function\s+([\w-]+)", code):
            end = code.find("\n}\n", m.start())
            functions[m.group(1)] = code[m.start():end if end != -1 else len(code)]
        checks = {name: body for name, body in functions.items()
                  if re.search(r"(?i)GetAccessRules|Get-Acl\b|GetAccessControl", body)
                  and any(holds(v, body) for _, v in rights)}
        self.assertTrue(checks,
                        "no function in install.ps1 reads an ACL and builds a write mask holding GenericWrite "
                        "(0x40000000) or GenericAll (0x10000000) as integers (review N1, security M-6); "
                        f"functions seen: {sorted(functions)}")
        for fname, body in checks.items():
            for name, value in rights:
                with self.subTest(function=fname, right=name):
                    self.assertTrue(holds(value, body),
                                    f"{fname} (the parent ACL check) does not count {name} (0x{value:08x}) as a "
                                    "write right in its integer mask (review N1, architecture §2.5, security M-6)")

    # ---- rework 4: security M-6, the rights mask and the silent catch --------

    def test_install_ps1_never_casts_undefined_rights(self):
        """Security M-6: `[FileSystemRights]0x40000000` (GenericWrite) and
        `0x10000000` (GenericAll) are not defined enum values, so the cast
        THROWS in PowerShell, and the Windows parent check never fired.
        install.ps1 must build the mask from integers (e.g. `[long]` of the
        named rights `-bor 0x40000000L -bor 0x10000000L`, compared with
        `[long]$rule.FileSystemRights`), never cast an integer with bits
        outside the defined rights (0x001F01FF) to [FileSystemRights]."""
        code = "\n".join(ln.split("#", 1)[0] if ln.lstrip().startswith("#") else ln
                         for ln in (ROOT / self.script).read_text(encoding="utf-8").splitlines())
        defined = 0x001F01FF
        bad = [m.group(0) for m in re.finditer(
            r"\[(?:System\.Security\.AccessControl\.)?FileSystemRights\]\s*\(?\s*(0x[0-9A-Fa-f]+|\d+)", code)
            if int(m.group(1), 0) & ~defined]
        self.assertEqual(bad, [], "install.ps1 casts an integer outside the defined FileSystemRights to "
                                  "[FileSystemRights]; PowerShell throws on that cast (security M-6): use an "
                                  "integer mask")

    def test_install_ps1_acl_read_failure_is_not_silent(self):
        """Security M-6, round-4 ruling (fail closed): a `try` that reads an
        ACL or a Unix mode (GetAccessControl, Get-Acl, GetUnixFileMode,
        UnixStat) must not end in a `catch` that returns quietly; the catch
        refuses (Exit-WithError or throw). Static: the M-6 bug was exactly
        `catch { return }` hiding the throwing cast."""
        text = (ROOT / self.script).read_text(encoding="utf-8")
        self.assertRegex(text, r"GetAccessControl|Get-Acl\b",
                         "install.ps1 no longer reads an ACL; update this test with the code")
        pairs = _ps_try_catch(text)
        self.assertTrue(pairs, "no try/catch found in install.ps1; update this test with the code")
        reads = r"GetAccessControl|Get-Acl\b|GetUnixFileMode|UnixStat"
        for line, body, catch in pairs:
            if not re.search(reads, body):
                continue
            with self.subTest(try_at_line=line):
                self.assertRegex(catch, r"Exit-WithError|\bthrow\b",
                                 f"install.ps1:{line}: the catch after a try that reads an ACL/mode does not "
                                 f"refuse ({catch.strip()!r}); a failed read must refuse (round-4 ruling, "
                                 "security M-6)")

    # ---- rework 4: review N7, a non-empty staging is refused ----------------

    def test_install_ps1_refuses_non_empty_staging(self):
        """Review N7 (parity with RB6/H-2): right after staging is created, a
        file appears in it (the scratch copy of install.ps1 in the fixture
        bundle gets one line after `Initialize-PrivateDirectory $path` in
        Initialize-Staging). install.ps1 asserts staging is empty after
        `Set-Location`, before it pins, and refuses naming staging and
        that it is not empty; today the run goes on and refuses later by an
        unrelated rule (the manifest's "not listed")."""
        bundle, target = self._fresh()
        _insert_staging_hook(bundle / "install.ps1",
                             "New-Item -ItemType File -Path (Join-Path $path 'planted-by-racer') | Out-Null")
        _write_manifest(bundle)
        result, _, log = self._install(bundle, target)
        out = self._out(result)
        self.assertNotEqual(result.returncode, 0, "install.ps1 accepted a staging directory that was not empty:\n"
                            + out)
        self.assertEqual(log, "", "docker ran from a staging directory that was not empty")
        self.assertRegex(out.lower(), r"staging", "the refusal names staging (review N7)")
        self.assertRegex(out.lower(), r"not empty|non-empty|empty",
                         "the refusal says staging is not empty (review N7), not some later rule:\n" + out)
        self.assertFalse(target.exists(), "the claimed target was left behind")

    # ---- rework 5: security M-7, no recursive removal of staging by name -----

    def test_install_ps1_never_removes_staging_recursively_by_name(self):
        """Security M-7: `Remove-Item -LiteralPath $script:Staging -Recurse`
        in the finally deletes whatever directory sits at the staging name
        at exit (probe W1r). The pinned staging is emptied from inside; its
        name is removed non-recursively, `[System.IO.Directory]::Delete(
        $script:Staging, $false)` (or with no second argument). Static: no
        statement removes the staging path (or a variable copied from it)
        recursively: Remove-Item with -Recurse, Directory.Delete(..., $true),
        DirectoryInfo.Delete($true), or `rm -r`."""
        text = (ROOT / self.script).read_text(encoding="utf-8")
        code = [(n, ln) for n, ln in enumerate(text.splitlines(), 1) if not ln.lstrip().startswith("#")]
        names = {"script:Staging", "Staging"}
        for _, ln in code:
            m = re.match(r"\s*\$([\w:]+)\s*=\s*\$(?:script:)?Staging\b\s*$", ln)
            if m:
                names.add(m.group(1))
        ref = r"\$(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\b(?!\s*=[^=])"
        rx = re.compile(r"(?i)(?=[^\n]*" + ref + r")(?:[^\n]*\bRemove-Item\b[^\n]*-Recurse\b"
                        r"|[^\n]*\bDirectory\]::Delete\s*\([^\n]*,\s*\$true\b"
                        r"|[^\n]*\.Delete\s*\(\s*\$true\s*\)"
                        r"|[^\n]*\brm\s+(?:-\w+\s+)*-\w*[rR])")
        self.assertRegex(text, r"\$script:Staging\b", "install.ps1 no longer names $script:Staging; update this "
                                                       "test with the code")
        bad = [f"install.ps1:{n}: {ln.strip()}" for n, ln in code if rx.search(ln)]
        self.assertEqual(bad, [], "install.ps1 removes staging recursively by its name (security M-7): empty the "
                                  "pinned staging from inside, then [System.IO.Directory]::Delete($script:Staging, "
                                  "$false)")

    # ---- rework 4: security L-15, a parent owned by another user (off Windows)

    def test_install_ps1_refuses_parent_owned_by_another_user(self):
        """Security L-15, round-4 ruling: off Windows, install.ps1 refuses a
        target parent owned by neither the operator nor root, naming the
        parent and the owner rule, before any docker call or claim. Needs a
        directory on this host owned by another non-root uid and not
        group/world-writable; the test scans a few system places for one."""
        if os.name == "nt":
            self.skipTest("POSIX owners; the Windows parent rule is InstallPs1WindowsAclTest")
        foreign = _foreign_owned_dir()
        if foreign is None:
            self.skipTest("no directory owned by another non-root uid (and not group/world-writable) exists on "
                          "this host, so the ps1 owner rule (security L-15) cannot be exercised here")
        assert foreign is not None
        bundle, _ = self._fresh()
        target = foreign / f"ke-l15-probe-{os.getpid()}-{self.n}"
        self.assertFalse(target.exists())
        result, _, log = self._install(bundle, target)
        out = self._out(result)
        self.assertNotEqual(result.returncode, 0, out)
        self.assertRegex(out.lower(), r"owned by|\bowner\b",
                         f"install.ps1 did not refuse {foreign} (owner uid {foreign.stat().st_uid}) by the owner "
                         "rule (security L-15, round-4 ruling):\n" + out)
        self.assertIn(str(foreign), out, "the refusal names the parent")
        self.assertEqual(log, "", "docker ran under a parent owned by another user")
        self.assertFalse(target.exists())

    def test_install_ps1_session_recovers_after_signal(self):
        """Review RB1: run in-process (`& .\\install.ps1` in an open session),
        a SIGTERM during load fails that run cleanly; a second run in the same
        session then succeeds (`Fired` is reset), and once the script has
        returned the session dies on SIGTERM again (the registrations are
        disposed)."""
        if os.name == "nt":
            self.skipTest("POSIX signals; the gates image is Linux")
        import signal
        import time

        bundle1, target1 = self._fresh()
        bundle2, target2 = self._fresh()
        marker, ready = self.tmp / "run1-loading", self.tmp / "session-ready"
        hooks = [{"on": r"^load\b", "touch": str(marker), "sleep": 3}]
        script = "\n".join([
            "$env:FAKE_DOCKER_HOOKS = $env:KE_TEST_HOOKS_RUN1",
            f"Set-Location -LiteralPath '{bundle1}'",
            f"& '{bundle1 / 'install.ps1'}' -Target '{target1}'",
            "[Console]::Out.WriteLine('RUN1=' + $LASTEXITCODE)",
            "Remove-Item Env:FAKE_DOCKER_HOOKS",
            f"Set-Location -LiteralPath '{bundle2}'",
            f"& '{bundle2 / 'install.ps1'}' -Target '{target2}'",
            "[Console]::Out.WriteLine('RUN2=' + $LASTEXITCODE)",
            "[Console]::Out.Flush()",
            f"New-Item -ItemType File -Path '{ready}' | Out-Null",
            "Start-Sleep -Seconds 60",
            "[Console]::Out.WriteLine('SURVIVED')",
            "exit 7",
        ])
        env = self._env(KE_TEST_HOOKS_RUN1=json.dumps(hooks))
        proc = subprocess.Popen(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
                                cwd=self.tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        try:
            self.assertTrue(self._wait_for(marker, proc), "run 1 never reached docker load")
            os.kill(proc.pid, signal.SIGTERM)
            reached = self._wait_for(ready, proc, 120)
            if reached:
                time.sleep(0.5)
                os.kill(proc.pid, signal.SIGTERM)
            try:
                out, err = proc.communicate(timeout=30)
                hung = False
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                out, err = proc.communicate()
                hung = True
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        both = f"{out}{err}"
        run1 = re.search(r"^RUN1=(\S*)", out or "", re.M)
        run2 = re.search(r"^RUN2=(\S*)", out or "", re.M)
        self.assertIsNotNone(run1, "run 1 ended the whole session instead of returning:\n" + both)
        assert run1 is not None
        self.assertNotIn(run1.group(1), ("0", ""), "run 1 was interrupted but reported success:\n" + both)
        self.assertFalse(target1.exists(), "run 1 published its target after SIGTERM (review RB1):\n" + both)
        self.assertEqual(self._staging_left(target1.parent), [], "staging left behind:\n" + both)
        self.assertIsNotNone(run2, "the session never finished run 2:\n" + both)
        assert run2 is not None
        self.assertEqual(run2.group(1), "0",
                         "a clean second run in the same session failed: KeInterrupt.Fired was not reset "
                         "(review RB1):\n" + both)
        self.assertTrue((target2 / "docker-compose.override.yml").is_file(), both)
        self.assertTrue(reached, both)
        self.assertFalse(hung or "SURVIVED" in (out or ""),
                         "after install.ps1 returned, the session still ignores SIGTERM: the signal "
                         "registrations were not disposed (review RB1):\n" + both)

    def test_install_ps1_requires_pwsh_7_3(self):
        """Review RB2(b): Windows PowerShell 5.1 fails at Add-Type with a C#
        error; `CreateDirectory(path, UnixFileMode)` is .NET 7. The script
        says so up front."""
        text = (ROOT / self.script).read_text(encoding="utf-8")
        self.assertRegex(text, r"(?im)^#requires\s+-version\s+7\.3\s*$",
                         "install.ps1 lacks `#Requires -Version 7.3` (review RB2b)")

    def test_install_ps1_creates_windows_staging_with_its_acl(self):
        """Security H-1 fix 1: on Windows, staging is created with its
        protected DACL in one call (FileSystemAclExtensions.Create /
        CreateDirectory with a DirectorySecurity), never created first and
        protected afterwards with Set-Acl (the window in which Authenticated
        Users hold Modify under C:\\). Static: the gates image has no Windows
        ACLs; InstallPs1WindowsAclTest checks the behaviour on a Windows host."""
        code = "\n".join(ln for ln in (ROOT / self.script).read_text(encoding="utf-8").splitlines()
                         if not ln.lstrip().startswith("#"))
        self.assertRegex(code, r"FileSystemAclExtensions\]::Create(?:Directory)?\s*\(",
                         "install.ps1 does not create Windows staging with its ACL in one call (security H-1)")
        self.assertNotRegex(code, r"(?i)\bSet-Acl\b",
                            "install.ps1 still protects staging after creating it (Set-Acl; security H-1)")


def _insert_staging_hook(script: Path, hook: str) -> None:
    """Puts `hook` (one PowerShell line) right after `Initialize-PrivateDirectory
    $path` in Initialize-Staging of a scratch copy of install.ps1: a racer's
    move at the instant staging exists (security probe W1's hooked copy).
    Only fixture copies are edited, never scripts/install.ps1."""
    lines = script.read_bytes().decode("utf-8").splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if re.match(r"\s*function\s+Initialize-Staging\b", ln)), None)
    if start is None:
        raise AssertionError("install.ps1 has no Initialize-Staging function; update this test with the code")
    at = next((i for i in range(start, len(lines))
               if re.match(r"\s*(?:\[void\]\s*)?Initialize-PrivateDirectory\s+\$path\b", lines[i])), None)
    if at is None:
        raise AssertionError("Initialize-Staging no longer calls `Initialize-PrivateDirectory $path`; update "
                             "this test with the code")
    indent = lines[at][:len(lines[at]) - len(lines[at].lstrip())]
    eol = "\r\n" if lines[at].endswith("\r\n") else "\n"
    lines.insert(at + 1, f"{indent}{hook}{eol}")
    script.write_bytes("".join(lines).encode("utf-8"))


def _ps_match_brace(text: str, i: int) -> int:
    """Index of the `}` closing the `{` at `i`, skipping PowerShell strings,
    here-strings and `#` comments."""
    depth, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("@'", i) or text.startswith('@"', i):
            close = "\n" + text[i + 1] + "@"
            j = text.find(close, i + 2)
            i = n if j == -1 else j + len(close)
            continue
        if c == "'":
            j = i + 1
            while j < n and not (text[j] == "'" and text[j + 1:j + 2] != "'"):
                j += 2 if text[j] == "'" else 1
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "`" else 1
            i = j + 1
            continue
        if c == "#":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _ps_try_catch(text: str) -> list[tuple[int, str, str]]:
    """(line, try body, catch body) for each `try { } catch [..] { }` in a
    PowerShell source; a try with several catches yields one tuple each."""
    out = []
    for m in re.finditer(r"(?m)(?<![\w-])try\s*\{", text):
        if text[:m.start()].rsplit("\n", 1)[-1].lstrip().startswith("#"):
            continue
        open_at = m.end() - 1
        close = _ps_match_brace(text, open_at)
        if close == -1:
            continue
        body = text[open_at + 1:close]
        rest = close + 1
        while True:
            c = re.match(r"\s*catch\s*(?:\[[^\]]+\]\s*,?\s*)*\{", text[rest:])
            if not c:
                break
            c_open = rest + c.end() - 1
            c_close = _ps_match_brace(text, c_open)
            if c_close == -1:
                break
            out.append((text.count("\n", 0, m.start()) + 1, body, text[c_open + 1:c_close]))
            rest = c_close + 1
    return out


def _foreign_owned_dir() -> Path | None:
    """A directory owned by a uid other than root and this process, that is
    not group- or world-writable (POSIX only), or None."""
    me = os.geteuid()  # type: ignore[attr-defined]
    for base in (Path("/"), Path("/var"), Path("/var/lib"), Path("/var/cache"), Path("/var/spool"),
                 Path("/home"), Path("/opt"), Path("/srv"), Path("/usr/local")):
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for p in entries:
            try:
                st = p.lstat()
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode) and st.st_uid not in (0, me) and not st.st_mode & 0o022:
                return p
    return None


class InstallPs1WindowsAclTest(unittest.TestCase):
    """Security H-1 on a Windows host: under a parent that grants
    Authenticated Users an inheritable Modify ACE (as `C:\\` does), the
    staging directory never carries an inherited ACE, not even for an
    instant. A poller reads each `.ke-install.*` DACL as soon as it appears.
    Windows only: the gates image is Linux, so `scripts/verify.sh` never runs
    it; run it on a Windows host with pwsh 7.3+."""

    def setUp(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows ACLs: runs only on a Windows host with pwsh; the gates image is "
                          "Linux, so verify.sh skips it (security H-1)")
        if shutil.which("pwsh") is None:
            self.fail(PWSH_MISSING)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    @staticmethod
    def _sddl(path: str) -> str | None:
        import ctypes
        from ctypes import wintypes

        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        sd = ctypes.c_void_p()
        info = 0x1 | 0x4  # OWNER | DACL
        rc = advapi.GetNamedSecurityInfoW(wintypes.LPCWSTR(path), 1, info, None, None, None, None,
                                          ctypes.byref(sd))
        if rc != 0:
            return None
        text = wintypes.LPWSTR()
        try:
            if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    sd, 1, info, ctypes.byref(text), None):
                return None
            value = text.value
            kernel.LocalFree(text)
            return value
        finally:
            kernel.LocalFree(sd)

    def _fake_env(self, tag: str) -> tuple[dict[str, str], Path]:
        """The run environment with the fake docker (via docker.cmd) first on
        PATH, and the fake's call log."""
        fake = fake_docker.install(self.tmp / f"fakebin-{tag}")
        winbin = self.tmp / f"winbin-{tag}"
        winbin.mkdir()
        (winbin / "docker.cmd").write_text(f'@"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
        log = self.tmp / f"docker-{tag}.log"
        log.write_text("", encoding="utf-8")
        env = {**os.environ, "PATH": f"{winbin}{os.pathsep}{os.environ.get('PATH', '')}",
               "FAKE_DOCKER_LOG": str(log), "FAKE_DOCKER_ENGINE": ENGINE_OK,
               "FAKE_COMPOSE_IMAGES": json.dumps(FIXTURE_STACK_IMAGES),
               "FAKE_DOCKER_LOAD": json.dumps({"ke-app.tar": f"Loaded image: {LOADED_APP_NAME}"})}
        return env, log

    def _run_ps1(self, bundle: Path, target: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
        return subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(bundle / "install.ps1"),
                               "-Target", str(target)],
                              cwd=bundle, env=env, capture_output=True, text=True, timeout=300)

    def _assert_parent_refused(self, parent: Path, what: str) -> None:
        bundle = self.tmp / f"bundle-{parent.name}"
        _make_fixture(bundle)
        env, log = self._fake_env(parent.name)
        target = parent / "ke"
        result = self._run_ps1(bundle, target, env)
        out = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0,
                            f"install.ps1 installed under a parent where {what}; it must refuse it (round-4 "
                            "ruling, orchestrator \"unit-2 rework round 4/5\"; security M-6):\n" + out)
        self.assertIn(str(parent), out, "the refusal names the parent")
        self.assertRegex(out.lower(), r"(?:others?|other users|group|world|another account)[- ](?:can )?writ"
                                      r"|writable by", "the refusal names the rule")
        self.assertEqual(log.read_text(encoding="utf-8"), "", "docker ran under a refused parent")
        self.assertFalse(target.exists(), "a refused parent got a claimed target")
        self.assertEqual([p.name for p in parent.iterdir() if p.name.startswith(STAGING_PREFIX)], [],
                         "a refused parent got staging")

    def test_parent_granting_authenticated_users_modify_is_refused(self):
        """Round-4 ruling (orchestrator "unit-2 rework round 4/5", POLICY
        CHANGE): a parent whose DACL gives Authenticated Users Modify (as
        `C:\\` does) is REFUSED before any docker call, claim or staging.
        This replaces the old expectation (test_staging_never_inherits_an_ace
        installed under such a parent and exited 0), by that ruling."""
        parent = self.tmp / "au-modify-parent"
        parent.mkdir()
        subprocess.run(["icacls", str(parent), "/grant", "*S-1-5-11:(OI)(CI)M"], check=True,
                       capture_output=True)
        self._assert_parent_refused(parent, "Authenticated Users hold Modify")

    def test_parent_others_can_create_in_is_refused(self):
        """Security M-6 (probes W2, W3), behavioural: an Everyone
        CreateDirectories (AD) ACE, or an Everyone GenericWrite ACE (NTFS
        stores it as FW), on the parent is refused. Today the rights-mask
        cast throws inside the check and `catch { return }` hides it, so
        these parents install silently."""
        for case, grant in (("everyone_create_directories", "*S-1-1-0:(AD)"),
                            ("everyone_generic_write", "*S-1-1-0:(GW)")):
            with self.subTest(case=case):
                parent = self.tmp / f"m6-{case}"
                parent.mkdir()
                subprocess.run(["icacls", str(parent), "/grant", grant], check=True, capture_output=True)
                self._assert_parent_refused(parent, f"Everyone holds {grant}")

    def test_staging_junction_to_operator_dir_is_never_emptied(self):
        """Security H-2 (probe W1) on Windows: right after staging is
        created, a racer renames it and plants a junction (no privilege
        needed) to a non-empty operator directory under its name. The
        scratch copy of install.ps1 in the fixture bundle gets that racer
        as one line after `Initialize-PrivateDirectory $path`. install.ps1
        must refuse, exit non-zero, run no docker command, and leave the
        victim's files intact: pin only after the private-directory assert
        and never empty through a reparse point."""
        parent = self.tmp / "h2-parent"
        parent.mkdir()
        victim = self.tmp / "victim"
        (victim / "sub").mkdir(parents=True)
        (victim / "keep1").write_text("secret\n", encoding="utf-8")
        (victim / "sub" / "k").write_text("s\n", encoding="utf-8")
        before = sorted(str(p.relative_to(victim)) for p in victim.rglob("*"))
        bundle = self.tmp / "bundle-h2"
        _make_fixture(bundle)
        _insert_staging_hook(
            bundle / "install.ps1",
            "Rename-Item -LiteralPath $path -NewName ((Split-Path -Leaf $path) + '.moved'); "
            "New-Item -ItemType Junction -Path $path -Target $env:KE_TEST_VICTIM | Out-Null; "
            "New-Item -ItemType File -Path $env:KE_TEST_SWAPPED | Out-Null")
        _write_manifest(bundle)
        env, log = self._fake_env("h2")
        swapped = self.tmp / "h2-swapped"
        env.update(KE_TEST_VICTIM=str(victim), KE_TEST_SWAPPED=str(swapped))
        target = parent / "ke"
        result = self._run_ps1(bundle, target, env)
        out = result.stdout + result.stderr
        self.assertTrue(swapped.exists(), "the hooked racer never ran; update this test with the code:\n" + out)
        after = sorted(str(p.relative_to(victim)) for p in victim.rglob("*"))
        self.assertEqual(after, before,
                         "install.ps1 emptied (or wrote into) the operator directory a junction swapped in for "
                         "staging led to (security H-2 W1):\n" + out)
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(log.read_text(encoding="utf-8"), "", "docker ran from a swapped staging")
        self.assertFalse(target.exists(), "the claimed target was left behind")

    def test_staging_never_inherits_an_ace(self):
        """Security H-1: staging never carries an inherited ACE, under a
        parent with an inheritable ACE. Round-4 ruling: a parent granting
        Authenticated Users Modify is now refused
        (test_parent_granting_authenticated_users_modify_is_refused), so the
        inheritable ACE here is Authenticated Users Read & Execute, which
        the parent rule allows and staging must still not inherit."""
        import threading

        parent = self.tmp / "shared-parent"
        parent.mkdir()
        subprocess.run(["icacls", str(parent), "/grant", "*S-1-5-11:(OI)(CI)RX"], check=True,
                       capture_output=True)
        bundle = self.tmp / "bundle"
        _make_fixture(bundle)
        fakebin = self.tmp / "fakebin"
        fake = fake_docker.install(fakebin)
        winbin = self.tmp / "winbin"
        winbin.mkdir()
        (winbin / "docker.cmd").write_text(f'@"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
        seen: dict[str, str | None] = {}
        stop = threading.Event()

        def poll() -> None:
            while not stop.is_set():
                for entry in os.scandir(parent):
                    if entry.name.startswith(STAGING_PREFIX) and entry.name not in seen:
                        seen[entry.name] = self._sddl(entry.path)

        watcher = threading.Thread(target=poll, daemon=True)
        watcher.start()
        env = {**os.environ, "PATH": f"{winbin}{os.pathsep}{os.environ.get('PATH', '')}",
               "FAKE_DOCKER_ENGINE": ENGINE_OK,
               "FAKE_COMPOSE_IMAGES": json.dumps(FIXTURE_STACK_IMAGES),
               "FAKE_DOCKER_LOAD": json.dumps({"ke-app.tar": f"Loaded image: {LOADED_APP_NAME}"})}
        try:
            result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File",
                                     str(bundle / "install.ps1"), "-Target", str(parent / "ke")],
                                    cwd=bundle, env=env, capture_output=True, text=True, timeout=300)
        finally:
            stop.set()
            watcher.join(5)
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, out)
        self.assertTrue(seen, "the poller never saw a staging directory")
        for name, sddl in seen.items():
            with self.subTest(staging=name):
                self.assertIsNotNone(sddl, "staging's security descriptor could not be read")
                assert sddl is not None
                dacl = sddl[sddl.find("D:"):]
                self.assertTrue(dacl.startswith("D:P"), f"staging's DACL is not protected at birth: {sddl}")
                self.assertNotRegex(dacl, r"\([A-Z]+;[A-Z]*ID[A-Z]*;",
                                    f"staging carried an inherited ACE (security H-1): {sddl}")
                self.assertNotIn(";AU)", dacl, f"Authenticated Users had access to staging: {sddl}")

    def test_empty_path_entry_is_dropped_on_windows(self):
        """Review RB5a, security L-9: on Windows an empty PATH entry is a
        stray separator; install.ps1 drops it and installs (a relative entry
        is still refused)."""
        bundle = self.tmp / "bundle-path"
        _make_fixture(bundle)
        fake = fake_docker.install(self.tmp / "fakebin-path")
        winbin = self.tmp / "winbin-path"
        winbin.mkdir()
        (winbin / "docker.cmd").write_text(f'@"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
        base = f"{winbin}{os.pathsep}{os.environ.get('PATH', '')}"
        pwsh = shutil.which("pwsh")
        assert pwsh is not None
        cases = {"leading_empty": (os.pathsep + base, True), "middle_empty": (
            base.replace(os.pathsep, os.pathsep * 2, 1), True), "relative": ("winbin" + os.pathsep + base, False)}
        for n, (case, (path, ok)) in enumerate(cases.items()):
            with self.subTest(case=case):
                parent = self.tmp / f"home-path{n}"
                parent.mkdir()
                env = {**os.environ, "PATH": path, "FAKE_DOCKER_ENGINE": ENGINE_OK,
                       "FAKE_COMPOSE_IMAGES": json.dumps(FIXTURE_STACK_IMAGES),
                       "FAKE_DOCKER_LOAD": json.dumps({"ke-app.tar": f"Loaded image: {LOADED_APP_NAME}"})}
                result = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-File", str(bundle / "install.ps1"),
                                         "-Target", str(parent / "ke")],
                                        cwd=bundle, env=env, capture_output=True, text=True, timeout=300)
                out = result.stdout + result.stderr
                if ok:
                    self.assertEqual(result.returncode, 0,
                                     "install.ps1 on Windows must drop an empty PATH entry and install:\n" + out)
                else:
                    self.assertNotEqual(result.returncode, 0, "a relative PATH entry was accepted:\n" + out)
                    self.assertIn("PATH", out)


# --------------------------------------------------------------------------
# The bundler: scripts/bundle.sh (bash only, ruling R1)
# --------------------------------------------------------------------------

_DEFAULT = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?-([^}]*)\}")


def _resolve(value: str) -> str:
    return _DEFAULT.sub(lambda m: m.group(2), value)


def _stack_images() -> dict[str, str]:
    """Service -> image of every service with no `profiles` in docker-compose.yml."""
    return {name: _resolve(str(svc["image"])) for name, svc in cs.services().items()
            if not svc.get("profiles") and svc.get("image")}


def _stack_depends() -> dict[str, list[str]]:
    """Service -> its depends_on services, for every stack service in
    docker-compose.yml (short or long form). The fake compose prints these
    services' images too for `config --images <svc>`, as Compose 5.x does
    (defect D1, docs/evidence/platform-offline/recorded-runs.md)."""
    out: dict[str, list[str]] = {}
    for name, svc in cs.services().items():
        if svc.get("profiles"):
            continue
        dep = svc.get("depends_on") or {}
        out[name] = sorted(dep) if isinstance(dep, dict) else sorted(str(d) for d in dep)
    return out


def _profile_images() -> dict[str, str]:
    out = {name: _resolve(str(svc["image"])) for name, svc in cs.services().items()
           if svc.get("profiles") and svc.get("image")}
    out.setdefault("dind", f"docker:29-dind@sha256:{hashlib.sha256(b'dind').hexdigest()}")
    return out


def _split_ref(ref: str) -> tuple[str, str | None]:
    """(repository, digest hex or None)."""
    base, _, digest = ref.partition("@sha256:")
    repo = base.rsplit(":", 1)[0] if ":" in base.rsplit("/", 1)[-1] else base
    return repo, (digest or None)


def _expected_as(ref: str, sha: str) -> tuple[str, str]:
    """(`as`, tar name) by the §2.5 scheme."""
    repo, digest = _split_ref(ref)
    name = repo.rsplit("/", 1)[-1]
    if digest:
        return f"ke-vendor/{name}:{digest[:12]}", name
    return f"{repo}:bundle-{sha[:12]}", name


def _image_record(ref: str, arch: str = "amd64") -> dict[str, Any]:
    return {"Id": "sha256:" + hashlib.sha256(ref.encode()).hexdigest(), "RepoTags": [ref.split("@")[0]],
            "RepoDigests": [ref] if "@" in ref else [], "Os": "linux", "Architecture": arch}


_REPO_COPY = (".env.example", ".gitignore", ".dockerignore", "docker-compose.yml", "pyproject.toml",
              "uv.lock", "NOTICE.md", "config", "scripts", "licenses", "docs/quickstart.md")


# ---- PS-3.8 licence notices: a stand-in for the ke-app image's venv --------
#
# The fake docker runs the real `engine/notices.py` against a site-packages
# directory built here (tests/fake_docker.py, FAKE_NOTICES_SITE). It holds one
# `*.dist-info` per runtime package of uv.lock, in the layouts the real
# ke-app image has (docs/evidence/platform-offline/red-nt-ke-app-licence-probe.txt):
#   modern  - `License-File: X` and `<dist-info>/licenses/X` (most packages);
#   noheader- no License-File header, `<dist-info>/licenses/LICENSE.md` in
#             RECORD, licence from a classifier only (httpx);
#   legacy  - `License-File: LICENSE`, the file at `<dist-info>/LICENSE` (six);
#   bare    - no header, `License:` field, file at `<dist-info>/LICENSE` (protobuf);
# plus the project's own distribution (knowledge-engine), which has no licence
# file in the real image and is not a third-party package.

PROJECT_DIST = "knowledge-engine"
# Distribution names as the real image spells them (PEP 503 normalises them to
# the uv.lock names).
DIST_SPELLING = {"pyyaml": "PyYAML", "typing-extensions": "typing_extensions", "pydantic-core": "pydantic_core"}
NOTICE_LAYOUT = {"httpx": "noheader", "six": "legacy", "protobuf": "bare"}
# package -> (metadata licence lines, licence the notices must show for it)
NOTICE_LICENCE = {
    "psycopg": (["License-Expression: LGPL-3.0-only"], "LGPL-3.0-only"),
    "psycopg-binary": (["License-Expression: LGPL-3.0-only"], "LGPL-3.0-only"),
    "httpx": (["Classifier: License :: OSI Approved :: BSD License"], "BSD"),
    "six": (["License: MIT"], "MIT"),
    "protobuf": (["License: 3-Clause BSD License"], "3-Clause BSD License"),
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _runtime_packages() -> dict[str, str]:
    """name -> version of every package uv.lock installs for the project
    without the dev group (its dependencies and the extras they name,
    transitively). Markers are ignored, so this is a superset on any one
    platform."""
    import tomllib
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    pkgs = {p["name"]: p for p in lock["package"]}
    todo = list(pkgs[PROJECT_DIST].get("dependencies", []))
    seen: dict[str, str] = {}
    done: set[tuple[str, str]] = set()
    while todo:
        dep = todo.pop()
        name = dep["name"]
        for extra in [""] + list(dep.get("extra", [])):
            if (name, extra) in done:
                continue
            done.add((name, extra))
            pkg = pkgs[name]
            seen[name] = pkg["version"]
            todo += pkg.get("dependencies", []) if not extra else pkg.get("optional-dependencies", {}).get(extra, [])
    seen.pop(PROJECT_DIST, None)
    return seen


def _notice_licence(name: str, i: int) -> tuple[list[str], str]:
    return NOTICE_LICENCE.get(name) or ((["License-Expression: MIT"], "MIT") if i % 2 == 0
                                        else (["License-Expression: Apache-2.0"], "Apache-2.0"))


def _licence_file_rel(name: str, version: str) -> str:
    """The site-relative path of the package's licence file in the fixture."""
    dist = f"{DIST_SPELLING.get(name, name).replace('-', '_')}-{version}.dist-info"
    layout = NOTICE_LAYOUT.get(name, "modern")
    leaf = "LICENSE.txt" if name.startswith("psycopg") else "LICENSE.md" if layout == "noheader" else "LICENSE"
    return f"{dist}/{leaf}" if layout in ("legacy", "bare") else f"{dist}/licenses/{leaf}"


def _make_site(site: Path) -> dict[str, str]:
    """Write the stand-in site-packages; returns the runtime packages."""
    packages = _runtime_packages()
    for name in NOTICE_LAYOUT:
        assert name in packages, f"precondition: {name} is a runtime package in uv.lock"
    entries = sorted(packages.items()) + [(PROJECT_DIST, "0.1.0")]
    for i, (name, version) in enumerate(entries):
        spelled = DIST_SPELLING.get(name, name)
        dist = f"{spelled.replace('-', '_')}-{version}.dist-info"
        (site / dist).mkdir(parents=True)
        meta = [f"Metadata-Version: {'2.4' if NOTICE_LAYOUT.get(name, 'modern') == 'modern' else '2.1'}",
                f"Name: {spelled}", f"Version: {version}"]
        record = [f"{dist}/METADATA,,", f"{dist}/RECORD,,"]
        if name != PROJECT_DIST:
            lines, _ = _notice_licence(name, i)
            meta += lines
            rel = _licence_file_rel(name, version)
            if NOTICE_LAYOUT.get(name) not in ("noheader", "bare"):
                meta.append(f"License-File: {rel.rsplit('/', 1)[1]}")
            (site / rel).parent.mkdir(parents=True, exist_ok=True)
            (site / rel).write_text(f"{spelled} licence text (fixture)\n", encoding="utf-8")
            record.insert(1, f"{rel},sha256=fixture,1")
        (site / dist / "METADATA").write_text("\n".join(meta) + "\n\n", encoding="utf-8")
        (site / dist / "RECORD").write_text("\n".join(record) + "\n", encoding="utf-8")
    return packages


def _md_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """(header cells, body rows) of each Markdown table; cells stripped."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    rows: list[list[str]] = []
    for line in text.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|"):
            rows.append([c.strip() for c in s.strip("|").split("|")])
            continue
        if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", c) for c in rows[1]):
            tables.append((rows[0], rows[2:]))
        rows = []
    return tables


def _md_table(text: str, *needed: str) -> list[dict[str, str]]:
    """The rows (header -> cell, headers lower-cased, `license` spelled
    `licence`) of the one table whose header has every `needed` column."""
    found = []
    for header, body in _md_tables(text):
        keys = [h.lower().replace("license", "licence") for h in header]
        if all(n in keys for n in needed):
            found.append([dict(zip(keys, row)) for row in body])
    assert len(found) == 1, f"want one table with columns {needed}, found {len(found)}:\n{text}"
    return found[0]


class _BundleBase:
    """bundle.sh in a throwaway git repository holding the files it copies,
    with the fake docker and fake df first on PATH. The fake logs and the
    bundle live outside that repository, so they never make it dirty."""

    def setUp(self) -> None:  # noqa: D401 - unittest hook
        t: Any = self
        t.assertTrue((ROOT / "scripts" / "bundle.sh").is_file(),
                     "scripts/bundle.sh is missing (PS-3.1 Offline bundle, architecture §2.5 Bundle)")
        self.tmp = Path(tempfile.mkdtemp())
        t.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        for rel in _REPO_COPY:
            src = ROOT / rel
            if src.is_dir():
                shutil.copytree(src, self.repo / rel,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.is_file():
                (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, self.repo / rel)
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture")
        self.sha = self._git("rev-parse", "HEAD").strip()
        fake_docker.install(self.tmp / "fakebin")
        fake_docker.install_df(self.tmp / "fakebin")
        self.log = self.tmp / "docker.log"
        self.json = self.tmp / "docker.jsonl"
        self.df_log = self.tmp / "df.log"
        self.path = f"{self.tmp / 'fakebin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
        self.stack = _stack_images()
        self.n = 0
        # PS-3.8: the ke-app image's venv as the notices generator sees it.
        self.site = self.tmp / "site-packages"
        self.packages = _make_site(self.site)

    def _git(self, *args: str) -> str:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.tmp),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        done = subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                               "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                              cwd=self.repo, env=env, capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            raise RuntimeError(f"git {args} failed: {done.stderr}")
        return done.stdout

    def _images_table(self, stack: dict[str, str], default: str = "amd64", **arch: str) -> dict[str, Any]:
        refs = set(stack.values()) | set(_profile_images().values())
        return {r: _image_record(r, arch.get(r, default)) for r in refs}

    def _bundle(self, out: Path | None = None, *, stack: dict[str, str] | None = None,
                images: dict[str, Any] | None = None, args: tuple[str, ...] = (), **env: str
                ) -> tuple[subprocess.CompletedProcess, list[list[str]], Path]:
        self.n += 1
        # PS-3.1 *Arch recorded*: the --out basename ends in -<arch>. The
        # default follows the fake daemon (FAKE_DOCKER_ARCH, unset = x86_64).
        daemon_arch = ARCH_OF.get(env.get("FAKE_DOCKER_ARCH", "x86_64"), "amd64")
        out = out or self.tmp / f"out{self.n}" / f"bundle-{daemon_arch}"
        (out.parent).mkdir(parents=True, exist_ok=True)
        for f in (self.log, self.json, self.df_log):
            f.write_text("", encoding="utf-8")
        stack = self.stack if stack is None else stack
        run_env = {
            "PATH": self.path, "HOME": str(self.tmp),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "FAKE_DOCKER_LOG": str(self.log), "FAKE_DOCKER_JSON": str(self.json),
            "FAKE_DF_LOG": str(self.df_log),
            "FAKE_DOCKER_ENGINE": ENGINE_OK,
            "FAKE_COMPOSE_IMAGES": json.dumps(stack),
            "FAKE_COMPOSE_PROFILE_IMAGES": json.dumps(_profile_images()),
            "FAKE_DOCKER_IMAGES": json.dumps(self._images_table(stack) if images is None else images),
            # Defect D1: by default the fake answers `config --images <svc>` the
            # way Compose 5.x does, with the depends_on services' images too, in
            # a shuffled order (tests/fake_docker.py, FAKE_COMPOSE_DEPENDS).
            "FAKE_COMPOSE_DEPENDS": json.dumps(_stack_depends()),
            # PS-3.8: `docker run ... engine.notices` runs the real generator
            # against self.site (tests/fake_docker.py).
            "FAKE_NOTICES_SITE": str(self.site), "FAKE_NOTICES_APP_ROOT": str(ROOT),
        }
        run_env.update(env)
        result = subprocess.run(["bash", "scripts/bundle.sh", *args, "--out", str(out)], env=run_env,
                                cwd=self.repo, capture_output=True, text=True, timeout=180)
        calls = [r["argv"] for r in fake_docker.records(self.json)]
        return result, calls, out

    @staticmethod
    def _out(result: subprocess.CompletedProcess) -> str:
        return (result.stdout or "") + (result.stderr or "")

    @staticmethod
    def _saves(calls: list[list[str]]) -> list[list[str]]:
        return [c for c in calls if c[:1] == ["save"] or c[:2] == ["image", "save"]]

    def _ok(self, **kw: Any) -> tuple[subprocess.CompletedProcess, list[list[str]], Path, dict[str, Any]]:
        t: Any = self
        result, calls, out = self._bundle(**kw)
        t.assertEqual(result.returncode, 0, "bundle.sh failed on a fit build host:\n" + self._out(result))
        t.assertTrue((out / "bundle.json").is_file(), "no bundle.json written")
        return result, calls, out, json.loads((out / "bundle.json").read_text(encoding="utf-8"))

    def _assert_no_bundle(self, result: subprocess.CompletedProcess, calls: list[list[str]],
                          out: Path, name: str | None = None) -> None:
        t: Any = self
        t.assertNotEqual(result.returncode, 0, "bundle.sh passed:\n" + self._out(result))
        t.assertEqual(self._saves(calls), [], "docker save ran before the refusal")
        written = [_rel(p, out) for p in (out / "bundle.json", out / "MANIFEST.sha256") if p.exists()]
        written += [_rel(p, out) for p in out.glob("images/*.tar")] if out.exists() else []
        t.assertEqual(written, [], "a bundle was written after the refusal")
        if name is not None:
            t.assertIn(name, self._out(result), "the refusal must name the image")

    def _expected(self) -> dict[str, dict[str, Any]]:
        """ref -> expected entry (file, as, services set)."""
        by_ref: dict[str, dict[str, Any]] = {}
        for svc, ref in self.stack.items():
            as_, name = _expected_as(ref, self.sha)
            e = by_ref.setdefault(ref, {"file": f"images/{name}.tar", "as": as_, "services": set()})
            e["services"].add(svc)
        return by_ref


class BundleScriptTest(_BundleBase, unittest.TestCase):

    # ---- PS-3.1 Every image listed / Stack images only (R7) -----------------

    def test_bundle_lists_every_compose_image(self):
        _, calls, _, data = self._ok()
        refs = [e.get("ref") for e in data.get("images", [])]
        for ref in sorted(set(self.stack.values())):
            with self.subTest(image=ref):
                self.assertIn(ref, refs, "a stack service image is not in bundle.json")
                as_ = self._expected()[ref]["as"]
                self.assertTrue([c for c in self._saves(calls) if c[-1] == as_],
                                f"no `docker save ... {as_}` for {ref}")

    def test_bundle_holds_stack_images_only(self):
        _, calls, out, data = self._ok()
        self.assertEqual(sorted(e.get("ref") for e in data.get("images", [])),
                         sorted(set(self.stack.values())),
                         "bundle.json must hold exactly the stack services' images (R7)")
        tars = sorted(_rel(p, out) for p in out.rglob("*.tar"))
        self.assertEqual(tars, sorted(e["file"] for e in self._expected().values()))
        verification = set(_profile_images().values()) - set(self.stack.values())
        touched = [c for c in calls if c[:1] in (["save"], ["tag"]) and set(c) & verification]
        self.assertEqual(touched, [], "a verification image (gates, dind) was tagged or saved (R7)")

    def test_bundle_json_names_every_image(self):
        _, _, _, data = self._ok()
        images = data.get("images", [])
        self.assertEqual(len(images), len(set(self.stack.values())),
                         "bundle.json has one entry per image (api and worker share one)")

    # ---- defect D1 (smoke-gate loop 1): Compose 5.x `config --images <svc>` --

    def _fake_compose(self, *args: str, seed: str = "1") -> subprocess.CompletedProcess:
        env = {"PATH": self.path, "HOME": str(self.tmp),
               "FAKE_COMPOSE_IMAGES": json.dumps(self.stack),
               "FAKE_COMPOSE_DEPENDS": json.dumps(_stack_depends()), "FAKE_COMPOSE_SEED": seed}
        return subprocess.run(["docker", "compose", "-f", "docker-compose.yml", "--env-file", ".env.example",
                               "config", *args], env=env, cwd=self.repo, capture_output=True, text=True,
                              timeout=60)

    def test_bundle_maps_each_service_to_own_image_despite_dependencies(self):
        """Defect D1 (docs/evidence/platform-offline/recorded-runs.md): on
        Compose 5.1.4 and 5.2.0 `docker compose config --images worker` also
        prints the images of worker's depends_on services (valkey), in an
        unstable order, so bundle.sh died with "service worker resolves to
        more than one image". bundle.sh must succeed on the real
        docker-compose.yml service graph and record each service under
        exactly its own image (`.services.<svc>.image`)."""
        deps = _stack_depends()
        with self.subTest(part="harness: the real graph has dependencies"):
            self.assertIn("valkey", deps.get("worker", []), "worker depends_on valkey in docker-compose.yml")
            self.assertTrue({"postgres", "neo4j", "valkey"} <= set(deps.get("api", [])),
                            "api depends_on postgres, neo4j and valkey in docker-compose.yml")
        with self.subTest(part="harness: the fake prints dependency images like Compose 5.x"):
            orders = set()
            for seed in ("1", "2", "3", "4", "5", "6"):
                done = self._fake_compose("--images", "worker", seed=seed)
                self.assertEqual(done.returncode, 0, done.stderr)
                lines = done.stdout.splitlines()
                self.assertEqual(sorted(lines), sorted({self.stack["worker"], self.stack["valkey"]}),
                                 "config --images worker prints ke-app and valkey")
                orders.add(tuple(lines))
            self.assertGreater(len(orders), 1, "the fake's order must vary with the seed")
            done = self._fake_compose("--format", "json")
            self.assertEqual(done.returncode, 0, done.stderr)
            model = json.loads(done.stdout)
            for svc, ref in self.stack.items():
                self.assertEqual(model["services"][svc]["image"], ref, f".services.{svc}.image")
        for seed in ("1", "2", "3", "4", "5", "6"):
            with self.subTest(seed=seed):
                result, _, _, data = self._ok(FAKE_COMPOSE_SEED=seed)
                self.assertNotIn("more than one image", self._out(result))
                expected = self._expected()
                got = {e.get("ref"): set(str(e.get("services", "")).split(" "))
                       for e in data.get("images", [])}
                self.assertEqual(got, {ref: e["services"] for ref, e in expected.items()},
                                 "each service is recorded under exactly its own image, never a "
                                 "dependency's (worker -> ke-app, not valkey)")
                listed = [s for e in data.get("images", []) for s in str(e.get("services", "")).split(" ")]
                self.assertEqual(sorted(listed), sorted(self.stack), "every stack service exactly once")

    # ---- security L-D1b (audit-d1.md): pins for the jq model lookup --------

    def _path_without_jq(self) -> str:
        """A PATH holding every tool of the current PATH except jq: the fake
        docker/df first, then one directory of links to everything else."""
        shadow = self.tmp / "nojq"
        shadow.mkdir(exist_ok=True)
        for d in os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep):
            if not d or not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if name == "jq" or (shadow / name).exists() or (shadow / name).is_symlink():
                    continue
                src = Path(d) / name
                if src.is_file() and os.access(src, os.X_OK):
                    (shadow / name).symlink_to(src)
        return f"{self.tmp / 'fakebin'}{os.pathsep}{shadow}"

    def _model_shim(self) -> str:
        """A `docker` ahead of the fake that rewrites the JSON model of
        `compose ... config --format json` per SHIM_MODEL (JSON):
        {"stdout": text} prints text instead; {"drop": svc} removes
        `.services.<svc>.image`; {"set": {svc: value}} sets it. Every call is
        still made, and logged, through the fake."""
        shim = self.tmp / "shim"
        shim.mkdir(exist_ok=True)
        real = self.tmp / "fakebin" / "docker"
        (shim / "docker").write_text(
            f"#!{sys.executable}\n"
            "import json, os, subprocess, sys\n"
            f"real = {str(real)!r}\n"
            "argv = sys.argv[1:]\n"
            "if not ('config' in argv and '--format' in argv and 'json' in argv):\n"
            "    os.execv(real, [real, *argv])\n"
            "done = subprocess.run([real, *argv], capture_output=True, text=True)\n"
            "sys.stderr.write(done.stderr)\n"
            "if done.returncode != 0:\n"
            "    sys.stdout.write(done.stdout); sys.exit(done.returncode)\n"
            "how = json.loads(os.environ.get('SHIM_MODEL') or '{}')\n"
            "if 'stdout' in how:\n"
            "    sys.stdout.write(how['stdout']); sys.exit(0)\n"
            "model = json.loads(done.stdout)\n"
            "if 'drop' in how:\n"
            "    model['services'][how['drop']].pop('image', None)\n"
            "for svc, value in how.get('set', {}).items():\n"
            "    model['services'][svc]['image'] = value\n"
            "print(json.dumps(model, indent=2))\n",
            encoding="utf-8", newline="\n")
        (shim / "docker").chmod(0o755)
        return f"{shim}{os.pathsep}{self.path}"

    def test_bundle_refuses_without_jq_before_any_docker_call(self):
        """L-D1b (a): jq is a build-host prerequisite (defect D1 fix). With no
        jq on PATH bundle.sh exits non-zero naming jq, before it makes any
        docker call (not even `docker info`) and before it writes anything."""
        path = self._path_without_jq()
        with self.subTest(part="harness: jq is absent, bash and git are not"):
            self.assertIsNone(shutil.which("jq", path=path), "the jq-free PATH still finds jq")
            for tool in ("bash", "git", "dirname", "docker"):
                self.assertIsNotNone(shutil.which(tool, path=path), f"the jq-free PATH lost {tool}")
        result, calls, out = self._bundle(PATH=path)
        self.assertNotEqual(result.returncode, 0, "bundle.sh passed with no jq:\n" + self._out(result))
        self.assertIn("jq", self._out(result), "the refusal must name jq")
        self.assertEqual(calls, [], "bundle.sh made docker calls before refusing for the missing jq")
        self.assertEqual(self.log.read_text(encoding="utf-8"), "", "the fake docker log is not empty")
        self.assertEqual(self.df_log.read_text(encoding="utf-8"), "", "df ran before the jq refusal")
        written = sorted(_rel(p, out) for p in out.rglob("*")) if out.exists() else []
        self.assertEqual(written, [], "a bundle file was written before the jq refusal")

    def test_bundle_refuses_when_compose_json_model_fails(self):
        """L-D1b (b): `docker compose config --format json` exiting non-zero,
        with nothing printed or with a full model printed, is refused before
        any save, and the refusal names that step (its exit status is checked,
        not just its output)."""
        cases = {"fails, prints nothing": {"FAKE_DOCKER_FAIL": "config --format json"},
                 "prints a model, then exits 3": {"FAKE_DOCKER_EXIT_AFTER": "config --format json"}}
        for name, env in cases.items():
            with self.subTest(case=name):
                result, calls, out = self._bundle(**env)
                self.assertTrue([c for c in calls if c[-3:] == ["config", "--format", "json"]],
                                f"the harness never reached config --format json: {calls}")
                self._assert_no_bundle(result, calls, out)
                self.assertIn("config --format json", self._out(result),
                              "the refusal must name the failing compose step")

    def test_bundle_refuses_service_without_image_in_model(self):
        """L-D1b (b): a stack service whose `.services.<svc>.image` is absent,
        null or empty in the resolved compose model is refused before any
        save, and the refusal names the service."""
        path = self._model_shim()
        cases = {"absent": ("worker", {"drop": "worker"}),
                 "null": ("valkey", {"set": {"valkey": None}}),
                 "empty": ("gateway", {"set": {"gateway": ""}})}
        for name, (svc, how) in cases.items():
            with self.subTest(image=name, service=svc):
                self.assertIn(svc, self.stack, f"{svc} is a stack service in docker-compose.yml")
                result, calls, out = self._bundle(PATH=path, SHIM_MODEL=json.dumps(how))
                self._assert_no_bundle(result, calls, out)
                self.assertIn(f"service {svc} has no image", self._out(result),
                              "the refusal must name the service with no image")

    def test_bundle_refuses_empty_json_model(self):
        """L-D1b (b): an empty JSON model (no output, `{}`, no services, null)
        is refused before any save. No output names the compose step; a model
        with no services names the first service (sorted: api) as imageless."""
        cases = {"no output": ("", "config --format json printed nothing"),
                 "{}": ("{}", "service api has no image"),
                 "no services": ('{"services": {}}', "service api has no image"),
                 "null": ("null", "service api has no image")}
        path = self._model_shim()
        for name, (text, said) in cases.items():
            with self.subTest(model=name):
                result, calls, out = self._bundle(PATH=path, SHIM_MODEL=json.dumps({"stdout": text}))
                self._assert_no_bundle(result, calls, out)
                self.assertIn(said, self._out(result))

    # ---- PS-3.1 One tar per image, no --platform (S1) -----------------------

    def test_bundle_saves_one_tar_per_image_without_platform(self):
        _, calls, out, _ = self._ok()
        for c in calls:
            self.assertNotIn("--platform", " ".join(c), f"--platform passed to docker: {c} (spike S1)")
            self.assertFalse(c[:1] in (["pull"], ["build"], ["push"], ["buildx"]),
                             f"bundle.sh never builds, pulls or pushes: {c}")
        saves = self._saves(calls)
        expected = self._expected()
        self.assertEqual(len(saves), len(expected), f"one save per image; saves: {saves}")
        for ref, e in expected.items():
            with self.subTest(image=ref):
                mine = [c for c in saves if c[-1] == e["as"]]
                self.assertEqual(len(mine), 1, f"save of {e['as']}: {saves}")
                save = mine[0]
                target = (save[save.index("-o") + 1] if "-o" in save
                          else save[save.index("--output") + 1])
                self.assertEqual(Path(target).resolve(), (out / e["file"]).resolve())
                at = calls.index(save)
                self.assertIn(["tag", ref, e["as"]], calls[:at], "tag <ref> <as> before the save")
                inspected = [c for c in calls[:at] if (c[:2] == ["image", "inspect"] or c[:1] == ["inspect"])
                             and ref in c]
                self.assertTrue(inspected, f"image inspect {ref} (the digest pin) before the save")

    # ---- PS-3.1 bundle.json entries and the `as` scheme ---------------------

    def test_bundle_json_records_file_ref_as(self):
        _, _, out, data = self._ok()
        text = (out / "bundle.json").read_text(encoding="utf-8")
        with self.subTest(part="header"):
            self.assertEqual(data.get("format"), 1)
            self.assertEqual(data.get("git_sha"), self.sha)
            self.assertIs(data.get("dirty"), False)
            # The header's arch moved to test_bundle_json_records_arch (PS-3.1
            # per-arch bundles, *Arch recorded*: "arch" replaces "platform").
            self.assertRegex(str(data.get("created")), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        expected = self._expected()
        seen_services: list[str] = []
        as_values: list[str] = []
        for entry in data.get("images", []):
            with self.subTest(entry=entry.get("ref")):
                self.assertEqual(set(entry), {"file", "ref", "as", "services"},
                                 "exactly four fields per entry (R2)")
                exp = expected.get(entry["ref"])
                self.assertIsNotNone(exp, f"unexpected image {entry['ref']}")
                assert exp is not None
                self.assertEqual(entry["file"], exp["file"])
                self.assertEqual(entry["as"], exp["as"],
                                 "as = ke-<x>:bundle-<sha12> or ke-vendor/<name>:<digest12>")
                self.assertNotIn("@sha256:", entry["as"])
                first = entry["as"].split("/", 1)[0]
                self.assertFalse("/" in entry["as"] and ("." in first or ":" in first),
                                 "`as` carries no registry host")
                names = entry["services"].split(" ")
                self.assertTrue(entry["services"] and all(SERVICE_NAME.match(n) for n in names),
                                f"services {entry['services']!r}")
                self.assertEqual(set(names), exp["services"])
                seen_services += names
                as_values.append(entry["as"])
                lines = [ln.rstrip(",") for ln in text.splitlines() if f'"ref": {json.dumps(entry["ref"])}' in ln]
                self.assertEqual(len(lines), 1, "one image per line (the bash installer reads lines)")
                self.assertEqual(json.loads(lines[0]), entry)
        with self.subTest(part="every stack service in exactly one entry"):
            self.assertEqual(sorted(seen_services), sorted(self.stack))
        with self.subTest(part="no two entries share an as"):
            self.assertEqual(len(as_values), len(set(as_values)))
        with self.subTest(part="name collision refused"):
            other = f"example/postgres:1@sha256:{hashlib.sha256(b'other pg').hexdigest()}"
            stack = dict(self.stack, extra=other)
            result, calls, out2 = self._bundle(stack=stack)
            self._assert_no_bundle(result, calls, out2, "postgres")

    # ---- PS-3.1 Manifest ----------------------------------------------------

    def test_bundle_manifest_covers_every_file(self):
        _, _, out, _ = self._ok()
        lines = (out / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
        listed = []
        for line in lines:
            m = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
            self.assertIsNotNone(m, f"not a sha256sum line: {line!r}")
            assert m is not None
            self.assertEqual(_sha256(out / m.group(2)), m.group(1), m.group(2))
            listed.append(m.group(2))
        self.assertEqual(listed, sorted(listed, key=lambda s: s.encode("utf-8")), "LC_ALL=C order")
        self.assertEqual(listed, [r for r in _regular_files(out) if r != "MANIFEST.sha256"])
        for rel in ("install.sh", "install.ps1", "bundle.json", "app/docker-compose.yml"):
            self.assertIn(rel, listed)

    def test_bundle_prints_manifest_hash(self):
        result, _, out, _ = self._ok()
        self.assertIn(_sha256(out / "MANIFEST.sha256"), result.stdout,
                      "bundle.sh prints the manifest's own sha256 for an out-of-band check")

    def test_bundle_has_no_wheels(self):
        _, _, out, _ = self._ok()
        self.assertEqual([_rel(p, out) for p in out.rglob("*.whl")], [])

    def test_bundle_always_ships_net_isolated(self):
        # Review N5 (platform-offline rework round 1): the bundled smoke.sh
        # calls scripts/net_isolated.sh, so the bundle always carries it and
        # bundle.sh copies it with no exists-guard: without it, no bundle.
        with self.subTest(case="present (shipped, byte-equal)"):
            _, _, out, _ = self._ok()
            shipped = out / "app" / "scripts" / "net_isolated.sh"
            self.assertTrue(shipped.is_file(), "app/scripts/net_isolated.sh is not in the bundle")
            self.assertEqual(_sha256(shipped), _sha256(ROOT / "scripts" / "net_isolated.sh"))
            listed = (out / "MANIFEST.sha256").read_text(encoding="utf-8")
            self.assertIn("  app/scripts/net_isolated.sh", listed)
            self.assertEqual([_rel(p, out) for p in out.rglob("image_tag.sh")], [],
                             "image_tag.sh is verify-only and is not shipped (architecture §2.1)")
        with self.subTest(case="static: no exists-guard"):
            body = "\n".join(l for l in (ROOT / "scripts" / "bundle.sh").read_text(encoding="utf-8")
                             .splitlines() if not l.lstrip().startswith("#"))
            self.assertNotRegex(body, r"\[\[?\s+-[ef]\s+\"?scripts/net_isolated\.sh",
                                "bundle.sh guards the net_isolated.sh copy with an exists-test")
        with self.subTest(case="missing from the tree: bundle.sh fails"):
            self._git("rm", "-q", "--", "scripts/net_isolated.sh")
            self._git("commit", "-q", "-m", "fixture without net_isolated.sh")
            result, calls, out = self._bundle()
            self.assertNotEqual(result.returncode, 0,
                                "bundle.sh wrote a bundle without net_isolated.sh:\n" + self._out(result))
            self.assertFalse((out / "MANIFEST.sha256").exists(), "a manifest was written regardless")

    # ---- PS-3.1 Where written (A40): dirty tree -----------------------------

    def test_bundle_json_marks_dirty_tree(self):
        with self.subTest(tree="clean"):
            _, _, _, data = self._ok()
            self.assertIs(data.get("dirty"), False)
        with self.subTest(tree="dirty"):
            with open(self.repo / "docker-compose.yml", "a", encoding="utf-8") as fh:
                fh.write("# uncommitted change\n")
            _, _, _, data = self._ok()
            self.assertIs(data.get("dirty"), True, "a bundle from a dirty tree is allowed and marked")
            self.assertEqual(data.get("git_sha"), self.sha)

    # ---- PS-3.1 Free disk (R6) ----------------------------------------------

    def test_bundle_fails_below_free_disk(self):
        # Orchestrator ruling 1 after CI run 39359710258 (docs/handoffs/platform-offline.md,
        # 2026-10-20; log docs/evidence/platform-offline/ci-39359710258.log: 9.1 GiB free
        # on / at the offline stage): the floor is 7 GiB, the same in bundle.sh and
        # offline_check.sh (was 10 GiB). Measured need ~4.3 GiB (bundle 0.94 + dind 3.3).
        with self.subTest(free="3 GiB"):
            result, calls, out = self._bundle(FAKE_DF_AVAIL_KB=str(3 * GIB_KB))
            self.assertNotEqual(result.returncode, 0, "bundled with 3 GiB free:\n" + self._out(result))
            self.assertEqual(self._saves(calls), [], "docker save ran below the disk floor")
            self.assertFalse(out.exists() and any(out.iterdir()), "wrote into --out below the floor")
            msg = self._out(result)
            # Review N8 (ruling in docs/handoffs/platform-offline.md, rework round 1):
            # the message says GiB (was "10 GB"); the figure is 7 since ruling 1 above.
            self.assertRegex(msg, r"need 7 GiB free", "names the required space in GiB")
            self.assertRegex(msg, r"found 3 GiB\b", "names the available space in GiB")
            self.assertTrue(str(out) in msg or str(out.parent) in msg, "names the path")
            self.assertTrue(self.df_log.read_text(encoding="utf-8").strip(), "df was not consulted")
        with self.subTest(free="7 GiB less 1 KiB (rounds down)"):
            result, calls, out = self._bundle(FAKE_DF_AVAIL_KB=str(7 * GIB_KB - 1))
            self.assertNotEqual(result.returncode, 0, self._out(result))
            self.assertEqual(self._saves(calls), [])
            self.assertFalse(out.exists() and any(out.iterdir()), "wrote into --out below the floor")
            self.assertRegex(self._out(result), r"need 7 GiB free")
            self.assertRegex(self._out(result), r"found 6 GiB\b",
                             "the figure found is rounded down, never up to the floor (review N8)")
        with self.subTest(free="exactly 7 GiB (accepted)"):
            result, _, _ = self._bundle(FAKE_DF_AVAIL_KB=str(7 * GIB_KB))
            self.assertEqual(result.returncode, 0, self._out(result))
        with self.subTest(free="9 GiB (accepted: the CI runner's free space, run 39359710258)"):
            result, _, _ = self._bundle(FAKE_DF_AVAIL_KB=str(9 * GIB_KB))
            self.assertEqual(result.returncode, 0, self._out(result))

    def test_bundle_reads_available_column_when_filesystem_has_spaces(self):
        # Security L-6: `df -P` prints a filesystem name with spaces unquoted,
        # so a fixed `$4` reads "Used" as "Available".
        with self.subTest(free="3 GiB on '/dev/my disk', 97 GiB used"):
            result, calls, out = self._bundle(FAKE_DF_AVAIL_KB=str(3 * GIB_KB),
                                              FAKE_DF_TOTAL_KB=str(100 * GIB_KB),
                                              FAKE_DF_FILESYSTEM="/dev/my disk")
            self.assertNotEqual(result.returncode, 0,
                                "bundled with 3 GiB free (read the Used column):\n" + self._out(result))
            self.assertEqual(self._saves(calls), [])
            self.assertRegex(self._out(result), r"found 3 GiB\b")
        with self.subTest(free="50 GiB on '/dev/my disk' (control)"):
            result, _, _ = self._bundle(FAKE_DF_AVAIL_KB=str(50 * GIB_KB),
                                        FAKE_DF_TOTAL_KB=str(60 * GIB_KB),
                                        FAKE_DF_FILESYSTEM="/dev/my disk")
            self.assertEqual(result.returncode, 0, self._out(result))

    # ---- security M-3: the manifest hash is kept beside the bundle ----------

    def test_bundle_writes_manifest_hash_beside_bundle(self):
        result, _, out, _ = self._ok()
        record = out.parent / f"{out.name}.manifest.sha256"
        self.assertTrue(record.is_file(), f"bundle.sh writes {record.name} beside (not inside) the bundle")
        sha = _sha256(out / "MANIFEST.sha256")
        self.assertEqual(record.read_text(encoding="utf-8").split()[:1], [sha],
                         "the record starts with the manifest's sha256")
        self.assertFalse(list(out.rglob("*.manifest.sha256")), "the record is not inside the bundle")

    def test_bundle_refuses_existing_manifest_record(self):
        # Architecture §2.5 Bundle: a release record is never overwritten.
        out = self.tmp / "rec" / "bundle-amd64"  # PS-3.1: the --out basename ends in -<arch>
        out.parent.mkdir(parents=True)
        record = out.parent / f"{out.name}.manifest.sha256"
        record.write_text("an earlier release record\n", encoding="utf-8")
        result, calls, out = self._bundle(out)
        self._assert_no_bundle(result, calls, out, str(record))
        self.assertEqual(record.read_text(encoding="utf-8"), "an earlier release record\n",
                         "the existing record was changed")

    # ---- security L-7: only tracked config ships -----------------------------

    def test_bundle_ships_tracked_config_only(self):
        (self.repo / "config" / ".env.local").write_text("KE_SECRET=local-only\n", encoding="utf-8")
        (self.repo / "config" / "stray.txt").write_text("untracked\n", encoding="utf-8")
        tracked = sorted(self._git("ls-files", "config").split())
        result, calls, out = self._bundle()
        if result.returncode != 0:
            self._assert_no_bundle(result, calls, out)
            return
        shipped = sorted("config/" + _rel(p, out / "app" / "config")
                         for p in (out / "app" / "config").rglob("*") if p.is_file())
        self.assertEqual(shipped, tracked, "app/config holds exactly `git ls-files config` (security L-7)")

    # ---- review N7: unpinned third-party image -------------------------------

    def test_bundle_refuses_unpinned_third_party_image(self):
        vendor = sorted(r for r in set(self.stack.values()) if "@sha256:" in r)[0]
        stack = {k: ("valkey/valkey:8" if v == vendor else v) for k, v in self.stack.items()}
        result, calls, out = self._bundle(stack=stack, images=self._images_table(stack))
        self._assert_no_bundle(result, calls, out, "valkey/valkey:8")

    # ---- review N6: a failing `compose config --services` is fatal -----------

    def test_bundle_fails_when_compose_config_fails(self):
        result, calls, out = self._bundle(FAKE_DOCKER_EXIT_AFTER="config --services")
        self._assert_no_bundle(result, calls, out)

    # ---- PS-3.1 Digest pin checked on the build host (R2) -------------------

    def test_bundle_fails_when_pinned_digest_unresolved(self):
        vendor = sorted(r for r in set(self.stack.values()) if "@sha256:" in r)
        self.assertTrue(vendor, "the stack has no digest-pinned vendor image")
        ref = vendor[0]
        images = self._images_table(self.stack)
        del images[ref]
        result, calls, out = self._bundle(images=images)
        name = _expected_as(ref, self.sha)[1]
        self._assert_no_bundle(result, calls, out, name)
        self.assertFalse([c for c in calls if c[:1] == ["pull"]], "bundle.sh never pulls")

    # ---- architecture §2.6 item 5 refusals (no PS-3.x name of their own) ----

    def test_bundle_refuses_unfit_image_or_out(self):
        vendor = sorted(r for r in set(self.stack.values()) if "@sha256:" in r)[0]
        # The non_amd64 case moved to test_bundle_refuses_image_of_other_arch
        # (PS-3.1 per-arch bundles, *Every image has the arch*; architecture §2.6 5b).
        with self.subTest(case="reference_fails_pattern"):
            bad = "valkey/valkey:8;id"
            stack = {k: (bad if v == vendor else v) for k, v in self.stack.items()}
            result, calls, out = self._bundle(stack=stack, images=self._images_table(stack))
            self._assert_no_bundle(result, calls, out)
        with self.subTest(case="out_not_empty"):
            out = self.tmp / "busy-amd64"  # PS-3.1: the --out basename ends in -<arch>
            out.mkdir()
            (out / "keep.txt").write_text("x\n", encoding="utf-8")
            result, calls, _ = self._bundle(out)
            self.assertNotEqual(result.returncode, 0, self._out(result))
            self.assertEqual(self._saves(calls), [])
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["keep.txt"])

    # ---- PS-3.1 per-arch bundles (architecture §2.5 Arch, §2.6 item 5b) ----

    def _arch_run(self, daemon: str, *, out_name: str | None = None, args: tuple[str, ...] = (),
                  images: dict[str, Any] | None = None
                  ) -> tuple[subprocess.CompletedProcess, list[list[str]], Path]:
        """bundle.sh against a fake daemon reporting `daemon`, with every image
        of the daemon's own arch unless `images` says otherwise."""
        arch = ARCH_OF.get(daemon, "amd64")
        out = self.tmp / f"arch{self.n + 1}" / (out_name or f"bundle-{arch}")
        table = self._images_table(self.stack, default=arch) if images is None else images
        return self._bundle(out, images=table, args=args, FAKE_DOCKER_ARCH=daemon)

    def _header(self, out: Path) -> tuple[str, dict[str, Any]]:
        text = (out / "bundle.json").read_text(encoding="utf-8")
        return text.splitlines()[0], json.loads(text)

    def test_arch_normalisation(self):
        for daemon, arch in ARCH_OF.items():
            with self.subTest(daemon=daemon):
                result, _, out = self._arch_run(daemon)
                self.assertEqual(result.returncode, 0,
                                 f"bundle.sh on a daemon reporting {daemon} (images linux/{arch}):\n"
                                 + self._out(result))
                _, data = self._header(out)
                self.assertEqual(data.get("arch"), arch,
                                 f"Architecture {daemon} normalises to {arch} (PS-3.1 Arch normalisation)")
        for daemon in ("riscv64", "armv7l"):
            with self.subTest(daemon=daemon):
                result, calls, out = self._arch_run(daemon, out_name="bundle-amd64",
                                                    images=self._images_table(self.stack))
                self._assert_no_bundle(result, calls, out, daemon)

    def test_bundle_arch_comes_from_daemon(self):
        with self.subTest(case="x86_64_daemon"):
            result, _, out = self._arch_run("x86_64")
            self.assertEqual(result.returncode, 0, self._out(result))
            self.assertEqual(self._header(out)[1].get("arch"), "amd64")
        with self.subTest(case="aarch64_daemon"):
            result, calls, out = self._arch_run("aarch64")
            self.assertEqual(result.returncode, 0,
                             "an arm64 daemon with arm64 images must give an arm64 bundle:\n"
                             + self._out(result))
            self.assertEqual(self._header(out)[1].get("arch"), "arm64")
            for c in calls:
                self.assertNotIn("--platform", " ".join(c), f"--platform passed to docker: {c} (spike S1)")
                self.assertFalse(c[:1] in (["pull"], ["build"], ["push"], ["buildx"]),
                                 f"bundle.sh never builds, pulls or pushes: {c}")
            self.assertEqual(len(self._saves(calls)), len(self._expected()), "one save per image on arm64")
        with self.subTest(case="matching_arch_flag"):
            result, _, out = self._arch_run("aarch64", args=("--arch", "arm64"))
            self.assertEqual(result.returncode, 0,
                             "--arch arm64 on an aarch64 daemon is a matching assertion:\n" + self._out(result))
            self.assertEqual(self._header(out)[1].get("arch"), "arm64")
        with self.subTest(case="mismatched_arch_flag_refused"):
            result, calls, out = self._arch_run("aarch64", args=("--arch", "amd64"))
            self._assert_no_bundle(result, calls, out)
            msg = self._out(result)
            self.assertIn("amd64", msg, "the refusal names the asserted arch")
            self.assertTrue("arm64" in msg.replace(str(out), "") or "aarch64" in msg,
                            f"the refusal names the daemon's arch:\n{msg}")
        for bad in ("x86_64", "sparc"):
            with self.subTest(case=f"bad_arch_value_{bad}"):
                result, calls, out = self._arch_run("x86_64", args=("--arch", bad))
                self._assert_no_bundle(result, calls, out)
                self.assertIn("usage", self._out(result).lower(),
                              f"--arch {bad} is a usage error (only amd64|arm64)")

    def test_bundle_refuses_image_of_other_arch(self):
        vendor = sorted(r for r in set(self.stack.values()) if "@sha256:" in r)[0]
        names = {_expected_as(r, self.sha)[1] for r in self.stack.values()}
        for daemon in ("x86_64", "aarch64"):
            native = ARCH_OF[daemon]
            foreign = "arm64" if native == "amd64" else "amd64"
            with self.subTest(daemon=daemon, case="mixed"):
                images = self._images_table(self.stack, default=native, **{vendor: foreign})
                result, calls, out = self._arch_run(daemon, images=images)
                self._assert_no_bundle(result, calls, out, _expected_as(vendor, self.sha)[1])
                self.assertIn(f"linux/{foreign}", self._out(result),
                              "the refusal names the os/arch it found")
            with self.subTest(daemon=daemon, case="all_foreign"):
                images = self._images_table(self.stack, default=foreign)
                result, calls, out = self._arch_run(daemon, images=images)
                self._assert_no_bundle(result, calls, out)
                msg = self._out(result)
                self.assertTrue(any(n in msg for n in names), f"the refusal names an image:\n{msg}")
                self.assertIn(f"linux/{foreign}", msg, "the refusal names the os/arch it found")

    def test_bundle_json_records_arch(self):
        for daemon in ("x86_64", "aarch64"):
            arch = ARCH_OF[daemon]
            with self.subTest(daemon=daemon):
                result, _, out = self._arch_run(daemon)
                self.assertEqual(result.returncode, 0, self._out(result))
                line, data = self._header(out)
                m = HEADER_RE.match(line)
                self.assertIsNotNone(m, f"the header line is not the fixed §2.5 form with \"arch\": {line!r}")
                assert m is not None
                self.assertEqual(m.group(1), arch)
                self.assertEqual(data.get("arch"), arch)
                self.assertNotIn("platform", data, "\"arch\" replaces \"platform\" in the header")

    def test_bundle_out_name_carries_arch(self):
        for daemon in ("x86_64", "aarch64"):
            arch = ARCH_OF[daemon]
            with self.subTest(daemon=daemon, out=f"bundle-{arch}"):
                result, _, out = self._arch_run(daemon)
                self.assertEqual(result.returncode, 0, self._out(result))
                self.assertTrue(out.name.endswith(f"-{arch}"))
                self.assertTrue((out.parent / f"bundle-{arch}.manifest.sha256").is_file(),
                                "the release record carries the arch")
        refused = {
            "no_suffix": ("x86_64", "bundle"),
            "other_arch_suffix": ("x86_64", "bundle-arm64"),
            "other_arch_suffix_on_arm64": ("aarch64", "bundle-amd64"),
            "suffix_not_at_end": ("x86_64", "bundle-amd64-rc1"),
        }
        for case, (daemon, name) in refused.items():
            with self.subTest(case=case):
                result, calls, out = self._arch_run(daemon, out_name=name)
                self._assert_no_bundle(result, calls, out)
                self.assertFalse((out.parent / f"{name}.manifest.sha256").exists(),
                                 "a release record was written after the refusal")
                self.assertIn("usage", self._out(result).lower(),
                              "an --out basename not ending in -<arch> is a usage error (PS-3.1)")


_PLACEHOLDER_LICENCE = re.compile(r"(?i)^(?:|unknown|n/?a|none|-+|\?+|todo|tbd|see .*)$")
_NOT_SHIPPED = ("docker-compose.offline.yml", "docker-compose.override.yml", ".env", "image_tag.sh", "verify.sh",
                "test.sh", "lint.sh", "build.sh", "build.ps1", "env_value.sh", "bundle.sh", "offline_check.sh",
                "smoke_otlp.py")


def _cell(value: str) -> str:
    """A table cell without Markdown code ticks or link brackets."""
    return value.strip().strip("`").strip()


class BundleNoticesTest(_BundleBase, unittest.TestCase):
    """PS-3.8 licence notices (rulings R4, R7, human Q43) and architecture
    §2.5 Bundle root / §2.6 item 6. The notices generator runs inside the
    ke-app image being bundled (`docker run ... <ke-app> -m engine.notices`);
    the fake docker runs the real engine/notices.py against `self.site`."""

    NOTICES = "THIRD_PARTY_NOTICES.md"

    def _notices(self, out: Path) -> str:
        path = out / self.NOTICES
        self.assertTrue(path.is_file(), f"the bundle has no {self.NOTICES} at its root (PS-3.8, §2.5 Bundle root)")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _notice_runs(calls: list[list[str]]) -> list[tuple[int, list[str]]]:
        return [(i, c) for i, c in enumerate(calls)
                if (c[:1] == ["run"] or c[:2] == ["container", "run"]) and "engine.notices" in c]

    def _app_refs(self) -> set[str]:
        refs = {r for r in self.stack.values() if _split_ref(r)[0] == "ke-app"}
        self.assertEqual(len(refs), 1, f"precondition: one ke-app image in the stack: {self.stack}")
        ref = next(iter(refs))
        return {ref, _expected_as(ref, self.sha)[0]}

    def _vendor(self) -> dict[str, str]:
        """name (last path segment) -> pinned reference, of each third-party stack image."""
        out = {}
        for ref in sorted(set(self.stack.values())):
            repo, digest = _split_ref(ref)
            if digest:
                out[repo.rsplit("/", 1)[-1]] = ref
        return out

    def _image_rows(self, text: str) -> dict[str, dict[str, str]]:
        """reference -> row of the stack-image table."""
        rows = _md_table(text, "image", "reference", "licence", "source")
        by_ref: dict[str, dict[str, str]] = {}
        for row in rows:
            ref = _cell(row["reference"])
            self.assertNotIn(ref, by_ref, f"the image {ref} is listed twice")
            by_ref[ref] = row
        return by_ref

    def _assert_nothing_written(self, result: subprocess.CompletedProcess, calls: list[list[str]],
                                out: Path, names: str) -> None:
        self._assert_no_bundle(result, calls, out)
        self.assertRegex(self._out(result), names, "the refusal must name the package or image")
        left = sorted(_rel(p, out) for p in out.rglob("*") if p.is_file()) if out.exists() else []
        self.assertEqual(left, [], "bundle.sh left files in --out after the notices refusal (no bundle)")
        self.assertFalse(Path(str(out) + ".manifest.sha256").exists(), "a release record was written")

    # ---- PS-3.8: every runtime package from uv.lock, with its licence -------

    def test_bundle_has_third_party_notices(self):
        _, calls, out, _ = self._ok()
        text = self._notices(out)
        with self.subTest(part="generated in the ke-app image, offline, before any save"):
            runs = self._notice_runs(calls)
            self.assertEqual(len(runs), 1, f"one `docker run ... engine.notices`: {[c for _, c in runs]}")
            at, argv = runs[0] if runs else (0, [])
            pairs = set(zip(argv, argv[1:])) | {tuple(a.split("=", 1)) for a in argv if a.startswith("--")
                                                  and "=" in a}
            self.assertIn("--rm", argv)
            self.assertTrue({("--network", "none"), ("--net", "none")} & pairs, "the generator runs with no network")
            self.assertIn(("--pull", "never"), pairs, "bundle.sh never pulls (§2.5 Bundle): --pull never")
            self.assertTrue(self._app_refs() & set(argv),
                            f"the generator runs in the ke-app image being bundled ({self._app_refs()}): {argv}")
            saves = [i for i, c in enumerate(calls) if c in self._saves(calls)]
            self.assertTrue(saves and at < min(saves), "the notices run before the first docker save")
        rows = _md_table(text, "package", "version", "licence")
        by_name = {_norm(_cell(r["package"])): r for r in rows}
        for i, (name, version) in enumerate(sorted(self.packages.items())):
            with self.subTest(package=name):
                row = by_name.get(_norm(name))
                self.assertIsNotNone(row, f"runtime package {name} from uv.lock is not in {self.NOTICES}")
                assert row is not None
                self.assertEqual(_cell(row["version"]), version)
                self.assertIn(_notice_licence(name, i)[1], row["licence"],
                              "the licence: License-Expression, else License, else the licence classifiers")
                self.assertIn(_licence_file_rel(name, version), " | ".join(row.values()),
                              "the row names the package's licence file(s) in the image")
        listed = (out / "MANIFEST.sha256").read_text(encoding="utf-8")
        self.assertIn(f"  {self.NOTICES}\n", listed, "THIRD_PARTY_NOTICES.md is listed in the manifest")

    def test_notices_fail_when_package_licence_missing(self):
        # R7: a runtime package whose licence file is not in the ke-app image
        # fails bundle.sh, naming the package, and no bundle is written. Any
        # runtime package (PS-3.8), not only (L)GPL ones; covers each licence
        # layout of the real image. The project's own distribution has no
        # licence file and is not a third-party package (control).
        with self.subTest(case="control: the full set passes"):
            _, calls, out, _ = self._ok()
            self.assertIn("psycopg", self._notices(out))
            self.assertEqual(len(self._notice_runs(calls)), 1)
        cases = {"psycopg (LGPL, licenses/LICENSE.txt)": "psycopg",
                 "psycopg-binary": "psycopg-binary",
                 "six (legacy layout, MIT)": "six",
                 "httpx (no License-File header)": "httpx"}
        for case, name in cases.items():
            with self.subTest(case=case):
                site = self.tmp / f"site-{_norm(name)}"
                shutil.copytree(self.site, site)
                (site / _licence_file_rel(name, self.packages[name])).unlink()
                result, calls, out = self._bundle(FAKE_NOTICES_SITE=str(site))
                self.assertNotEqual(result.returncode, 0,
                                    f"bundle.sh passed with {name}'s licence file missing from the image:\n"
                                    + self._out(result))
                self.assertTrue(self._notice_runs(calls), "the refusal did not come from the notices generator")
                pat = name.replace("-", "[-_]")
                self._assert_nothing_written(result, calls, out, rf"(?i)(?<![\w-]){pat}(?![\w-])")
                self.assertRegex(self._out(result), r"(?i)licen[cs]e", "the refusal says a licence is missing")

    # ---- PS-3.8 Third-party images (A43, R4) and the Phoenix exception (Q43) -

    def test_notices_list_every_stack_image_with_licence(self):
        vendor = self._vendor()
        self.assertTrue(vendor, "precondition: the stack has third-party images")
        _, _, out, data = self._ok()
        rows = self._image_rows(self._notices(out))
        bundled = {e["ref"] for e in data.get("images", [])}
        for name, ref in vendor.items():
            with self.subTest(image=name):
                self.assertIn(ref, bundled, "precondition: the image is in bundle.json")
                row = rows.get(ref)
                self.assertIsNotNone(row, f"{ref} has no row (by its pinned reference) in {self.NOTICES}")
                assert row is not None
                self.assertIn(_cell(row["image"]), {name, _split_ref(ref)[0]},
                              "the Image cell names the image (its name or repository)")
                self.assertNotRegex(_cell(row["licence"]), _PLACEHOLDER_LICENCE, f"{name} has no licence")
        with self.subTest(case="an image with no known licence fails the bundle"):
            widget = f"example.org/acme/widget:1@sha256:{hashlib.sha256(b'widget').hexdigest()}"
            stack = dict(self.stack, widget=widget)
            result, calls, out2 = self._bundle(stack=stack, images=self._images_table(stack))
            self.assertNotEqual(result.returncode, 0,
                                "bundle.sh bundled a third-party image it has no licence for:\n" + self._out(result))
            self._assert_nothing_written(result, calls, out2, r"widget")

    def test_notices_neo4j_has_source_url(self):
        neo4j = self._vendor().get("neo4j")
        self.assertIsNotNone(neo4j, "precondition: neo4j is a stack image")
        _, _, out, _ = self._ok()
        row = self._image_rows(self._notices(out)).get(str(neo4j))
        self.assertIsNotNone(row, f"neo4j ({neo4j}) has no row in {self.NOTICES}")
        assert row is not None
        self.assertRegex(_cell(row["licence"]), r"^GPL-3\.0(?:-only|-or-later)?$",
                         "Neo4j Community is listed as GPL-3.0 (A43, R4)")
        self.assertRegex(_cell(row["source"]), r"https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/\S*)?",
                         "Neo4j's row gives an https source URL (R4)")
        self.assertNotRegex(_cell(row["source"]), r"http://", "the source URL is https")

    def test_notices_mark_phoenix_as_exception(self):
        phoenix = self._vendor().get("phoenix")
        self.assertIsNotNone(phoenix, "precondition: phoenix is a stack image")
        _, _, out, _ = self._ok()
        row = self._image_rows(self._notices(out)).get(str(phoenix))
        self.assertIsNotNone(row, f"phoenix ({phoenix}) has no row in {self.NOTICES}")
        assert row is not None
        self.assertNotRegex(_cell(row["licence"]), _PLACEHOLDER_LICENCE, "Phoenix is listed with its licence")
        text = " | ".join(row.values())
        self.assertRegex(text, r"(?i)\bexception\b",
                         "Phoenix is marked as the exception to `open-source components only` (human Q43)")
        self.assertRegex(text, r"\bQ43\b", "the mark cites the human ruling (Q43)")
        others = [r for ref, r in self._image_rows(self._notices(out)).items() if ref != phoenix]
        self.assertFalse([r for r in others if re.search(r"\bQ43\b", " | ".join(r.values()))],
                         "only Phoenix carries the Q43 exception")

    # ---- architecture §2.5 Bundle root, §2.6 item 6 ---------------------------

    def test_bundle_contents(self):
        # Things the bundle must leave behind, present in the build tree.
        shutil.copyfile(ROOT / "docker-compose.offline.yml", self.repo / "docker-compose.offline.yml")
        (self.repo / "docker").mkdir()
        shutil.copyfile(ROOT / "docker" / "app.Dockerfile", self.repo / "docker" / "app.Dockerfile")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture: offline compose and docker/")
        (self.repo / ".env").write_text("KE_STORES__POSTGRES__PASSWORD=local-secret\n", encoding="utf-8")
        (self.repo / "docker-compose.override.yml").write_text("services: {}\n", encoding="utf-8")
        tracked_config = sorted(self._git("ls-files", "config").split())
        _, _, out, _ = self._ok()
        with self.subTest(part="app/ is exact"):
            expected = sorted({"docker-compose.yml", ".env.example", "docs/quickstart.md", *tracked_config,
                               *(f"scripts/{s}" for s in ("launch.sh", "teardown.sh", "smoke.sh", "launch.ps1",
                                                          "teardown.ps1", "net_isolated.sh"))},
                              key=lambda s: s.encode("utf-8"))
            self.assertEqual(_regular_files(out / "app"), expected, "app/ holds exactly §2.5 Bundle step 3")
        with self.subTest(part="the root is exact"):
            self.assertEqual(sorted(p.name for p in out.iterdir()),
                             sorted(["MANIFEST.sha256", "bundle.json", "install.sh", "install.ps1", "NOTICE.md",
                                     "licenses", self.NOTICES, "app", "images"]),
                             "the bundle root holds §2.5 Bundle step 4 and the records")
        with self.subTest(part="NOTICE.md and licenses/ are the committed files"):
            self.assertTrue((ROOT / "NOTICE.md").is_file(), "NOTICE.md is not committed at the repository root")
            for lic in ("LGPL-3.0.txt", "GPL-3.0.txt"):
                self.assertTrue((ROOT / "licenses" / lic).is_file(), f"licenses/{lic} is not committed")
            self.assertTrue((out / "NOTICE.md").is_file(), "the bundle has no NOTICE.md")
            if (ROOT / "NOTICE.md").is_file() and (out / "NOTICE.md").is_file():
                self.assertEqual(_sha256(out / "NOTICE.md"), _sha256(ROOT / "NOTICE.md"))
            committed = _regular_files(ROOT / "licenses") if (ROOT / "licenses").is_dir() else []
            shipped = _regular_files(out / "licenses") if (out / "licenses").is_dir() else []
            self.assertTrue(committed, "licenses/ is empty or missing")
            self.assertEqual(shipped, committed, "licenses/ ships as committed")
            for rel in set(shipped) & set(committed):
                self.assertEqual(_sha256(out / "licenses" / rel), _sha256(ROOT / "licenses" / rel))
        with self.subTest(part="listed in the manifest"):
            listed = {ln.split("  ", 1)[1] for ln in
                      (out / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines() if "  " in ln}
            want = {"NOTICE.md", self.NOTICES} | {f"licenses/{r}" for r in
                                                  (_regular_files(out / "licenses") if (out / "licenses").is_dir()
                                                   else [])}
            self.assertEqual(sorted(want - listed), [], "not in MANIFEST.sha256")
            self.assertTrue(any(r.startswith("licenses/") for r in listed), "no licenses/ file in the manifest")
        with self.subTest(part="never shipped"):
            found = sorted(_rel(p, out) for p in out.rglob("*")
                           if p.name in _NOT_SHIPPED or p.name.endswith("Dockerfile") or p.name == "docker")
            self.assertEqual(found, [], "a verify-only, build-only or local file is in the bundle")
        with self.subTest(part="static: NOTICE.md and licenses/ are copied with no exists-guard"):
            body = "\n".join(l for l in (ROOT / "scripts" / "bundle.sh").read_text(encoding="utf-8")
                             .splitlines() if not l.lstrip().startswith("#"))
            self.assertNotRegex(body, r"\[\[?\s+-[efd]\s+\"?(?:NOTICE\.md|licenses)\b",
                                "bundle.sh guards the NOTICE.md/licenses copy with an exists-test (§2.5: "
                                "copied unconditionally)")
        for rel in ("NOTICE.md", "licenses"):
            with self.subTest(part=f"missing from the tree: {rel}"):
                src = self.repo / rel
                self.assertTrue(src.exists(), f"precondition: {rel} is committed (copied into the fixture)")
                if not src.exists():
                    continue
                aside = self.tmp / f"aside-{rel}"
                shutil.move(str(src), str(aside))
                try:
                    result, _, out2 = self._bundle()
                finally:
                    shutil.move(str(aside), str(src))
                self.assertNotEqual(result.returncode, 0,
                                    f"bundle.sh wrote a bundle without {rel}:\n" + self._out(result))
                self.assertFalse((out2 / "MANIFEST.sha256").exists(), "a manifest was written regardless")


class DistIgnoredTest(unittest.TestCase):
    """PS-3.1 Where written (A40): bundles go under a gitignored `dist/`, and
    `dist/` stays out of every build context (architecture §2.5)."""

    def test_dist_is_gitignored(self):
        for name in (".gitignore", ".dockerignore"):
            with self.subTest(file=name):
                lines = [ln.strip() for ln in (ROOT / name).read_text(encoding="utf-8").splitlines()]
                self.assertTrue({"dist", "dist/", "/dist", "/dist/"} & set(lines),
                                f"{name} does not ignore dist/")


# --------------------------------------------------------------------------
# install.sh on macOS (PS-3.1 per-arch bundles, Q50): bash 3.2 and BSD tools
# --------------------------------------------------------------------------

def _forbid(rx: str) -> re.Pattern[str]:
    return re.compile(rx)


_OPTS = r"(?:\s+-[A-Za-z0-9]+)*\s+"  # leading option clusters before the one tested
# PS-3.1 forbid list -> (pattern over code with comments removed, a sample it must catch).
GNU_OR_BASH4: dict[str, tuple[re.Pattern[str], str]] = {
    "declare -A / local -A / typeset -A": (
        _forbid(r"\b(?:declare|local|typeset)(?:\s+-[A-Za-z0-9]+)*\s+-[A-Za-z0-9]*A"), "local -A seen"),
    "declare -n / local -n": (
        _forbid(r"\b(?:declare|local|typeset)(?:\s+-[A-Za-z0-9]+)*\s+-[A-Za-z0-9]*n\b"), "declare -n ref=x"),
    "mapfile / readarray": (_forbid(r"\b(?:mapfile|readarray)\b"), "mapfile -t lines < f"),
    "${x,,} ${x^^} ${x,} ${x^}": (
        _forbid(r"\$\{[#!]?[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?(?:,,?|\^\^?)"), 'v="${name^^}"'),
    "|&": (_forbid(r"\|&"), "cmd |& tee f"),
    "&>>": (_forbid(r"&>>"), "cmd &>> f"),
    ";;&": (_forbid(r";;&"), "a) x ;;&"),
    "coproc": (_forbid(r"\bcoproc\b"), "coproc cat"),
    "wait -n": (_forbid(r"\bwait\s+-n\b"), "wait -n"),
    "globstar": (_forbid(r"\bglobstar\b"), "shopt -s globstar"),
    "mv -T / cp -T": (
        _forbid(r"\b(?:mv|cp)\b" + _OPTS + r"(?:-[A-Za-z0-9]*T|--no-target-directory)"), 'mv -T -- "$a" "$b"'),
    "stat -c / stat --": (_forbid(r"\bstat\b" + _OPTS + r"(?:-[A-Za-z0-9]*c|--)"), "stat -c %a f"),
    "readlink -f": (_forbid(r"\breadlink\b" + _OPTS + r"(?:-[A-Za-z0-9]*f|--canonicalize)"), "readlink -f x"),
    "realpath": (_forbid(r"\brealpath\b"), 'p="$(realpath x)"'),
    "find ... -printf": (_forbid(r"(?<![\w-])-f?printf\b"), "find . -type f -printf '%s\\n'"),
    "sed -i / sed -r": (
        _forbid(r"\bsed\b" + _OPTS + r"(?:-[A-Za-z0-9]*[ir]|--in-place|--regexp-extended)"), "sed -i 's/a/b/' f"),
    "grep -P": (_forbid(r"\bgrep\b" + _OPTS + r"(?:-[A-Za-z0-9]*P|--perl-regexp)"), "grep -oP 'x'"),
    "sort -z / sort -V": (
        _forbid(r"\bsort\b" + _OPTS + r"(?:-[A-Za-z0-9]*[zV]|--zero-terminated|--version-sort)"), "sort -z"),
    "xargs -r": (_forbid(r"\bxargs\b" + _OPTS + r"(?:-[A-Za-z0-9]*r|--no-run-if-empty)"), "xargs -0r rm"),
    "du -b": (_forbid(r"\bdu\b" + _OPTS + r"(?:-[A-Za-z0-9]*b|--bytes)"), "du -sb dir"),
    "timeout": (_forbid(r"\btimeout\b"), "timeout 5 docker info"),
    "tac": (_forbid(r"\btac\b"), "tac f"),
    "base64 -w": (_forbid(r"\bbase64\b" + _OPTS + r"(?:-[A-Za-z0-9]*w|--wrap)"), "base64 -w0 f"),
    "date -d": (_forbid(r"\bdate\b" + _OPTS + r"(?:-[A-Za-z0-9]*d|--date)"), "date -u -d @0"),
    # Review P5 (rework round 2): bash 4+ forms the list missed.
    "[[ -v / [ -v / test -v": (_forbid(r"(?:\[\[?|\btest)\s+(?:!\s+)?-v\b"), "[[ -v name ]]"),
    "${x@Q} and other @ transforms": (
        _forbid(r"\$\{[#!]?[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?@[QEPAaKkUuL]\}"), 'echo "${x@Q}"'),
    "negative subscript ${a[-1]}": (_forbid(r"\$\{[#!]?[A-Za-z_][A-Za-z0-9_]*\[\s*-\s*[0-9$]"), 'last="${a[-1]}"'),
    "negative substring length ${x:0:-1}": (
        _forbid(r"\$\{[A-Za-z_][A-Za-z0-9_]*:[^}:]*:\s*-\s*[0-9$]"), 'v="${x:0:-1}"'),
    "$EPOCHSECONDS / $EPOCHREALTIME / $BASHPID": (
        _forbid(r"\$\{?(?:EPOCHSECONDS|EPOCHREALTIME|BASHPID)\b"), "t=$EPOCHSECONDS"),
    "printf '%(...)T'": (_forbid(r"%\([^)]*\)T"), "printf '%(%s)T' -1"),
    "local -": (_forbid(r"\blocal\s+-(?=\s|;|$)"), "local -"),
    "declare -g / -l / -u": (
        _forbid(r"\b(?:declare|local|typeset)(?:\s+-[A-Za-z0-9]+)*\s+-[A-Za-z0-9]*[glu]"), "declare -g x=1"),
    "shopt -s lastpipe": (_forbid(r"\blastpipe\b"), "shopt -s lastpipe"),
    "case fall-through ;&": (_forbid(r"(?<!;);&(?!&)"), "a) x ;&"),
}
_MKTEMP = re.compile(r"\bmktemp\b([^)\n;|&]*)")
_SHA_CALL = re.compile(r"\b(?:sha256sum|shasum)\b")
_FUNC_START = re.compile(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*(\{.*)?$")


def _code_lines(text: str) -> list[tuple[int, str]]:
    """(line number, code) with whole-line and trailing comments removed."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        out.append((n, re.sub(r"(^|\s)#.*$", "", line)))
    return out


def _functions(text: str) -> dict[str, tuple[int, int]]:
    """name -> (first line, last line) of each shell function."""
    lines = text.splitlines()
    found: dict[str, tuple[int, int]] = {}
    i = 0
    while i < len(lines):
        m = _FUNC_START.match(lines[i])
        if m:
            if (m.group(2) or "").rstrip().endswith("}"):
                found[m.group(1)] = (i + 1, i + 1)
            else:
                end = next((j for j in range(i + 1, len(lines)) if re.match(r"^\}\s*$", lines[j])), i)
                found[m.group(1)] = (i + 1, end + 1)
                i = end
        i += 1
    return found


def _portability_findings(text: str, require_sha_helper: bool = True) -> list[str]:
    """The forbid list over `text`. The single-SHA-helper rule applies when
    `require_sha_helper` is set or the script hashes anything at all."""
    code = _code_lines(text)
    hashes = any(_SHA_CALL.search(re.sub(r"'[^']*'", "''", ln)) for _, ln in code)
    require_sha_helper = require_sha_helper or hashes
    findings = []
    for name, (rx, _) in GNU_OR_BASH4.items():
        for n, line in code:
            if rx.search(line):
                findings.append(f"line {n}: {name}: {line.strip()}")
    for n, line in code:
        for m in _MKTEMP.finditer(line):
            if "XXXXXX" not in m.group(1):
                findings.append(f"line {n}: mktemp with no XXXXXX template: {line.strip()}")
    funcs = _functions(text)
    helpers = []
    for name, (a, b) in funcs.items():
        body = "\n".join(ln for n, ln in code if a <= n <= b)
        if re.search(r"\bshasum\s+-a\s*256\b", body) and re.search(r"\bsha256sum\b", body):
            helpers.append((name, a, b))
    if require_sha_helper and len(helpers) != 1:
        findings.append("SHA-256 must come from exactly one helper function that uses sha256sum if "
                        f"present and otherwise `shasum -a 256`; found {[h[0] for h in helpers]}")
    span = (helpers[0][1], helpers[0][2]) if len(helpers) == 1 else (0, -1)
    for n, line in code:
        if span[0] <= n <= span[1]:
            continue
        if _SHA_CALL.search(re.sub(r"'[^']*'", "''", line)):
            findings.append(f"line {n}: sha256sum/shasum outside the helper: {line.strip()}")
    return findings


# A GNU-only option makes the shim exit 97 (PS-3.1). Long options are GNU-only
# for these tools, except sort's portable long forms.
_BSD_RULES: dict[str, dict[str, Any]] = {
    "mv": {"letters": "Tt", "long": "all"},
    "cp": {"letters": "Ttd", "long": "all"},
    "stat": {"letters": "c", "long": "all"},
    "readlink": {"letters": "fem", "long": "all"},
    "sed": {"letters": "irzsu", "long": "all"},
    "sort": {"letters": "zV", "long": ["--zero-terminated", "--version-sort"]},
    "xargs": {"letters": "rda", "long": "all"},
    "date": {"letters": "d", "long": "all"},
    "find": {"predicates": ["-printf", "-fprintf", "-fprint", "-fprint0", "-regextype", "-readable",
                            "-writable", "-executable", "-xtype"]},
}

_BSD_SHIM = r'''
import os, sys
TOOL, REAL, RULES = %r, %r, %r
args = sys.argv[1:]
bad = None
if "predicates" in RULES:
    bad = next((a for a in args if a in RULES["predicates"]), None)
else:
    for a in args:
        if a == "--":
            break
        if a.startswith("--"):
            if RULES["long"] == "all" or a.split("=", 1)[0] in RULES["long"]:
                bad = a
                break
        elif a.startswith("-") and len(a) > 1 and any(c in RULES["letters"] for c in a[1:]):
            bad = a
            break
if bad is not None:
    with open(os.environ["BSD_SHIM_VIOLATIONS"], "a", encoding="utf-8") as fh:
        fh.write("%%s %%s\n" %% (TOOL, " ".join(args)))
    sys.stderr.write("bsd shim: %%s: GNU-only option %%s\n" %% (TOOL, bad))
    sys.exit(97)
os.execv(REAL, [REAL] + args)
'''

_SHASUM_SHIM = r'''
import hashlib, os, sys
args = sys.argv[1:]
with open(os.environ["SHASUM_LOG"], "a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\n")
if args[:2] != ["-a", "256"]:
    sys.stderr.write("shasum shim: only `shasum -a 256 [--] [file...]` is provided\n")
    sys.exit(97)
files = [a for a in args[2:] if a != "--"] or ["-"]
for f in files:
    data = sys.stdin.buffer.read() if f == "-" else open(f, "rb").read()
    print("%s  %s" % (hashlib.sha256(data).hexdigest(), f))
'''


class InstallShPortableTest(unittest.TestCase):
    """PS-3.1 *install.sh on macOS (Q50)*: bash 3.2 and BSD userland. The shim
    run approximates macOS; it is not proof of it."""

    SCRIPT = ROOT / "scripts" / "install.sh"

    def test_install_sh_uses_no_gnu_or_bash4_constructs(self):
        # The forbid list catches its own samples, so a pattern that matches
        # nothing cannot pass this test vacuously.
        for name, (rx, sample) in GNU_OR_BASH4.items():
            with self.subTest(self_check=name):
                self.assertRegex(sample, rx)
        with self.subTest(self_check="mktemp with no XXXXXX template"):
            self.assertTrue([f for f in _portability_findings("x=$(mktemp -d)\n") if "mktemp" in f])
        with self.subTest(self_check="sha256sum outside the helper"):
            sample = ('sha() {\n  if command -v sha256sum >/dev/null; then sha256sum -- "$1"; '
                      'else shasum -a 256 -- "$1"; fi\n}\nsum="$(sha256sum -- f)"\n')
            self.assertTrue([f for f in _portability_findings(sample) if "outside the helper" in f])
        self.assertTrue(self.SCRIPT.is_file(), "scripts/install.sh is missing")
        findings = _portability_findings(self.SCRIPT.read_text(encoding="utf-8"))
        self.assertEqual(findings, [],
                         "scripts/install.sh uses bash 4+ or GNU-only constructs (PS-3.1, Q50: it must run "
                         "under macOS /bin/bash 3.2 with BSD tools):\n" + "\n".join(findings))

    def test_operator_scripts_use_no_gnu_or_bash4_constructs(self):
        """Rework round 2 (review RB2a, Q53 extended): launch.sh and
        teardown.sh are on the operator path too, so the same forbid list
        (with review P5's additions) applies to all three scripts."""
        for name in ("install.sh", "launch.sh", "teardown.sh"):
            with self.subTest(script=name):
                path = ROOT / "scripts" / name
                self.assertTrue(path.is_file(), f"scripts/{name} is missing")
                findings = _portability_findings(path.read_text(encoding="utf-8"),
                                                 require_sha_helper=name == "install.sh")
                self.assertEqual(findings, [],
                                 f"scripts/{name} uses bash 4+ or GNU-only constructs (Q53: the operator "
                                 "scripts run under macOS /bin/bash 3.2 with BSD tools):\n" + "\n".join(findings))

    # ---- the shim run ------------------------------------------------------

    _SHIM_TESTS = ("test_install_sh_runs_with_bsd_tool_shims", "test_launch_and_teardown_run_with_bsd_tool_shims",
                   "test_launch_enforces_compose_version_floor")

    def setUp(self) -> None:
        if self._testMethodName not in self._SHIM_TESTS:
            return
        if os.name == "nt":
            self.skipTest("POSIX shims and PATH; the gates image is Linux")
        self.bash = shutil.which("bash")
        self.assertIsNotNone(self.bash, "bash is not on PATH")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        fakebin, shimbin, sysbin = self.tmp / "fakebin", self.tmp / "shimbin", self.tmp / "sysbin"
        fake_docker.install(fakebin)
        shimbin.mkdir()
        sysbin.mkdir()
        for tool, rules in _BSD_RULES.items():
            real = shutil.which(tool)
            self.assertIsNotNone(real, f"{tool} is not on PATH")
            shim = shimbin / tool
            shim.write_text(f"#!{sys.executable}\n" + _BSD_SHIM % (tool, real, rules),
                            encoding="utf-8", newline="\n")
            shim.chmod(0o755)
        shasum = shimbin / "shasum"
        shasum.write_text(f"#!{sys.executable}\n{_SHASUM_SHIM}", encoding="utf-8", newline="\n")
        shasum.chmod(0o755)
        # Everything else from the system, except sha256sum (so the shasum fallback runs).
        skip = set(_BSD_RULES) | {"sha256sum", "shasum", "docker"}
        for d in ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"):
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                src = os.path.join(d, name)
                if name in skip or (sysbin / name).exists() or not os.access(src, os.X_OK) \
                        or os.path.isdir(src):
                    continue
                os.symlink(src, sysbin / name)
        self.path = os.pathsep.join(str(p) for p in (fakebin, shimbin, sysbin))
        self.violations = self.tmp / "violations.log"
        self.shasum_log = self.tmp / "shasum.log"
        self.log = self.tmp / "docker.log"
        self.json = self.tmp / "docker.jsonl"
        self.n = 0

    def _run(self, arch: str = "amd64", tamper: Any = None, **env: str
             ) -> tuple[subprocess.CompletedProcess, list[list[str]], str, Path]:
        self.n += 1
        bundle, target = self.tmp / f"bundle{self.n}", self.tmp / f"target{self.n}"
        _make_fixture(bundle, None, arch)
        if tamper:
            tamper(bundle)
        for f in (self.violations, self.shasum_log, self.log, self.json):
            f.write_text("", encoding="utf-8")
        run_env = {
            "PATH": self.path, "HOME": str(self.tmp),
            "BSD_SHIM_VIOLATIONS": str(self.violations), "SHASUM_LOG": str(self.shasum_log),
            "FAKE_DOCKER_LOG": str(self.log), "FAKE_DOCKER_JSON": str(self.json),
            "FAKE_DOCKER_ENGINE": ENGINE_OK,
            "FAKE_COMPOSE_IMAGES": json.dumps(FIXTURE_STACK_IMAGES),
            "FAKE_DOCKER_LOAD": json.dumps({"ke-app.tar": f"Loaded image: {LOADED_APP_NAME}"}),
        }
        run_env.update(env)
        assert self.bash is not None
        result = subprocess.run([self.bash, "--posix", str(bundle / "install.sh"), str(target)],
                                env=run_env, cwd=bundle, capture_output=True, text=True, timeout=120)
        calls = [r["argv"] for r in fake_docker.records(self.json)]
        return result, calls, self.log.read_text(encoding="utf-8"), target

    def test_install_sh_runs_with_bsd_tool_shims(self):
        self.assertIsNone(shutil.which("sha256sum", path=self.path), "the shim PATH must lack sha256sum")

        def out(r: subprocess.CompletedProcess) -> str:
            return (r.stdout or "") + (r.stderr or "")

        def loads(calls: list[list[str]]) -> list[list[str]]:
            return [c for c in calls if c[:1] == ["load"]]

        with self.subTest(case="clean_install"):
            result, calls, _, target = self._run()
            self.assertEqual(self.violations.read_text(encoding="utf-8"), "",
                             "install.sh used a GNU-only tool option:\n" + out(result))
            self.assertEqual(result.returncode, 0,
                             "install.sh failed under bash --posix with BSD-like tools and no "
                             "sha256sum:\n" + out(result))
            self.assertTrue(self.shasum_log.read_text(encoding="utf-8").strip(),
                            "with no sha256sum, the helper falls back to `shasum -a 256`")
            self.assertEqual(len(loads(calls)), len(FIXTURE_ENTRIES), calls)
            self.assertTrue((target / "docker-compose.override.yml").is_file())

        def changed(b: Path) -> None:
            p = b / "images" / "ke-app.tar"
            p.write_bytes(bytes([p.read_bytes()[0] ^ 1]) + p.read_bytes()[1:])

        with self.subTest(case="tamper_changed_file"):
            result, _, log, target = self._run(tamper=changed)
            self.assertEqual(self.violations.read_text(encoding="utf-8"), "",
                             "install.sh used a GNU-only tool option:\n" + out(result))
            self.assertNotEqual(result.returncode, 0, out(result))
            self.assertEqual(log, "", "a docker command ran before the manifest check passed")
            self.assertIn("images/ke-app.tar", out(result))
            self.assertRegex(out(result).lower(), RULE_HASH)
            self.assertFalse(target.exists() and any(target.iterdir()))
        with self.subTest(case="arch_mismatch"):
            result, calls, _, target = self._run(arch="arm64", FAKE_DOCKER_ARCH="x86_64")
            self.assertEqual(self.violations.read_text(encoding="utf-8"), "",
                             "install.sh used a GNU-only tool option:\n" + out(result))
            self.assertNotEqual(result.returncode, 0, out(result))
            self.assertIn("arm64", out(result))
            self.assertTrue("amd64" in out(result) or "x86_64" in out(result), out(result))
            self.assertEqual(loads(calls), [])
            self.assertFalse(target.exists() and any(target.iterdir()))

    def test_launch_and_teardown_run_with_bsd_tool_shims(self):
        """Rework round 2 (review RB2a, Q53 extended): launch.sh (argument
        and version parsing through `compose up`) and teardown.sh run under
        bash --posix with the BSD-like shims against the fake docker."""
        proj = self.tmp / "proj"
        (proj / "scripts").mkdir(parents=True)
        for rel in (".env.example", "docker-compose.yml", "scripts/launch.sh", "scripts/teardown.sh"):
            shutil.copyfile(ROOT / rel, proj / rel)

        def run(argv: list[str]) -> tuple[subprocess.CompletedProcess, list[list[str]], str]:
            for f in (self.violations, self.log, self.json):
                f.write_text("", encoding="utf-8")
            env = {"PATH": self.path, "HOME": str(self.tmp), "BSD_SHIM_VIOLATIONS": str(self.violations),
                   "SHASUM_LOG": str(self.shasum_log), "FAKE_DOCKER_LOG": str(self.log),
                   "FAKE_DOCKER_JSON": str(self.json), "FAKE_DOCKER_ENGINE": ENGINE_OK}
            assert self.bash is not None
            r = subprocess.run([self.bash, "--posix", *argv], env=env, cwd=proj,
                               capture_output=True, text=True, timeout=120)
            return r, [rec["argv"] for rec in fake_docker.records(self.json)], \
                self.violations.read_text(encoding="utf-8")

        with self.subTest(script="launch.sh"):
            result, calls, bad = run(["scripts/launch.sh"])
            out = result.stdout + result.stderr
            self.assertEqual(bad, "", "launch.sh used a GNU-only tool option:\n" + out)
            self.assertEqual(result.returncode, 0, "launch.sh failed with BSD-like tools:\n" + out)
            self.assertTrue([c for c in calls if c[:1] == ["compose"] and "up" in c], calls)
        with self.subTest(script="teardown.sh"):
            result, calls, bad = run(["scripts/teardown.sh", "--volumes"])
            out = result.stdout + result.stderr
            self.assertEqual(bad, "", "teardown.sh used a GNU-only tool option:\n" + out)
            self.assertEqual(result.returncode, 0, "teardown.sh failed with BSD-like tools:\n" + out)
            self.assertTrue([c for c in calls if c[:1] == ["compose"] and "down" in c], calls)
        with self.subTest(script="teardown.sh bad argument"):
            result, _, bad = run(["scripts/teardown.sh", "--nope"])
            self.assertEqual(bad, "")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_launch_enforces_compose_version_floor(self):
        """Review RB5b (kills mutant atl, `at_least` always true): launch.sh
        refuses Compose 2.23.9 and 2 and accepts 2.24, 2.24.0-desktop.1 and
        2.100.1, under bash and under bash --posix with the BSD-like shims.
        The fake's `compose version --short` prints FAKE_COMPOSE_VERSION."""
        proj = self.tmp / "proj-version"
        (proj / "scripts").mkdir(parents=True)
        for rel in (".env.example", "docker-compose.yml", "scripts/launch.sh"):
            shutil.copyfile(ROOT / rel, proj / rel)
        fakebin = self.tmp / "fakebin"
        plain = f"{fakebin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
        modes = {"bash": ([], plain), "bash --posix + BSD shims": (["--posix"], self.path)}
        versions = {"2.23.9": False, "2": False, "2.24": True, "2.24.0-desktop.1": True, "2.100.1": True}
        for mode, (flags, path) in modes.items():
            for version, ok in versions.items():
                with self.subTest(shell=mode, compose=version):
                    for f in (self.violations, self.log, self.json):
                        f.write_text("", encoding="utf-8")
                    env = {"PATH": path, "HOME": str(self.tmp), "BSD_SHIM_VIOLATIONS": str(self.violations),
                           "SHASUM_LOG": str(self.shasum_log), "FAKE_DOCKER_LOG": str(self.log),
                           "FAKE_DOCKER_JSON": str(self.json), "FAKE_DOCKER_ENGINE": ENGINE_OK,
                           "FAKE_COMPOSE_VERSION": version}
                    assert self.bash is not None
                    r = subprocess.run([self.bash, *flags, "scripts/launch.sh"], env=env, cwd=proj,
                                       capture_output=True, text=True, timeout=120)
                    out = r.stdout + r.stderr
                    calls = [rec["argv"] for rec in fake_docker.records(self.json)]
                    ups = [c for c in calls if c[:1] == ["compose"] and "up" in c]
                    self.assertEqual(self.violations.read_text(encoding="utf-8"), "",
                                     "launch.sh used a GNU-only tool option:\n" + out)
                    self.assertTrue([c for c in calls if c[:2] == ["compose", "version"]],
                                    f"launch.sh never asked the fake for its compose version: {calls}")
                    if ok:
                        self.assertEqual(r.returncode, 0, f"launch.sh refused Compose {version} (>= 2.24):\n" + out)
                        self.assertTrue(ups, f"launch.sh did not reach `compose up` with Compose {version}")
                    else:
                        self.assertNotEqual(r.returncode, 0,
                                            f"launch.sh accepted Compose {version} (< 2.24; review RB5b):\n" + out)
                        self.assertIn("2.24", out, "the refusal names the minimum")
                        self.assertIn(version, out, "the refusal names the version found")
                        self.assertEqual(ups, [], f"`compose up` ran with Compose {version}")


# --------------------------------------------------------------------------
# Rework round 2, review RB2(c): the operator scripts keep their exec bit
# --------------------------------------------------------------------------

class ExecBitTest(unittest.TestCase):
    """`core.filemode=false` here, so a plain `git add` records 100644 and a
    Linux checkout gets "Permission denied". git must record 100755
    (`git add --chmod=+x`)."""

    def test_operator_scripts_are_executable_in_git(self):
        # Review B2 (platform-offline rework round 1): verify.sh and smoke.sh
        # call offline_check.sh and net_isolated.sh directly, not through bash.
        scripts = ("scripts/bundle.sh", "scripts/install.sh", "scripts/launch.sh", "scripts/teardown.sh",
                   "scripts/offline_check.sh", "scripts/net_isolated.sh")
        done = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", "--", *scripts],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        modes = {ln.split("\t", 1)[1]: ln.split()[0] for ln in done.stdout.splitlines() if "\t" in ln}
        for rel in scripts:
            with self.subTest(script=rel):
                self.assertIn(rel, modes, f"{rel} is not in the git index (review RB2c: "
                                          "`git add --chmod=+x`)")
                self.assertEqual(modes[rel], "100755",
                                 f"git records {rel} as {modes[rel]}, not 100755 (review RB2c)")


# --------------------------------------------------------------------------
# PS-3.2 Docs (amended 2026-10-19, "build it for both"): docs/quickstart.md
# --------------------------------------------------------------------------

class QuickstartOfflineTest(unittest.TestCase):
    QUICKSTART = ROOT / "docs" / "quickstart.md"

    def _text(self) -> str:
        self.assertTrue(self.QUICKSTART.is_file(), "docs/quickstart.md is missing")
        return self.QUICKSTART.read_text(encoding="utf-8")

    def test_quickstart_describes_offline_install(self):
        text = self._text()
        required = {
            "the bundler": r"scripts/bundle\.sh",
            "both installers": r"install\.sh[\s\S]*install\.ps1|install\.ps1[\s\S]*install\.sh",
            "M-3 step 1: the out-of-band release record": r"\.manifest\.sha256",
            "M-3 step 1: the manifest it is compared with": r"MANIFEST\.sha256",
            "M-3 step 2: check the installer with sha256sum": r"\bsha256sum\b",
            "M-3 step 2: check the installer with Get-FileHash": r"Get-FileHash",
            "M-3 step 3: --expect-manifest": r"--expect-manifest",
            "M-3 step 3: -ExpectManifest": r"-ExpectManifest",
            "arm64 bundles through DOCKER_CONTEXT": r"DOCKER_CONTEXT",
            "both arches": r"\bamd64\b[\s\S]*\barm64\b|\barm64\b[\s\S]*\bamd64\b",
            "--out ending in -<arch>": r"bundle\.sh[^\n]*--out\s+\S*-(?:<arch>|amd64|arm64)\b",
            "the umask note (review N9)": r"\bumask\b",
            "macOS offline install with bash": r"(?is)mac\s?os.{0,400}install\.sh|install\.sh.{0,400}mac\s?os",
        }
        for what, rx in required.items():
            with self.subTest(item=what):
                self.assertIsNotNone(re.search(rx, text),
                                     f"docs/quickstart.md does not give: {what} (PS-3.2 Docs; /{rx}/)")

    @staticmethod
    def _code_blocks(text: str) -> list[tuple[int, list[str]]]:
        """(index of the opening fence line, lines) of each fenced block."""
        lines, blocks, i = text.splitlines(), [], 0
        while i < len(lines):
            if lines[i].lstrip().startswith("```"):
                j = next((k for k in range(i + 1, len(lines)) if lines[k].lstrip().startswith("```")), len(lines))
                blocks.append((i, lines[i + 1:j]))
                i = j
            i += 1
        return blocks

    # Rework round 2 (review RB2, security quickstart gaps a-e).
    OPERATOR_ONLY = (r"(?i)\bparent\b[^\n]{0,240}\b(?:only you|only the operator|operator[- ]only|"
                     r"no one else|nobody else|not writable by)|\b(?:only you|only the operator|operator[- ]only)"
                     r"\b[^\n]{0,240}\bparent\b")

    def test_quickstart_offline_commands_run_as_written(self):
        """Review RB2(b, c), security (c): the commands work on a stock host."""
        text = self._text()
        required = {
            "install.ps1 through `pwsh -File` (RB2b: PS 5.1 cannot run it)":
                r"pwsh\s+(?:-\w+\s+)*-File\s+\S*install\.ps1",
            "`bash ./install.sh` (RB2c: the exec bit is lost on FAT/zip)": r"\bbash\s+\./install\.sh\b",
            "`bash scripts/bundle.sh` (RB2c)": r"\bbash\s+(?:\./)?scripts/bundle\.sh\b",
            "`shasum -a 256 -c` for the manifest check on a Mac (P6, security c)": r"\bshasum\s+-a\s+256\s+-c\b",
        }
        for what, rx in required.items():
            with self.subTest(item=what):
                self.assertIsNotNone(re.search(rx, text), f"docs/quickstart.md does not give: {what} (/{rx}/)")
        bad = []
        for _, block in self._code_blocks(text):
            for line in block:
                cmd = re.sub(r"^\s*(?:\$\s+)?(?:[A-Z_]+=\S*\s+)*", "", line)
                if re.match(r"(?:\./|\.\\)?install\.(?:sh|ps1)\b|(?:\./)?scripts/bundle\.sh\b", cmd):
                    bad.append(line.strip())
        with self.subTest(item="no bare ./install.sh, .\\install.ps1 or scripts/bundle.sh command"):
            self.assertEqual(bad, [], "these quickstart commands need the exec bit or Windows PowerShell 5.1; "
                                      "use `bash ...` and `pwsh -File ...` (review RB2b/c)")

    def test_quickstart_offline_safety_notes(self):
        """Security quickstart gaps (b) and (e), review RB2(d) and P6."""
        text = self._text()
        required = {
            "copy the bundle off shared or removable media before verifying (security M-4, gap b)":
                r"(?i)\bcop(?:y|ies)\b[^\n]{0,240}\b(?:shared|removable|writable|network share|usb)\b"
                r"|\b(?:shared|removable)\b[^\n]{0,240}\bcop(?:y|ies)\b",
            "the target's parent writable only by the operator (security H-1, gap e; RB2d)": self.OPERATOR_ONLY,
            "bundle.sh needs a Linux build host (P6)":
                r"(?i)\bbuild (?:host|machine)\b[^\n]{0,240}\blinux\b|\blinux\b[^\n]{0,240}\bbuild (?:host|machine)\b",
        }
        for what, rx in required.items():
            with self.subTest(item=what):
                self.assertIsNotNone(re.search(rx, text), f"docs/quickstart.md does not say: {what} (/{rx}/)")

    def test_quickstart_target_not_directly_under_c_or_opt(self):
        """Security H-1 (gap a), review RB2(d): an example target directly
        under `C:\\` or `/opt` puts staging in a parent others can write (or
        cannot be written by a non-root operator). Such an example is allowed
        only with the operator-only-parent note in the ten lines above it."""
        text = self._text()
        lines = text.splitlines()
        risky = re.compile(r"-Target\s+['\"]?[A-Za-z]:\\[^\\\s'\"]+['\"]?(?:\s|$)"
                           r"|install\.sh\b[^\n]*\s['\"]?/opt/[^/\s'\"]+/?['\"]?\s*$")
        bad = []
        for start, block in self._code_blocks(text):
            for k, line in enumerate(block):
                if risky.search(line):
                    above = "\n".join(lines[max(0, start - 10):start + 1 + k])
                    if not re.search(self.OPERATOR_ONLY, above):
                        bad.append(line.strip())
        self.assertEqual(bad, [], "quickstart example targets directly under C:\\ or /opt without the "
                                  "operator-only parent note (security H-1, review RB2d)")

    def test_quickstart_names_existing_scripts(self):
        """Review RB4: every `scripts/<name>` or `scripts\\<name>` in a
        quickstart code block or inline code span names a file under
        scripts/. A `scripts` run straight into a name (`scriptsaunch.ps1`,
        the `\\l` of `scripts\\launch.ps1` eaten) is a broken command."""
        text = self._text()
        spans = ["\n".join(block) for _, block in self._code_blocks(text)]
        spans += re.findall(r"(?<!`)`([^`\n]+)`(?!`)", text)
        bad = []
        for span in spans:
            for m in re.finditer(r"(?<![A-Za-z0-9_])scripts([/\\]?)([A-Za-z0-9_.-]+\.(?:sh|ps1|py))\b", span):
                sep, name = m.groups()
                if not sep:
                    bad.append(f"{m.group(0)} (no separator after `scripts`)")
                elif not (ROOT / "scripts" / name).is_file():
                    bad.append(f"{m.group(0)} (no scripts/{name})")
        self.assertEqual(bad, [], "docs/quickstart.md names scripts that do not exist (review RB4)")

    def test_quickstart_round3_notes(self):
        """Review N3 and the security quickstart nits (rework round 3)."""
        text = self._text()
        with self.subTest(item="every pwsh install.ps1 command uses -NoProfile"):
            cmds = [ln.strip() for _, block in self._code_blocks(text) for ln in block
                    if re.search(r"\bpwsh\b[^\n]*install\.ps1", ln)]
            self.assertTrue(cmds, "the quickstart gives no pwsh install.ps1 command")
            self.assertEqual([c for c in cmds if not re.search(r"\bpwsh\s+(?:-\w+\s+)*-NoProfile\b", c)], [],
                             "use `pwsh -NoProfile -File .\\install.ps1 ...`, as the script header says (review N3)")
        with self.subTest(item="Get-FileHash prints uppercase hex"):
            self.assertTrue(re.search(r"(?is)Get-FileHash.{0,400}upper[- ]?case|upper[- ]?case.{0,400}Get-FileHash",
                                      text), "say that Get-FileHash prints uppercase hex (security nit)")
        paragraphs = [re.sub(r"\s+", " ", p) for p in re.split(r"\n\s*\n", text)]
        with self.subTest(item="install.ps1 is for Windows; install.sh on Linux and macOS"):
            rx = (r"(?i)\binstall\.ps1\b[^.]{0,160}\b(?:is )?(?:for windows|windows[- ]only|only (?:on|for) windows)"
                  r"[^.]{0,200}\binstall\.sh\b[^.]{0,120}\b(?:linux|mac\s?os)\b")
            self.assertTrue([p for p in paragraphs if re.search(rx, p)],
                            "add the line: install.ps1 is for Windows; use install.sh on Linux and macOS "
                            "(security L-12 nit)")
        with self.subTest(item="no claim that install.ps1 refuses an empty PATH entry"):
            claims = []
            for p in paragraphs:
                for clause in re.split(r"[.;()]\s", p):
                    if re.search(r"(?i)\brefus\w*\b[^.]*\bempty\b|\bempty\b[^.]*\brefus\w*", clause) \
                            and "PATH" in clause and not re.search(r"\binstall\.sh\b|\bbash\b", clause):
                        claims.append(clause.strip())
            self.assertEqual(claims, [], "a PATH refusal of empty entries is claimed for both installers; on "
                                         "Windows install.ps1 drops empty entries (review N3): name install.sh")
            self.assertTrue(re.search(r"(?i)(?:install\.ps1|windows)[^.]{0,200}\b(?:drops?|ignores?|removes?|skips?)\b"
                                      r"[^.]{0,80}\bempty\b|\bempty\b[^.]{0,80}\b(?:dropped|ignored|removed|skipped)\b"
                                      r"[^.]{0,120}\bwindows\b", " ".join(paragraphs)),
                            "say that install.ps1 on Windows drops empty PATH entries (review N3)")

    def test_quickstart_parent_rule_round5(self):
        """Review RB8 (= security L-19) and security I-14, round 5. PS-3.2
        Docs round 4: the target's parent must be owned and writable only by
        the operator (or root / Administrators), and the installer REFUSES
        otherwise, including a sticky /tmp-style parent and `C:\\`. I-14:
        the same advice extends to the directories above the parent, and
        the target is not on synced or shared media."""
        text = self._text()
        paragraphs = [re.sub(r"\s+", " ", p) for p in re.split(r"\n\s*\n", text)]
        sentences = [s for p in paragraphs for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*(])", p)]
        with self.subTest(item="no sentence says the installer warns about the parent"):
            warns = [s for s in sentences if re.search(r"(?i)\bwarn(?:s|ing|ed)?\b", s)
                     and re.search(r"(?i)\bparent\b", s)]
            self.assertEqual(warns, [], "the quickstart still says the installer warns about the target's parent; "
                                        "since round 4 it refuses (review RB8, PS-3.2 Docs)")
        refuse = [p for p in paragraphs if re.search(r"(?i)\brefus(?:e|es|ed|al)\b", p)
                  and re.search(r"(?i)\bparent\b", p)]
        with self.subTest(item="the installer refuses a parent others can write"):
            self.assertTrue([p for p in refuse if re.search(
                r"(?i)\bwrit\w*\b[^.]{0,120}\b(?:others?|anyone else|other (?:users|accounts))\b"
                r"|\b(?:others?|anyone else|other (?:users|accounts))\b[^.]{0,120}\bwrit", p)],
                "say that the installer refuses a target parent that others can write (review RB8)")
        with self.subTest(item="the refusal includes a sticky /tmp-style parent and C:\\"):
            self.assertTrue([p for p in refuse if re.search(r"(?i)\bsticky\b", p) and "/tmp" in p and "C:\\" in p],
                            "in the paragraph that says the installer refuses the parent, name a sticky "
                            "/tmp-style parent and C:\\ as refused (PS-3.2 Docs round 4, review RB8)")
        with self.subTest(item="the parent must be owned by the operator"):
            self.assertTrue([p for p in refuse if re.search(
                r"(?i)\bowned\b[^.]{0,80}\b(?:by you|only by you|by the operator)\b"
                r"|\b(?:you|the operator)\s+(?:must\s+)?own\b", p)],
                "say that the target's parent must be owned by you (or root / Administrators), and that the "
                "installer refuses a parent another account owns (PS-3.2 Docs round 4, review RB8)")
        with self.subTest(item="the directories above the parent are not writable by others either"):
            above = [s for s in sentences
                     if re.search(r"(?i)\b(?:director(?:y|ies)|folders?)\s+above\b|\bancestors?\b"
                                  r"|\bevery (?:directory|folder) (?:above|on the (?:path|way))\b", s)
                     and re.search(r"(?i)\bwrit", s)]
            self.assertTrue(above, "advise that the directories above the target's parent are not writable by "
                                   "others either (security I-14, M-7: an ancestor writer can swap the parent)")
        with self.subTest(item="the target is not on synced or shared media"):
            media = [s for s in sentences
                     if re.search(r"(?i)\btarget\b|\binstall (?:it )?into\b", s)
                     and re.search(r"(?i)\b(?:synced|syncing|sync(?:ed)? folders?|shared (?:media|folders?|drives?)"
                                   r"|network (?:share|drive|folder)s?|onedrive|dropbox|nfs)\b", s)
                     and re.search(r"(?i)\b(?:not|never|avoid|no)\b|\bdon'?t\b|\boutside\b", s)]
            self.assertTrue(media, "say that the target is not on synced or shared media (OneDrive, Dropbox, a "
                                   "network share): the parent check cannot see who can write there (security "
                                   "I-14)")

    def test_quickstart_icacls_grants_current_user_sid(self):
        """Security L-L2c (docs/evidence/platform-offline/audit-l2.md): the
        quickstart's icacls one-liner granted `$env:USERNAME`, which is
        resolved by name, so a local account with the same name can shadow
        the domain user. Every icacls command in the quickstart grants the
        current user's SID in the `*<SID>` form, for example
        `"*$([Security.Principal.WindowsIdentity]::GetCurrent().User.Value):(R,W)"`."""
        text = self._text()
        calls = [m.group(0) for m in re.finditer(r"(?i)\bicacls(?:\.exe)?\b[^`\n]*", text)
                 if re.search(r"(?i)/grant", m.group(0))]
        self.assertTrue(calls, "the quickstart no longer shows an icacls grant that restricts .env on Windows")
        for call in calls:
            with self.subTest(call=call):
                self.assertNotIn("USERNAME", call.upper(), "grant by SID, not by user name (L-L2c)")
                self.assertRegex(call, r"/grant:r\s+['\"]\*(?:\$\(\s*\[(?:System\.)?Security\.Principal\."
                                       r"WindowsIdentity\]::GetCurrent\(\)\.User(?:\.Value)?\s*\)|S-1-)",
                                 "the grant must be the current user's SID: "
                                 "`\"*$([Security.Principal.WindowsIdentity]::GetCurrent().User.Value):(R,W)\"` "
                                 "(L-L2c)")

    def _offline_section(self) -> str:
        text = self._text()
        m = re.search(r"(?m)^## Offline bundle\b.*$", text)
        self.assertIsNotNone(m, "docs/quickstart.md has no `## Offline bundle` section")
        assert m is not None
        nxt = re.search(r"(?m)^## (?!#)", text[m.end():])
        return text[m.start():m.end() + (nxt.start() if nxt else len(text))]

    def test_quickstart_offline_operator_steps(self):
        """Smoke-gate loop 1, findings F1-F5 of the recorded offline runs
        (docs/evidence/platform-offline/recorded-runs.md). Each must be said
        in the `## Offline bundle` section, where the air-gap operator reads."""
        section = self._offline_section()
        paragraphs = [re.sub(r"\s+", " ", p) for p in re.split(r"\n\s*\n", section)]
        launch_at = section.find("bash scripts/launch.sh")
        with self.subTest(item="F1: create .env from .env.example and set real secrets before launch"):
            # Paragraphs with their offsets in the section (a fenced block may
            # carry the command, so the paragraph before it counts as well).
            raw = [(m.start(), re.sub(r"\s+", " ", m.group(0)))
                   for m in re.finditer(r"(?s).+?(?:\n\s*\n|\Z)", section)]
            hits = [at for i, (at, p) in enumerate(raw)
                    if re.search(r"\.env\.example", p + (raw[i + 1][1] if i + 1 < len(raw) else ""))
                    and re.search(r"(?i)\b(?:cp|copy|create)\b[^.]{0,80}\.env\b",
                                  p + (raw[i + 1][1] if i + 1 < len(raw) else ""))
                    and re.search(r"(?i)\b(?:secrets?|passwords?)\b", p)]
            self.assertTrue(hits, "the offline section must tell the operator to create `.env` from `.env.example` "
                                  "(for example `cp .env.example .env`) and set real secrets before launch; "
                                  "launch.sh otherwise creates it silently with placeholder secrets (F1)")
            self.assertNotEqual(launch_at, -1, "the offline section has no `bash scripts/launch.sh` step")
            self.assertLess(min(hits, default=len(section)), launch_at,
                            "the .env step must come before the launch step (F1)")
        with self.subTest(item="F2: one install per host, or a distinct COMPOSE_PROJECT_NAME per install"):
            proj = [p for p in paragraphs if "COMPOSE_PROJECT_NAME" in p]
            self.assertTrue(proj, "the offline section must name COMPOSE_PROJECT_NAME: every install on a host "
                                  "shares the project `knowledge-engine` and its volumes unless it is set (F2)")
            self.assertTrue([p for p in proj if re.search(
                r"(?i)\bone install(?:ation)? per (?:host|machine)\b|\b(?:each|every|per|second|another) "
                r"install(?:ation)?\b|\bdistinct\b|\bdifferent\b|\bunique\b", p)],
                "say: one install per host, or a distinct COMPOSE_PROJECT_NAME for each install (F2)")
            self.assertTrue([p for p in proj if re.search(r"--volumes", p)
                             and re.search(r"(?i)\b(?:delet|remov|destroy|wip|eras)\w*\b", p)],
                            "say that `teardown --volumes` deletes that project's data (volumes) (F2)")
        with self.subTest(item="F3: bash scripts/smoke.sh and when its store-outage check runs"):
            self.assertRegex(section, r"\bbash\s+scripts/smoke\.sh\b",
                             "the offline section must name `bash scripts/smoke.sh` (F3)")
            self.assertTrue([p for p in paragraphs if "smoke.sh" in p
                             and re.search(r"(?i)\boutage\b|\bstops?\b[^.]{0,40}\b(?:postgres|a store|the store)",
                                           p)
                             and re.search(r"(?i)\b(?:stopped|not running|is down|torn down|not up)\b", p)],
                            "say that smoke.sh runs the store-outage check only when the project is stopped "
                            "(it then launches and tears down itself) (F3)")
        with self.subTest(item="F4: a WSL build host needs Docker Desktop's WSL integration"):
            self.assertTrue([p for p in paragraphs if re.search(r"\bWSL\b", p)
                             and re.search(r"(?i)\bintegration\b", p) and re.search(r"(?i)docker desktop", p)],
                            "say that a WSL build host needs Docker Desktop's WSL integration enabled for that "
                            "distro; without it `docker` in WSL is a stub that refuses (F4)")
        with self.subTest(item="F5: sha256sum -c <out>.manifest.sha256 (Linux) for the out-of-band record"):
            self.assertRegex(section, r"\bsha256sum\s+-c\s+(?:--strict\s+)?\S*\.manifest\.sha256\b",
                             "show `sha256sum -c bundle-<arch>.manifest.sha256` for the out-of-band record (F5)")
        with self.subTest(item="F5: shasum -a 256 -c <out>.manifest.sha256 (Mac)"):
            self.assertRegex(section, r"\bshasum\s+-a\s+256\s+-c\s+\S*\.manifest\.sha256\b",
                             "show `shasum -a 256 -c bundle-<arch>.manifest.sha256` on a Mac (F5)")
        with self.subTest(item="F5: run from the bundle's parent directory"):
            m = re.search(r"\bsha256sum\s+-c\s+(?:--strict\s+)?\S*\.manifest\.sha256\b", section)
            near = section[max(0, m.start() - 400):m.end() + 400] if m else ""
            self.assertRegex(near, r"(?i)\bparent\b|\bcd\s+\.\.|\bbeside\b|\bnext to\b|\bdirectory (?:that )?"
                                   r"holds\b|\bcontains? (?:the )?bundle",
                             "say to run the record check from the directory that holds the bundle (its "
                             "parent): the record names `bundle-<arch>/MANIFEST.sha256` (F5)")

    def _offline_step5(self) -> str:
        """The `### 5.` subsection of the offline section (configure, launch, check)."""
        section = self._offline_section()
        m = re.search(r"(?m)^### 5\.[^\n]*$", section)
        self.assertIsNotNone(m, "the offline section has no `### 5.` step (configure, launch and check)")
        assert m is not None
        nxt = re.search(r"(?m)^#{2,3} ", section[m.end():])
        return section[m.start():m.end() + (nxt.start() if nxt else len(section))]

    def test_quickstart_offline_env_step_is_private_and_names_ke_env(self):
        """Smoke-gate loop 2, findings F10 and F12 of the recorded offline runs
        (docs/evidence/platform-offline/recorded2-runs.md), in step 5 where the
        operator creates `.env`.

        F12: `cp .env.example .env` leaves the file that now holds the real
        secrets 0644, readable by every local user; the step says
        `chmod 600 .env`, and what a Windows operator does instead.
        F10: the step said to set real secrets but not what KE_ENV must be.
        Orchestrator ruling 2026-10-19 (platform-offline smoke loop 2, on the
        tester's KE_ENV/auth flag; docs/architecture.md line 3900, ADR-KE-010):
        for this release the step says to keep KE_ENV=dev on a trusted host
        with the default loopback binding (KE_BIND_ADDRESS 127.0.0.1) and still
        set real secrets; that KE_ENV=prod requires authentication, which
        arrives with auth-audit, and the engine refuses prod until then; and
        it names KE_AUTH__ENABLED. The ruling replaced this test's earlier
        "KE_ENV=prod for a real deployment" and "placeholders refused under
        prod" subtests (written in the same RED step, never green)."""
        import typing

        from engine.config.settings import Settings

        step = self._offline_step5()
        flat = re.sub(r"\s+", " ", step)
        paragraphs = [re.sub(r"\s+", " ", p) for p in re.split(r"\n\s*\n", step)]
        sentences = [s for p in paragraphs for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`(])", p)]
        cp_at = step.find("cp .env.example .env")
        launch_at = step.find("bash scripts/launch.sh")
        with self.subTest(item="F12: chmod 600 .env after the copy, before launch"):
            self.assertNotEqual(cp_at, -1, "step 5 has no `cp .env.example .env`")
            m = re.search(r"\bchmod\s+0?600\s+\.env\b", step)
            self.assertIsNotNone(m, "step 5 must tell the operator to run `chmod 600 .env`: the copy holds the "
                                    "real secrets and is otherwise 0644, readable by every local user (F12)")
            assert m is not None
            self.assertLess(cp_at, m.start(), "`chmod 600 .env` must come after `cp .env.example .env` (F12)")
            self.assertNotEqual(launch_at, -1, "step 5 has no `bash scripts/launch.sh`")
            self.assertLess(m.start(), launch_at, "`chmod 600 .env` must come before the launch (F12)")
        with self.subTest(item="F12: a Windows note on who can read .env"):
            self.assertTrue([p for p in paragraphs if re.search(r"\bWindows\b", p) and ".env" in p
                             and re.search(r"(?i)\bchmod\b|\bpermissions?\b|\bACLs?\b|\bicacls\b|\breadable\b"
                                           r"|\baccess\b|\bonly (?:you|your)\b", p)],
                            "step 5 must say what a Windows operator does about who can read .env (chmod does "
                            "not apply there), for example that a target under the user profile is readable "
                            "only by that user and administrators (F12)")
        envs = typing.get_args(Settings.model_fields["env"].annotation)
        self.assertIn("dev", envs, "precondition: KE_ENV accepts `dev` (engine/config/settings.py)")
        self.assertIn("prod", envs, "precondition: KE_ENV accepts `prod` (engine/config/settings.py)")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertRegex(example, r"(?m)^KE_ENV=dev\s*$", "precondition: .env.example ships KE_ENV=dev")
        self.assertRegex(example, r"(?m)^KE_BIND_ADDRESS=127\.0\.0\.1\s*$",
                         "precondition: .env.example binds loopback")
        with self.subTest(item="F10: for this release keep KE_ENV=dev on a trusted host, loopback, real secrets"):
            self.assertTrue([p for p in paragraphs if re.search(r"\bKE_ENV=dev\b", p)
                             and re.search(r"(?i)\bthis release\b|\bfor now\b|\bcurrently\b|\buntil auth-audit\b",
                                           p)
                             and re.search(r"(?i)\btrusted\b", p)
                             and re.search(r"\bKE_BIND_ADDRESS\b|\b127\.0\.0\.1\b|(?i:\bloopback\b)", p)
                             and re.search(r"(?i)\breal (?:secrets?|passwords?)\b|\bsecrets?\b", p)],
                            "step 5 must say, in one paragraph: for this release keep `KE_ENV=dev` on a trusted "
                            "host with the default loopback binding (KE_BIND_ADDRESS 127.0.0.1), and still set "
                            "real secrets (F10, orchestrator ruling 2026-10-19)")
        with self.subTest(item="F10: KE_ENV=prod needs authentication (auth-audit); refused until then"):
            self.assertTrue([s for s in sentences if re.search(r"\bKE_ENV=prod\b|`prod`|\bprod\b", s)
                             and re.search(r"(?i)\bauthentication\b|\bauth\b", s)
                             and re.search(r"\bauth-audit\b", s)
                             and re.search(r"(?i)\brefus\w*\b|\b(?:will not|won't|does not|doesn't|fails? to) "
                                           r"start\b", s)],
                            "step 5 must say that KE_ENV=prod requires authentication, which arrives with the "
                            "auth-audit item, and that the engine refuses prod until then (F10, orchestrator "
                            "ruling 2026-10-19; docs/architecture.md line 3900)")
        with self.subTest(item="F10: names KE_AUTH__ENABLED"):
            self.assertIn("KE_AUTH__ENABLED", flat,
                          "step 5 must name KE_AUTH__ENABLED (F10, orchestrator ruling 2026-10-19)")

    def test_quickstart_project_name_advice_precedes_launch(self):
        """Recorded run 3, finding Q1 (recorded3-runs.md): step 5's block ends
        with `bash scripts/launch.sh` and the COMPOSE_PROJECT_NAME advice came
        four paragraphs later, so an operator who copies the block launches
        under the shared default project first. The advice (one install per
        host, or a distinct COMPOSE_PROJECT_NAME) comes before the launch line,
        or the block exports COMPOSE_PROJECT_NAME before it."""
        step = self._offline_step5()
        launch = re.search(r"(?m)^[ \t]*bash scripts/launch\.sh\b", step)
        self.assertIsNotNone(launch, "step 5 has no `bash scripts/launch.sh` line")
        assert launch is not None
        before = step[:launch.start()]
        exported = re.search(r"(?m)^[ \t]*export COMPOSE_PROJECT_NAME=\S+", before)
        advice = [p for p in re.split(r"\n\s*\n", before) if "COMPOSE_PROJECT_NAME" in p
                  and re.search(r"(?i)\bone install(?:ation)? per (?:host|machine)\b|\b(?:each|every|per|second|"
                                r"another) install(?:ation)?\b|\bdistinct\b|\bdifferent\b|\bunique\b",
                                re.sub(r"\s+", " ", p))]
        self.assertTrue(exported or advice,
                        "step 5 must give the COMPOSE_PROJECT_NAME advice (one install per host, or a distinct "
                        "name per install) before `bash scripts/launch.sh`, or export it in the block before "
                        "the launch line (Q1)")

    def test_quickstart_code_first_comes_first(self):
        text = self._text()
        first_bundle = text.find("bundle.sh")
        self.assertNotEqual(first_bundle, -1, "docs/quickstart.md names no bundle.sh (PS-3.2 Docs path 2)")
        for step in ("git clone", "build.sh", "launch.sh"):
            with self.subTest(step=step):
                at = text.find(step)
                self.assertNotEqual(at, -1, f"the code-first path names no {step}")
                self.assertLess(at, first_bundle,
                                f"code-first ({step}) must come before the offline bundle (PS-3.2 Docs)")
