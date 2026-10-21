"""platform-offline: least privilege for the gate services (security L-5).

Criteria: docs/requirements.md PS-3.5 (both `gates` and `gates-it`, ruling
R7; spike S2 specifics). Design: docs/architecture.md §2.2 *Unprivileged
gates, read-only checkout* and §2.6 (L-5 static first). Test names are the
PS-3.5 names (orchestrator ruling, docs/handoffs/platform-offline.md). Every
compose test is parametrised over both gate services with subTest.

The runtime halves (`test_gates_it_cannot_write_repo`,
`test_gates_it_cannot_read_repo_env`,
`test_gates_uv_locked_catches_drift_as_non_root`) are integration tests and
live in tests/integration (full).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any

from tests import compose_support as cs
from tests.engine_support import ROOT

GATE_SERVICES = cs.ONE_SHOT_SERVICES  # ("gates", "gates-it")
GATE_UID = "10001"
REPO_TARGET = "/work"
GATES_DOCKERFILE = ROOT / "docker" / "gates.Dockerfile"
TEST_SH = ROOT / "scripts" / "test.sh"

READ_ONLY_REPO_ENV = {
    "MYPY_CACHE_DIR": "/tmp/mypy",
    "PYTHONDONTWRITEBYTECODE": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


# --- helpers -----------------------------------------------------------------

def _gate_service(name: str) -> dict[str, Any]:
    svc = cs.services().get(name)
    if svc is None:
        raise AssertionError(f"{name} is missing from docker-compose.yml")
    return svc


def _gate_services_in_every_file() -> list[tuple[str, str, dict[str, Any]]]:
    """Every definition of a gate service, in every compose file (the base file
    and any overlay such as a `.env` mask), so no overlay adds a writable mount."""
    return [(f, n, s) for f, n, s in cs.all_services() if n in GATE_SERVICES]


def _uid(user: Any) -> str:
    return str(user).split(":", 1)[0].strip() if user is not None else ""


def _volumes(svc: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise each volume to {type, source, target, read_only}."""
    out: list[dict[str, Any]] = []
    for volume in svc.get("volumes") or []:
        if isinstance(volume, dict):
            out.append({
                "type": str(volume.get("type", "volume")),
                "source": str(volume.get("source", "")),
                "target": str(volume.get("target", "")),
                "read_only": volume.get("read_only") is True,
            })
            continue
        text = str(volume)
        # Short syntax SRC:DST[:MODE]; a leading Windows drive letter is part of SRC.
        drive = ""
        if re.match(r"^[A-Za-z]:[\\/]", text):
            drive, text = text[:2], text[2:]
        parts = text.split(":")
        if len(parts) == 1:
            out.append({"type": "volume", "source": "", "target": parts[0], "read_only": False})
            continue
        source, target = drive + parts[0], parts[1]
        modes = parts[2].split(",") if len(parts) > 2 else []
        kind = "bind" if (drive or re.match(r"^[./~$\\]", source) or "/" in source) else "volume"
        out.append({"type": kind, "source": source, "target": target, "read_only": "ro" in modes})
    return out


def _tmpfs_entries(svc: dict[str, Any]) -> list[str]:
    tmpfs = svc.get("tmpfs")
    if tmpfs is None:
        return []
    if isinstance(tmpfs, str):
        return [tmpfs]
    return [str(t) for t in tmpfs]


def _logical_lines(path: Path) -> list[str]:
    """Dockerfile instructions with backslash continuations joined and
    comment lines dropped."""
    lines: list[str] = []
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue
        current += stripped
        lines.append(current.strip())
        current = ""
    if current.strip():
        lines.append(current.strip())
    return lines


def _env_value(instruction: str, key: str) -> str | None:
    match = re.match(r"^ENV\s+(.*)$", instruction, re.IGNORECASE)
    if not match:
        return None
    found = re.search(rf"(?:^|\s){re.escape(key)}(?:=|\s+)(\S+)", match.group(1))
    return found.group(1).strip("\"'") if found else None


def _config_surface(include_env_example: bool) -> list[Path]:
    """Compose files, Dockerfiles, everything under scripts/, the CI workflows
    and optionally .env.example: the places a gate environment variable can be
    set (PS-3.5)."""
    files: set[Path] = set(cs.compose_files())
    files.update(p for p in ROOT.glob("*Dockerfile*") if p.is_file())
    files.update(p for p in (ROOT / "docker").rglob("*") if p.is_file() and "Dockerfile" in p.name)
    files.update(p for p in (ROOT / "scripts").rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts)
    files.update(p for p in (ROOT / ".github" / "workflows").glob("*") if p.is_file())
    if include_env_example:
        files.add(ROOT / ".env.example")
    return sorted(p for p in files if p.is_file())


