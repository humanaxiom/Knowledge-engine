"""platform-sbom U0 (PSC-25): psycopg on Debian's libpq.

Criteria: docs/requirements.md PSC-25 (Q64, ruled by the human; Q65 and Q66
ruled by the orchestrator). Design: docs/architecture.md ADR-KE-016 point 0
and docs/evidence/platform-sbom/design-notes.md N0 ("U0 RED tests").

One module for the unit: its checks span pyproject.toml, uv.lock, both
Dockerfiles, the smoke host half and NOTICE.md, and no existing module holds
all of them. Each static check is an `assert_*` method that takes paths, so
the mutant driver (docs/evidence/platform-sbom/u0/) runs it on scratch copies;
the tests call them on the repository's files.

Interface pinned here (tester, U0 RED, 2026-10-22):
- The ke-app builder's resolved set is uv.lock walked from the project with
  no dev group and the `pq-c` group (the final builder sync, `--no-dev
  --group pq-c`), markers evaluated for CPython 3.12 on linux x86_64 and on
  linux aarch64. An unknown marker variable counts as true, so a marker can
  never hide psycopg-binary.
- `ARG LIBPQ_VERSION=<15.N-R+deb12uM>` once, before the first FROM, in
  docker/app.Dockerfile and docker/gates.Dockerfile; each stage that uses it
  redeclares a bare `ARG LIBPQ_VERSION`. The pin's libpq number is 15.N ->
  150000+N (psycopg's `pq.version()` form).
- Smoke: in the api, `compose exec -T api python [flags] -c CODE` prints what
  smoke checks (psycopg.pq.__impl__, version(), __build_version__ and the
  extension path), and `compose exec -T api ldd <path>` reads the extension
  the CODE named. The fake docker models both (tests/fake_docker.py,
  "platform-sbom U0"); smoke may also use dpkg-query/dpkg -S/realpath in the
  api. The libpq that ldd reports may be under `/lib/<triplet>/` or
  `/usr/lib/<triplet>/` (bookworm is merged-usr; both name the file libpq5
  owns). If smoke reads the pin from docker/app.Dockerfile, add that file to
  the shared smoke setUp's copy list (tests/test_stack_scripts.py), as
  net_isolated.sh was.

Full tier: the real image is proved by the `full` smoke stage against the
image `verify.sh full` builds; `test_gates_psycopg_is_c_impl_on_debian_libpq`
proves the gates image the suite runs in. These fast tests do not stand in
for either.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any

from tests import fake_docker
from tests import test_stack_scripts as tss
from tests.engine_support import ROOT
from tests.test_image_scan import _instructions, _stages

APP_DOCKERFILE = ROOT / "docker" / "app.Dockerfile"
GATES_DOCKERFILE = ROOT / "docker" / "gates.Dockerfile"
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
NOTICE = ROOT / "NOTICE.md"

PROJECT = "knowledge-engine"
BUILDER_GROUPS = ("pq-c",)
IMAGE_GROUPS = ("pq-c", "pq-build")
LIBPQ_PIN_RE = re.compile(r"^\d+\.\d+-\d+\+deb12u\d+$")
PYTHON_BOOKWORM_RE = re.compile(r"^python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
LIBPQ_VAR_RE = r"(?:\$\{LIBPQ_VERSION\}|\$LIBPQ_VERSION)"
# A compiler, a build tool, or a -dev package, as a word of a RUN.
BUILD_ONLY_RE = re.compile(r"(?:gcc(?:-\d+)?|g\+\+(?:-\d+)?|c\+\+|cc|clang(?:-\d+)?|cpp(?:-\d+)?|make|"
                           r"build-essential|[A-Za-z0-9.+]+-dev)")


# --------------------------------------------------------------------------
# PEP 508 markers, for the builder's platforms
# --------------------------------------------------------------------------

def _builder_env(machine: str) -> dict[str, str]:
    return {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix",
            "implementation_name": "cpython", "platform_python_implementation": "CPython",
            "platform_machine": machine, "python_version": "3.12", "python_full_version": "3.12.13",
            "implementation_version": "3.12.13", "extra": ""}


BUILDER_ENVS = {"linux x86_64": _builder_env("x86_64"), "linux aarch64": _builder_env("aarch64")}
_VERSION_VARS = {"python_version", "python_full_version", "implementation_version"}
_TOKEN_RE = re.compile(r"""\s*(?:(?P<str>'[^']*'|"[^"]*")|(?P<op>===|==|!=|<=|>=|~=|<|>|\(|\))|"""
                       r"""(?P<word>[A-Za-z_][A-Za-z0-9_.]*))""")


def _vtuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text)[:4])


