"""platform-sbom U0 RED: drive the static U0 checks (tests 1-5 and 8 of
tests/test_psycopg_c.py) against scratch copies.

Never writes the repository. It reads the repo's app.Dockerfile,
gates.Dockerfile, pyproject.toml, uv.lock and NOTICE.md, builds a TARGET of
each per design-notes N0 in the scratch directory, then mutants of the
target, and runs every check on each variant. The TARGET lock's psycopg-c
sdist URL and sha256, the pq-build pins and the LIBPQ_VERSION value are
placeholders: the real values come from `uv lock` in the gates image and
bookworm's apt at GREEN.

It also runs the existing AppImageTest (tests/test_image_scan.py) on the
target app.Dockerfile, so a contradiction with an existing test shows now.

Usage (host, from the repo root): uv run python docs/evidence/platform-sbom/u0/u0_mutants.py [scratch-dir]
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from tests import test_image_scan  # noqa: E402
from tests import test_psycopg_c as t  # noqa: E402

SCRATCH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "scratch"
SCRATCH.mkdir(parents=True, exist_ok=True)

PIN = "15.14-0+deb12u1"  # placeholder bookworm version (GREEN reads the real one)
C_URL = "https://files.pythonhosted.org/packages/00/00/placeholder/psycopg_c-3.3.6.tar.gz"
C_HASH = "0" * 64  # placeholder; `uv lock` writes the real sha256


def sub(text: str, old: str, new: str, count: int = 1) -> str:
    assert text.count(old) == count, (old, text.count(old))
    return text.replace(old, new)


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


# ---- targets -----------------------------------------------------------------

def target_app() -> str:
    s = read("docker/app.Dockerfile")
    s = sub(s, "FROM ghcr.io/astral-sh/uv:", f"ARG LIBPQ_VERSION={PIN}\nFROM ghcr.io/astral-sh/uv:")
    s = sub(s, " AS builder\nCOPY --from=uv /uv /usr/local/bin/uv\n",
            " AS builder\nARG LIBPQ_VERSION\n"
            "RUN apt-get update \\\n"
            " && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev=${LIBPQ_VERSION} \\\n"
            " && rm -rf /var/lib/apt/lists/*\n"
            "COPY --from=uv /uv /usr/local/bin/uv\n")
    s = sub(s, "RUN uv sync --locked --no-dev --no-install-project\n",
            "RUN uv sync --locked --no-dev --group pq-build --no-install-project\n"
            "RUN uv sync --locked --no-dev --group pq-build --group pq-c --no-binary-package psycopg-c "
            "--no-install-project\n")
    s = sub(s, "RUN uv sync --locked --no-dev --no-editable \\\n",
            "RUN uv sync --locked --no-dev --group pq-c --no-binary-package psycopg-c --no-editable \\\n")
    last_from = s.rindex("\nFROM python:")
    head, tail = s[:last_from], s[last_from:]
    tail = sub(tail, "\nENV PATH=/opt/venv/bin:$PATH \\\n    PYTHONUNBUFFERED=1\n",
               "\nARG LIBPQ_VERSION\nENV PATH=/opt/venv/bin:$PATH \\\n    PYTHONUNBUFFERED=1\n"
               "RUN apt-get update \\\n"
               " && apt-get install -y --no-install-recommends libpq5=${LIBPQ_VERSION} \\\n"
               " && rm -rf /var/lib/apt/lists/*\n")
    return head + tail


def target_gates() -> str:
    s = read("docker/gates.Dockerfile")
    s = sub(s, "FROM ghcr.io/astral-sh/uv:", f"ARG LIBPQ_VERSION={PIN}\nFROM ghcr.io/astral-sh/uv:")
    s = sub(s, "\nENV POWERSHELL_TELEMETRY_OPTOUT=1", "\nARG LIBPQ_VERSION\nENV POWERSHELL_TELEMETRY_OPTOUT=1")
    s = sub(s, "      shellcheck=0.9.0-1 libicu72 libssl3 zlib1g \\\n",
            "      shellcheck=0.9.0-1 libicu72 libssl3 zlib1g \\\n"
            "      gcc libc6-dev libpq-dev=${LIBPQ_VERSION} \\\n")
    s = sub(s, "RUN uv sync --locked \\\n",
            "RUN uv sync --locked --group pq-build --no-install-project \\\n"
            " && uv sync --locked --group pq-build --group pq-c --no-binary-package psycopg-c "
            "--no-install-project \\\n"
            " && uv sync --locked --group pq-build --group pq-c --no-binary-package psycopg-c \\\n")
    return s


def target_pyproject() -> str:
    s = read("pyproject.toml")
    s = sub(s, '"psycopg[binary]>=3.3.6",', '"psycopg>=3.3.6",')
    s = sub(s, '    "types-pyyaml>=6.0.12.20260906",\n]\n',
            '    "types-pyyaml>=6.0.12.20260906",\n]\n'
            '# The ke-app and ke-gates images only (PSC-25): psycopg-c built on Debian libpq.\n'
            'pq-c = ["psycopg[c]>=3.3.6"]\n'
            'pq-build = ["setuptools==80.9.0", "wheel==0.45.1"]\n'
            '\n[tool.uv]\nno-build-isolation-package = ["psycopg-c"]\n')
    return s


def target_lock() -> str:
    s = read("uv.lock")
    s = sub(s, '    { name = "psycopg", extra = ["binary"] },\n', '    { name = "psycopg" },\n')
    s = sub(s, '    { name = "psycopg", extras = ["binary"], specifier = ">=3.3.6" },\n',
            '    { name = "psycopg", specifier = ">=3.3.6" },\n')
    s = sub(s, '[package.dev-dependencies]\ndev = [\n    { name = "coverage" },\n    { name = "mypy" },\n'
               '    { name = "types-pyyaml" },\n]\n',
            '[package.dev-dependencies]\ndev = [\n    { name = "coverage" },\n    { name = "mypy" },\n'
            '    { name = "types-pyyaml" },\n]\npq-build = [\n    { name = "setuptools" },\n'
            '    { name = "wheel" },\n]\npq-c = [\n    { name = "psycopg", extra = ["c"] },\n]\n')
    s = sub(s, 'binary = [\n    { name = "psycopg-binary", marker = "implementation_name != \'pypy\'" },\n]\n',
            'c = [\n    { name = "psycopg-c", marker = "implementation_name != \'pypy\'" },\n]\n')
    start = s.index('[[package]]\nname = "psycopg-binary"\n')
    end = s.index("[[package]]\n", start + 10)
    s = s[:start] + (
        '[[package]]\nname = "psycopg-c"\nversion = "3.3.6"\nsource = { registry = "https://pypi.org/simple" }\n'
        f'sdist = {{ url = "{C_URL}", hash = "sha256:{C_HASH}", size = 1 }}\n\n'
    ) + s[end:]
    s += ('\n[[package]]\nname = "setuptools"\nversion = "80.9.0"\nsource = { registry = "https://pypi.org/simple" }\n'
          '\n[[package]]\nname = "wheel"\nversion = "0.45.1"\nsource = { registry = "https://pypi.org/simple" }\n')
    return s


def target_notice(lock: str) -> str:
    s = read("NOTICE.md")
    m = re.search(r'name = "psycopg"\nversion = "3.3.6"\n.*?sdist = \{ url = "([^"]+)", hash = "sha256:([0-9a-f]+)"',
                  lock, re.S)
    assert m
    start = s.index("## psycopg (LGPL-3.0-only)\n")
    end = s.index("\n## ", start + 5)
    section = ("## psycopg (LGPL-3.0-only)\n\n"
               "The `ke-app` image installs `psycopg` and `psycopg-c` 3.3.6 from PyPI,\n"
               "unmodified, under the GNU Lesser General Public License version 3 only\n"
               "(`licenses/LGPL-3.0.txt`). `psycopg-c` is compiled in the image's builder\n"
               "stage against Debian's `libpq5`. The sources are the sdists locked in `uv.lock`:\n"
               f"`psycopg` {m.group(1)}\n(sha256 `{m.group(2)}`);\n"
               f"`psycopg-c` {C_URL}\n(sha256 `{C_HASH}`).\n")
    return s[:start] + section + s[end:]


# ---- checks ------------------------------------------------------------------

CHECKS = {
    "1 lock": lambda v: t.builder_lock_problems(v["uv.lock"]),
    "2 pyproject": lambda v: t.pyproject_problems(v["pyproject.toml"]),
    "3 build": lambda v: t.app_build_problems(v["app.Dockerfile"]),
    "4 runtime": lambda v: t.app_runtime_problems(v["app.Dockerfile"]),
    "5 pin/base": lambda v: t.pin_base_problems(v["app.Dockerfile"], v["gates.Dockerfile"]),
    "8 notice": lambda v: t.notice_problems(v["NOTICE.md"], v["uv.lock"]),
}


def app_image_test(app: Path, gates: Path, lock: Path) -> list[str]:
    """Existing AppImageTest (PSC-17) on the variant: names of failing tests."""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_image_scan.AppImageTest)
    result = unittest.TestResult()
    with mock.patch.object(test_image_scan, "APP_DOCKERFILE", app), \
            mock.patch.object(test_image_scan, "GATES_DOCKERFILE", gates), \
            mock.patch.object(test_image_scan, "UV_LOCK", lock):
        suite.run(result)
    return sorted({str(c[0]).split()[0] for c in result.failures + result.errors})


def main() -> int:
    ta, tg, tp, tl = target_app(), target_gates(), target_pyproject(), target_lock()
    tn = target_notice(tl)
    target = {"app.Dockerfile": ta, "gates.Dockerfile": tg, "pyproject.toml": tp, "uv.lock": tl, "NOTICE.md": tn}
    last_sync = "RUN uv sync --locked --no-dev --group pq-c --no-binary-package psycopg-c --no-editable"
    runtime = "libpq5=${LIBPQ_VERSION} \\\n"
    trixie = lambda s: s.replace("-slim-bookworm@", "-slim-trixie@")  # noqa: E731
    variants: dict[str, tuple[dict[str, str], set[str]]] = {
        "current repo files (RED)": ({k: read(r) for k, r in (
            ("app.Dockerfile", "docker/app.Dockerfile"), ("gates.Dockerfile", "docker/gates.Dockerfile"),
            ("pyproject.toml", "pyproject.toml"), ("uv.lock", "uv.lock"), ("NOTICE.md", "NOTICE.md"))},
            set(CHECKS)),
        "TARGET per N0": ({}, set()),
        "M1 compiler (gcc) in the runtime stage": ({"app.Dockerfile": sub(ta, runtime, "libpq5=${LIBPQ_VERSION} gcc \\\n")},
                                                   {"4 runtime"}),
        "M2 unpinned libpq5": ({"app.Dockerfile": sub(ta, runtime, "libpq5 \\\n")}, {"4 runtime"}),
        "M3 libpq-dev in the runtime stage": ({"app.Dockerfile": sub(ta, runtime, "libpq5=${LIBPQ_VERSION} "
                                                                                 "libpq-dev=${LIBPQ_VERSION} \\\n")},
                                              {"4 runtime"}),
        "M4 final sync without --no-binary-package psycopg-c": (
            {"app.Dockerfile": sub(ta, last_sync, last_sync.replace(" --no-binary-package psycopg-c", ""))},
            {"3 build"}),
        "M5 final sync keeps pq-build": (
            {"app.Dockerfile": sub(ta, last_sync, last_sync.replace("--group pq-c", "--group pq-build --group pq-c"))},
            {"3 build"}),
        "M6 psycopg-binary resolvable for linux (pq-c, linux marker)": (
            {"uv.lock": sub(tl, 'pq-c = [\n', 'pq-c = [\n    { name = "psycopg-binary", marker = '
                                              '"sys_platform == \'linux\'" },\n') + t._BINARY_PKG},
            {"1 lock", "8 notice"}),
        "M7 psycopg-binary kept in the lock for win32 only": (
            {"uv.lock": sub(tl, '    { name = "psycopg" },\n    { name = "pydantic-settings" },\n',
                            '    { name = "psycopg" },\n    { name = "psycopg-binary", marker = '
                            '"sys_platform == \'win32\'" },\n    { name = "pydantic-settings" },\n') + t._BINARY_PKG},
            {"1 lock"}),
        "M8 psycopg-c with a locked wheel": (
            {"uv.lock": sub(tl, f'hash = "sha256:{C_HASH}", size = 1 }}\n',
                            f'hash = "sha256:{C_HASH}", size = 1 }}\nwheels = [\n    {{ url = '
                            f'"https://files.pythonhosted.org/x/psycopg_c-3.3.6-cp312-cp312-manylinux_2_28_x86_64.whl", '
                            f'hash = "sha256:{C_HASH}", size = 1 }},\n]\n')},
            {"1 lock"}),
        "M9 pin not +deb12u (pgdg 15.14-1.pgdg120+1)": (
            {"app.Dockerfile": ta.replace(PIN, "15.14-1.pgdg120+1"),
             "gates.Dockerfile": tg.replace(PIN, "15.14-1.pgdg120+1")},
            {"3 build", "5 pin/base"}),
        "M10 pin +deb13u on a trixie base (both images)": (
            {"app.Dockerfile": trixie(ta.replace(PIN, "17.6-0+deb13u1")),
             "gates.Dockerfile": trixie(tg.replace(PIN, "17.6-0+deb13u1"))},
            {"3 build", "5 pin/base"}),
        "M11 gates on a different pin": ({"gates.Dockerfile": tg.replace(PIN, "15.13-0+deb12u1")}, {"5 pin/base"}),
        "M12 pyproject default-groups include pq-c": (
            {"pyproject.toml": sub(tp, 'no-build-isolation-package = ["psycopg-c"]\n',
                                   'no-build-isolation-package = ["psycopg-c"]\ndefault-groups = ["dev", "pq-c"]\n')},
            {"2 pyproject"}),
        "M13 pyproject keeps psycopg[binary]": (
            {"pyproject.toml": sub(tp, '"psycopg>=3.3.6",', '"psycopg[binary]>=3.3.6",')}, {"2 pyproject"}),
        "M14 NOTICE without psycopg-c": (
            {"NOTICE.md": tn.replace("`psycopg` and `psycopg-c` 3.3.6", "`psycopg` 3.3.6").replace(
                "`psycopg-c` is compiled", "The C extension is compiled").replace(
                f"`psycopg-c` {C_URL}\n(sha256 `{C_HASH}`)", "the C part in the same project")},
            {"8 notice"}),
        "M15 NOTICE with a wrong psycopg-c sha256": ({"NOTICE.md": tn.replace(C_HASH, "1" * 64)}, {"8 notice"}),
    }
    bad = 0
    print(f"{'variant':<62} {'check':<12} {'want':<5} {'got':<5} first problem")
    for n, (name, (changes, want_fail)) in enumerate(variants.items()):
        files = dict(target, **changes)
        paths = {}
        for fname, text in files.items():
            p = SCRATCH / f"v{n:02d}" / fname
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
            paths[fname] = p
        for check, fn in CHECKS.items():
            problems = fn(paths)
            got = "fail" if problems else "pass"
            want = "fail" if check in want_fail else "pass"
            ok = got == want
            bad += not ok
            print(f"{name[:62]:<62} {check:<12} {want:<5} {got:<5} {'' if ok else 'UNEXPECTED '}"
                  f"{(problems[0] if problems else '')[:120]}")
        if name == "TARGET per N0":
            failing = app_image_test(paths["app.Dockerfile"], paths["gates.Dockerfile"], paths["uv.lock"])
            bad += bool(failing)
            print(f"{'TARGET per N0':<62} {'AppImageTest':<12} {'pass':<5} {'fail' if failing else 'pass':<5} "
                  f"{failing if failing else '(existing PSC-17 tests green on the target)'}")
    print(f"\nunexpected results: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
