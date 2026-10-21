"""platform-stack-ready (2b): compose wiring for readiness and the model host
(fast).

- `test_compose_model_wiring` (architecture §2.4 "Model wiring", 2b plan):
  `api`, `worker` and `gates-it` set `KE_MODELS__{COMPOSE,REWRITE,AUDIT,EMBED}__BASE_URL`
  to `http://gateway:${KE_GATEWAY_MODEL_LISTEN:-8102}/v1` from one YAML anchor
  (`x-model-env`), and their allowlist to `gateway,${KE_EGRESS_ALLOWLIST:-}`;
  `gateway` keeps `${KE_EGRESS_ALLOWLIST:-}`; `gates-it` also gets
  `KE_MODEL_UPSTREAM` and the two store passwords; `defaults.yaml` keeps
  `base_url: null`.
- `test_compose_postgres_identity_matches_defaults` (PS-2.5 *Store identity*,
  review round-0 N4): the user and database the `postgres` service creates
  equal `stores.postgres.user` and `stores.postgres.database`.
"""

from __future__ import annotations

import re
import unittest

from tests import compose_support as cs
from tests.engine_support import DEFAULTS, read_env_example

PASSES = ("COMPOSE", "REWRITE", "AUDIT", "EMBED")
BASE_URL = "http://gateway:${KE_GATEWAY_MODEL_LISTEN:-8102}/v1"
APP_ALLOWLIST = "gateway,${KE_EGRESS_ALLOWLIST:-}"
MODEL_CONSUMERS = ("api", "worker", "gates-it")


def _defaults() -> dict:
    import yaml

    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))


class ModelWiringTest(unittest.TestCase):
    def test_compose_model_wiring(self):
        services = cs.services()
        for name in MODEL_CONSUMERS:
            env = cs.environment(services.get(name, {}))
            for p in PASSES:
                with self.subTest(service=name, model_pass=p):
                    self.assertEqual(env.get(f"KE_MODELS__{p}__BASE_URL"), BASE_URL)
            with self.subTest(service=name, key="KE_EGRESS_ALLOWLIST"):
                self.assertEqual(env.get("KE_EGRESS_ALLOWLIST"), APP_ALLOWLIST,
                                 "the app allowlist is the stack's own forward plus the operator's")
        gateway = cs.environment(services["gateway"])
        self.assertEqual(gateway.get("KE_EGRESS_ALLOWLIST"), "${KE_EGRESS_ALLOWLIST:-}",
                         "the gateway's allowlist is unchanged (security M-3)")
        for p in PASSES:
            self.assertNotIn(f"KE_MODELS__{p}__BASE_URL", gateway)

    def test_model_base_urls_come_from_one_anchor(self):
        text = cs.MAIN_COMPOSE.read_text(encoding="utf-8")
        self.assertIsNotNone(re.search(r"(?m)^x-model-env:\s*&\S+", text),
                             "docker-compose.yml has no top-level x-model-env anchor")
        self.assertEqual(text.count(BASE_URL), len(PASSES),
                         "each pass's base URL must be written once, in the anchor")
        self.assertEqual(text.count(APP_ALLOWLIST), 1,
                         "the app allowlist must be written once, in the anchor")

    def test_gates_it_gets_model_upstream_and_store_passwords(self):
        env = cs.environment(cs.services()["gates-it"])
        self.assertEqual(env.get("KE_MODEL_UPSTREAM"), "${KE_MODEL_UPSTREAM:-}")
        for key in ("KE_STORES__POSTGRES__PASSWORD", "KE_STORES__NEO4J__PASSWORD"):
            with self.subTest(key=key):
                self.assertEqual(env.get(key), f"${{{key}}}",
                                 "gates-it reads the verify project's store passwords (no default)")

    def test_defaults_keep_null_base_urls(self):
        models = _defaults()["models"]
        for p in PASSES:
            with self.subTest(model_pass=p):
                self.assertIsNone(models[p.lower()]["base_url"],
                                  "outside compose there is no model host unless configured")


def _resolve(value: str) -> str:
    """A compose value: a literal, or `${VAR:-default}` whose default must
    equal the .env.example value (checked by test_compose_defaults_match_env_example)."""
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?-([^}]*)\}", value)
    if match:
        example = read_env_example().get(match.group(1))
        return example if example is not None else match.group(2)
    return value


class StoreIdentityTest(unittest.TestCase):
    def test_compose_postgres_identity_matches_defaults(self):
        stores = _defaults()["stores"]["postgres"]
        env = cs.environment(cs.services()["postgres"])
        self.assertIn("POSTGRES_USER", env, "postgres must set its user explicitly")
        self.assertIn("POSTGRES_DB", env, "postgres must set its database explicitly")
        self.assertNotRegex(env["POSTGRES_USER"], r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$",
                            "a variable without a default would make the identity depend on .env")
        self.assertEqual(_resolve(env["POSTGRES_USER"]), stores["user"])
        self.assertEqual(_resolve(env["POSTGRES_DB"]), stores["database"])


# --------------------------------------------------------------------------
# PS-2.7 *Model host only through the gateway* (human ruling F-A), review
# R-B1: across the gateway's nginx config and templates, the only upstream
# outside the stack is the value of KE_MODEL_UPSTREAM; every other upstream
# is a compose service name.
# --------------------------------------------------------------------------