def marker_true(marker: str, env: dict[str, str]) -> bool:
    """Evaluate a PEP 508 marker. Unknown variables count as true (so a
    marker never hides a package from the builder's set)."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(marker):
        if marker[pos:].strip() == "":
            break
        m = _TOKEN_RE.match(marker, pos)
        if not m:
            raise ValueError(f"cannot parse marker {marker!r} at {pos}")
        kind = m.lastgroup or ""
        tokens.append((kind, m.group(kind)))
        pos = m.end()
    i = 0

    def peek() -> tuple[str, str] | None:
        return tokens[i] if i < len(tokens) else None

    def take() -> tuple[str, str]:
        nonlocal i
        i += 1
        return tokens[i - 1]

    def value(tok: tuple[str, str]) -> str | None:
        kind, text = tok
        if kind == "str":
            return text[1:-1]
        return env.get(text)  # None: unknown variable

    def compare() -> bool:
        tok = peek()
        if tok == ("op", "("):
            take()
            out = disjunction()
            take()  # ")"
            return out
        left_tok = take()
        op_tok = take()
        op = op_tok[1]
        if op == "not":
            take()  # "in"
            op = "not in"
        right_tok = take()
        left, right = value(left_tok), value(right_tok)
        if left is None or right is None:
            return True
        var = left_tok[1] if left_tok[0] == "word" else right_tok[1]
        if op in ("==", "==="):
            return left == right if var not in _VERSION_VARS else _vtuple(left) == _vtuple(right)
        if op == "!=":
            return left != right if var not in _VERSION_VARS else _vtuple(left) != _vtuple(right)
        if op == "in":
            return left in right
        if op == "not in":
            return left not in right
        lv, rv = _vtuple(left), _vtuple(right)
        return {"<": lv < rv, "<=": lv <= rv, ">": lv > rv, ">=": lv >= rv, "~=": lv >= rv}.get(op, True)

    def conjunction() -> bool:
        out = compare()
        while peek() == ("word", "and"):
            take()
            out = compare() and out
        return out

    def disjunction() -> bool:
        out = conjunction()
        while peek() == ("word", "or"):
            take()
            out = conjunction() or out
        return out

    return disjunction()


# --------------------------------------------------------------------------
# uv.lock: what the ke-app builder resolves
# --------------------------------------------------------------------------

def _lock(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def builder_set(lock: dict[str, Any], env: dict[str, str], groups: tuple[str, ...] = BUILDER_GROUPS,
                problems: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """name -> lock entry of every package the builder installs: the
    project's dependencies plus `groups`, the extras they name, transitively,
    with markers evaluated for `env`."""
    problems = problems if problems is not None else []
    by_name: dict[str, list[dict[str, Any]]] = {}
    for pkg in lock.get("package", []):
        by_name.setdefault(pkg["name"], []).append(pkg)
    project = next((p for p in lock.get("package", []) if p.get("name") == PROJECT), None)
    if project is None:
        problems.append(f"uv.lock has no {PROJECT} package")
        return {}
    todo = list(project.get("dependencies", []))
    lock_groups = project.get("dev-dependencies", {})
    for group in groups:
        if group not in lock_groups:
            problems.append(f"uv.lock has no `{group}` group for {PROJECT} (the builder syncs --group {group})")
        todo += lock_groups.get(group, [])
    seen: dict[str, dict[str, Any]] = {}
    done: set[tuple[str, str, str]] = set()
    while todo:
        dep = todo.pop()
        if dep.get("marker") and not marker_true(dep["marker"], env):
            continue
        name = dep["name"]
        for pkg in by_name.get(name, []):
            if dep.get("version") and pkg.get("version") != dep["version"]:
                continue
            for extra in [""] + list(dep.get("extra", [])):
                key = (name, pkg.get("version", ""), extra)
                if key in done:
                    continue
                done.add(key)
                seen[name] = pkg
                if extra:
                    if extra not in pkg.get("optional-dependencies", {}):
                        problems.append(f"uv.lock: {name} has no locked extra `{extra}`")
                    todo += pkg.get("optional-dependencies", {}).get(extra, [])
                else:
                    todo += pkg.get("dependencies", [])
        if name not in by_name:
            problems.append(f"uv.lock names {name} but has no package entry for it")
    seen.pop(PROJECT, None)
    return seen


def builder_lock_problems(path: Path) -> list[str]:
    lock = _lock(path)
    problems: list[str] = []
    for label, env in BUILDER_ENVS.items():
        found: list[str] = []
        got = builder_set(lock, env, BUILDER_GROUPS, found)
        problems += [p for p in found if p not in problems]
        if "psycopg-binary" in got:
            problems.append(f"the ke-app builder ({label}) resolves psycopg-binary")
        if "psycopg-c" not in got:
            problems.append(f"the ke-app builder ({label}) does not resolve psycopg-c")
        elif "psycopg" in got and got["psycopg-c"].get("version") != got["psycopg"].get("version"):
            problems.append(f"({label}) psycopg-c {got['psycopg-c'].get('version')} is not at psycopg's "
                            f"version {got['psycopg'].get('version')}")
    for pkg in lock.get("package", []):
        if pkg["name"] == "psycopg-binary":
            problems.append("uv.lock still holds psycopg-binary (ADR-KE-016 point 0: no marker or extra keeps it)")
        if pkg["name"] != "psycopg-c":
            continue
        sdist = pkg.get("sdist") or {}
        if not str(sdist.get("url", "")).startswith("https://"):
            problems.append(f"psycopg-c {pkg.get('version')} has no locked sdist URL")
        if not SHA256_RE.match(str(sdist.get("hash", ""))):
            problems.append(f"psycopg-c {pkg.get('version')} sdist has no sha256 hash: {sdist.get('hash')!r}")
        if pkg.get("wheels"):
            problems.append(f"psycopg-c {pkg.get('version')} has locked wheels (it must build from its sdist)")
    return problems


# --------------------------------------------------------------------------
# Dockerfiles
# --------------------------------------------------------------------------

def _commands(run: str) -> list[str]:
    """The shell commands of a RUN, split on && || ; and |."""
    return [c.strip() for c in re.split(r"&&|\|\||;|\|", run) if c.strip()]


def _uv_syncs(body: list[tuple[str, str]]) -> list[list[str]]:
    out = []
    for keyword, rest in body:
        if keyword != "RUN":
            continue
        for cmd in _commands(rest):
            words = cmd.split()
            for j in range(len(words) - 1):
                if re.fullmatch(r"(?:.*/)?uv", words[j]) and words[j + 1] == "sync":
                    out.append(words[j:])
                    break
    return out


def _flag_values(words: list[str], flag: str) -> list[str]:
    out = []
    for j, w in enumerate(words):
        if w == flag and j + 1 < len(words):
            out.append(words[j + 1])
        elif w.startswith(flag + "="):
            out.append(w.split("=", 1)[1])
    return out


def _apt_installs(run: str) -> list[list[str]]:
    """The words after `install` of each apt-get/apt install command."""
    out = []
    for cmd in _commands(run):
        m = re.search(r"\bapt(?:-get)?\s+(?:\S+\s+)*?install\b(.*)$", cmd)
        if m:
            out.append(m.group(1).split())
    return out


def _packages(words: list[str]) -> list[str]:
    return [re.sub(LIBPQ_VAR_RE, "${LIBPQ_VERSION}", w.strip("\"'")) for w in words if not w.startswith("-")]


def libpq_pin(path: Path) -> tuple[str | None, list[str]]:
    """(the global `ARG LIBPQ_VERSION=` value, problems)."""
    problems: list[str] = []
    instrs = _instructions(path)
    first_from = next((n for n, (k, _) in enumerate(instrs) if k == "FROM"), len(instrs))
    pins = []
    for n, (keyword, rest) in enumerate(instrs):
        if keyword != "ARG":
            continue
        m = re.fullmatch(r"LIBPQ_VERSION(?:=(.*))?", rest.strip())
        if not m:
            continue
        if m.group(1) is not None:
            if n > first_from:
                problems.append(f"{path.name}: `ARG {rest}` sets the pin inside a stage (declare it once, "
                                f"before the first FROM)")
            else:
                pins.append(m.group(1).strip("\"'"))
    if len(pins) != 1:
        problems.append(f"{path.name}: {len(pins)} global `ARG LIBPQ_VERSION=` before the first FROM, want 1")
        return (pins[0] if pins else None), problems
    if not LIBPQ_PIN_RE.match(pins[0]):
        problems.append(f"{path.name}: LIBPQ_VERSION {pins[0]!r} is not a bookworm version "
                        f"(<major>.<minor>-<rev>+deb12u<n>)")
    return pins[0], problems


def pq_number(pin: str) -> int:
    m = re.match(r"^(\d+)\.(\d+)", pin)
    assert m, pin
    return int(m.group(1)) * 10000 + int(m.group(2))


def _has_bare_arg(body: list[tuple[str, str]]) -> bool:
    return any(k == "ARG" and rest.strip() == "LIBPQ_VERSION" for k, rest in body)


def _builder(stages: list[dict[str, Any]]) -> dict[str, Any] | None:
    found = [s for s in stages if (s["name"] or "").lower() == "builder"]
    return found[0] if len(found) == 1 else None


def app_build_problems(path: Path) -> list[str]:
    """test_app_dockerfile_builds_psycopg_c_on_pinned_libpq on `path`."""
    pin, problems = libpq_pin(path)
    stages = _stages(path)
    builder = _builder(stages)
    if builder is None:
        return problems + ["app.Dockerfile has no single `AS builder` stage"]
    body = builder["body"]
    if not _has_bare_arg(body):
        problems.append("builder: no `ARG LIBPQ_VERSION` (the pin is empty in the stage)")
    if pin is not None:
        text = "\n".join(f"{k} {r}" for k, r in _instructions(path))
        if text.count(pin) != 1:
            problems.append(f"app.Dockerfile: the pin {pin!r} is written {text.count(pin)} times; "
                            f"it is a literal once, then ${{LIBPQ_VERSION}}")
    apt_runs = [rest for k, rest in body if k == "RUN" and _apt_installs(rest)]
    pkgs = [p for rest in apt_runs for words in _apt_installs(rest) for p in _packages(words)]
    if "libpq-dev=${LIBPQ_VERSION}" not in pkgs:
        problems.append(f"builder: no `apt-get install ... libpq-dev=${{LIBPQ_VERSION}}` (got {pkgs})")
    if not [p for p in pkgs if re.fullmatch(r"gcc(?:-\d+)?(?:=\S+)?", p)]:
        problems.append(f"builder: installs no compiler (gcc) to build psycopg-c (got {pkgs})")
    for rest in apt_runs:
        if "--no-install-recommends" not in rest:
            problems.append(f"builder: apt install without --no-install-recommends: {rest}")
        if not re.search(r"\brm\s+-rf\s+/var/lib/apt/lists/\*", rest):
            problems.append(f"builder: the apt RUN does not remove /var/lib/apt/lists/*: {rest}")
    all_syncs = [w for s in stages for w in _uv_syncs(s["body"])]
    for words in all_syncs:
        line = " ".join(words)
        if "--locked" not in words:
            problems.append(f"`{line}` has no --locked")
        if "pq-c" in _flag_values(words, "--group") and "psycopg-c" not in _flag_values(words, "--no-binary-package"):
            problems.append(f"`{line}` names pq-c without --no-binary-package psycopg-c")
        if "--all-groups" in words or "--frozen" in words:
            problems.append(f"`{line}` uses --all-groups or --frozen")
    syncs = _uv_syncs(body)
    if not syncs:
        return problems + ["builder: no `uv sync`"]
    for words in syncs:
        if "--no-dev" not in words:
            problems.append(f"builder: `{' '.join(words)}` has no --no-dev")
    final = syncs[-1]
    groups = _flag_values(final, "--group")
    if "pq-c" not in groups:
        problems.append(f"builder: the final sync does not name --group pq-c: {' '.join(final)}")
    if "pq-build" in groups:
        problems.append(f"builder: the final sync keeps pq-build (it would ship): {' '.join(final)}")
    if "--no-editable" not in final:
        problems.append(f"builder: the final sync has no --no-editable: {' '.join(final)}")
    if "--inexact" in final:
        problems.append(f"builder: the final sync is --inexact (pq-build would stay): {' '.join(final)}")
    if not [w for w in syncs[:-1] if "pq-build" in _flag_values(w, "--group")]:
        problems.append("builder: no sync installs pq-build before psycopg-c is built (no build isolation)")
    return problems


def app_runtime_problems(path: Path) -> list[str]:
    """test_runtime_stage_has_no_compiler on `path`."""
    problems: list[str] = []
    stages = _stages(path)
    if not stages:
        return ["app.Dockerfile has no FROM"]
    final = stages[-1]
    body = final["body"]
    if (final["name"] or "").lower() == "builder":
        problems.append("the last stage is the builder")
    if not _has_bare_arg(body):
        problems.append("last stage: no `ARG LIBPQ_VERSION` (libpq5=${LIBPQ_VERSION} would be empty)")
    apt_runs = [(n, rest) for n, (k, rest) in enumerate(body) if k == "RUN" and _apt_installs(rest)]
    if len(apt_runs) != 1:
        problems.append(f"last stage: {len(apt_runs)} RUNs install apt packages, want exactly 1")
    for n, rest in apt_runs:
        installs = _apt_installs(rest)
        pkgs = [p for words in installs for p in _packages(words)]
        if pkgs != ["libpq5=${LIBPQ_VERSION}"]:
            problems.append(f"last stage: installs {pkgs}, want exactly ['libpq5=${{LIBPQ_VERSION}}']")
        flags = [w for words in installs for w in words if w.startswith("-")]
        if "--no-install-recommends" not in flags:
            problems.append(f"last stage: apt install without --no-install-recommends: {rest}")
        if "-y" not in flags and "--yes" not in flags and "-qy" not in flags:
            problems.append(f"last stage: apt install without -y: {rest}")
        if not re.search(r"\bapt-get\s+update\b", rest):
            problems.append(f"last stage: no apt-get update in the install RUN: {rest}")
        if not re.search(r"\brm\s+-rf\s+/var/lib/apt/lists/\*", rest):
            problems.append(f"last stage: /var/lib/apt/lists/* not removed in the same RUN: {rest}")
        users = [m for m, (k, _) in enumerate(body) if k == "USER"]
        if users and users[0] < n:
            problems.append("last stage: the apt RUN comes after USER (it needs root)")
    for keyword, rest in body:
        if keyword != "RUN":
            continue
        words = [w.strip("\"'") for w in re.split(r"[\s;&|()<>`=]+", rest) if w]
        bad = [w for w in words if not w.startswith("-") and BUILD_ONLY_RE.fullmatch(w)]
        if bad:
            problems.append(f"last stage: a RUN names build-only packages or tools {bad}: {rest}")
    builder = _builder(stages)
    b_pkgs = [p for k, rest in (builder["body"] if builder else []) if k == "RUN"
              for words in _apt_installs(rest) for p in _packages(words)]
    if not [p for p in b_pkgs if p.split("=")[0] == "libpq-dev"]:
        problems.append(f"builder: no libpq-dev (got {b_pkgs})")
    return problems


def pin_base_problems(app: Path, gates: Path) -> list[str]:
    """test_libpq_pin_matches_bookworm_base on `app` and `gates`."""
    pin, problems = libpq_pin(app)
    if pin is not None and "+deb12u" not in pin:
        problems.append(f"app.Dockerfile: the pin {pin!r} is not a Debian 12 (+deb12u) version")
    bases = [s["ref"] for s in _stages(app) if s["ref"].startswith("python:")]
    if len(bases) < 2:
        problems.append(f"app.Dockerfile: {len(bases)} python base FROM lines, want the builder and the last stage")
    for ref in bases:
        if not PYTHON_BOOKWORM_RE.match(ref):
            problems.append(f"app.Dockerfile: base {ref!r} is not python:3.12-slim-bookworm@sha256 (the pin is deb12)")
    if len(set(bases)) > 1:
        problems.append(f"app.Dockerfile: the builder and the last stage use different bases: {sorted(set(bases))}")
    g_pin, g_problems = libpq_pin(gates)
    problems += g_problems
    if pin is not None and g_pin != pin:
        problems.append(f"gates.Dockerfile pins LIBPQ_VERSION {g_pin!r}, app.Dockerfile {pin!r}")
    g_bases = [s["ref"] for s in _stages(gates) if s["ref"].startswith("python:")]
    for ref in g_bases:
        if not PYTHON_BOOKWORM_RE.match(ref):
            problems.append(f"gates.Dockerfile: base {ref!r} is not python:3.12-slim-bookworm@sha256")
    g_stages = _stages(gates)
    g_body = g_stages[-1]["body"] if g_stages else []
    if not _has_bare_arg(g_body):
        problems.append("gates.Dockerfile: the gates stage has no `ARG LIBPQ_VERSION`")
    g_pkgs = [p for k, rest in g_body if k == "RUN" for words in _apt_installs(rest) for p in _packages(words)]
    if "libpq-dev=${LIBPQ_VERSION}" not in g_pkgs:
        problems.append("gates.Dockerfile: no `libpq-dev=${LIBPQ_VERSION}` (gates build psycopg-c on the same pin)")
    return problems


# --------------------------------------------------------------------------
# pyproject.toml
# --------------------------------------------------------------------------

_REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?\s*(.*)$")


def _req(text: str) -> tuple[str, set[str], str]:
    m = _REQ_RE.match(text)
    assert m, text
    name = re.sub(r"[-_.]+", "-", m.group(1)).lower()
    extras = {e.strip().lower() for e in (m.group(2) or "").split(",") if e.strip()}
    return name, extras, m.group(3).strip()


def pyproject_problems(path: Path) -> list[str]:
    """test_pyproject_puts_psycopg_c_in_image_groups_only on `path`."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    deps = [_req(d) for d in data.get("project", {}).get("dependencies", [])]
    pq = [d for d in deps if d[0].startswith("psycopg")]
    if [d[0] for d in pq] != ["psycopg"]:
        problems.append(f"dependencies: want exactly one psycopg entry, `psycopg` (got {[d[0] for d in pq]})")
    for name, extras, _ in pq:
        if extras:
            problems.append(f"dependencies: {name}[{','.join(sorted(extras))}] has an extra; "
                            f"the default install is pure psycopg (Q65)")
    groups = data.get("dependency-groups", {})
    every: list[tuple[str, str, set[str], str]] = [("dependencies", *d) for d in deps]
    for gname, entries in groups.items():
        for entry in entries:
            if isinstance(entry, str):
                every.append((f"group {gname}", *_req(entry)))
    for where, extras_map in data.get("project", {}).get("optional-dependencies", {}).items():
        for entry in extras_map:
            every.append((f"extra {where}", *_req(entry)))
    for where, name, extras, _ in every:
        if name == "psycopg-binary" or (name == "psycopg" and "binary" in extras):
            problems.append(f"{where}: names psycopg-binary (PSC-25: ke-app ships none; ADR-KE-016: not locked)")
    pq_c = [(n, e) for where, n, e, _ in every if where == "group pq-c"]
    if "pq-c" not in groups:
        problems.append("no `pq-c` dependency group")
    elif ("psycopg", {"c"}) not in pq_c:
        problems.append(f"group pq-c: want `psycopg[c]` (the extra pins psycopg-c to psycopg's version), got {pq_c}")
    if "pq-build" not in groups:
        problems.append("no `pq-build` dependency group (psycopg-c's build requires, hash-locked)")
    else:
        build = groups["pq-build"]
        if not build:
            problems.append("group pq-build is empty")
        for entry in build:
            if not isinstance(entry, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][^\s;,]*", entry.strip()):
                problems.append(f"group pq-build: {entry!r} is not pinned `name==version`")
    for gname in ("pq-c", "pq-build"):
        for entry in groups.get(gname, []):
            if isinstance(entry, dict):
                problems.append(f"group {gname}: includes another group {entry}")
    for gname, entries in groups.items():
        if gname in IMAGE_GROUPS:
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("include-group") in IMAGE_GROUPS:
                problems.append(f"group {gname} includes {entry['include-group']} (hosts would compile)")
            elif isinstance(entry, str) and _req(entry)[0] == "psycopg-c" or (
                    isinstance(entry, str) and _req(entry)[:2] == ("psycopg", {"c"})):
                problems.append(f"group {gname} names psycopg-c (hosts would compile)")
    uv = data.get("tool", {}).get("uv", {})
    if uv.get("no-build-isolation-package") != ["psycopg-c"]:
        problems.append(f"[tool.uv] no-build-isolation-package is {uv.get('no-build-isolation-package')!r}, "
                        f"want ['psycopg-c']")
    defaults = uv.get("default-groups", ["dev"])
    if defaults == "all" or [g for g in (defaults if isinstance(defaults, list) else []) if g in IMAGE_GROUPS]:
        problems.append(f"[tool.uv] default-groups {defaults!r} include an image group (a host's uv run would compile)")
    return problems


