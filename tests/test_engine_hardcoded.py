"""platform-config PS-1.2: no hardcoded hosts, ports or model names.

The scanner is a pure function in `tests/hardcoded_scan.py` (§2.3,
"No-hardcoded scan"); the developer writes it against the contract the
fixture tests below pin down:

    find_hardcoded(files, declared_values, exemptions) -> list[Finding]

- `files`: mapping of repo-relative POSIX path -> file text;
- `declared_values`: iterable of literal strings (ports, hosts, model names);
- `exemptions`: iterable of `(path, symbol, reason)`; the line assigning
  `symbol` in `path` is not flagged (in a Dockerfile, which has no
  assignment for an instruction, `symbol` is one whole instruction line,
  matched exactly; platform-sbom U4b);
- each Finding has `.path`, `.line` (1-based) and `.value`.

Rule 1: a declared value appearing as a whole token in a scanned file is a
finding, except compose `${VAR:-value}` defaults. Rule 2 (Python only): any
`scheme://host[:port]` string literal, and any integer assigned to a name
containing `port`, is a finding. Files under `config/defaults.yaml`,
`.env.example`, `config/verify.env`, `tests/` and `docs/` are never flagged.

The repository tests then run the scanner (via collect_files) over engine/, harness_telemetry/,
scripts/, docker/, docker-compose*.yml and .github/ with the declared values
of config/defaults.yaml and .env.example, plus the model host name.
"""

from __future__ import annotations

import re
import unittest
from typing import Any
from urllib.parse import urlsplit

from tests.engine_support import DEFAULTS, ENV_EXAMPLE, ROOT, read_env_example

# The recorded exemptions. First (ADR-KE-010; architecture §2.3,
# "harness_telemetry default collector"): harness_telemetry is a standalone
# template package with no config system and log_event runs on the host, so
# its default collector stays a literal, pinned to .env.example by
# test_harness_default_collector_matches_env_example (platform-stack, PS-2.2).
# Second (platform-sbom U4b, PSC-26, design-notes N16; orchestrator U4b
# ruling 1): ke-neo4j is FROM scratch, so it declares again the official
# image's ExposedPorts; 7687 is also config/defaults.yaml's neo4j port.
EXEMPTIONS = [(
    "harness_telemetry/tracing.py",
    "DEFAULT_COLLECTOR",
    "standalone template package with no config system; drift-tested against "
    ".env.example by test_harness_default_collector_matches_env_example",
), (
    "docker/neo4j.Dockerfile",
    "EXPOSE 7473 7474 7687",
    "mirrors the pinned official neo4j image's own ExposedPorts metadata (PSC-26, design-notes N16); "
    "not a port the engine configures",
)]

# Human ruling Q7: the model host's name is a host name under PS-1.2 even
# though config/defaults.yaml ships no default for it (Q32).
MODEL_HOST_NAME = "aria-gb10-2"