GATEWAY_DIR = cs.MAIN_COMPOSE.parent / "docker" / "gateway"
PASS_DIRECTIVES = ("proxy_pass", "grpc_pass", "fastcgi_pass", "uwsgi_pass", "scgi_pass",
                   "memcached_pass")
MODEL_UPSTREAM_REF = "${KE_MODEL_UPSTREAM}"
# A block body: anything but braces, or a whole `${VAR}` reference.
_BLOCK = r"(?:[^{}]|\$\{[^{}]*\})*"


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
                     for line in text.splitlines())


def _upstream_values(text: str) -> list[str]:
    """Every value an upstream can take in one nginx config file: each pass
    target, a `$variable` target resolved through its `set` and every value
    of its `map`, and every `server` line inside an `upstream` block."""
    text = _strip_comments(text)
    sets: dict[str, list[str]] = {}
    for var, value in re.findall(r"\bset\s+\$(\w+)\s+(\"[^\"]*\"|'[^']*'|[^;\s]+)\s*;", text):
        sets.setdefault(var, []).append(value.strip("\"'"))
    for var, body in re.findall(rf"\bmap\s+\S+\s+\$(\w+)\s*\{{({_BLOCK})\}}", text):
        for _key, value in re.findall(r"(\S+)\s+(\"[^\"]*\"|'[^']*'|[^;\s]+)\s*;", body):
            sets.setdefault(var, []).append(value.strip("\"'"))
    values: list[str] = []
    for directive in PASS_DIRECTIVES:
        for target in re.findall(rf"\b{directive}\s+([^;\s]+)\s*;", text):
            var = re.fullmatch(r"\$(\w+)", target)
            if var:
                assert var.group(1) in sets, f"{directive} ${var.group(1)} is never set"
                values.extend(sets[var.group(1)])
            else:
                values.append(target)
    for body in re.findall(rf"\bupstream\s+\S+\s*\{{({_BLOCK})\}}", text):
        values.extend(re.findall(r"\bserver\s+([^;\s]+)", body))
    return values


def _upstream_host(value: str) -> str:
    """The host of `scheme://host:port/...`, `host:port` or `host`."""
    rest = value.split("://", 1)[1] if "://" in value else value
    host = re.split(r"[:/]", rest, maxsplit=1)[0]
    return host


def _external_upstreams(files: dict[str, str], services: set[str]) -> list[tuple[str, str]]:
    """(file, value) for every upstream value that is not a compose service."""
    external = []
    for name, text in files.items():
        for value in _upstream_values(text):
            if _upstream_host(value) not in services:
                external.append((name, value))
    return external


class GatewayUpstreamTest(unittest.TestCase):
    def _gateway_files(self) -> dict[str, str]:
        files = {str(p.relative_to(GATEWAY_DIR)).replace("\\", "/"): p.read_text(encoding="utf-8")
                 for p in sorted(GATEWAY_DIR.rglob("*"))
                 if p.is_file() and (p.name == "nginx.conf" or "template" in p.suffix
                                     or p.suffix == ".conf")}
        self.assertIn("nginx.conf", files)
        self.assertTrue([n for n in files if n.startswith("templates/")], "no gateway templates found")
        return files

    def test_gateway_only_external_upstream_is_model_upstream(self):
        services = set(cs.services())
        files = self._gateway_files()
        external = _external_upstreams(files, services)
        self.assertEqual([value for _, value in external], [MODEL_UPSTREAM_REF],
                         "the only upstream outside the stack must be ${KE_MODEL_UPSTREAM}, "
                         f"once; every other upstream a compose service name: {external}")
        self.assertEqual(external[0][0], "templates/model.conf.stream-template")
        for name, text in files.items():
            with self.subTest(file=name):
                body = _strip_comments(text)
                if name != "templates/model.conf.stream-template":
                    self.assertNotIn("KE_MODEL_UPSTREAM", body,
                                     "KE_MODEL_UPSTREAM may feed only the model forward")
        # The gateway is the only service told KE_MODEL_UPSTREAM besides
        # gates-it, which only reads it to skip or run model-calling tests.
        for name, svc in cs.services().items():
            if "KE_MODEL_UPSTREAM" in cs.environment(svc):
                with self.subTest(service=name):
                    self.assertIn(name, {"gateway", "api", "worker", "gates-it"})

    def test_gateway_upstream_scan_sees_a_planted_host(self):
        # Guards the scan itself: a literal, a `set` variable and an
        # `upstream` block pointing outside the stack are each reported.
        services = set(cs.services())
        plants = {
            "literal": "location / { proxy_pass http://evil.example:80; }",
            "set variable": "location / { set $u http://evil.example:80; proxy_pass $u; }",
            "map value": "map $x $u { default \"api:8080\"; ~y \"evil.example:1\"; }\n"
                         "server { proxy_pass $u; }",
            "upstream block": "upstream pool { server evil.example:80; }\n"
                              "server { location / { proxy_pass http://pool; } }",
        }
        for case, text in plants.items():
            with self.subTest(case=case):
                external = _external_upstreams({"planted.conf": text}, services | {"pool"})
                self.assertIn("evil.example", " ".join(v for _, v in external), external)
        clean = "location / { set $u http://api:${KE_API__LISTEN_PORT}; proxy_pass $u; }"
        self.assertEqual(_external_upstreams({"clean.conf": clean}, services), [])


if __name__ == "__main__":
    unittest.main()
