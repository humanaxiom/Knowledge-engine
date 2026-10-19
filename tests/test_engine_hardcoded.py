"""platform-config PS-1.2: no hardcoded hosts, ports or model names.

The scanner is a pure function in `tests/hardcoded_scan.py` (§2.3,
"No-hardcoded scan"); the developer writes it against the contract the
fixture tests below pin down:

    find_hardcoded(files, declared_values, exemptions) -> list[Finding]

- `files`: mapping of repo-relative POSIX path -> file text;
- `declared_values`: iterable of literal strings (ports, hosts, model names);
- `exemptions`: iterable of `(path, symbol, reason)`; the line assigning
  `symbol` in `path` is not flagged;
- each Finding has `.path`, `.line` (1-based) and `.value`.

Rule 1: a declared value appearing as a whole token in a scanned file is a
finding, except compose `${VAR:-value}` defaults. Rule 2 (Python only): any
`scheme://host[:port]` string literal, and any integer assigned to a name
containing `port`, is a finding. Files under `config/defaults.yaml`,
`.env.example`, `config/verify.env`, `tests/` and `docs/` are never flagged.

The repository tests then run the scanner over engine/, harness_telemetry/,
scripts/, docker/, docker-compose*.yml and .github/ with the declared values
of config/defaults.yaml and .env.example, plus the model host name.
"""

from __future__ import annotations

import re
import unittest
from typing import Any
from urllib.parse import urlsplit

from tests.engine_support import DEFAULTS, ENV_EXAMPLE, ROOT, read_env_example

# The single recorded exemption (ADR-KE-010; architecture §2.3,
# "harness_telemetry default collector"). harness_telemetry is a standalone
# template package with no config system and log_event runs on the host, so
# its default collector stays a literal, pinned to .env.example by
# test_harness_default_collector_matches_env_example (platform-stack, PS-2.2).
EXEMPTIONS = [(
    "harness_telemetry/tracing.py",
    "DEFAULT_COLLECTOR",
    "standalone template package with no config system; drift-tested against "
    ".env.example by test_harness_default_collector_matches_env_example",
)]

# Human ruling Q7: the model host's name is a host name under PS-1.2 even
# though config/defaults.yaml ships no default for it (Q32).
MODEL_HOST_NAME = "aria-gb10-2"

LOOPBACK = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

SCANNED_DIRS = ("engine", "harness_telemetry", "scripts", "docker", ".github")
TEXT_SUFFIXES = {".py", ".sh", ".ps1", ".yml", ".yaml", ".toml", ".cfg", ".ini",
                 ".json", ".txt", ".env", ""}


def _scan(files: dict[str, str], declared: list[str], exemptions: Any = ()) -> list[Any]:
    from tests.hardcoded_scan import find_hardcoded

    return list(find_hardcoded(files, declared, list(exemptions)))


def _values(findings: list[Any]) -> set[str]:
    return {str(f.value) for f in findings}


class ScannerContractTest(unittest.TestCase):
    """The scanner on fixtures first (architecture §2.6, step 7)."""

    def test_planted_port_literal_is_flagged(self):  # DR38 mutation
        files = {"engine/stores.py": 'def connect():\n    return open_db("postgres", 5432)\n'}
        findings = _scan(files, ["5432"])
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual((findings[0].path, findings[0].line, str(findings[0].value)),
                         ("engine/stores.py", 2, "5432"))

    def test_port_token_boundaries(self):
        files = {"scripts/x.sh": "echo 154321 54320 v5432x\n"}
        self.assertEqual(_scan(files, ["5432"]), [])

    def test_planted_model_name_is_flagged(self):
        files = {"scripts/pull.sh": "ollama pull qwen2.5:14b-instruct\n"}
        self.assertIn("qwen2.5:14b-instruct", _values(_scan(files, ["qwen2.5:14b-instruct"])))

    def test_planted_host_name_is_flagged(self):
        files = {"docker-compose.yml": f"    extra_hosts: ['{MODEL_HOST_NAME}:10.0.0.9']\n"}
        self.assertIn(MODEL_HOST_NAME, _values(_scan(files, [MODEL_HOST_NAME])))

    def test_compose_variable_default_is_allowed(self):
        files = {"docker-compose.yml": 'ports:\n  - "${KE_PG_PORT:-5432}:5432"\n'}
        findings = _scan(files, ["5432"])
        # The default inside ${...:-...} is allowed; the bare container side is not.
        self.assertEqual([f.line for f in findings], [2])
        self.assertEqual(len(findings), 1)
        files = {"docker-compose.yml": 'ports:\n  - "${KE_PG_PORT:-5432}:${PG_INNER:-5432}"\n'}
        self.assertEqual(_scan(files, ["5432"]), [])

    def test_shell_parameter_default_is_flagged_outside_compose(self):
        # Review B4: only compose `${VAR:-default}` defaults are declared
        # values (ruling B7a). The same syntax in a script hides a literal.
        for path, line in (("scripts/x.sh", "PORT=${PG_PORT:-5432}\n"),
                           ("scripts/x.sh", 'psql -p "${PG_PORT:-5432}"\n'),
                           ("docker/entry.sh", "exec app --port ${PORT-5432}\n"),
                           (".github/workflows/ci.yml", "  PG: ${PG_PORT:-5432}\n"),
                           ("engine/x.py", 'PORT = os.path.expandvars("${PG_PORT:-5432}")\n')):
            with self.subTest(path=path, line=line):
                self.assertIn("5432", _values(_scan({path: line}, ["5432"])))
        # A compose file's own default stays declared, override files included.
        for path in ("docker-compose.yml", "docker-compose.override.yml"):
            with self.subTest(path=path):
                self.assertEqual(_scan({path: '  - "${KE_PG_PORT:-5432}:${PG:-5432}"\n'},
                                       ["5432"]), [])

    def test_url_literal_in_python_is_flagged_even_if_undeclared(self):
        files = {"engine/x.py": 'BASE = "http://somewhere.example:9000/v1"\n'}
        self.assertEqual(len(_scan(files, [])), 1)

    def test_integer_port_assignment_in_python_is_flagged(self):
        for source in ("port = 1234\n", "listen_port: int = 8081\n", "DB_PORT=15432\n",
                       "connect(port=2345)\n"):
            with self.subTest(source=source):
                self.assertEqual(len(_scan({"engine/x.py": source}, [])), 1)

    def test_rule_two_is_python_only(self):
        files = {"scripts/x.sh": "port=1234\n"}
        self.assertEqual(_scan(files, []), [])

    def test_exemption_covers_only_its_symbol_and_path(self):
        line = 'DEFAULT_COLLECTOR = "http://localhost:47101"\n'
        self.assertEqual(_scan({"harness_telemetry/tracing.py": line}, ["47101"], EXEMPTIONS), [])
        self.assertTrue(_scan({"engine/tracing.py": line}, ["47101"], EXEMPTIONS))
        other = 'OTHER = "http://localhost:47101"\n'
        self.assertTrue(_scan({"harness_telemetry/tracing.py": other}, ["47101"], EXEMPTIONS))

    def test_allowed_locations_are_never_flagged(self):
        for path in ("config/defaults.yaml", ".env.example", "config/verify.env",
                     "tests/test_x.py", "docs/architecture.md"):
            with self.subTest(path=path):
                files = {path: 'port = 5432\nURL = "http://aria-gb10-2:8000"\n'}
                self.assertEqual(_scan(files, ["5432", MODEL_HOST_NAME]), [])