# --------------------------------------------------------------------------
# NOTICE.md
# --------------------------------------------------------------------------

def notice_problems(notice: Path, lock_path: Path) -> list[str]:
    """test_notice_psycopg_section_matches_lock on `notice` and `lock_path`."""
    problems: list[str] = []
    lock = _lock(lock_path)
    pkgs: dict[str, dict[str, Any]] = {}
    for env in BUILDER_ENVS.values():
        pkgs.update({n: p for n, p in builder_set(lock, env).items() if n.startswith("psycopg")})
    if "psycopg-c" not in pkgs:
        problems.append(f"the builder's locked set has no psycopg-c (psycopg packages: {sorted(pkgs)})")
    text = notice.read_text(encoding="utf-8")
    m = re.search(r"(?ms)^## psycopg\b([^\n]*)\n(.*?)(?=^## |\Z)", text)
    if not m:
        return problems + ["NOTICE.md has no `## psycopg` section"]
    heading, section = m.group(1), m.group(2)
    if "LGPL-3.0-only" not in heading:
        problems.append(f"NOTICE.md psycopg heading {heading.strip()!r} does not say LGPL-3.0-only")
    flat = " ".join(section.split())
    for name, pkg in sorted(pkgs.items()):
        if not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", flat):
            problems.append(f"NOTICE.md psycopg section does not name {name}")
        sdist = pkg.get("sdist") or {}
        url, digest = sdist.get("url"), str(sdist.get("hash", "")).removeprefix("sha256:")
        if not url:
            problems.append(f"{name} has no locked sdist for NOTICE.md to name")
            continue
        if url not in flat:
            problems.append(f"NOTICE.md psycopg section does not give {name}'s locked sdist URL {url}")
        if digest not in flat:
            problems.append(f"NOTICE.md psycopg section does not give {name}'s sdist sha256 {digest}")
        if pkg.get("version") and pkg["version"] not in flat:
            problems.append(f"NOTICE.md psycopg section does not give {name}'s version {pkg['version']}")
    if re.search(r"(?i)psycopg[-_]binary", section):
        problems.append("NOTICE.md psycopg section still names psycopg-binary (PSC-25: instead of psycopg-binary)")
    return problems