def _non_comment_mentions(name: str, include_env_example: bool) -> list[str]:
    """Every non-comment line that names `name`; a comment explaining the ban
    is allowed, any other mention counts as setting it."""
    token = re.compile(rf"\b{re.escape(name)}\b")
    hits: list[str] = []
    for path in _config_surface(include_env_example):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if token.search(line):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}")
    return hits


# --- compose: both gate services ---------------------------------------------

class GateServicesComposeTest(unittest.TestCase):
    """PS-3.5, compose config, parametrised over `gates` and `gates-it`."""

    def test_gates_it_is_non_root_with_read_only_repo(self):  # PS-3.5 (R7: both)
        for name in GATE_SERVICES:
            with self.subTest(service=name):
                svc = _gate_service(name)
                uid = _uid(svc.get("user"))
                self.assertNotIn(uid, ("", "0", "root"),
                                 f"{name} runs as root (user={svc.get('user')!r}); PS-3.5")
                repo = [v for v in _volumes(svc) if v["target"] == REPO_TARGET]
                self.assertEqual(len(repo), 1, f"{name} must mount the checkout at {REPO_TARGET}")
                self.assertTrue(repo[0]["read_only"],
                                f"{name} mounts the checkout read-write: {repo[0]}")

    def test_gate_services_run_as_uid_10001(self):  # PS-3.5 *Non-root uid*
        for name in GATE_SERVICES:
            with self.subTest(service=name):
                svc = _gate_service(name)
                self.assertEqual(_uid(svc.get("user")), GATE_UID,
                                 f"{name} user is {svc.get('user')!r}, expected {GATE_UID} "
                                 "(architecture §2.2 L-5)")
        with self.subTest(image="docker/gates.Dockerfile last USER"):
            users = [ln for ln in _logical_lines(GATES_DOCKERFILE)
                     if re.match(r"^USER\s", ln, re.IGNORECASE)]
            self.assertTrue(users, "gates.Dockerfile sets no USER; it must end as 10001 (§2.2)")
            self.assertEqual(_uid(users[-1].split(None, 1)[1]), GATE_UID,
                             f"last USER in gates.Dockerfile is {users[-1]!r}")

    def test_gate_services_run_as_uid_and_gid_10001(self):  # security L-1
        for name in GATE_SERVICES:
            with self.subTest(service=name):
                self.assertEqual(str(_gate_service(name).get("user")), f"{GATE_UID}:{GATE_UID}",
                                 "the primary group must not be 0: root-group files in the image "
                                 "would be writable")
        users = [ln for ln in _logical_lines(GATES_DOCKERFILE)
                 if re.match(r"^USER\s", ln, re.IGNORECASE)]
        self.assertTrue(users, "gates.Dockerfile sets no USER; it must end as 10001:10001 "
                               "(review-l5-r1 n3)")
        self.assertEqual(users[-1].split(None, 1)[1].strip(), f"{GATE_UID}:{GATE_UID}")

    def test_gate_services_drop_capabilities_and_new_privileges(self):  # security L-2
        for name in GATE_SERVICES:
            with self.subTest(service=name):
                svc = _gate_service(name)
                self.assertEqual([str(c).upper() for c in svc.get("cap_drop") or []], ["ALL"])
                self.assertNotIn("cap_add", svc)
                self.assertIn("no-new-privileges:true",
                              [str(o).replace(" ", "") for o in svc.get("security_opt") or []])

    def test_gate_services_use_long_syntax_read_only_checkout(self):  # architecture §2.2
        for name in GATE_SERVICES:
            with self.subTest(service=name):
                repo = [v for v in _gate_service(name).get("volumes") or []
                        if isinstance(v, dict) and v.get("target") == REPO_TARGET]
                self.assertEqual(len(repo), 1, "checkout must use long syntax with read_only: true")
                self.assertIs(repo[0].get("read_only"), True)

    def test_gates_mask_overlay_holds_only_the_env_mask(self):  # review B1
        # The overlay is merged over the base file, so it must not carry (and
        # tests must not read) any other gate property: networks, profiles and
        # network_mode live in docker-compose.yml only.
        overlay = cs.load(ROOT / "docker-compose.gates-mask.yml")
        self.assertEqual(list(overlay), ["services"], "overlay has top-level keys other than services")
        self.assertEqual(sorted(overlay["services"]), sorted(GATE_SERVICES))
        for name in GATE_SERVICES:
            with self.subTest(service=name):
                self.assertEqual(overlay["services"][name],
                                 {"volumes": ["./docker/empty:/work/.env:ro"]})
        self.assertEqual((ROOT / "docker" / "empty").read_bytes(), b"")

    def test_gate_services_mount_repo_read_only(self):  # PS-3.5 *Read-only checkout*
        for name in GATE_SERVICES:
            with self.subTest(service=name, check="checkout"):
                repo = [v for v in _volumes(_gate_service(name)) if v["target"] == REPO_TARGET]
                self.assertEqual(len(repo), 1, f"{name} must mount the checkout at {REPO_TARGET}")
                self.assertEqual(repo[0]["type"], "bind")
                self.assertTrue(repo[0]["read_only"],
                                f"{name} mounts the checkout read-write: {repo[0]}")
        for file_name, name, svc in _gate_services_in_every_file():
            for volume in _volumes(svc):
                if volume["type"] != "bind":
                    continue
                with self.subTest(file=file_name, service=name, mount=volume["target"]):
                    self.assertTrue(volume["read_only"],
                                    f"{file_name}: {name} has a writable bind mount {volume}")

    def test_gate_services_tmp_is_exec_tmpfs(self):  # PS-3.5 *Executable tmpfs*
        for name in GATE_SERVICES:
            with self.subTest(service=name):
                entries = [e for e in _tmpfs_entries(_gate_service(name))
                           if e.split(":", 1)[0].rstrip("/") == "/tmp"]
                self.assertEqual(len(entries), 1,
                                 f"{name} has no /tmp tmpfs (tmpfs={_gate_service(name).get('tmpfs')!r})")
                options = entries[0].split(":", 1)[1].split(",") if ":" in entries[0] else []
                self.assertIn("exec", options, f"{name} /tmp tmpfs is not exec: {entries[0]!r}")
                self.assertNotIn("noexec", options, f"{name} /tmp tmpfs is noexec: {entries[0]!r}")
                self.assertIn("mode=1777", options, f"{name} /tmp tmpfs mode is not 1777: {entries[0]!r}")

    def test_gate_services_env_for_read_only_repo(self):  # PS-3.5 *Caches off the checkout*
        for name in GATE_SERVICES:
            env = cs.environment(_gate_service(name))
            for key, value in READ_ONLY_REPO_ENV.items():
                with self.subTest(service=name, key=key):
                    self.assertEqual(env.get(key), value,
                                     f"{name} must set {key}={value} (got {env.get(key)!r})")


