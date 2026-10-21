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
- model-roles (MR-5, §2.4 *Model roles*): `ModelRolesSuiteTest` drives
  tests/integration/test_model_roles.py with no model host. Keys unset: the
  four role tests skip "not configured" with no probe. Order: embed,
  compose, rewrite, audit via `load_tests`. Against a stub transport: the
  assertions §2.4 states, the stderr timing lines, and failure messages that
  name `finish_reason` and message keys but never their values.
"""

from __future__ import annotations

import ast
import contextlib
import errno
import inspect
import io
import json
import re
import socket
import textwrap
import unittest
from typing import Any
from unittest import mock

from tests.engine_support import ROOT, base_env, environ, load_settings

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


ROLE_ORDER = ["test_embed_role_answers", "test_compose_role_answers",
              "test_rewrite_role_answers", "test_audit_role_answers"]
ROLES = ("embed", "compose", "rewrite", "audit")
# The real-run shape (§2.4 Model wiring): the app allowlist is `gateway,<model
# host>`, so the guard alone would let a direct request to the model host
# through; the stub's host record is what proves every call went via gateway.
ROLES_ENV = dict(KE_ENV="ci", KE_MODEL_UPSTREAM=UPSTREAM,
                 KE_EGRESS_ALLOWLIST="gateway,modelhost",
                 **{f"KE_MODELS__{r.upper()}__BASE_URL": "http://gateway:8102/v1" for r in ROLES})
HIDDEN = "hidden-reasoning-value-3b8d"  # a response value that no output may carry
OTHER_MODEL = "other-model-value-5e1a"  # the response's model name, also a value
TIMING = re.compile(r"^model-role (embed|compose|rewrite|audit) (\S+) (\d+\.\d)s$")


def _role_module() -> Any:
    from tests.integration import test_model_roles

    return test_model_roles


def _role_suite() -> unittest.TestSuite:
    # loadTestsFromModule honours the module's load_tests, as discover does.
    return unittest.TestLoader().loadTestsFromModule(_role_module())


def _flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    out: list[unittest.TestCase] = []
    for item in suite:
        out.extend(_flatten(item) if isinstance(item, unittest.TestSuite) else [item])
    return out


class _Stub:
    """A stub model host. Records the host of every request it is sent, so a
    case can assert that each one went through the stack's `gateway`. Every
    response carries HIDDEN as a value, so any output that echoes a response
    shows it."""

    def __init__(self, *, content: str = "ready", finish: str = "stop", dim: int = 768,
                 model: str | None = None, extra: dict[str, Any] | None = None,
                 embed_status: int = 200) -> None:
        self.content, self.finish, self.dim = content, finish, dim
        self.model, self.extra, self.embed_status = model, extra or {}, embed_status
        self.hosts: list[str] = []

    def __call__(self, request: Any) -> Any:
        import httpx

        self.hosts.append(request.url.host)
        body = json.loads(request.content)
        name = self.model or body["model"]
        if request.url.path.endswith("/embeddings"):
            if self.embed_status != 200:
                return httpx.Response(self.embed_status, text=f"<html>{HIDDEN}</html>",
                                      headers={"content-type": "text/html"})
            return httpx.Response(200, json={"model": name, "id": HIDDEN,
                                             "data": [{"embedding": [0.0] * self.dim}]})
        message = {"role": "assistant", "content": self.content, **self.extra}
        return httpx.Response(200, json={"model": name, "id": HIDDEN, "choices": [
            {"index": 0, "message": message, "finish_reason": self.finish}]})


def _stub(**kwargs: Any) -> _Stub:
    return _Stub(**kwargs)


def _run_roles(handler: Any, **env: str) -> tuple[unittest.TestResult, str]:
    """Run the role suite with the host check stubbed and a stub transport."""
    import httpx

    module = _role_module()
    err = io.StringIO()
    with environ(base_env(**{**ROLES_ENV, **env})), \
            mock.patch.object(module, "require_model_host", lambda test: None), \
            mock.patch("httpx.HTTPTransport",
                       lambda *a, **k: httpx.MockTransport(handler)), \
            contextlib.redirect_stderr(err):
        outcome = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(_role_suite())
    return outcome, err.getvalue()


class ModelRolesSuiteTest(unittest.TestCase):
    def test_model_role_tests_run_in_order(self):
        module = _role_module()
        names = [t._testMethodName for t in _flatten(_role_suite())]
        self.assertEqual(names, ROLE_ORDER)
        declared = {name for _, cls in inspect.getmembers(module, inspect.isclass)
                    if issubclass(cls, unittest.TestCase)
                    for name in unittest.TestLoader().getTestCaseNames(cls)}
        self.assertEqual(declared, set(ROLE_ORDER), "every role test is in load_tests")
        for test in _flatten(_role_suite()):
            name = test._testMethodName
            with self.subTest(test=name):
                method = getattr(type(test), name)
                self.assertIs(getattr(method, "model_calling", False), True,
                              f"{name} is not marked @model_calling")
                tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
                first = tree.body[0].body[0]
                self.assertEqual(ast.unparse(first), "require_model_host(self)",
                                 f"{name} must call require_model_host(self) first")

    def test_model_role_tests_skip_not_configured(self):
        from tests.integration import model
        from tests.integration.model import NOT_CONFIGURED

        cases = {
            "keys unset": ({"KE_ENV": "ci"}, "KE_MODEL_UPSTREAM", "KE_EGRESS_ALLOWLIST"),
            "operator allowlist empty": ({"KE_ENV": "ci", "KE_MODEL_UPSTREAM": UPSTREAM,
                                          "KE_EGRESS_ALLOWLIST": "gateway"},
                                         "KE_EGRESS_ALLOWLIST", "KE_MODEL_UPSTREAM"),
        }
        for case, (env, key, other) in cases.items():
            with self.subTest(case=case):
                model.reset_probe_cache()
                probe = mock.MagicMock()
                with environ(base_env(**env)), \
                        mock.patch("engine.llm.client.ModelClient.probe", probe, create=True):
                    outcome = unittest.TextTestRunner(stream=io.StringIO(),
                                                      verbosity=0).run(_role_suite())
                self.assertEqual((outcome.failures, outcome.errors), ([], []))
                skipped = _ids(outcome.skipped)
                self.assertEqual(list(skipped), ROLE_ORDER)
                for reason in skipped.values():
                    self.assertEqual(reason, NOT_CONFIGURED.format(key=key, other=other))
                probe.assert_not_called()

    def _checked(self, outcome: unittest.TestResult, err: str, stub: _Stub,
                 timing_lines: int) -> dict[str, str]:
        """The checks every stub case shares; returns the failures by test name.

        - stderr holds only timing lines (L-MR2): nothing a role test prints
          may carry a prompt, an input or a response.
        - no failure text and no stderr line carries a response value (L-MR3).
        - every request the stub saw went to the stack's gateway (L-MR1).
        """
        self.assertEqual(outcome.errors, [], "role tests fail by assertion, never by error")
        self.assertEqual(set(stub.hosts), {"gateway"},
                         "every request reaches the model through the stack's gateway")
        lines = err.splitlines()
        for line in lines:
            self.assertRegex(line, TIMING, f"stderr carries only timing lines; stderr={err!r}")
        self.assertEqual(len(lines), timing_lines, f"stderr={err!r}")
        failed = _ids(outcome.failures)
        for name, text in failed.items():
            with self.subTest(test=name):
                self.assertNotIn(HIDDEN, text, "a failure message echoes a response value")
                self.assertNotIn(OTHER_MODEL, text, "a failure message echoes the response model")
        self.assertNotIn(HIDDEN, err)
        return failed

    def test_model_role_assertions_on_a_stub_host(self):
        settings = load_settings(base_env(**ROLES_ENV))
        models = {r: getattr(settings.models, r).model for r in ROLES}

        with self.subTest(case="answers"):
            stub = _stub()
            outcome, err = _run_roles(stub)
            self.assertTrue(outcome.wasSuccessful(), outcome.failures + outcome.errors)
            self.assertEqual(outcome.testsRun, 4)
            self._checked(outcome, err, stub, timing_lines=4)
            self.assertEqual(len(stub.hosts), 4, "one request per role")
            lines = [TIMING.match(line).groups() for line in err.splitlines()]
            self.assertEqual([(r, m) for r, m, _ in lines], [(r, models[r]) for r in ROLES],
                             f"one timing line per role, in order; stderr={err!r}")

        with self.subTest(case="reasoning only, no content"):
            stub = _stub(content="", finish="length", extra={"reasoning": HIDDEN})
            outcome, err = _run_roles(stub)
            failed = self._checked(outcome, err, stub, timing_lines=4)
            self.assertEqual(set(failed), set(ROLE_ORDER[1:]))
            for name, text in failed.items():
                with self.subTest(test=name):
                    self.assertIn("finish_reason='length'", text)
                    self.assertIn("'reasoning'", text)

        with self.subTest(case="whitespace content"):
            stub = _stub(content="  \n", extra={"reasoning": HIDDEN})
            outcome, err = _run_roles(stub)
            failed = self._checked(outcome, err, stub, timing_lines=4)
            self.assertEqual(set(failed), set(ROLE_ORDER[1:]))

        with self.subTest(case="response names another model"):
            stub = _stub(model=OTHER_MODEL, content=HIDDEN)
            outcome, err = _run_roles(stub)
            failed = self._checked(outcome, err, stub, timing_lines=4)
            self.assertEqual(set(failed), set(ROLE_ORDER[1:]))
            for name, text in failed.items():
                with self.subTest(test=name):
                    self.assertIn("names a different model", text)

        with self.subTest(case="embedding of the wrong length"):
            stub = _stub(dim=767)
            outcome, err = _run_roles(stub)
            failed = self._checked(outcome, err, stub, timing_lines=4)
            self.assertEqual(set(failed), {"test_embed_role_answers"})

        with self.subTest(case="embed endpoint answers non-200"):
            # L-MR5: the failure names the status code and content type only,
            # never the body (an upstream error page is a server value).
            stub = _stub(embed_status=500)
            outcome, err = _run_roles(stub)
            failed = self._checked(outcome, err, stub, timing_lines=4)
            self.assertEqual(set(failed), {"test_embed_role_answers"})
            text = failed["test_embed_role_answers"]
            self.assertIn("500", text)
            self.assertIn("text/html", text)

        for role in ROLES:
            with self.subTest(case="base_url not through the gateway", role=role):
                # L-MR4: every role, embed included, refuses a base_url that
                # bypasses the gateway, before any request is sent.
                stub = _stub()
                outcome, err = _run_roles(
                    stub, **{f"KE_MODELS__{role.upper()}__BASE_URL": "http://modelhost:8000/v1"})
                failed = self._checked(outcome, err, stub, timing_lines=3)
                name = f"test_{role}_role_answers"
                self.assertEqual(set(failed), {name})
                self.assertIn("gateway", failed[name])
                self.assertEqual(len(stub.hosts), 3, "the misrouted role sends no request")


if __name__ == "__main__":
    unittest.main()