# --------------------------------------------------------------------------
# Fixtures: a target shape per N0, and controls that must fail
# --------------------------------------------------------------------------

_HASH_C = "sha256:" + "c" * 64
_LOCK_HEAD = 'version = 1\nrevision = 3\nrequires-python = "==3.12.*"\n'
TARGET_LOCK = _LOCK_HEAD + '''
[[package]]
name = "knowledge-engine"
version = "0.1.0"
source = { editable = "." }
dependencies = [
    { name = "psycopg" },
]

[package.dev-dependencies]
dev = [
    { name = "coverage" },
]
pq-build = [
    { name = "setuptools" },
]
pq-c = [
    { name = "psycopg", extra = ["c"] },
]

[[package]]
name = "coverage"
version = "7.16.2"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "psycopg"
version = "3.3.6"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "typing-extensions" },
    { name = "tzdata", marker = "sys_platform == 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/76/26/x/psycopg-3.3.6.tar.gz", hash = "sha256:''' + "a" * 64 + '''", size = 1 }

[package.optional-dependencies]
c = [
    { name = "psycopg-c", marker = "implementation_name != 'pypy'" },
]

[[package]]
name = "psycopg-c"
version = "3.3.6"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/aa/bb/x/psycopg_c-3.3.6.tar.gz", hash = "''' + _HASH_C + '''", size = 1 }

[[package]]
name = "setuptools"
version = "80.9.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "typing-extensions"
version = "4.15.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "tzdata"
version = "2026.1"
source = { registry = "https://pypi.org/simple" }
'''
_BINARY_PKG = '''
[[package]]
name = "psycopg-binary"
version = "3.3.6"
source = { registry = "https://pypi.org/simple" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/0a/42/x/psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.whl", hash = "sha256:''' + "b" * 64 + '''", size = 1 },
]
'''


def _lock_controls() -> dict[str, str]:
    t = TARGET_LOCK
    return {
        "today's shape: dependencies psycopg[binary]": t.replace(
            '    { name = "psycopg" },\n]\n\n[package.dev', '    { name = "psycopg", extra = ["binary"] },\n]\n\n'
            '[package.dev', 1).replace(
            "c = [\n    { name = \"psycopg-c\"", "binary = [\n    { name = \"psycopg-binary\" },\n]\nc = [\n"
            "    { name = \"psycopg-c\"", 1) + _BINARY_PKG,
        "pq-c keeps psycopg-binary for linux": t.replace(
            'pq-c = [\n', 'pq-c = [\n    { name = "psycopg-binary", marker = "sys_platform == \'linux\'" },\n', 1)
            + _BINARY_PKG,
        "psycopg-binary locked for win32 only": t.replace(
            '    { name = "psycopg" },\n]\n\n[package.dev',
            '    { name = "psycopg" },\n    { name = "psycopg-binary", marker = "sys_platform == \'win32\'" },\n]\n\n'
            '[package.dev', 1) + _BINARY_PKG,
        "psycopg-c with a wheel": t.replace(
            'psycopg_c-3.3.6.tar.gz", hash = "' + _HASH_C + '", size = 1 }\n',
            'psycopg_c-3.3.6.tar.gz", hash = "' + _HASH_C + '", size = 1 }\nwheels = [\n    { url = '
            '"https://files.pythonhosted.org/x/psycopg_c-3.3.6-cp312-cp312-manylinux_2_28_x86_64.whl", hash = "'
            + _HASH_C + '", size = 1 },\n]\n', 1),
        "psycopg-c sdist without a sha256": t.replace(_HASH_C, "md5:" + "c" * 32, 1),
        "psycopg-c only on aarch64": t.replace(
            "marker = \"implementation_name != 'pypy'\"", "marker = \"platform_machine == 'aarch64'\"", 1),
        "no pq-c group in the lock": t.replace('pq-c = [\n    { name = "psycopg", extra = ["c"] },\n]\n', "", 1),
        "psycopg-c not at psycopg's version": t.replace(
            'name = "psycopg-c"\nversion = "3.3.6"', 'name = "psycopg-c"\nversion = "3.3.5"', 1),
    }


TARGET_NOTICE = """# Notices

## psycopg (LGPL-3.0-only)

The `ke-app` image installs `psycopg` and `psycopg-c` 3.3.6 under the GNU
Lesser General Public License version 3 only. `psycopg`:
https://files.pythonhosted.org/packages/76/26/x/psycopg-3.3.6.tar.gz
(sha256 `""" + "a" * 64 + """`); `psycopg-c`, compiled in the image against
Debian's libpq5:
https://files.pythonhosted.org/packages/aa/bb/x/psycopg_c-3.3.6.tar.gz
(sha256 `""" + "c" * 64 + """`).

## Licence texts
"""

TARGET_PYPROJECT = """[project]
name = "knowledge-engine"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi>=0.146.0",
    "psycopg>=3.3.6",
]

[dependency-groups]
dev = ["coverage>=7.16.2"]
pq-c = ["psycopg[c]>=3.3.6"]
pq-build = ["setuptools==80.9.0", "wheel==0.45.1"]

[tool.uv]
no-build-isolation-package = ["psycopg-c"]
"""