# PS-2.19 N5: 0.0.0.0 is the unspecified (all-interfaces) address, not loopback.
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


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
        # model-roles MR-3: a current role name (ADR-KE-014).
        files = {"scripts/pull.sh": "ollama pull gpt-oss:120b\n"}
        self.assertIn("gpt-oss:120b", _values(_scan(files, ["gpt-oss:120b"])))

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

    def test_dockerfile_exemption_covers_only_its_instruction_line(self):
        # platform-sbom U4b (PSC-26, N16; orchestrator U4b ruling 1): the
        # neo4j EXPOSE line is exempt, and only that exact line of that file.
        path, line = "docker/neo4j.Dockerfile", "EXPOSE 7473 7474 7687\n"
        self.assertEqual(_scan({path: line}, ["7687"], EXEMPTIONS), [])
        self.assertEqual(_scan({path: "  EXPOSE 7473 7474 7687  \n"}, ["7687"], EXEMPTIONS), [])
        for other in ("EXPOSE 7687\n", "EXPOSE 7473 7474 7687 8080\n", "EXPOSE 7473 7474 7687/tcp\n",
                      "ENV NEO4J_server_bolt_listen__address=:7687\n", "# bolt listens on 7687\n",
                      "HEALTHCHECK CMD cypher-shell -a bolt://localhost:7687 'RETURN 1'\n",
                      "RUN echo EXPOSE 7473 7474 7687\n", "EXPOSE=7687\n"):
            with self.subTest(same_file=other):
                self.assertTrue(_scan({path: other}, ["7687"], EXEMPTIONS), "another line of the file was exempted")
        with self.subTest(case="the exempt line plus another literal: one finding, on the other line"):
            found = _scan({path: line + "ENV BOLT=7687\n"}, ["7687"], EXEMPTIONS)
            self.assertEqual([(f.line, f.value) for f in found], [(2, "7687")])
        for other_path in ("docker/app.Dockerfile", "docker/gateway.Dockerfile", "docker/neo4j/Dockerfile",
                           "Dockerfile", "docker-compose.yml", "scripts/build.sh"):
            with self.subTest(other_path=other_path):
                self.assertTrue(_scan({other_path: line}, ["7687"], EXEMPTIONS), "the exemption left its file")
        with self.subTest(case="the Python exemption keeps the assignment form (N4)"):
            self.assertTrue(_scan({"harness_telemetry/tracing.py": "DEFAULT_COLLECTOR\n"},
                                  ["DEFAULT_COLLECTOR"], EXEMPTIONS),
                            "a bare symbol line (no assignment) was exempted in a Python file")

    def test_dockerfile_exemption_skips_continuation_lines(self):
        # platform-sbom U5 (U4b review N7, security I-2; orchestrator U5
        # ruling 7; design-notes "N8 amendment, U5", item 5): the exempt text
        # on a continuation line of another instruction is not exempt. The
        # previous physical line, right-stripped, must not end in `\`.
        path, line = "docker/neo4j.Dockerfile", "EXPOSE 7473 7474 7687\n"
        for case, text in {"RUN continued": "RUN echo \\\n" + line,
                           "RUN continued, trailing blanks after the backslash": "RUN echo \\  \t\n" + line,
                           "ENV continued": "ENV A=1 \\\n" + line,
                           "after the real file's ENV continuation lines": "ENV PATH=/bin \\\n    LANG=C \\\n" + line}.items():
            with self.subTest(case=case):
                found = _scan({path: text}, ["7687"], EXEMPTIONS)
                self.assertTrue([f for f in found if f.value == "7687"],
                                f"the exempt line was exempted as a continuation line ({case})")
        for case, text in {"first line": line, "after a complete instruction": "WORKDIR /var/lib/neo4j\n" + line,
                           "after a blank line": "RUN echo \\\n    done\n\n" + line,
                           "after a line with a backslash inside": 'RUN echo "a\\b" done\n' + line}.items():
            with self.subTest(case=case):
                self.assertEqual(_scan({path: text}, ["7687"], EXEMPTIONS), [], case)
        with self.subTest(case="the real docker/neo4j.Dockerfile is still exempt"):
            real = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn(line, real.replace("\r\n", "\n"), "docker/neo4j.Dockerfile has no EXPOSE line")
            self.assertEqual(_scan({path: real}, ["7687"], EXEMPTIONS), [])
        with self.subTest(case="the Python assignment exemption is unchanged after a backslash line"):
            text = 'X = "a" \\\n    "b"\nDEFAULT_COLLECTOR = "http://localhost:47101"\n'
            self.assertEqual(_scan({"harness_telemetry/tracing.py": text}, ["47101"], EXEMPTIONS), [])

    def test_allowed_locations_are_never_flagged(self):
        for path in ("config/defaults.yaml", ".env.example", "config/verify.env",
                     "tests/test_x.py", "docs/architecture.md"):
            with self.subTest(path=path):
                files = {path: 'port = 5432\nURL = "http://aria-gb10-2:8000"\n'}
                self.assertEqual(_scan(files, ["5432", MODEL_HOST_NAME]), [])


def _repo_paths() -> list[str]:
    """Tracked and not-ignored untracked files (so new, uncommitted files count)."""
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, check=True)
    return sorted({p for p in result.stdout.decode("utf-8").split("\0")
                   if p and (ROOT / p).is_file()})


