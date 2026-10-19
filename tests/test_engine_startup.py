"""platform-config PS-1.5, PS-1.7, PS-1.9: startup refusals and traced startup.

Contract used here (docs/architecture.md §2.3, ADR-KE-010):
- `engine.startup.check(settings)` raises `StartupRefused` naming the setting;
  in `dev` it logs warnings (logger namespace `engine`) instead for auth off
  and hide flags off, and allows placeholder secrets;
- `engine.startup.startup()` loads Settings from the environment, runs the
  check inside the spans of §2.3's span table, and returns the Settings;
- `engine.egress.is_local_endpoint` decides "local collector" (Q3 ruling).

Orchestrator ruling (2026-10-18, platform-config handoff): the `changeme`
placeholder prefix check is case-insensitive.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

from tests.engine_support import (
    SAFE_SECRET,
    SocketSpy,
    base_env,
    environ,
    load_settings,
    read_env_example,
    secret_env_names,
)


def _check(settings: Any) -> None:
    from engine.startup import check

    check(settings)


def _refused() -> type[Exception]:
    from engine.startup import StartupRefused

    return StartupRefused


def _names_any(message: str, *names: str) -> bool:
    return any(n.lower() in message.lower() for n in names)


class StartupRefusalTest(unittest.TestCase):
    def assertRefused(self, env: dict[str, str], *names: str) -> str:
        settings = load_settings(env)
        with self.assertRaises(_refused()) as ctx:
            _check(settings)
        message = str(ctx.exception)
        self.assertTrue(_names_any(message, *names),
                        f"refusal does not name {names}: {message!r}")
        return message

    def test_startup_refuses_unsafe(self):
        # 1. Auth disabled outside dev.
        for env_name in ("prod", "ci"):
            with self.subTest(case="auth off", env=env_name):
                self.assertRefused(base_env(KE_ENV=env_name, KE_AUTH__ENABLED="false"),
                                   "auth.enabled", "KE_AUTH__ENABLED")

        # 2. Trace export to a collector that is not local.
        for endpoint in ("http://collector.example.com:6006", "http://203.0.113.5:6006"):
            with self.subTest(case="non-local collector", endpoint=endpoint):
                host = endpoint.split("://")[1].split(":")[0]
                self.assertRefused(
                    base_env(HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT=endpoint),
                    host)
            with self.subTest(case="non-local collector refused in dev too", endpoint=endpoint):
                host = endpoint.split("://")[1].split(":")[0]
                self.assertRefused(
                    base_env(KE_ENV="dev", HARNESS_TRACING="otlp",
                             PHOENIX_COLLECTOR_ENDPOINT=endpoint),
                    host)

        # 3. Hide flags not true outside dev.
        for flag, dotted in (("OPENINFERENCE_HIDE_INPUTS", "hide_inputs"),
                             ("OPENINFERENCE_HIDE_OUTPUTS", "hide_outputs")):
            for env_name in ("prod", "ci"):
                with self.subTest(case="hide flag off", flag=flag, env=env_name):
                    self.assertRefused(base_env(KE_ENV=env_name, **{flag: "false"}),
                                       flag, dotted)

    def test_startup_accepts_local_collectors(self):
        for endpoint in ("http://localhost:47101", "http://127.0.0.1:6006",
                         "http://[::1]:6006", "http://phoenix:6006"):
            with self.subTest(endpoint=endpoint):
                _check(load_settings(base_env(HARNESS_TRACING="otlp",
                                              PHOENIX_COLLECTOR_ENDPOINT=endpoint)))
        with self.subTest(case="no export, so any collector is accepted"):
            _check(load_settings(base_env(HARNESS_TRACING="off",
                                          PHOENIX_COLLECTOR_ENDPOINT="http://collector.example.com")))

    def test_startup_safe_defaults_pass(self):
        settings = load_settings()
        self.assertEqual(settings.env, "prod")
        _check(settings)  # the shipped defaults start without refusal

    def test_dev_auth_off_warns(self):
        settings = load_settings(base_env(KE_ENV="dev", KE_AUTH__ENABLED="false"))
        with self.assertLogs("engine", level="WARNING") as logs:
            _check(settings)
        self.assertTrue(any("auth" in line.lower() for line in logs.output), logs.output)

    def test_hide_flags_default_true_in_every_env(self):
        for env_name in ("dev", "ci", "prod"):
            with self.subTest(env=env_name):
                settings = load_settings(base_env(KE_ENV=env_name))
                self.assertIs(settings.telemetry.hide_inputs, True)
                self.assertIs(settings.telemetry.hide_outputs, True)

    def test_dev_hide_flag_off_warns_naming_flag(self):
        for flag in ("OPENINFERENCE_HIDE_INPUTS", "OPENINFERENCE_HIDE_OUTPUTS"):
            with self.subTest(flag=flag):
                settings = load_settings(base_env(KE_ENV="dev", **{flag: "false"}))
                with self.assertLogs("engine", level="WARNING") as logs:
                    _check(settings)
                dotted = flag.replace("OPENINFERENCE_", "").lower()
                self.assertTrue(any(_names_any(line, flag, dotted) for line in logs.output),
                                logs.output)


class PlaceholderSecretTest(unittest.TestCase):
    def test_startup_refuses_placeholder_secrets(self):
        names = secret_env_names()
        self.assertTrue(names, "Settings declares no SecretStr fields")
        for name in names:
            dotted = name[3:].lower().replace("__", ".")
            placeholders = (
                f"changeme-{name[3:].lower().replace('__', '-').replace('_', '-')}",
                "changeme-something-else-entirely",   # not the .env.example value
                "changemeplease",
                "CHANGEME-UPPER",                      # case-insensitive (ruling)
                "ChangeMe-Mixed",
            )
            for value in placeholders:
                for env_name in ("prod", "ci"):
                    with self.subTest(secret=name, value=value, env=env_name):
                        settings = load_settings(base_env(KE_ENV=env_name, **{name: value}))
                        with self.assertRaises(_refused()) as ctx:
                            _check(settings)
                        message = str(ctx.exception)
                        self.assertTrue(_names_any(message, name, dotted),
                                        f"refusal does not name {name}: {message!r}")
                        self.assertNotIn(value.lower(), message.lower())
                with self.subTest(secret=name, value=value, env="dev"):
                    _check(load_settings(base_env(KE_ENV="dev", **{name: value})))

    def test_placeholder_hidden_behind_invisible_prefix_is_refused(self):
        # Security L1: leading whitespace or a zero-width character does not
        # smuggle a placeholder past the check outside dev.
        for name in secret_env_names():
            for value in (" changeme-x", "\tchangeme-x", "​changeme-x",
                          "​ \tCHANGEME-x", "  ​​ChangeMe"):
                for env_name in ("prod", "ci"):
                    with self.subTest(secret=name, value=repr(value), env=env_name):
                        settings = load_settings(base_env(KE_ENV=env_name, **{name: value}))
                        with self.assertRaises(_refused()) as ctx:
                            _check(settings)
                        self.assertTrue(_names_any(str(ctx.exception), name),
                                        str(ctx.exception))

    # Security L1b (rework 2): characters that render as nothing, or as a
    # look-alike, hide the placeholder anywhere in it, not only at the edges.
    L1B_HIDERS = {
        "U+180E mongolian vowel separator": "᠎",
        "U+00AD soft hyphen": "­",
        "U+034F combining grapheme joiner": "͏",
        "U+2061 function application": "⁡",
        "U+3164 hangul filler": "ㅤ",
        "U+202E right-to-left override": "‮",
        "U+E0020 tag space": "\U000e0020",
        "U+200B zero width space": "​",
        "U+2028 line separator": " ",  # Zl (review R2-N2)
        "U+2029 paragraph separator": " ",  # Zp (review R2-N2)
    }

    def test_placeholder_hidden_by_invisible_characters_is_refused(self):
        values = {}
        for label, char in self.L1B_HIDERS.items():
            values[f"{label} before"] = f"{char}changeme-x"
            values[f"{label} inside"] = f"chan{char}geme-x"
        values["fullwidth changeme"] = "ｃｈａｎｇｅｍｅ"
        values["fullwidth CHANGEME-x"] = "ＣＨＡＮＧＥＭＥ-x"
        for name in secret_env_names():
            for label, value in values.items():
                for env_name in ("prod", "ci"):
                    with self.subTest(secret=name, value=label, env=env_name):
                        settings = load_settings(base_env(KE_ENV=env_name, **{name: value}))
                        with self.assertRaises(_refused()) as ctx:
                            _check(settings)
                        self.assertTrue(_names_any(str(ctx.exception), name),
                                        str(ctx.exception))
                        self.assertNotIn(value, str(ctx.exception))
                with self.subTest(secret=name, value=label, env="dev"):
                    _check(load_settings(base_env(KE_ENV="dev", **{name: value})))

    def test_real_secrets_with_ordinary_characters_are_accepted(self):
        # L1b must not over-refuse: a real secret is not a placeholder.
        for name in secret_env_names():
            for value in (SAFE_SECRET, "Xk9#mP2$vL8@qR4!wZ", "pässwörd-Ünïcode-2026",
                          "日本語パスワード2026", "not changeme",
                          "x-changeme", "change-me-later-9f3a"):
                for env_name in ("prod", "ci"):
                    with self.subTest(secret=name, value=value, env=env_name):
                        _check(load_settings(base_env(KE_ENV=env_name, **{name: value})))

    def test_placeholder_check_is_prefix_only(self):
        for name in secret_env_names():
            for value in ("not-changeme", "xchangeme", SAFE_SECRET):
                with self.subTest(secret=name, value=value):
                    _check(load_settings(base_env(KE_ENV="prod", **{name: value})))

    def test_placeholder_check_reads_no_file(self):
        import builtins
        import io

        settings = load_settings(base_env(KE_ENV="prod",
                                          KE_STORES__POSTGRES__PASSWORD="changeme-x"))
        real_open = builtins.open
        opened: list[str] = []

        def spy_open(file: Any, *args: Any, **kwargs: Any) -> Any:
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        with mock.patch("builtins.open", spy_open), mock.patch.object(io, "open", spy_open):
            with self.assertRaises(_refused()):
                _check(settings)
        self.assertFalse([p for p in opened if ".env" in p], opened)

    def test_env_example_secret_placeholders_are_changeme(self):
        example = read_env_example()
        for name in secret_env_names():
            with self.subTest(secret=name):
                self.assertIn(name, example, f".env.example does not list {name}")
                value = example[name]
                self.assertTrue(value.startswith("changeme-"), f"{name}={value!r}")
                rest = value[len("changeme-"):]
                self.assertTrue(rest, f"{name}: placeholder does not name the key")
                self.assertEqual(rest, rest.lower(), "placeholder key is lowercase (ruling)")
                key_tokens = set(name.lower().replace("__", "_").split("_"))
                rest_tokens = [t for t in rest.replace("_", "-").split("-") if t]
                for token in rest_tokens:
                    self.assertIn(token, key_tokens,
                                  f"{name}: placeholder {value!r} does not name the key")


class StartupTracingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from tests import support

        cls.support = support

    def _run_startup(self, env: dict[str, str]) -> tuple[Any, BaseException | None]:
        from engine.startup import startup

        self.support.EXPORTER.clear()
        result, error = None, None
        with environ(env):
            try:
                result = startup()
            except Exception as exc:
                error = exc
        return result, error

    def test_startup_is_traced(self):
        settings, error = self._run_startup(base_env(KE_ENV="prod"))
        self.assertIsNone(error)
        self.assertEqual(settings.env, "prod")
        spans = self.support.finished_spans()
        for name in ("engine.startup", "engine.config.load", "engine.startup.refusals",
                     "engine.egress.startup_check"):
            with self.subTest(span=name):
                self.assertIn(name, spans)
                self.assertEqual(spans[name].attributes.get("openinference.span.kind"), "CHAIN")
        root = spans["engine.startup"]
        self.assertEqual(root.attributes.get("ke.env"), "prod")
        for child in ("engine.config.load", "engine.startup.refusals"):
            self.assertEqual(spans[child].context.trace_id, root.context.trace_id)
        # No secret value in any span attribute.
        for span in spans.values():
            for value in (span.attributes or {}).values():
                self.assertNotIn(SAFE_SECRET, str(value), span.name)

    def test_refused_startup_marks_spans(self):
        from opentelemetry.trace import StatusCode

        _, error = self._run_startup(base_env(KE_ENV="prod", KE_AUTH__ENABLED="false"))
        self.assertIsInstance(error, _refused())
        spans = self.support.finished_spans()
        self.assertEqual(spans["engine.startup"].status.status_code, StatusCode.ERROR)
        refusals = spans["engine.startup.refusals"]
        self.assertTrue(_names_any(str(refusals.attributes.get("ke.refused_setting")),
                                   "auth.enabled", "KE_AUTH__ENABLED"))

    def test_config_load_span_names_overridden_keys_not_values(self):
        self._run_startup(base_env(KE_ENV="prod", KE_STORES__POSTGRES__PORT="47123"))
        span = self.support.finished_spans()["engine.config.load"]
        rendered = " ".join(str(v) for v in (span.attributes or {}).values())
        self.assertIn("KE_STORES__POSTGRES__PORT", rendered)
        self.assertNotIn("47123", rendered)
        self.assertNotIn(SAFE_SECRET, rendered)

    def test_non_local_collector_gets_no_exporter(self):
        import opentelemetry.exporter.otlp.proto.http.trace_exporter as otlp

        env = base_env(KE_ENV="prod", HARNESS_TRACING="otlp",
                       PHOENIX_COLLECTOR_ENDPOINT="http://collector.example.com:6006")
        spy = SocketSpy()
        with mock.patch.object(otlp, "OTLPSpanExporter") as exporter, spy.active():
            _, error = self._run_startup(env)
        self.assertIsInstance(error, _refused())
        exporter.assert_not_called()
        self.assertEqual(spy.attempts, [])

    def test_configure_tracing_attaches_nothing_for_non_local(self):
        import opentelemetry.exporter.otlp.proto.http.trace_exporter as otlp

        from engine.telemetry import configure_tracing

        env = base_env(KE_ENV="dev", HARNESS_TRACING="otlp",
                       PHOENIX_COLLECTOR_ENDPOINT="http://203.0.113.5:6006")
        settings = load_settings(env)
        with mock.patch.object(otlp, "OTLPSpanExporter") as exporter, environ(env):
            configure_tracing(settings)
        exporter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