# --- image -------------------------------------------------------------------

class GatesImageOwnershipTest(unittest.TestCase):
    """PS-3.5 *Image-owned venv and uv cache* (static, Dockerfile)."""

    def test_gates_image_venv_and_uv_cache_owned_by_gate_user(self):
        lines = _logical_lines(GATES_DOCKERFILE)
        sync_at = [i for i, ln in enumerate(lines)
                   if re.match(r"^RUN\s", ln, re.IGNORECASE) and re.search(r"\buv\s+sync\b", ln)]
        self.assertTrue(sync_at, "gates.Dockerfile has no `uv sync`")

        cache_at = [(i, _env_value(ln, "UV_CACHE_DIR")) for i, ln in enumerate(lines)
                    if _env_value(ln, "UV_CACHE_DIR")]
        with self.subTest(check="UV_CACHE_DIR is a fixed image path set before the first uv sync"):
            self.assertTrue(cache_at, "gates.Dockerfile does not set UV_CACHE_DIR (§2.2 L-5)")
            index, cache = cache_at[0]
            self.assertLess(index, sync_at[0], "UV_CACHE_DIR is set after the first `uv sync`")
            self.assertTrue(cache and cache.startswith("/"), f"UV_CACHE_DIR {cache!r} is not absolute")
            self.assertFalse(re.match(r"^/(root|home)(/|$)", cache or ""),
                             f"UV_CACHE_DIR {cache!r} is under a home directory")

        venv = None
        for ln in lines:
            venv = _env_value(ln, "UV_PROJECT_ENVIRONMENT") or venv
        with self.subTest(check="venv is /opt/venv"):
            self.assertEqual(venv, "/opt/venv")

        with self.subTest(check="venv and uv cache chowned to 10001 after the last uv sync"):
            cache = cache_at[0][1] if cache_at else "<UV_CACHE_DIR unset>"
            # The chown may share the sync's RUN (one layer, review N6) but must
            # come after `uv sync` in it, or be in a later RUN; exactly once, so
            # no second layer stores the venv again.
            after_sync = [re.sub(r"^.*?\buv\s+sync\b", "", lines[sync_at[-1]])] + lines[sync_at[-1] + 1:]
            chowns = [ln for ln in after_sync
                      if re.search(rf"\bchown\s+(?:-\S+\s+)*{GATE_UID}(?::\S+)?\s", ln)]
            joined = " ".join(chowns)
            self.assertTrue(chowns, "no `chown 10001` after the last `uv sync`")
            self.assertEqual(len(chowns), 1, "chown the venv and cache once: no duplicate layer (N6)")
            self.assertIn(f"{GATE_UID}:{GATE_UID}", joined)
            self.assertRegex(joined, r"\bchown\s+(?:-\S+\s+)*-R\b", "chown must be recursive")
            for path in ("/opt/venv", str(cache)):
                self.assertRegex(joined, rf"(?:^|\s){re.escape(path)}/?(?:$|[\s;&|])",
                                 f"{path} is not chowned to {GATE_UID}")

        with self.subTest(check="safe.directory is /work only, never *"):
            text = " ".join(lines)
            self.assertIn("safe.directory /work", text)
            self.assertNotRegex(text, r"safe\.directory\s+['\"]?\*")