def _collect_repo_files() -> dict[str, str]:
    # PS-2.19 N2 (platform-stack-up): the scanner's own collector picks every
    # text file in the PS-1.2 scope whatever its suffix, and fails naming any
    # file it cannot classify. It replaces the suffix allowlist
    # (the old TEXT_SUFFIXES), which missed *.conf, *.template, *.sql, *.cypher and
    # compose.yaml (review N2).
    from tests.hardcoded_scan import collect_files

    return dict(collect_files(ROOT, _repo_paths()))


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
        # Review round-0 N3 (platform-stack-ready, PS-2.24): `*_LISTEN` keys
        # are container listen ports, so their values count as ports too.
        if ("PORT" in upper or upper.endswith("_LISTEN")) and value.isdigit():
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
        # Review round-0 N3 (PS-2.24, mutant P5): every *_LISTEN value is a
        # declared port, and a literal compose `target:` port is flagged.
        listens = {k: v for k, v in read_env_example().items() if k.endswith("_LISTEN")}
        self.assertTrue(listens, "precondition: .env.example declares *_LISTEN ports")
        for key, value in listens.items():
            with self.subTest(listen=key):
                self.assertIn(value, ports, f"{key}={value} is not treated as a port")
        api_listen = listens["KE_GATEWAY_API_LISTEN"]
        literal = {"docker-compose.yml": f"    ports:\n      - target: {api_listen}\n"}
        with self.subTest(case="literal compose target"):
            self.assertTrue(_scan(literal, sorted(ports)), "a literal `target:` port is not flagged")
        variable = {"docker-compose.yml": f"      - target: ${{KE_GATEWAY_API_LISTEN:-{api_listen}}}\n"}
        with self.subTest(case="compose target variable (control)"):
            self.assertEqual(_scan(variable, sorted(ports)), [])
        findings = _scan(_collect_repo_files(), sorted(ports), EXEMPTIONS)
        self.assertEqual(findings, [], "hardcoded ports:\n" + self._report(findings))

    def test_no_hardcoded_hosts_or_models(self):
        _, names = _declared()
        # model-roles MR-3 (ADR-KE-014): the role and fallback names now declared.
        for model in ("qwen3.5:latest", "gpt-oss:120b", "gpt-oss:20b", "nomic-embed-text"):
            self.assertIn(model, names, f"{model} is not declared in config")
        self.assertIn(MODEL_HOST_NAME, names)
        findings = _scan(_collect_repo_files(), sorted(names), EXEMPTIONS)
        self.assertEqual(findings, [], "hardcoded hosts or models:\n" + self._report(findings))

    def test_model_host_name_only_in_allowed_locations(self):
        # N1: DNS names are case-insensitive (PS-2.19).
        offenders = [path for path, text in _collect_repo_files().items()
                     if re.search(re.escape(MODEL_HOST_NAME), text, re.I)]
        self.assertEqual(offenders, [])


