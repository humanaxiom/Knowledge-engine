"""platform-offline, integration: gate least privilege at runtime (PS-3.5, L-5).

Runs in `gates-it` (verify.sh full), as the real unprivileged user on the real
read-only checkout. The static half is tests/test_gate_least_privilege.py.

- `test_gates_it_cannot_write_repo`: a write to the repo root and to
  `.git/hooks` fails; a write to `/tmp` succeeds (control).
- `test_gates_it_cannot_read_repo_env`: the repo-root `.env`, when the host
  has one, is masked by the committed empty file. When the host has none,
  there is nothing to mask.
- `test_gates_uv_locked_catches_drift_as_non_root`: as uid 10001 with no
  network, `uv run --locked` passes on the committed lock and fails on a
  pyproject that has drifted from it.
"""

from __future__ import annotations

import errno
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.engine_support import ROOT

WORK = Path("/work")
GATE_UID = 10001


def _try_write(path: Path) -> OSError | None:
    """Append to `path`. Append mode (not `x`) fails with EROFS on an existing
    read-only file instead of EEXIST, which would hide a writable file."""
    created = not path.exists()
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("probe")
    except OSError as exc:
        return exc
    if created:
        path.unlink()
    return None


class GateLeastPrivilegeTest(unittest.TestCase):
    def setUp(self) -> None:
        if ROOT.resolve() != WORK:
            self.fail(f"runs only in the gates-it container with the checkout at {WORK}; "
                      f"this checkout is {ROOT}")

    def test_gates_it_cannot_write_repo(self):
        self.assertEqual(os.getuid(), GATE_UID, "gates-it must run as the unprivileged user")
        targets = [WORK / "ke-write-probe", WORK / "docker" / "ke-write-probe"]
        if (WORK / ".git").is_dir():
            targets.append(WORK / ".git" / "hooks" / "ke-write-probe")
        for target in targets:
            with self.subTest(target=str(target)):
                error = _try_write(target)
                self.assertIsNotNone(error, f"wrote {target}: the checkout is writable")
                assert error is not None
                self.assertEqual(error.errno, errno.EROFS, f"{target}: {error}")
        # A git worktree (or submodule) has `.git` as a file: the hooks path is
        # not under /work, so that target is not applicable here (review N4).
        if not (WORK / ".git").is_dir():
            self.assertTrue((WORK / ".git").is_file(), "/work/.git is neither a directory nor a file")
        # Control: /tmp is writable, so a container that cannot write anywhere
        # does not pass this test.
        self.assertIsNone(_try_write(Path(tempfile.gettempdir()) / "ke-write-probe"))

    def test_gates_it_cannot_read_repo_env(self):
        env = WORK / ".env"
        if not env.exists():
            # The host had no .env, so verify.sh added no mask (a mount point
            # cannot be created in a read-only checkout). Nothing to read.
            self.skipTest("no repo-root .env on the host, so verify.sh added no mask; "
                          "the masked-file path is not exercised")
        self.assertEqual(env.read_bytes(), b"",
                         "/work/.env is not the empty mask: the gate can read the host .env")
        self.assertEqual(env.stat().st_size, 0)
        error = _try_write(env)  # the mask is read-only too
        self.assertIsNotNone(error, "the masked /work/.env is writable")
        assert error is not None
        self.assertEqual(error.errno, errno.EROFS, str(error))

    def test_gates_uv_locked_catches_drift_as_non_root(self):
        self.assertEqual(os.getuid(), GATE_UID)
        env = dict(os.environ)
        self.assertEqual(env.get("UV_OFFLINE"), "1", "the gates have no network")
        self.assertNotIn("UV_NO_SYNC", env, "UV_NO_SYNC hides lock drift")
        self.assertNotIn("UV_FROZEN", env, "UV_FROZEN hides lock drift")

        control = subprocess.run(["uv", "run", "--locked", "python", "-c", "pass"], cwd=WORK, env=env,
                                 capture_output=True, text=True, timeout=120)
        self.assertEqual(control.returncode, 0,
                         f"control: uv run --locked failed on the committed lock\n{control.stderr}")

        text = (WORK / "pyproject.toml").read_text(encoding="utf-8")
        version, count = re.subn(r'(?m)^version = "[^"]*"', 'version = "9.9.9"', text, count=1)
        self.assertEqual(count, 1, "pyproject.toml has no project version to drift")
        extra, count = re.subn(r"(?m)^dependencies = \[\n", 'dependencies = [\n    "six>=1.16",\n',
                               text, count=1)
        self.assertEqual(count, 1, "pyproject.toml has no dependencies list to drift")
        for case, drifted in (("version bump", version), ("extra dependency", extra)):
            with self.subTest(drift=case), tempfile.TemporaryDirectory() as tmp:
                shutil.copy(WORK / "uv.lock", tmp)
                (Path(tmp) / "pyproject.toml").write_text(drifted, encoding="utf-8")
                # A temp venv: a bypass cannot re-point the shared /opt/venv at
                # a directory that is deleted when this case ends.
                case_env = {**env, "UV_PROJECT_ENVIRONMENT": str(Path(tmp) / "venv")}
                result = subprocess.run(["uv", "run", "--locked", "python", "-c", "pass"], cwd=tmp,
                                        env=case_env, capture_output=True, text=True, timeout=120)
                self.assertNotEqual(result.returncode, 0,
                                    f"uv run --locked passed on a drifted pyproject.toml ({case})")
                # Offline, uv re-resolves a stale lock before it can say "needs
                # to be updated", and the resolution fails on the network. Either
                # message is the lock gate refusing; a green run would be the
                # failure.
                self.assertRegex(
                    result.stderr,
                    r"(?i)lockfile at .{0,20}uv\.lock.{0,10} needs to be updated|"
                    r"no solution found when resolving",
                    f"unexpected failure reason ({case}): {result.stderr}")


if __name__ == "__main__":
    unittest.main()