# --- coverage and uv environment ----------------------------------------------

class CoverageAndUvEnvTest(unittest.TestCase):
    """PS-3.5 *Coverage data file* and *No UV_NO_SYNC* (S2 items 4 and 5)."""

    def test_coverage_data_file_is_under_tmp(self):
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        run = config.get("tool", {}).get("coverage", {}).get("run", {})
        self.assertEqual(run.get("data_file"), "/tmp/.coverage",
                         "[tool.coverage.run] data_file must be /tmp/.coverage (PS-3.5)")
        with self.subTest(check="test.sh does not rm coverage files in the checkout"):
            # architecture §2.2: `coverage erase` honours data_file; an `rm` of
            # `.coverage*` in the read-only checkout fails with EROFS.
            for line in TEST_SH.read_text(encoding="utf-8").splitlines():
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotRegex(line, r"\brm\b.*\.coverage",
                                    f"scripts/test.sh removes coverage data in the checkout: {line.strip()}")

    def test_coverage_erase_removes_stale_parallel_data(self):  # review B2
        # Behavioural: the real `coverage erase` with the repo's own
        # [tool.coverage.run] table (only data_file redirected to a temp dir)
        # must remove a planted stale parallel file beside the data file. Without
        # `parallel = true` erase leaves `.coverage.*` behind and a later
        # `combine` would count it.
        run = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "tool"]["coverage"]["run"]
        self.assertIs(run.get("parallel"), True)
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            stale = data_dir / ".coverage.stale-host.pid1.x1y2z3"
            stale.write_bytes(b"stale")
            main = data_dir / ".coverage"
            main.write_bytes(b"stale")
            rc = Path(tmp) / "coveragerc.toml"
            # The repo's own run table, only data_file redirected.
            table = {**run, "data_file": (data_dir / ".coverage").as_posix()}
            rc.write_text("[tool.coverage.run]\n" + "".join(
                f"{key} = {json.dumps(value)}\n" for key, value in table.items()),
                encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "coverage", "erase", f"--rcfile={rc}"],
                                    cwd=tmp, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(stale.exists(), "coverage erase left a stale parallel data file")
            self.assertFalse(main.exists())

    def test_coverage_file_env_is_never_set(self):
        hits = _non_comment_mentions("COVERAGE_FILE", include_env_example=False)
        self.assertEqual(hits, [], "COVERAGE_FILE leaks into nested coverage runs (S2 item 4); "
                                   "use [tool.coverage.run] data_file instead")

    def test_uv_no_sync_is_never_set(self):
        hits = _non_comment_mentions("UV_NO_SYNC", include_env_example=True)
        self.assertEqual(hits, [], "UV_NO_SYNC hides pyproject/uv.lock drift (S2 item 5)")


if __name__ == "__main__":
    unittest.main()
