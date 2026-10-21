"""platform-config rework 1, review N12: every ModelClient call is traced.

Contract (docs/architecture.md §2.3 span table and "N12 (rework 1)"): every
`ModelClient` call method opens `llm_span(f"model.{pass}")` around the HTTP
request; the span is kind LLM, carries the model name, and is ERROR when the
egress guard denies the host.

`ModelClient` had no call method when this test was written. The first one is
pinned here as `complete(messages)`: an OpenAI-compatible
`POST {base_url}/chat/completions` with body `{"model": <pass model>,
"messages": messages}`, returning the decoded JSON response. The HTTP layer is
an `httpx.MockTransport` swapped in for `httpx.HTTPTransport`, so the guard
still runs first and no socket is opened.
"""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest import mock

from tests.engine_support import SocketSpy, base_env, load_settings

ALLOWED = "model-host.internal"
DENIED = "denied.example"
MESSAGES = [{"role": "user", "content": "say hi"}]


class ModelClientTracingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from tests import support

        cls.support = support

    def _client(self, base_url: str, handler: Any) -> Any:
        import httpx

        from engine.llm.client import ModelClient

        settings = load_settings(base_env(
            KE_EGRESS_ALLOWLIST=ALLOWED, KE_MODELS__COMPOSE__BASE_URL=base_url))
        with mock.patch.object(httpx, "HTTPTransport",
                               lambda *a, **k: httpx.MockTransport(handler)):
            client = ModelClient(settings, "compose")
        self.addCleanup(client.close)
        return client, settings

    def test_complete_emits_llm_span_with_model_name(self):
        import httpx

        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}})

        client, settings = self._client(f"http://{ALLOWED}:9000/v1", handler)
        model = settings.models.compose.model
        self.support.EXPORTER.clear()
        result = client.complete(MESSAGES)

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].method, "POST")
        self.assertEqual(str(seen[0].url), f"http://{ALLOWED}:9000/v1/chat/completions")
        body = json.loads(seen[0].content)
        self.assertEqual(body["model"], model)
        self.assertEqual(body["messages"], MESSAGES)
        self.assertEqual(result["choices"][0]["message"]["content"], "hi")

        spans = self.support.finished_spans()
        self.assertIn("model.compose", spans, sorted(spans))
        span = spans["model.compose"]
        self.assertEqual(span.attributes.get("openinference.span.kind"), "LLM")
        self.assertEqual(span.attributes.get("llm.model_name"), model)

    def test_denied_host_marks_llm_span_error(self):
        from opentelemetry.trace import StatusCode

        from engine.egress import EgressDenied

        called: list[Any] = []

        def handler(request: Any) -> Any:
            called.append(request)
            raise AssertionError("the inner transport must not be reached")

        client, _ = self._client(f"http://{DENIED}:9000/v1", handler)
        self.support.EXPORTER.clear()
        spy = SocketSpy()
        with spy.active(), self.assertRaises(EgressDenied):
            client.complete(MESSAGES)
        self.assertEqual(called, [])
        self.assertEqual(spy.attempts, [])
        span = self.support.finished_spans()["model.compose"]
        self.assertEqual(span.attributes.get("openinference.span.kind"), "LLM")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)


if __name__ == "__main__":
    unittest.main()