_PIN = "15.14-0+deb12u1"
_BASE = "python:3.12-slim-bookworm@sha256:" + "3" * 64
TARGET_APP = f"""ARG LIBPQ_VERSION={_PIN}
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:{"f" * 64} AS uv

FROM {_BASE} AS builder
ARG LIBPQ_VERSION
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \\
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev=${{LIBPQ_VERSION}} \\
 && rm -rf /var/lib/apt/lists/*
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --group pq-build --no-install-project
RUN uv sync --locked --no-dev --group pq-build --group pq-c --no-binary-package psycopg-c --no-install-project
COPY engine ./engine
RUN uv sync --locked --no-dev --group pq-c --no-binary-package psycopg-c --no-editable \\
    && rm -f /opt/venv/.lock

FROM {_BASE}
ARG LIBPQ_VERSION
ENV PATH=/opt/venv/bin:$PATH
RUN apt-get update \\
 && apt-get install -y --no-install-recommends libpq5=${{LIBPQ_VERSION}} \\
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
WORKDIR /app
RUN useradd --no-create-home --uid 10001 ke
USER ke
CMD ["python", "-m", "engine.api"]
"""
TARGET_GATES = f"""ARG LIBPQ_VERSION={_PIN}
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:{"f" * 64} AS uv

FROM {_BASE}
ARG LIBPQ_VERSION
RUN apt-get update \\
 && apt-get install -y --no-install-recommends git jq gcc libc6-dev libpq-dev=${{LIBPQ_VERSION}} \\
 && rm -rf /var/lib/apt/lists/*
RUN uv sync --locked --group pq-build --group pq-c --no-binary-package psycopg-c
"""


class _Scratch:
    """Write fixture text to a temp file that the test removes."""

    def __init__(self, case: unittest.TestCase) -> None:
        self.dir = Path(tempfile.mkdtemp())
        case.addCleanup(shutil.rmtree, self.dir, True)
        self.n = 0

    def write(self, text: str, name: str) -> Path:
        self.n += 1
        path = self.dir / f"{self.n:02d}" / name
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8", newline="\n")
        return path


# --------------------------------------------------------------------------
# The tests
# --------------------------------------------------------------------------

