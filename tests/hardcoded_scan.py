"""The no-hardcoded scanner (PS-1.2): a pure function, contract in the
docstring of tests/test_engine_hardcoded.py."""

from __future__ import annotations

import re
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


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    value: str


def _allowed(path: str) -> bool:
    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)


def _is_compose(path: str) -> bool:
    return bool(re.fullmatch(r"(?:.*/)?docker-compose[^/]*\.ya?ml", path))


def _token(value: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w.-]){re.escape(value)}(?![\w-]|\.\w)")


def find_hardcoded(
    files: Mapping[str, str],
    declared_values: Iterable[str],
    exemptions: Iterable[tuple[str, str, str]],
) -> list[Finding]:
    """Declared values as whole tokens (rule 1) and, in Python, URL literals
    and integer ports (rule 2). Exempt lines assign an exempt symbol."""
    patterns = [(v, _token(v)) for v in dict.fromkeys(str(v) for v in declared_values) if v]
    exempt = [(path, re.compile(rf"^\s*{re.escape(symbol)}\b")) for path, symbol, _ in exemptions]
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
    return findings