def _collect_repo_files() -> dict[str, str]:
    paths = [p for d in SCANNED_DIRS if (ROOT / d).is_dir() for p in (ROOT / d).rglob("*")]
    paths += list(ROOT.glob("docker-compose*.yml"))
    files: dict[str, str] = {}
    for path in paths:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix not in TEXT_SUFFIXES and not path.name.endswith("Dockerfile"):
            continue
        try:
            files[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return files


def _declared() -> tuple[set[str], set[str]]:
    """(ports, hosts and model names) declared in defaults.yaml and .env.example."""
    import yaml

    data = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    service_names = set(data.get("stack", {}).get("service_names", []))
    ports: set[str] = set()
    names: set[str] = {MODEL_HOST_NAME}

    def add_url(value: str) -> None:
        parts = urlsplit(value if "://" in value else f"//{value}")
        if parts.port:
            ports.add(str(parts.port))
        if parts.hostname:
            names.add(parts.hostname)

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k).lower())
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif node is None or isinstance(node, bool):
            return
        elif "port" in key and isinstance(node, int):
            ports.add(str(node))
        elif key in {"model", "fallback_model"} or key.endswith("_model"):
            names.add(str(node))
        elif key == "host" or key.endswith("_host"):
            names.add(str(node))
        elif isinstance(node, str) and ("url" in key or "endpoint" in key or "upstream" in key):
            add_url(node)

    walk(data)
    for key, value in read_env_example().items():
        upper = key.upper()
        if not value or value.startswith("changeme"):
            continue
        if "PORT" in upper and value.isdigit():
            ports.add(value)
        elif "MODEL" in upper and "UPSTREAM" not in upper and "URL" not in upper:
            names.add(value)
        elif "HOST" in upper:
            names.add(value)
        elif any(t in upper for t in ("URL", "ENDPOINT", "UPSTREAM")):
            add_url(value)
    # Compose service names are the stack's identities, not hardcoded hosts;
    # loopback is not a deployment host (any loopback URL literal in Python
    # is still caught by rule 2).
    names -= service_names | LOOPBACK
    return ports, names


class RepositoryScanTest(unittest.TestCase):
    def _report(self, findings: list[Any]) -> str:
        return "\n".join(f"{f.path}:{f.line}: {f.value}" for f in findings)

    def test_declared_value_files_exist(self):
        self.assertTrue(DEFAULTS.is_file(), "config/defaults.yaml is missing")
        self.assertTrue(ENV_EXAMPLE.is_file(), ".env.example is missing")

    def test_no_hardcoded_ports(self):
        ports, _ = _declared()
        self.assertTrue(ports, "no ports declared in defaults.yaml/.env.example")
        findings = _scan(_collect_repo_files(), sorted(ports), EXEMPTIONS)
        self.assertEqual(findings, [], "hardcoded ports:\n" + self._report(findings))

    def test_no_hardcoded_hosts_or_models(self):
        _, names = _declared()
        for model in ("qwen2.5:14b-instruct", "llama3.1:8b", "nomic-embed-text"):
            self.assertIn(model, names, f"{model} is not declared in config")
        self.assertIn(MODEL_HOST_NAME, names)
        findings = _scan(_collect_repo_files(), sorted(names), EXEMPTIONS)
        self.assertEqual(findings, [], "hardcoded hosts or models:\n" + self._report(findings))

    def test_model_host_name_only_in_allowed_locations(self):
        offenders = [path for path, text in _collect_repo_files().items()
                     if re.search(re.escape(MODEL_HOST_NAME), text)]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