class PsycopgCStaticTest(unittest.TestCase):
    """PSC-25 static checks (fast): lock, pyproject, Dockerfiles, NOTICE.md."""

    maxDiff = None

    # ---- assert_* take paths, so mutants can be driven -----------------------

    def assert_builder_lock(self, lock: Path = UV_LOCK) -> None:
        problems = builder_lock_problems(lock)
        self.assertEqual(problems, [], f"{lock.name}: the ke-app builder must resolve psycopg-c from its locked "
                                       f"sdist and no psycopg-binary (PSC-25 Lock, ADR-KE-016 point 0)")

    def assert_pyproject(self, path: Path = PYPROJECT) -> None:
        self.assertEqual(pyproject_problems(path), [],
                         f"{path.name}: psycopg-c only in the image groups (PSC-25, Q65, N0)")

    def assert_app_build(self, path: Path = APP_DOCKERFILE) -> None:
        self.assertEqual(app_build_problems(path), [],
                         f"{path.name}: the builder compiles psycopg-c on the pinned libpq-dev (PSC-25 Builder stage)")

    def assert_app_runtime(self, path: Path = APP_DOCKERFILE) -> None:
        self.assertEqual(app_runtime_problems(path), [],
                         f"{path.name}: the shipped stage installs only libpq5=${{LIBPQ_VERSION}} and no "
                         f"compiler or -dev package (PSC-25 Runtime stage)")

    def assert_pin_base(self, app: Path = APP_DOCKERFILE, gates: Path = GATES_DOCKERFILE) -> None:
        self.assertEqual(pin_base_problems(app, gates), [],
                         "LIBPQ_VERSION is a +deb12u pin on the -bookworm base, the same in both images (N0 Drift)")

    def assert_notice(self, notice: Path = NOTICE, lock: Path = UV_LOCK) -> None:
        self.assertEqual(notice_problems(notice, lock), [],
                         "NOTICE.md's psycopg section names each psycopg package the builder installs, with its "
                         "locked sdist URL and sha256 (PSC-25 Notices)")

    def _controls(self, check, target: tuple[Path, ...], controls: dict[str, tuple[Path, ...]]) -> None:
        with self.subTest(control="target shape (N0) passes"):
            check(*target)
        for name, paths in controls.items():
            with self.subTest(control=name):
                with self.assertRaises(AssertionError, msg=f"the check passed a control that must fail: {name}"):
                    check(*paths)

    # ---- 1 ------------------------------------------------------------------

    def test_ke_app_resolves_psycopg_c_not_binary(self):
        """PSC-25 Lock (A65/A66, ADR-KE-016 point 0): what `uv sync --locked
        --no-dev --group pq-c` installs in the builder, on linux x86_64 and
        aarch64, read offline from uv.lock: psycopg-c at psycopg's version
        from its locked sdist (sha256, no wheels), and no psycopg-binary; the
        lock holds no psycopg-binary at all. RED: today the builder resolves
        psycopg-binary and the lock has no psycopg-c or `pq-c` group."""
        s = _Scratch(self)
        self._controls(self.assert_builder_lock, (s.write(TARGET_LOCK, "uv.lock"),),
                       {k: (s.write(v, "uv.lock"),) for k, v in _lock_controls().items()})
        self.assert_builder_lock(UV_LOCK)

    # ---- 2 ------------------------------------------------------------------

    def test_pyproject_puts_psycopg_c_in_image_groups_only(self):
        """PSC-25 Lock, Q65, N0 pyproject: `dependencies` has `psycopg` with
        no extra; group `pq-c` is `psycopg[c]`; group `pq-build` pins the
        build backend `==`; `no-build-isolation-package = ["psycopg-c"]`; the
        default groups (dev) hold neither image group; psycopg-binary is
        nowhere. RED: `psycopg[binary]>=3.3.6` in dependencies."""
        s = _Scratch(self)
        t = TARGET_PYPROJECT
        controls = {
            "today's psycopg[binary]": t.replace('"psycopg>=3.3.6"', '"psycopg[binary]>=3.3.6"'),
            "dependencies psycopg[c] (hosts compile)": t.replace('"psycopg>=3.3.6"', '"psycopg[c]>=3.3.6"'),
            "default-groups include pq-c": t + 'default-groups = ["dev", "pq-c"]\n',
            "pq-build unpinned": t.replace('"setuptools==80.9.0"', '"setuptools>=80"'),
            "build isolation left on": t.replace('no-build-isolation-package = ["psycopg-c"]\n', ""),
            "dev includes pq-c": t.replace('dev = ["coverage>=7.16.2"]', 'dev = ["coverage>=7.16.2", '
                                                                          '{include-group = "pq-c"}]'),
            "pq-c names psycopg-binary": t.replace('pq-c = ["psycopg[c]>=3.3.6"]',
                                                   'pq-c = ["psycopg[c]>=3.3.6", "psycopg-binary>=3.3.6"]'),
        }
        self._controls(self.assert_pyproject, (s.write(t, "pyproject.toml"),),
                       {k: (s.write(v, "pyproject.toml"),) for k, v in controls.items()})
        self.assert_pyproject(PYPROJECT)

    # ---- 3 ------------------------------------------------------------------

    def test_app_dockerfile_builds_psycopg_c_on_pinned_libpq(self):
        """PSC-25 Builder stage, N0 app.Dockerfile: one global `ARG
        LIBPQ_VERSION=<..+deb12u..>` (the only literal); the builder installs
        gcc and `libpq-dev=${LIBPQ_VERSION}`; every `uv sync` is --locked and
        every sync naming pq-c has `--no-binary-package psycopg-c`; pq-build
        is installed before the compile; the final builder sync is `--no-dev
        --group pq-c --no-editable` without pq-build. RED: no pin, no
        libpq-dev, no pq-c sync."""
        s = _Scratch(self)
        t = TARGET_APP
        last_sync = "RUN uv sync --locked --no-dev --group pq-c --no-binary-package psycopg-c --no-editable"
        controls = {
            "no global pin": t.replace(f"ARG LIBPQ_VERSION={_PIN}\n", "", 1),
            "pin in a stage": t.replace(f"ARG LIBPQ_VERSION={_PIN}\n", "", 1).replace(
                "AS builder\nARG LIBPQ_VERSION\n", f"AS builder\nARG LIBPQ_VERSION={_PIN}\n", 1),
            "pin not +deb12u": t.replace(_PIN, "15.14-1.pgdg120+1"),
            "libpq-dev unpinned": t.replace("libpq-dev=${LIBPQ_VERSION}", "libpq-dev"),
            "no compiler in the builder": t.replace(" gcc libc6-dev", " libc6-dev"),
            "final sync without --no-binary-package": t.replace(last_sync, last_sync.replace(
                " --no-binary-package psycopg-c", "")),
            "final sync keeps pq-build": t.replace(last_sync, last_sync.replace(
                "--group pq-c", "--group pq-build --group pq-c")),
            "final sync without --locked": t.replace(last_sync, last_sync.replace(" --locked", "")),
            "no pq-build before the compile": t.replace(
                "RUN uv sync --locked --no-dev --group pq-build --no-install-project\n", "").replace(
                "--group pq-build --group pq-c", "--group pq-c"),
        }
        self._controls(self.assert_app_build, (s.write(t, "app.Dockerfile"),),
                       {k: (s.write(v, "app.Dockerfile"),) for k, v in controls.items()})
        self.assert_app_build(APP_DOCKERFILE)

    # ---- 4 ------------------------------------------------------------------

    def test_runtime_stage_has_no_compiler(self):
        """PSC-25 Runtime stage: the last stage has one apt RUN, `apt-get
        update`, `apt-get install -y --no-install-recommends
        libpq5=${LIBPQ_VERSION}` and `rm -rf /var/lib/apt/lists/*`, before
        USER; no gcc/cc/make/-dev anywhere in it; the builder has libpq-dev.
        RED: today's last stage installs no libpq5 and the builder has no
        libpq-dev."""
        s = _Scratch(self)
        t = TARGET_APP
        runtime = "libpq5=${LIBPQ_VERSION} \\\n"
        controls = {
            "gcc in the last stage": t.replace(runtime, "libpq5=${LIBPQ_VERSION} gcc \\\n"),
            "libpq-dev in the last stage": t.replace(runtime, "libpq5=${LIBPQ_VERSION} libpq-dev=${LIBPQ_VERSION} \\\n"),
            "unpinned libpq5": t.replace(runtime, "libpq5 \\\n"),
            "make in a later RUN": t.replace("RUN useradd", "RUN apt-get purge -y make && useradd"),
            "apt lists kept": t.replace(" \\\n && rm -rf /var/lib/apt/lists/*\nCOPY --from=builder",
                                        "\nCOPY --from=builder"),
            "recommends allowed": t.replace("install -y --no-install-recommends libpq5", "install -y libpq5"),
            "no ARG in the last stage": t.replace("FROM " + _BASE + "\nARG LIBPQ_VERSION\n", "FROM " + _BASE + "\n"),
            "no libpq-dev in the builder": t.replace(" libpq-dev=${LIBPQ_VERSION}", ""),
        }
        self._controls(self.assert_app_runtime, (s.write(t, "app.Dockerfile"),),
                       {k: (s.write(v, "app.Dockerfile"),) for k, v in controls.items()})
        self.assert_app_runtime(APP_DOCKERFILE)

    # ---- 5 ------------------------------------------------------------------

    def test_libpq_pin_matches_bookworm_base(self):
        """N0 Drift: the pin is `+deb12u<n>`, both python FROM lines of
        app.Dockerfile are the same -bookworm digest, and gates.Dockerfile
        pins the same LIBPQ_VERSION and installs `libpq-dev=${LIBPQ_VERSION}`
        on a -bookworm base. RED: neither Dockerfile has the pin."""
        s = _Scratch(self)
        app, gates = TARGET_APP, TARGET_GATES
        trixie = _BASE.replace("bookworm", "trixie")
        controls = {
            "pin not +deb12u (pgdg)": (app.replace(_PIN, "15.14-1.pgdg120+1"), gates),
            "pin +deb13u on a trixie base": (app.replace(_PIN, "17.6-0+deb13u1").replace(_BASE, trixie), gates),
            "app base moved to trixie": (app.replace(_BASE, trixie), gates),
            "builder and last stage on different digests": (
                app.replace(f"FROM {_BASE} AS builder", f"FROM {_BASE.replace('3' * 64, '4' * 64)} AS builder"),
                gates),
            "gates on a different pin": (app, gates.replace(_PIN, "15.13-0+deb12u1")),
            "gates without the pin": (app, gates.replace(f"ARG LIBPQ_VERSION={_PIN}\n", "")),
            "gates libpq-dev unpinned": (app, gates.replace("libpq-dev=${LIBPQ_VERSION}", "libpq-dev")),
        }
        self._controls(self.assert_pin_base,
                       (s.write(app, "app.Dockerfile"), s.write(gates, "gates.Dockerfile")),
                       {k: (s.write(a, "app.Dockerfile"), s.write(g, "gates.Dockerfile"))
                        for k, (a, g) in controls.items()})
        self.assert_pin_base(APP_DOCKERFILE, GATES_DOCKERFILE)

    # ---- 8 ------------------------------------------------------------------

    def test_notice_psycopg_section_matches_lock(self):
        """PSC-25 Notices: every psycopg package in the builder's locked set
        (psycopg, psycopg-c) is named in NOTICE.md's `## psycopg
        (LGPL-3.0-only)` section with its version, locked sdist URL and
        sha256, and psycopg-binary is not named. RED: the lock gives the
        builder psycopg-binary (no sdist) and no psycopg-c, and the section
        names psycopg-binary."""
        s = _Scratch(self)
        lock = s.write(TARGET_LOCK, "uv.lock")
        n = TARGET_NOTICE
        controls = {
            "NOTICE without psycopg-c": n.replace("`psycopg-c`, compiled", "the C extension, compiled").replace(
                "and `psycopg-c` 3.3.6", "3.3.6"),
            "psycopg-c's hash wrong": n.replace("c" * 64, "d" * 64),
            "psycopg-c's URL missing": n.replace("https://files.pythonhosted.org/packages/aa/bb/x/psycopg_c-3.3.6.tar.gz\n",
                                                 ""),
            "still names psycopg-binary": n.replace("Debian's libpq5:", "Debian's libpq5 (was psycopg-binary):"),
            "heading lost the licence": n.replace("## psycopg (LGPL-3.0-only)", "## psycopg"),
        }
        self._controls(self.assert_notice, (s.write(n, "NOTICE.md"), lock),
                       {k: (s.write(v, "NOTICE.md"), lock) for k, v in controls.items()})
        with self.subTest(control="today's lock (builder resolves psycopg-binary) fails"):
            with self.assertRaises(AssertionError):
                self.assert_notice(s.write(n, "NOTICE.md"),
                                   s.write(_lock_controls()["today's shape: dependencies psycopg[binary]"], "uv.lock"))
        self.assert_notice(NOTICE, UV_LOCK)


# ---- 6 ----------------------------------------------------------------------

class GatesPsycopgTest(unittest.TestCase):
    """PSC-25, N0 "Runtime proof": the gates image the suite runs in imports
    the same psycopg implementation that ships (a real import)."""

    def test_gates_psycopg_is_c_impl_on_debian_libpq(self):
        """In ke-gates: `psycopg.pq.__impl__ == "c"`; `pq.version()` and
        `pq.__build_version__` both equal the gates.Dockerfile pin's number;
        no `psycopg_binary` is importable; the libpq mapped into this process
        is Debian's under /usr/lib/<triplet>/ (or its /lib alias), not a copy
        under /opt/venv. RED: the gates venv has psycopg-binary, so the impl
        is `binary`."""
        if os.environ.get("KE_IN_GATES") != "1":
            self.skipTest("runs in the ke-gates image only (KE_IN_GATES=1); scripts/verify.sh runs it there")
        import psycopg

        impl = psycopg.pq.__impl__
        self.assertEqual(impl, "c", f"psycopg.pq.__impl__ is {impl!r} in ke-gates, want 'c' (PSC-25)")
        self.assertIsNone(importlib.util.find_spec("psycopg_binary"),
                          "psycopg_binary is importable in ke-gates (PSC-25: no vendored copy)")
        pin, problems = libpq_pin(GATES_DOCKERFILE)
        self.assertEqual(problems, [], "gates.Dockerfile has no usable LIBPQ_VERSION pin")
        assert pin is not None
        want = pq_number(pin)
        self.assertEqual(psycopg.pq.version(), want, f"libpq version() is not the pin {pin} ({want})")
        self.assertEqual(psycopg.pq.__build_version__, want,
                         f"psycopg-c was built against libpq {psycopg.pq.__build_version__}, not the pin {pin}")
        maps = Path("/proc/self/maps").read_text(encoding="utf-8").splitlines()
        libpq = sorted({line.split()[-1] for line in maps if "libpq" in line.split()[-1]})
        self.assertTrue(libpq, "no libpq is mapped into the process after importing psycopg-c")
        for path in libpq:
            self.assertRegex(path, r"^(?:/usr)?/lib/(?:x86_64|aarch64)-linux-gnu/libpq\.so\.5(?:\.\d+)*$",
                             f"the loaded libpq {path} is not Debian's libpq5")


