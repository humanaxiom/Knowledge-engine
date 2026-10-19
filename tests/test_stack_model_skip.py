"""platform-stack-ready (2b), PS-2.7 (rest): model-calling tests run or skip
by name (fast), and the unit suite calls no model.

The helper is tests/integration/model.py (`@model_calling`,
`require_model_host`), architecture §2.2 "Where (2b)". These tests drive it
with a fixture suite: the probe is `ModelClient.probe` and the reason comes
from `engine.readiness.classify`, so they are RED until both exist.

- `test_model_tests_skip_with_named_reason`: unreachable host → skipped,
  naming the host and "unreachable" with a vocabulary reason; reachable → runs;
  `KE_MODEL_UPSTREAM` or the operator's `KE_EGRESS_ALLOWLIST` empty → skipped
  "not configured", naming the key, with no probe; a test not marked
  model-calling that hits the probe failure fails rather than skips.
- `test_no_model_calls_in_unit_suite`: the unit gate has no network, and no
  unit test module depends on the model host.
"""

from __future__ import annotations

import errno
import io
import socket
import unittest
from typing import Any
from unittest import mock

from tests.engine_support import ROOT, base_env, environ

UPSTREAM = "modelhost:8000"
CONFIGURED = dict(KE_ENV="ci", KE_MODEL_UPSTREAM=UPSTREAM,
                  KE_EGRESS_ALLOWLIST="gateway,modelhost",
                  KE_MODELS__COMPOSE__BASE_URL="http://gateway:8102/v1")


def _refused() -> Exception:
    import httpx

    error = httpx.ConnectError("[Errno 111] Connection refused")
    error.__cause__ = ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")
    return error


def _fixture_suite() -> unittest.TestSuite:
    from tests.integration.model import model_calling, require_model_host

    class Fixture(unittest.TestCase):
        @model_calling
        def test_marked(self) -> None:
            require_model_host(self)

        def test_unmarked(self) -> None:
            require_model_host(self)

    @model_calling
    class MarkedClass(unittest.TestCase):
        def test_in_marked_class(self) -> None:
            require_model_host(self)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Fixture))
    suite.addTests(loader.loadTestsFromTestCase(MarkedClass))
    return suite


def _run(env: dict[str, str], probe: Any) -> tuple[unittest.TestResult, mock.MagicMock]:
    from tests.integration import model

    model.reset_probe_cache()
    stub = probe if isinstance(probe, mock.MagicMock) else mock.MagicMock(side_effect=probe)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run
    with environ(base_env(**env)), \
            mock.patch("engine.llm.client.ModelClient.probe", stub, create=True):
        outcome = result(_fixture_suite())
    return outcome, stub


def _ids(pairs: list[tuple[Any, str]]) -> dict[str, str]:
    return {test.id().rsplit(".", 1)[-1]: text for test, text in pairs}


class ModelSkipHelperTest(unittest.TestCase):
    def test_model_tests_skip_with_named_reason(self):
        with self.subTest(case="unreachable"):
            outcome, probe = _run(CONFIGURED, _refused())
            skipped = _ids(outcome.skipped)
            self.assertEqual(set(skipped), {"test_marked", "test_in_marked_class"}, skipped)
            for reason in skipped.values():
                self.assertEqual(reason, f"model host unreachable: {UPSTREAM} (refused)")
            self.assertEqual(probe.call_count, 1, "one probe per test run (cached)")
        with self.subTest(case="reachable"):
            outcome, probe = _run(CONFIGURED, None)
            self.assertEqual(outcome.skipped, [])
            self.assertEqual(set(_ids(outcome.failures)), {"test_unmarked"})
            self.assertEqual(outcome.testsRun - len(outcome.failures) - len(outcome.errors), 2,
                             "both marked tests run when the host answers")
            probe.assert_called_once()
            args = probe.call_args.args + tuple(probe.call_args.kwargs.values())
            self.assertIn(2, [int(a) for a in args if isinstance(a, (int, float))],
                          "the probe is bounded by readiness.timeout_s (2 s by default)")

    def test_model_tests_skip_not_configured(self):
        cases = {
            "KE_MODEL_UPSTREAM empty": ({**CONFIGURED, "KE_MODEL_UPSTREAM": ""}, "KE_MODEL_UPSTREAM"),
            "KE_MODEL_UPSTREAM unset": ({k: v for k, v in CONFIGURED.items()
                                         if k != "KE_MODEL_UPSTREAM"}, "KE_MODEL_UPSTREAM"),
            "operator allowlist empty": ({**CONFIGURED, "KE_EGRESS_ALLOWLIST": "gateway,"},
                                         "KE_EGRESS_ALLOWLIST"),
        }
        for case, (env, key) in cases.items():
            with self.subTest(case=case):
                outcome, probe = _run(env, _refused())
                skipped = _ids(outcome.skipped)
                self.assertEqual(set(skipped), {"test_marked", "test_in_marked_class"}, skipped)
                for reason in skipped.values():
                    self.assertIn("not configured", reason)
                    self.assertIn(key, reason)
                    self.assertNotIn("unreachable", reason)
                probe.assert_not_called()

    def test_unmarked_test_fails_rather_than_skips(self):
        for case, env in (("unreachable", CONFIGURED),
                          ("not configured", {**CONFIGURED, "KE_MODEL_UPSTREAM": ""})):
            with self.subTest(case=case):
                outcome, _ = _run(env, _refused())
                self.assertEqual(set(_ids(outcome.failures)), {"test_unmarked"})
                self.assertNotIn("test_unmarked", _ids(outcome.skipped))

    def test_real_probe_of_a_closed_port_skips_as_refused(self):
        # The real ModelClient.probe and classify, against a closed loopback
        # port (gates has `lo` under network_mode: none). No model host.
        from tests.integration import model

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = {**CONFIGURED, "KE_MODELS__COMPOSE__BASE_URL": f"http://127.0.0.1:{port}/v1",
               "KE_EGRESS_ALLOWLIST": "gateway,modelhost,127.0.0.1"}
        model.reset_probe_cache()
        with environ(base_env(**env)):
            outcome = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(_fixture_suite())
        skipped = _ids(outcome.skipped)
        self.assertEqual(set(skipped), {"test_marked", "test_in_marked_class"},
                         f"skipped={skipped} errors={outcome.errors}")
        for reason in skipped.values():
            self.assertEqual(reason, f"model host unreachable: {UPSTREAM} (refused)")


class UnitSuiteModelTest(unittest.TestCase):
    def test_no_model_calls_in_unit_suite(self):
        from tests import compose_support as cs

        gates = cs.services()["gates"]
        self.assertEqual(gates.get("network_mode"), "none",
                         "the unit gate must have no network at all (PS-2.7)")
        allowed = {"test_stack_model_skip.py"}
        for path in sorted((ROOT / "tests").glob("test*.py")):
            if path.name in allowed:
                continue
            with self.subTest(module=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"\brequire_model_host\b|@model_calling\b",
                                    "model-calling tests belong in tests/integration only")


if __name__ == "__main__":
    unittest.main()