class ScannerWideningTest(unittest.TestCase):
    """PS-2.19 (review N1-N5), platform-stack-up. Each case is RED against the
    platform-config scanner; the developer widens tests/hardcoded_scan.py.

    N2 contract, new in tests/hardcoded_scan.py:

        collect_files(root: Path, paths: Iterable[str]) -> Mapping[str, str]

    `paths` are repo-relative POSIX paths (tracked files). It returns the
    text of every path in the PS-1.2 scope (under engine/, harness_telemetry/,
    scripts/, docker/ or .github/, or a compose file of any name at the root:
    docker-compose*.y(a)ml, compose*.y(a)ml), whatever the suffix, and nothing
    outside it. A path in scope that is not UTF-8 text raises ValueError whose
    message names the path (never skipped)."""

    def test_n1_host_names_match_case_insensitively(self):
        for text in ("ssh ARIA-GB10-2\n", "host: Aria-Gb10-2\n"):
            with self.subTest(text=text):
                self.assertTrue(_scan({"scripts/x.sh": text}, [MODEL_HOST_NAME]),
                                f"{text.strip()!r} was not flagged")

    def test_n2_compose_files_of_any_name_keep_their_defaults(self):
        line = '  - "${KE_PG_PORT:-5432}:${PG:-5432}"\n'
        for path in ("compose.yaml", "compose.override.yml", "docker-compose.verify.yaml"):
            with self.subTest(path=path):
                self.assertEqual(_scan({path: line}, ["5432"]), [])

    def test_hardcoded_scan_covers_every_text_file(self):  # N2
        import tempfile
        from pathlib import Path

        from tests.hardcoded_scan import collect_files

        in_scope = {
            "engine/a.py": "x = 1\n",
            "engine/db/q.sql": "SELECT 1;\n",
            "engine/graph/q.cypher": "RETURN 1\n",
            "engine/templates/page.html": "<p>hi</p>\n",
            "harness_telemetry/t.j2": "{{ x }}\n",
            "docker/gateway/default.conf.template": "listen ${KE_GATEWAY_API_LISTEN};\n",
            "docker/gateway/nginx.conf": "events {}\n",
            "docker/gateway/10-ke-bind-check.sh": "#!/bin/sh\n",
            "docker/app.Dockerfile": "FROM x\n",
            "scripts/launch.ps1": "Write-Host hi\n",
            "scripts/noext": "echo hi\n",
            ".github/workflows/ci.yml": "on: push\n",
            "compose.yaml": "services: {}\n",
            "docker-compose.verify.yml": "services: {}\n",
            "docker-compose.override.yaml": "services: {}\n",
        }
        out_of_scope = {"README.md": "x\n", "docs/x.md": "x\n", "tests/test_x.py": "x\n"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in {**in_scope, **out_of_scope}.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            files = dict(collect_files(root, sorted({**in_scope, **out_of_scope})))
        self.assertEqual(files, in_scope)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "engine").mkdir()
            (root / "engine" / "blob.bin").write_bytes(b"\x00\xff\xfe\x80binary")
            (root / "engine" / "ok.py").write_text("x = 1\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                collect_files(root, ["engine/blob.bin", "engine/ok.py"])
            self.assertIn("engine/blob.bin", str(ctx.exception))

    def test_n3_tuple_and_dict_ports_are_flagged(self):
        for source in ('ADDR = ("db", 15433)\n',
                       'socket.create_connection(("0.0.0.0", 9999))\n',
                       'OPTS = {"port": 5433}\n',
                       "opts['port'] = 5433\n",
                       'connect(host="db", **{"port": 5433})\n'):
            with self.subTest(source=source):
                self.assertTrue(_scan({"engine/x.py": source}, []), "port literal not flagged")
        for source in ("retries = 3\n", 'SIZES = {"width": 5433}\n'):
            with self.subTest(control=source):
                self.assertEqual(_scan({"engine/x.py": source}, []), [])

    def test_n4_exemption_covers_only_the_assignment_line(self):
        path = "harness_telemetry/tracing.py"
        for line in ('DEFAULT_COLLECTOR == "http://localhost:47101"\n',
                     'DEFAULT_COLLECTOR += ":47101"\n',
                     'DEFAULT_COLLECTOR.replace("x", "47101")\n'):
            with self.subTest(line=line):
                self.assertTrue(_scan({path: line}, ["47101"], EXEMPTIONS),
                                "a non-assignment line was exempted")
        self.assertEqual(_scan({path: 'DEFAULT_COLLECTOR = "http://localhost:47101"\n'},
                               ["47101"], EXEMPTIONS), [])

    def test_n5_no_loopback_definition_includes_unspecified_address(self):
        from engine.egress import is_local_endpoint

        self.assertFalse(is_local_endpoint("http://0.0.0.0:6006", []))
        definition = re.compile(r"^\s*(\w*loopback\w*)\s*(?::[^=]*)?=(?!=)(.*)$", re.I)
        sources = [*sorted((ROOT / "tests").glob("*.py")), *sorted((ROOT / "engine").rglob("*.py"))]
        for path in sources:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = definition.match(line)
                if match:
                    with self.subTest(at=f"{path.relative_to(ROOT).as_posix()}:{number}"):
                        self.assertNotIn("0.0.0.0", match.group(2),
                                         f"{match.group(1)} counts 0.0.0.0 as loopback")


if __name__ == "__main__":
    unittest.main()