# ---- 7 ----------------------------------------------------------------------

def _exec_service(argv: list[str]) -> tuple[str | None, list[str]]:
    i = argv.index("exec") + 1
    while i < len(argv):
        if argv[i] in ("-e", "--env", "-u", "--user", "-w", "--workdir", "--index"):
            i += 2
            continue
        if argv[i].startswith("-"):
            i += 1
            continue
        return argv[i], argv[i + 1:]
    return None, []


class SmokePsycopgTest(unittest.TestCase):
    """PSC-25 *C implementation, system libpq*: the smoke host half checks,
    in the live api, the impl, the libpq versions and the libpq path. Driven
    with the fake docker (tests/fake_docker.py "platform-sbom U0"); the real
    run is the `full` smoke stage."""

    _smoke = tss.SmokeBackendIsolatedTest._smoke

    def setUp(self) -> None:
        tss.SmokeResolvesWithoutEnvTest.setUp(self)  # type: ignore[arg-type]
        for rel in ("docker/app.Dockerfile", "docker/gates.Dockerfile"):
            dest = self.tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)

    @staticmethod
    def _calls(records: list[dict]) -> tuple[list[tuple[int, str | None, list[str]]], list[int]]:
        execs = []
        readies = []
        for n, r in enumerate(records):
            argv = r["argv"]
            if argv[:1] == ["compose"] and "exec" in argv:
                svc, cmd = _exec_service(argv)
                execs.append((n, svc, cmd))
                if "engine.readiness" in argv and tss.READY_RX.search(" ".join(argv)):
                    readies.append(n)
        return execs, readies

    def test_smoke_checks_psycopg_c_impl_in_api(self):
        pin = fake_docker._libpq_pin()
        num = pq_number(pin)
        passing = {
            "default: psycopg-c on /lib/x86_64-linux-gnu/libpq.so.5": {},
            "libpq under /usr/lib/x86_64-linux-gnu": {"FAKE_LDD_LIBPQ": "/usr/lib/x86_64-linux-gnu/libpq.so.5"},
            "aarch64, /lib alias": {"FAKE_PQ_TRIPLET": "aarch64-linux-gnu"},
            "aarch64, /usr/lib": {"FAKE_PQ_TRIPLET": "aarch64-linux-gnu",
                                  "FAKE_LDD_LIBPQ": "/usr/lib/aarch64-linux-gnu/libpq.so.5"},
        }
        for case, extra in passing.items():
            with self.subTest(case=case):
                result, records = self._smoke(**extra)
                out = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, out)
                self.assertIn("smoke: PASS", out)
                execs, readies = self._calls(records)
                pythons = [(n, svc, cmd) for n, svc, cmd in execs
                           if cmd and os.path.basename(cmd[0]) in ("python", "python3") and "-c" in cmd
                           and "psycopg" in " ".join(cmd)]
                self.assertTrue(pythons, "smoke never runs `compose exec -T api python -c ...` reading psycopg "
                                         f"(PSC-25 smoke check): {[c for _, _, c in execs]}")
                self.assertEqual({svc for _, svc, _ in pythons}, {"api"}, "the psycopg check runs in api")
                self.assertTrue(all("-T" in records[n]["argv"] for n, _, _ in pythons), "exec -T (no tty)")
                code = " ".join(c for _, _, cmd in pythons for c in cmd)
                for attr in ("__impl__", "version", "__build_version__"):
                    self.assertIn(attr, code, f"the psycopg check does not read pq.{attr}")
                ldds = [(n, svc, cmd) for n, svc, cmd in execs if cmd and os.path.basename(cmd[0]) == "ldd"]
                self.assertTrue(ldds, "smoke never runs `compose exec -T api ldd <extension>`")
                self.assertEqual({svc for _, svc, _ in ldds}, {"api"}, "ldd runs in api")
                self.assertTrue([cmd for _, _, cmd in ldds if any("psycopg_c" in a for a in cmd[1:])],
                                f"ldd does not read the psycopg_c extension: {[c for _, _, c in ldds]}")
                self.assertTrue(readies and readies[0] < min(n for n, _, _ in pythons),
                                "the psycopg check runs once /readyz is ready (the api is up)")
        failing = {
            "impl binary": ({"FAKE_PQ_IMPL": "binary"}, None),
            "impl python": ({"FAKE_PQ_IMPL": "python"}, None),
            "version() != __build_version__": ({"FAKE_PQ_BUILD_VERSION": str(num + 1)}, str(num + 1)),
            "both != the pin": ({"FAKE_PQ_VERSION": str(num - 1)}, str(num - 1)),
            "libpq from psycopg_binary.libs": ({"FAKE_LDD_LIBPQ": "/opt/venv/lib/python3.12/site-packages/"
                                                                  "psycopg_binary.libs/libpq-9f3e2a1b.so.5.18"}, None),
            "libpq from /usr/local/lib": ({"FAKE_LDD_LIBPQ": "/usr/local/lib/libpq.so.5"}, None),
            "libpq not found": ({"FAKE_LDD_LIBPQ": "not found"}, None),
            "ldd mentions psycopg_binary": ({"FAKE_LDD_EXTRA": "\tlibkrb5-fb231cca.so.3.3 => /opt/venv/lib/"
                                                               "python3.12/site-packages/psycopg_binary.libs/"
                                                               "libkrb5-fb231cca.so.3.3 (0x00007f3a1b000000)"}, None),
            "the python check fails in api": ({"FAKE_DOCKER_HOOKS": json.dumps(
                [{"on": r"\bexec\b.*\bpython3?\b.* -c ", "exit": 1}])}, None),
            "ldd fails in api": ({"FAKE_DOCKER_HOOKS": json.dumps([{"on": r"\bexec\b.*\bldd\b", "exit": 1}])}, None),
        }
        for case, (extra, named) in failing.items():
            with self.subTest(case=case):
                result, records = self._smoke(**extra)
                out = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, f"smoke passed with {case}:\n{out}")
                self.assertNotIn("smoke: PASS", out)
                fails = [l for l in out.splitlines() if re.search(r"(?i)\bfail", l)
                         and re.search(r"(?i)psycopg|libpq", l)]
                self.assertTrue(fails, f"the failure must say FAIL and name psycopg or libpq ({case}):\n{out}")
                if named:
                    self.assertTrue([l for l in fails if named in l], f"the failure must name {named}:\n{out}")
                steps = tss._smoke_steps(records)
                self.assertEqual(steps[-1:], ["teardown"], f"smoke launched it, so it tears down: {steps}")

    # ---- U0 rework round 1 (review B1, N3; security M-1) ---------------------
    # Tester, 2026-10-23. Fake knobs: tests/fake_docker.py "platform-sbom U0"
    # (FAKE_PQ_VENV_EXTRA, FAKE_LIBPQ_REALPATH, FAKE_LIBPQ_OWNER,
    # FAKE_LIBPQ5_VERSION set but empty, FAKE_LIBPQ5_ABSENT, `find`).

    BASH_ERROR = re.compile(r"(?m)smoke\.sh: line \d+: ")

    def _assert_passes(self, case: str, extra: dict[str, str]) -> list[dict]:
        result, records = self._smoke(**extra)
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, f"smoke failed with {case}:\n{out}")
        self.assertIn("smoke: PASS", out)
        return records

    def _assert_fails(self, case: str, extra: dict[str, str], named: str | None = None) -> str:
        """smoke fails closed: non-zero, no PASS, a named `smoke: FAIL` line
        about psycopg or libpq (never a bare bash error), then teardown."""
        result, records = self._smoke(**extra)
        out = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, f"smoke passed with {case}:\n{out}")
        self.assertNotIn("smoke: PASS", out)
        self.assertIsNone(self.BASH_ERROR.search(out),
                          f"smoke stopped on a bash error, not a named FAIL ({case}):\n{out}")
        fails = [l for l in out.splitlines() if "smoke: FAIL" in l and re.search(r"(?i)psycopg|libpq", l)]
        self.assertTrue(fails, f"the failure must be a `smoke: FAIL` line naming psycopg or libpq ({case}):\n{out}")
        if named is not None:
            self.assertTrue([l for l in fails if named in l], f"the failure must name {named!r} ({case}):\n{out}")
        steps = tss._smoke_steps(records)
        self.assertEqual(steps[-1:], ["teardown"], f"smoke launched it, so it tears down: {steps}")
        return out

    def test_smoke_fails_when_psycopg_binary_is_beside_psycopg_c(self):
        # Review B1.2; PSC-25 (no psycopg_binary* in the image) and PSC-14
        # (PSC-25's full check proves the directory is absent). psycopg loads
        # `c` before `binary`, so with both installed impl stays `c` and the
        # psycopg_c ldd stays clean: only a look at the venv catches it. One
        # case per entry a psycopg-binary wheel installs, since find_spec sees
        # only the package dir; `.libs` and `.dist-info` need a directory scan.
        passing = {
            "control: psycopg and psycopg_c dist-info only": "psycopg-3.3.6.dist-info,psycopg_c-3.3.6.dist-info",
        }
        for case, entries in passing.items():
            with self.subTest(case=case):
                self._assert_passes(case, {"FAKE_PQ_VENV_EXTRA": entries})
        failing = {
            "psycopg_binary package dir": "psycopg_binary",
            "psycopg_binary.libs dir": "psycopg_binary.libs",
            "psycopg_binary-3.3.6.dist-info": "psycopg_binary-3.3.6.dist-info",
            "a whole psycopg-binary wheel": "psycopg_binary,psycopg_binary.libs,psycopg_binary-3.3.6.dist-info",
        }
        for case, entries in failing.items():
            with self.subTest(case=case):
                self._assert_fails(case, {"FAKE_PQ_VENV_EXTRA": entries}, named="psycopg_binary")

    def test_smoke_checks_dpkg_libpq5_owns_the_loaded_libpq(self):
        # Review B1.1; PSC-25 *C implementation, system libpq*: the libpq.so.5
        # the extension loads is a file the dpkg package libpq5 owns. Smoke
        # resolves the ldd path (the /lib alias is not dpkg's) and asks dpkg.
        passing = {
            "realpath /usr/lib/x86_64-linux-gnu/libpq.so.5.15, owner libpq5:amd64": (
                {"FAKE_LIBPQ_REALPATH": "/usr/lib/x86_64-linux-gnu/libpq.so.5.15"},
                "/usr/lib/x86_64-linux-gnu/libpq.so.5.15"),
            "aarch64: realpath /usr/lib/aarch64-linux-gnu/libpq.so.5.15, owner libpq5:arm64": (
                {"FAKE_PQ_TRIPLET": "aarch64-linux-gnu"}, "/usr/lib/aarch64-linux-gnu/libpq.so.5.15"),
        }
        for case, (extra, real) in passing.items():
            with self.subTest(case=case):
                records = self._assert_passes(case, extra)
                execs, _ = self._calls(records)
                searches = [(svc, cmd) for _, svc, cmd in execs
                            if cmd and os.path.basename(cmd[0]) in ("dpkg", "dpkg-query")
                            and ("-S" in cmd or "--search" in cmd)]
                self.assertTrue([c for s, c in searches if s == "api" and real in c],
                                f"smoke never asks dpkg in api who owns {real} (dpkg-query -S): "
                                f"{[c for _, _, c in execs]}")
        vendored = "/opt/venv/lib/python3.12/site-packages/psycopg_c.libs/libpq-0a1b2c3d.so.5.15"
        owned = "/usr/lib/x86_64-linux-gnu/libpq.so.5.15"
        failing = {
            "realpath is an unowned vendored copy": ({"FAKE_LIBPQ_REALPATH": vendored}, "libpq-0a1b2c3d"),
            "the Debian path, but dpkg owns no such file": ({"FAKE_LIBPQ_OWNER": ""}, None),
            "owned by libpq-dev, not libpq5": ({"FAKE_LIBPQ_OWNER": "libpq-dev:amd64"}, None),
            "owned by libpq5-fork (libpq5 is only a prefix)": ({"FAKE_LIBPQ_OWNER": "libpq5-fork:amd64"}, None),
            # Review N7: with no owner for the resolved path this case fails
            # at the ldd regex or, without the end anchor, at dpkg-query -S;
            # it pins fail-closed, not the anchor (the next two pin R2/R6).
            "ldd path libpq.so.5-evil, realpath unowned (ldd regex or dpkg -S)": (
                {"FAKE_LDD_LIBPQ": "/lib/x86_64-linux-gnu/libpq.so.5-evil"}, None),
            # Review N7 / mutant R2: only the libpq regex's end anchor stops
            # this; realpath gives the libpq5-owned file, so dpkg -S passes.
            "end anchor: ldd libpq.so.5.evil, realpath to the libpq5-owned file": (
                {"FAKE_LDD_LIBPQ": "/lib/x86_64-linux-gnu/libpq.so.5.evil",
                 "FAKE_DOCKER_HOOKS": json.dumps([{"on": r"\bexec\b.*\brealpath\b",
                                                   "stdout": owned + "\n", "exit": 0}])},
                "loads '/lib/x86_64-linux-gnu/libpq.so.5.evil', not Debian's libpq5"),
            # Review N7 / mutant R6: realpath -e exits non-zero but prints the
            # libpq5-owned file, so only the `realpath || { FAIL }` branch stops it.
            "realpath -e fails in api (its output is the libpq5-owned file)": (
                {"FAKE_DOCKER_HOOKS": json.dumps([{"on": r"\bexec\b.*\brealpath\b",
                                                   "stdout": owned + "\n", "exit": 1}])},
                "realpath /lib/x86_64-linux-gnu/libpq.so.5 failed in api"),
        }
        for case, (extra, named) in failing.items():
            with self.subTest(case=case):
                self._assert_fails(case, extra, named)

    def test_smoke_never_evaluates_the_libpq5_version(self):
        # Security M-1: the dpkg-query version is container output; smoke
        # validates it before any arithmetic and fails closed naming it.
        # Bash evaluates array subscripts in $(( )), so `0+PPID[$(cmd)]` would
        # run cmd on the host. Review N3: a value the sed match misses fails
        # with a named FAIL, not a bash arithmetic error.
        for name, template in {"PPID subscript": "0+PPID[$(touch {m})]",
                               "BASH_VERSINFO subscript": "0+BASH_VERSINFO[$(touch {m})]"}.items():
            with self.subTest(case=f"injection via {name}"):
                marker = self.tmp / f"m1-marker-{name.split()[0].lower()}"
                value = template.format(m=marker.as_posix())
                self.assertFalse(marker.exists(), "precondition")
                self._assert_fails(name, {"FAKE_LIBPQ5_VERSION": value}, named=value)
                self.assertFalse(marker.exists(),
                                 f"smoke ran a command from the libpq5 version on the host: {marker} exists")
        with self.subTest(case="non-numeric version x.y"):
            self._assert_fails("x.y", {"FAKE_LIBPQ5_VERSION": "x.y"}, named="x.y")

    def test_smoke_fails_closed_on_dpkg_query_errors(self):
        # Review N3: the `dpkg-query ... || { FAIL }` branch, and an empty
        # version (a named FAIL, not a bash arithmetic error).
        with self.subTest(case="dpkg-query exits non-zero in api"):
            out = self._assert_fails("dpkg-query fails", {"FAKE_LIBPQ5_ABSENT": "1"})
            self.assertIn("dpkg-query: no packages found matching libpq5", out,
                          "the failure shows dpkg-query's own message")
        with self.subTest(case="empty libpq5 version"):
            self._assert_fails("empty version", {"FAKE_LIBPQ5_VERSION": ""}, named="libpq5")


if __name__ == "__main__":
    unittest.main()
