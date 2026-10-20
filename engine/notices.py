"""Third-party package licence notices (PS-3.8, architecture §2.5 Licence notices).

    python -m engine.notices

Run by `scripts/bundle.sh` inside the `ke-app` image being bundled, so it lists
what the image really holds. Standard library only, and it reads nothing but
the installed distributions' metadata: no arguments, no network, no files
outside the interpreter's own `sys.path`.

stdout is a Markdown table, one row per installed distribution except the
project's own (`knowledge-engine`):

    | Package | Version | Licence | Licence files |

The licence is `License-Expression`, else `License`, else the licence
classifiers. The licence files are the paths, relative to site-packages and
including the `<name>-<version>.dist-info/` directory, that the distribution
installed and that exist: its RECORD entries under `<dist-info>/licenses/` or
named `LICEN[CS]E*`, `COPYING*` or `NOTICE*` in the `<dist-info>/` directory,
plus every `License-File` header it declares.

A distribution with no licence file in the image fails the run: stderr names
it, stdout stays empty and the exit code is 1. This is the mechanism behind
"the image keeps psycopg's LGPL text" (R7), and it applies to every package.

It is a build-time command line tool, not an agent step, so it opens no span.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Sequence
from importlib import metadata
from pathlib import Path, PurePosixPath

PROJECT = "knowledge-engine"
HEADER = ("Package", "Version", "Licence", "Licence files")
_NAMED_LICENCE_FILE = re.compile(r"(?i)^(?:LICEN[CS]E|COPYING|NOTICE)")
_MAX_LICENCE_CHARS = 100


def normalise(name: str) -> str:
    """The PEP 503 form of a distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _cell(value: str) -> str:
    """A table cell: one line, with no pipe to end the cell early."""
    return " ".join(value.replace("|", "/").split())


def _licence(dist: metadata.Distribution) -> str:
    """License-Expression, else License, else the licence classifiers."""
    meta = dist.metadata
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression
    field = (meta.get("License") or "").strip()
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::") and c.split("::")[-1].strip() != "OSI Approved"
    ]
    # Older packages put the whole licence text in `License`; a long or
    # multi-line value is no label, so the classifiers win when there are any.
    if field and "\n" not in field and len(field) <= _MAX_LICENCE_CHARS:
        return field
    if classifiers:
        return "; ".join(classifiers)
    if field:
        return field.splitlines()[0][:_MAX_LICENCE_CHARS]
    return "not declared (see the licence files)"


def _dist_info(files: Iterable[metadata.PackagePath]) -> PurePosixPath | None:
    """The `<name>-<version>.dist-info` directory: the parent of METADATA."""
    for f in files:
        path = PurePosixPath(f.as_posix())
        if path.name == "METADATA" and path.parent.name.endswith(".dist-info"):
            return path.parent
    return None


def _header_candidates(dist: metadata.Distribution, info: PurePosixPath) -> list[PurePosixPath]:
    out: list[PurePosixPath] = []
    for declared in dist.metadata.get_all("License-File") or []:
        rel = PurePosixPath(declared.strip())
        if not rel.parts or rel.is_absolute() or ".." in rel.parts:
            continue  # a declared name is never a path out of the dist-info
        out += [info / "licenses" / rel, info / rel]
    return out


def licence_files(dist: metadata.Distribution) -> list[str]:
    """The licence files `dist` installed that exist, sorted, site-relative."""
    files = list(dist.files or [])
    info = _dist_info(files)
    if info is None:
        return []
    found: set[str] = set()
    candidates = _header_candidates(dist, info)
    for f in files:
        path = PurePosixPath(f.as_posix())
        under_licenses = path.is_relative_to(info / "licenses")
        named = path.parent == info and bool(_NAMED_LICENCE_FILE.match(path.name))
        if under_licenses or named:
            candidates.append(path)
    for path in candidates:
        if Path(str(dist.locate_file(path.as_posix()))).is_file():
            found.add(path.as_posix())
    return sorted(found)


def rows(dists: Iterable[metadata.Distribution]) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """(table rows, names of the distributions with no licence file), by name."""
    seen: set[str] = set()
    table: list[tuple[str, str, str, str]] = []
    missing: list[str] = []
    for dist in dists:
        name = (dist.metadata.get("Name") or "").strip()
        key = normalise(name)
        if not name or key == PROJECT or key in seen:
            continue  # the first one on sys.path is the one Python imports
        seen.add(key)
        files = licence_files(dist)
        if not files:
            missing.append(name)
        table.append((name, dist.version, _licence(dist), ", ".join(files)))
    table.sort(key=lambda r: normalise(r[0]))
    return table, sorted(missing, key=normalise)


def render(table: Sequence[tuple[str, str, str, str]]) -> str:
    lines = ["| " + " | ".join(HEADER) + " |", "|" + "|".join("---" for _ in HEADER) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in table]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        sys.stderr.write("usage: python -m engine.notices (no arguments)\n")
        return 2
    table, missing = rows(metadata.distributions())
    if missing:
        sys.stderr.write(
            "notices: no licence file in the image for: " + ", ".join(missing)
            + " (every installed package must keep its licence text)\n"
        )
        return 1
    sys.stdout.write(render(table))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through bundle.sh
    sys.exit(main())
