"""platform-stack-ready (2b), integration: `/readyz` and the worker against the
real stack, in `gates-it` (verify.sh full). Order from docs/architecture.md
§2.6 "platform-stack-ready", Integration.

- `test_readyz_reports_each_dependency` (PS-2.5): GET /readyz on the real api
  gives 200, four checks, the stores ok, and `model_host.required` false.
- `test_readyz_fails_when_store_down` (PS-2.5, *Status and reasons*,
  *Bounded*): in process through the real route, with postgres pointed at a
  closed port on its own host and only the postgres password set to a marker
  (a wrong neo4j password would count toward neo4j's failed-auth lock):
  503, `postgres.reason == "refused"`, the marker nowhere in the body, and an
  answer within `readiness.timeout_s` plus the margin stated below.
- `test_readyz_ready_without_model_host` (PS-2.5, PS-Q6): in process, real
  stores, the compose pass's base URL at a closed gateway port (allowlisted):
  200, `model_host.ok` false with a vocabulary reason.
- `test_worker_consumes_noop_job` (PS-2.6): `engine.jobs.noop` enqueued by
  dotted path on `default` from gates-it is consumed by the real worker
  container: status `finished`, counter exactly 1.
- `test_readyz_reports_reachable_model_host` (PS-2.5, model-calling): skips
  by name through `require_model_host` unless the model host answers.
"""

from __future__ import annotations

import json
import os
import re
import time
import unittest
import urllib.error
import urllib.request
import uuid
from typing import Any

from tests.engine_support import DEFAULTS, load_settings
from tests.integration.model import model_calling, require_model_host
from tests.integration.stack import api_port, require_reachable

VOCABULARY = re.compile(
    r"^(?:timeout|refused|unreachable|auth_failed|egress_denied|not_configured"
    r"|error:[A-Za-z_][A-Za-z0-9_]*)$")
DEPS = {"postgres", "neo4j", "valkey", "model_host"}
MARKER = "pg-marker-pw-integration-5d1c"
# Stated margin for *Bounded*: the refused postgres dial answers at once; the
# other probes (real neo4j, valkey, the model forward) add at most a few
# seconds on a loaded runner.
MARGIN_S = 5.0


def _gates_it_env(**overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("KE_CONFIG_FILE", str(DEFAULTS))
    env["HARNESS_TRACING"] = "off"
    env.update(overrides)
    return env


def _readyz_in_process(**overrides: str) -> tuple[int, dict[str, Any], str, float, Any]:
    from fastapi.testclient import TestClient

    from engine.api import app, get_settings

    settings = load_settings(_gates_it_env(**overrides))
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        started = time.monotonic()
        response = TestClient(app).get("/readyz")
        elapsed = time.monotonic() - started
    finally:
        app.dependency_overrides.pop(get_settings, None)
    return response.status_code, response.json(), response.text, elapsed, settings


def _get_readyz() -> tuple[int, dict[str, Any]]:
    url = f"http://api:{api_port()}/readyz"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class ReadyzIntegrationTest(unittest.TestCase):
    def test_readyz_reports_each_dependency(self):
        require_reachable(self, "api", api_port(), "the api service")
        status, body = _get_readyz()
        self.assertEqual(status, 200, body)
        self.assertIs(body["ready"], True)
        self.assertEqual(set(body["checks"]), DEPS)
        for store in ("postgres", "neo4j", "valkey"):
            with self.subTest(store=store):
                self.assertEqual(body["checks"][store], {"ok": True, "reason": None})
        model = body["checks"]["model_host"]
        self.assertIs(model["required"], False)
        if not model["ok"]:
            self.assertRegex(str(model["reason"]), VOCABULARY)
        # Rework 1, Windows proof F1: api and gates-it get the same
        # ${KE_MODEL_UPSTREAM:-}; with it empty the live stack reports
        # not_configured (not a varying error from the gateway forward).
        if not os.environ.get("KE_MODEL_UPSTREAM"):
            self.assertEqual(model, {"ok": False, "reason": "not_configured", "required": False})

    def test_readyz_fails_when_store_down(self):
        require_reachable(self, "postgres", 5432, "the postgres service")
        status, body, text, elapsed, settings = _readyz_in_process(
            KE_STORES__POSTGRES__PORT="1", KE_STORES__POSTGRES__PASSWORD=MARKER)
        self.assertEqual(status, 503, body)
        self.assertIs(body["ready"], False)
        self.assertIs(body["checks"]["postgres"]["ok"], False)
        self.assertEqual(body["checks"]["postgres"]["reason"], "refused")
        for store in ("neo4j", "valkey"):
            with self.subTest(store=store):
                self.assertIs(body["checks"][store]["ok"], True, body)
        self.assertNotIn(MARKER, text)
        self.assertNotRegex(text, r"postgresql://|password|Traceback")
        self.assertLess(elapsed, settings.readiness.timeout_s + MARGIN_S,
                        f"/readyz took {elapsed:.1f}s with a store down (bound: timeout + {MARGIN_S}s)")

    def test_readyz_ready_without_model_host(self):
        # KE_MODEL_UPSTREAM set so the model host counts as configured
        # (rework 1, F1); the probe still goes to the closed gateway port.
        status, body, _, _, _ = _readyz_in_process(
            KE_MODELS__COMPOSE__BASE_URL="http://gateway:1/v1",
            KE_MODEL_UPSTREAM="modelhost.invalid:11434")
        self.assertEqual(status, 200, body)
        self.assertIs(body["ready"], True)
        model = body["checks"]["model_host"]
        self.assertIs(model["ok"], False)
        self.assertIs(model["required"], False)
        self.assertRegex(str(model["reason"]), VOCABULARY)
        self.assertNotEqual(model["reason"], "not_configured")

    @model_calling
    def test_readyz_reports_reachable_model_host(self):
        require_model_host(self)
        status, body = _get_readyz()
        self.assertEqual(status, 200, body)
        self.assertEqual(body["checks"]["model_host"],
                         {"ok": True, "reason": None, "required": False})


class WorkerIntegrationTest(unittest.TestCase):
    def test_worker_consumes_noop_job(self):
        import redis
        import rq
        from rq.serializers import JSONSerializer

        settings = load_settings(_gates_it_env())
        valkey = settings.stores.valkey
        require_reachable(self, valkey.host, valkey.port, "the valkey service")
        connection = redis.Redis(host=valkey.host, port=valkey.port,
                                 socket_connect_timeout=5, socket_timeout=5)
        self.addCleanup(connection.close)
        token = uuid.uuid4().hex
        # Security M-1 (handoff "orchestrator: rework round 1 of 5"): the worker
        # deserialises JSON only, so the producer enqueues with JSONSerializer.
        queue = rq.Queue("default", connection=connection, serializer=JSONSerializer)
        job = queue.enqueue("engine.jobs.noop", token)
        deadline = time.monotonic() + 60
        status = None
        while time.monotonic() < deadline:
            job.refresh()
            status = job.get_status()
            if status in ("finished", "failed", "stopped", "canceled"):
                break
            time.sleep(0.5)
        self.assertEqual(str(getattr(status, "value", status)), "finished",
                         f"the worker did not finish the noop job within 60 s (status {status})")
        self.assertEqual(connection.get(f"ke:noop:{token}"), b"1",
                         "the noop job must run exactly once")
        time.sleep(2)
        self.assertEqual(connection.get(f"ke:noop:{token}"), b"1", "the job ran again")


if __name__ == "__main__":
    unittest.main()
