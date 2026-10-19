"""platform-config PS-1.1: one typed settings object (ADR-KE-010, §2.3).

Each test maps to a criterion in docs/requirements.md § PS-1 platform-config.
`engine`, pydantic-settings and PyYAML are imported inside the tests, so each
criterion reports separately while they are missing.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.engine_support import (
    DEFAULTS,
    KNOWN_SECRETS,
    SAFE_SECRET,
    base_env,
    config_error,
    environ,
    load_settings,
    secret_env_names,
    settings_cls,
)


def _yaml_defaults() -> dict[str, Any]:
    import yaml

    data = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "config/defaults.yaml must be a mapping"
    return data


def _leaves(data: Any, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    if isinstance(data, dict):
        out: list[tuple[tuple[str, ...], Any]] = []
        for key, value in data.items():
            out.extend(_leaves(value, (*prefix, str(key))))
        return out
    return [(prefix, data)]


def _get(obj: Any, path: tuple[str, ...]) -> Any:
    for part in path:
        obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
    return obj


def _upstream(settings: Any) -> Any:
    """KE_MODEL_UPSTREAM's value; §2.3 nests it under `models`, F2 names it
    without the nesting, so accept either attribute location."""
    if hasattr(settings, "model_upstream"):
        return settings.model_upstream
    return settings.models.model_upstream


class TypedConfigTest(unittest.TestCase):
    def test_config_defaults_and_env_override(self):
        # Defaults come from config/defaults.yaml.
        settings = load_settings()
        self.assertEqual(settings.env, "prod")
        self.assertIs(settings.auth.enabled, True)
        self.assertEqual(list(settings.egress_allowlist), [])
        self.assertEqual(settings.models.compose.model, "qwen2.5:14b-instruct")
        self.assertEqual(settings.models.compose.fallback_model, "llama3.1:8b")
        self.assertEqual(settings.models.embed.model, "nomic-embed-text")
        self.assertEqual(settings.models.embed.dim, 768)
        self.assertIsNone(_upstream(settings))
        self.assertIs(settings.telemetry.hide_inputs, True)
        self.assertIs(settings.telemetry.hide_outputs, True)

        # Every leaf in defaults.yaml is the loaded value of the same key.
        for path, value in _leaves(_yaml_defaults()):
            with self.subTest(key=".".join(path)):
                loaded = _get(settings, path)
                if isinstance(value, list):
                    loaded = list(loaded)
                if isinstance(value, str) and loaded is not None:
                    # URL types may normalise a trailing slash.
                    loaded, value = str(loaded).rstrip("/"), value.rstrip("/")
                self.assertEqual(loaded, value)

        # Environment overrides, KE_ prefix and __ nesting, typed.
        env = base_env(
            KE_ENV="dev",
            KE_STORES__POSTGRES__PORT="47999",
            KE_EGRESS_ALLOWLIST="model-a.internal,model-b.internal",
            KE_MODELS__COMPOSE__BASE_URL="http://model-a.internal:9000/v1",
            KE_MODEL_UPSTREAM="model-b.internal:9001",
            KE_AUTH__ENABLED="false",
        )
        overridden = load_settings(env)
        self.assertEqual(overridden.env, "dev")
        self.assertEqual(overridden.stores.postgres.port, 47999)
        self.assertIsInstance(overridden.stores.postgres.port, int)
        self.assertEqual(list(overridden.egress_allowlist),
                         ["model-a.internal", "model-b.internal"])
        self.assertEqual(str(overridden.models.compose.base_url),
                         "http://model-a.internal:9000/v1")
        self.assertEqual(_upstream(overridden), "model-b.internal:9001")
        self.assertIs(overridden.auth.enabled, False)
        # An override touches only its own key.
        self.assertEqual(overridden.stores.postgres.host, settings.stores.postgres.host)

        # Standard tool names keep their own names (F2).
        tools = load_settings(base_env(
            PHOENIX_COLLECTOR_ENDPOINT="http://localhost:47101",
            HARNESS_TRACING="console",
            OPENINFERENCE_HIDE_INPUTS="false",
            OPENINFERENCE_HIDE_OUTPUTS="false",
        ))
        self.assertEqual(str(tools.telemetry.collector_endpoint).rstrip("/"),
                         "http://localhost:47101")
        self.assertEqual(tools.telemetry.tracing, "console")
        self.assertIs(tools.telemetry.hide_inputs, False)
        self.assertIs(tools.telemetry.hide_outputs, False)

    def test_config_init_args_take_precedence(self):
        settings = load_settings(base_env(KE_ENV="prod"), env="ci")
        self.assertEqual(settings.env, "ci")

    def test_every_non_secret_setting_has_a_yaml_default(self):
        from pydantic import BaseModel

        defaults = _yaml_defaults()
        secrets = {tuple(n[3:].lower().split("__")) for n in secret_env_names()}

        def walk(model: Any, prefix: tuple[str, ...]):
            for name, field in model.model_fields.items():
                path = (*prefix, name)
                ann = field.annotation
                if isinstance(ann, type) and issubclass(ann, BaseModel):
                    yield from walk(ann, path)
                else:
                    yield path

        for path in walk(settings_cls(), ()):
            if path in secrets:
                continue
            with self.subTest(key=".".join(path)):
                node: Any = defaults
                for part in path:
                    self.assertIsInstance(node, dict, ".".join(path))
                    self.assertIn(part, node, f"{'.'.join(path)} has no default in defaults.yaml")
                    node = node[part]

    def test_config_missing_defaults_file_names_path(self):
        missing = str(Path(tempfile.gettempdir()) / "ke-no-such-dir" / "defaults.yaml")
        with self.assertRaises(config_error()) as ctx:
            load_settings(base_env(KE_CONFIG_FILE=missing))
        self.assertIn("defaults.yaml", str(ctx.exception))
        self.assertIn("ke-no-such-dir", str(ctx.exception))

    def test_config_rejects_bad_type(self):
        bad = "not-a-port-SENTINELVALUE"
        with self.assertRaises(config_error()) as ctx:
            load_settings(base_env(KE_STORES__POSTGRES__PORT=bad))
        message = str(ctx.exception)
        self.assertTrue(
            "KE_STORES__POSTGRES__PORT" in message or "stores.postgres.port" in message,
            f"message does not name the key: {message!r}")
        self.assertNotIn(bad, message)
        self.assertNotIn("SENTINELVALUE", message)

        # Same for a wrong type in the YAML file.
        text = DEFAULTS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "defaults.yaml"
            import yaml

            data = yaml.safe_load(text)
            data["stores"]["valkey"]["port"] = "YAMLSENTINEL"
            broken.write_text(yaml.safe_dump(data), encoding="utf-8")
            with self.assertRaises(config_error()) as ctx:
                load_settings(base_env(KE_CONFIG_FILE=str(broken)))
        message = str(ctx.exception)
        self.assertTrue("stores.valkey.port" in message or "KE_STORES__VALKEY__PORT" in message,
                        f"message does not name the key: {message!r}")
        self.assertNotIn("YAMLSENTINEL", message)

    def test_config_ignores_unprefixed_names(self):
        env = base_env(
            ENV="dev",
            EGRESS_ALLOWLIST="evil.example",
            MODEL_BASE_URL="http://evil.example:9999/v1",
            MODEL_UPSTREAM="evil.example:9999",
        )
        settings = load_settings(env)
        self.assertEqual(settings.env, "prod")
        self.assertEqual(list(settings.egress_allowlist), [])
        self.assertIsNone(_upstream(settings))
        for name in ("compose", "rewrite", "audit", "embed"):
            with self.subTest(model_pass=name):
                self.assertIsNone(getattr(settings.models, name).base_url)

    def test_config_missing_secret_names_key(self):
        names = secret_env_names()
        for known in KNOWN_SECRETS:
            self.assertIn(known, names, f"{known} must be a SecretStr setting")
        for name in names:
            with self.subTest(secret=name):
                env = base_env()
                del env[name]
                with self.assertRaises(config_error()) as ctx:
                    with environ(env):
                        settings_cls()()
                message = str(ctx.exception)
                dotted = name[3:].lower().replace("__", ".")
                self.assertTrue(name in message or dotted in message,
                                f"message does not name {name}: {message!r}")
                self.assertNotIn(SAFE_SECRET, message)

    def test_config_secrets_have_no_yaml_default(self):
        defaults = _yaml_defaults()
        for name in secret_env_names():
            path = tuple(name[3:].lower().split("__"))
            with self.subTest(secret=name):
                node: Any = defaults
                for part in path[:-1]:
                    node = node.get(part, {}) if isinstance(node, dict) else {}
                self.assertNotIn(path[-1], node if isinstance(node, dict) else {})

    def test_secret_values_are_not_in_repr(self):
        settings = load_settings()
        self.assertNotIn(SAFE_SECRET, repr(settings))
        self.assertNotIn(SAFE_SECRET, str(settings))


def _full_text(exc: BaseException) -> str:
    """The message plus everything a traceback would print (chained causes)."""
    import traceback

    return "".join(traceback.format_exception(exc))


class PrecedenceTest(unittest.TestCase):
    """Review N6 (kills M5): two names reach the same key. The order is the one
    engine/config/loader.py documents: init > KE_ variables > standard tool
    names > YAML.

    Model upstream (orchestrator ruling, 2026-10-19, rework 1, under F2 "no
    aliases"): KE_MODEL_UPSTREAM is the only accepted name.
    KE_MODELS__MODEL_UPSTREAM is ignored, alone or alongside it."""

    def test_model_upstream_has_one_name(self):
        alone = load_settings(base_env(KE_MODELS__MODEL_UPSTREAM="nested.internal:9001"))
        self.assertIsNone(alone.models.model_upstream,
                          "KE_MODELS__MODEL_UPSTREAM must have no effect (F2: no aliases)")
        both = load_settings(base_env(KE_MODELS__MODEL_UPSTREAM="nested.internal:9001",
                                      KE_MODEL_UPSTREAM="flat.internal:9002"))
        self.assertEqual(both.models.model_upstream, "flat.internal:9002")

    def test_ke_names_outrank_standard_names(self):
        cases = [
            (dict(KE_TELEMETRY__TRACING="console", HARNESS_TRACING="otlp"),
             ("telemetry", "tracing"), "console"),
            (dict(KE_TELEMETRY__TRACING="off", HARNESS_TRACING="console"),
             ("telemetry", "tracing"), "off"),
            (dict(KE_TELEMETRY__COLLECTOR_ENDPOINT="http://localhost:47101",
                  PHOENIX_COLLECTOR_ENDPOINT="http://collector.example.com:6006"),
             ("telemetry", "collector_endpoint"), "http://localhost:47101"),
            (dict(KE_TELEMETRY__HIDE_INPUTS="true", OPENINFERENCE_HIDE_INPUTS="false"),
             ("telemetry", "hide_inputs"), True),
            (dict(KE_TELEMETRY__HIDE_OUTPUTS="false", OPENINFERENCE_HIDE_OUTPUTS="true"),
             ("telemetry", "hide_outputs"), False),
        ]
        for overrides, path, expected in cases:
            with self.subTest(overrides=overrides):
                loaded = _get(load_settings(base_env(**overrides)), path)
                if isinstance(expected, str):
                    loaded = str(loaded).rstrip("/")
                self.assertEqual(loaded, expected)

    def test_standard_name_used_when_ke_name_unset(self):
        settings = load_settings(base_env(HARNESS_TRACING="console",
                                          KE_MODEL_UPSTREAM="flat.internal:9002"))
        self.assertEqual(settings.telemetry.tracing, "console")
        self.assertEqual(settings.models.model_upstream, "flat.internal:9002")

    def test_error_names_the_variable_the_user_set(self):
        sentinel = "BADVALUESENTINEL"
        cases = {
            "HARNESS_TRACING": f"bogus-{sentinel}",
            "PHOENIX_COLLECTOR_ENDPOINT": f"not a url {sentinel}",
            "OPENINFERENCE_HIDE_INPUTS": f"maybe-{sentinel}",
            "OPENINFERENCE_HIDE_OUTPUTS": f"maybe-{sentinel}",
            "KE_TELEMETRY__TRACING": f"bogus-{sentinel}",
        }
        for name, value in cases.items():
            with self.subTest(variable=name):
                env = base_env(**{name: value})
                if name != "HARNESS_TRACING":
                    env.pop("HARNESS_TRACING")
                with self.assertRaises(config_error()) as ctx:
                    load_settings(env)
                message = str(ctx.exception)
                self.assertIn(name, message, f"error does not name {name}: {message!r}")
                self.assertNotIn(sentinel, _full_text(ctx.exception))


class ConfigErrorNeverCarriesValueTest(unittest.TestCase):
    """Review N7 (kills M17): neither the message nor any chained cause (what
    a traceback prints) carries the bad value; pydantic's ValidationError text
    includes input values, so it must not be chained."""

    def test_config_error_has_no_value_anywhere(self):
        sentinel = "N7SENTINELVALUE"
        cases = {
            "KE_STORES__POSTGRES__PORT": f"port-{sentinel}",
            "KE_ENV": f"staging-{sentinel}",
            "KE_AUTH__ENABLED": f"perhaps-{sentinel}",
            "KE_MODELS__COMPOSE__BASE_URL": f"::not-a-url-{sentinel}",
            "KE_MODELS__EMBED__DIM": f"dim-{sentinel}",
        }
        for name, value in cases.items():
            with self.subTest(variable=name):
                with self.assertRaises(config_error()) as ctx:
                    load_settings(base_env(**{name: value}))
                exc = ctx.exception
                self.assertNotIn(sentinel, str(exc))
                self.assertNotIn(sentinel, _full_text(exc))
                self.assertIsNone(exc.__cause__)
                self.assertTrue(exc.__suppress_context__)


class ModelUrlUserinfoTest(unittest.TestCase):
    """Security M4 (rework 2): a model URL with userinfo is refused at load.

    Credentials in `base_url` reach exported spans through HTTP error
    messages, so `KE_MODELS__<PASS>__BASE_URL` and `KE_MODEL_UPSTREAM` reject
    any `user[:password]@`; the ConfigError names the variable and never
    carries the password (or the rest of the value)."""

    PASSWORD = "PW4SENTINELx9"

    def _values(self) -> dict[str, str]:
        pw = self.PASSWORD
        return {
            "user and password": f"http://u:{pw}@allowed.example/v1",
            "https, user and password": f"https://svc:{pw}@allowed.example:8443/v1",
            "user only": f"http://{pw}@allowed.example/v1",
        }

    def test_base_url_with_userinfo_is_refused(self):
        for model_pass in ("COMPOSE", "REWRITE", "AUDIT", "EMBED"):
            name = f"KE_MODELS__{model_pass}__BASE_URL"
            for label, value in self._values().items():
                with self.subTest(variable=name, value=label):
                    with self.assertRaises(config_error()) as ctx:
                        load_settings(base_env(**{name: value}))
                    message = str(ctx.exception)
                    self.assertIn(name, message, f"error does not name {name}: {message!r}")
                    self.assertNotIn(self.PASSWORD, _full_text(ctx.exception))

    def test_model_upstream_with_userinfo_is_refused(self):
        values = dict(self._values())
        values["no scheme, user and password"] = f"u:{self.PASSWORD}@allowed.example:9001"
        for label, value in values.items():
            with self.subTest(value=label):
                with self.assertRaises(config_error()) as ctx:
                    load_settings(base_env(KE_MODEL_UPSTREAM=value))
                message = str(ctx.exception)
                self.assertIn("KE_MODEL_UPSTREAM", message, message)
                self.assertNotIn(self.PASSWORD, _full_text(ctx.exception))

    def test_startup_refuses_userinfo_without_the_password(self):
        from engine.startup import startup

        for name in ("KE_MODELS__COMPOSE__BASE_URL", "KE_MODEL_UPSTREAM"):
            with self.subTest(variable=name):
                value = f"http://u:{self.PASSWORD}@allowed.example/v1"
                # The host is allowlisted, so only the userinfo can refuse it.
                with environ(base_env(KE_EGRESS_ALLOWLIST="allowed.example", **{name: value})):
                    with self.assertRaises(config_error()) as ctx:
                        startup()
                self.assertIn(name, str(ctx.exception))
                self.assertNotIn(self.PASSWORD, _full_text(ctx.exception))

    def test_urls_without_userinfo_still_load(self):
        settings = load_settings(base_env(
            KE_MODELS__COMPOSE__BASE_URL="http://allowed.example:9000/v1",
            KE_MODEL_UPSTREAM="allowed.example:9001"))
        self.assertEqual(str(settings.models.compose.base_url), "http://allowed.example:9000/v1")
        self.assertEqual(_upstream(settings), "allowed.example:9001")


class ConfigErrorContractTest(unittest.TestCase):
    """Security L4: malformed input that pydantic-settings or URL parsing
    rejects outside pydantic validation still surfaces as a ConfigError that
    names the variable, from startup(), without the value."""

    def test_malformed_values_raise_config_error(self):
        from engine.startup import startup

        cases = {
            "KE_STACK__SERVICE_NAMES": "not-json-L4SENTINEL",
            "KE_MODEL_UPSTREAM": "[::1",
        }
        for name, value in cases.items():
            with self.subTest(variable=name):
                with environ(base_env(**{name: value})):
                    with self.assertRaises(config_error()) as ctx:
                        startup()
                message = str(ctx.exception)
                self.assertIn(name, message, f"error does not name {name}: {message!r}")
                self.assertNotIn(value, _full_text(ctx.exception))


if __name__ == "__main__":
    unittest.main()
