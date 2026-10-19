"""The no-hardcoded scanner (PS-1.2): a pure function, contract in the
docstring of tests/test_engine_hardcoded.py."""

from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

ALLOWED_PREFIXES = ("tests/", "docs/")
ALLOWED_FILES = {"config/defaults.yaml", ".env.example", "config/verify.env"}

# `${VAR:-default}` defaults declared in compose files are allowed, so they are
# blanked before rule 1; the same syntax elsewhere hides a literal (review B4).
_COMPOSE_DEFAULT = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-([^}]*)\}")
# scheme://host[:port] where the host is written out (not a {placeholder}).
_URL_LITERAL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://(?:\[[0-9A-Fa-f:]+\]|[A-Za-z0-9])[^\s\"'`)>,]*")
# Integer assigned to a name containing "port": `port = 1`, `p_port: int = 1`, `port=1`.
_PORT_ASSIGN = re.compile(r"\b\w*port\w*\s*(?::\s*[\w\[\], .|]+?)?\s*=(?!=)\s*\d+\b", re.I)
# Review N3: a "port" dict key or subscript with an integer, and a
# (host, port) tuple with a four- or five-digit port.
_PORT_KEY = re.compile(r"""["']\w*port\w*["']\s*(?::|\]\s*=(?!=))\s*\d+\b""", re.I)
_ADDR_TUPLE = re.compile(r"""\(\s*["'][^"']*["']\s*,\s*\d{4,5}\s*\)""")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    value: str


def _allowed(path: str) -> bool:
    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)


def _is_compose(path: str) -> bool:
    return bool(re.fullmatch(r"(?:.*/)?(?:docker-)?compose[^/]*\.ya?ml", path))


# PS-1.2 scope: these roots, and a compose file of any name at the root.
_SCOPE_ROOTS = ("engine/", "harness_telemetry/", "scripts/", "docker/", ".github/")


def in_scope(path: str) -> bool:
    return path.startswith(_SCOPE_ROOTS) or (
        "/" not in path and _is_compose(path))


def collect_files(root: Path, paths: Iterable[str]) -> Mapping[str, str]:
    """Text of every path in the PS-1.2 scope, whatever its suffix (review N2).
    A scoped path that is not UTF-8 text raises ValueError naming it."""
    files: dict[str, str] = {}
    for rel in paths:
        if not in_scope(rel):
            continue
        try:
            files[rel] = (root / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{rel}: not UTF-8 text, cannot be scanned ({exc.reason})") from exc
    return files


def _token(value: str) -> re.Pattern[str]:
    # Case-insensitive: DNS names are (review N1).
    return re.compile(rf"(?<![\w.-]){re.escape(value)}(?![\w-]|\.\w)", re.I)


def find_hardcoded(
    files: Mapping[str, str],
    declared_values: Iterable[str],
    exemptions: Iterable[tuple[str, str, str]],
) -> list[Finding]:
    """Declared values as whole tokens (rule 1) and, in Python, URL literals
    and integer ports (rule 2). Exempt lines assign an exempt symbol."""
    patterns = [(v, _token(v)) for v in dict.fromkeys(str(v) for v in declared_values) if v]
    # Review N4: only the line that assigns the symbol (not ==, +=, a call).
    exempt = [(path, re.compile(rf"^\s*{re.escape(symbol)}\s*(?::[^=]*)?=(?!=)"))
              for path, symbol, _ in exemptions]
    findings: list[Finding] = []
    for path, text in files.items():
        if _allowed(path):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if any(path == p and rx.match(line) for p, rx in exempt):
                continue
            # Compose: blank the whole default. Elsewhere: expose the default
            # as a bare token so it is found.
            scrubbed = _COMPOSE_DEFAULT.sub(
                (lambda m: " " * len(m.group(0))) if _is_compose(path)
                else (lambda m: " " + m.group(1) + " "), line)
            for value, pattern in patterns:
                if pattern.search(scrubbed):
                    findings.append(Finding(path, number, value))
            if path.endswith(".py"):
                for match in _URL_LITERAL.finditer(line):
                    findings.append(Finding(path, number, match.group(0)))
                for match in _PORT_ASSIGN.finditer(line):
                    findings.append(Finding(path, number, match.group(0)))
                # N3 shapes: one finding per line, and none when rule 1 or the
                # shapes above already flagged that line.
                if not any(f.path == path and f.line == number for f in findings):
                    for pattern in (_PORT_KEY, _ADDR_TUPLE):
                        for match in pattern.finditer(line):
                            findings.append(Finding(path, number, match.group(0)))
    return findings
