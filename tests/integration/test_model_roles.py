"""model-roles MR-5, integration (model-calling, `verify.sh full`): each model
role answers through the stack's gateway forward. Design: docs/architecture.md
§2.4 *Model roles* and §2.6 *model-roles*; ADR-KE-014.

- `test_embed_role_answers`: `ModelClient(settings, "embed")`, POST
  `{base_url}/embeddings` through `client.http_client` (guarded transport,
  `trust_env=False`, the embed role's timeout); HTTP 200, exactly one `data`
  item, its vector length is `models.embed.dim`.
- `test_compose_role_answers`, `test_rewrite_role_answers`,
  `test_audit_role_answers`: `ModelClient(settings, <role>).complete()`
  unchanged (no `max_tokens`, no system prompt), one user message asking for
  one word; HTTP 200, `result["model"] == client.model`, and
  `choices[0].message.content.strip()` non-empty. Reasoning alone is not an
  answer. A failure names `finish_reason` and the message's key names, never
  their values; a model mismatch does not print the response's model; an embed
  non-200 names the status code and content type, never the body.
- Each asserts the role's `base_url` host is the stack's `gateway` service.
- Each is `@model_calling` and calls `require_model_host(self)` first, so
  without `KE_MODEL_UPSTREAM` and `KE_EGRESS_ALLOWLIST` it skips with PS-2.7's
  "not configured" reason.
- Each writes one stderr line around its one model call:
  `model-role <role> <model> <seconds>s` (MR-5 per-role time).
- Order embed, compose, rewrite, audit is fixed by `load_tests` (unittest
  would otherwise sort audit first); no warm-up.
"""

from __future__ import annotations

import sys
import time
import unittest
from typing import Any
from urllib.parse import urlsplit

from tests.integration.model import STACK_FORWARD, model_calling, require_model_host

ROLES_IN_ORDER = ("embed", "compose", "rewrite", "audit")
PROMPT = [{"role": "user", "content": "Reply with the single word: ready"}]
EMBED_INPUT = "ready"


def _timing_line(role: str, model: str, seconds: float) -> None:
    print(f"model-role {role} {model} {seconds:.1f}s", file=sys.stderr, flush=True)


class ModelRolesTest(unittest.TestCase):
    def _client(self, role: str) -> tuple[Any, Any, list[int]]:
        from engine.config import Settings
        from engine.llm.client import ModelClient

        settings = Settings()
        client = ModelClient(settings, role)
        self.addCleanup(client.close)
        self.assertIsNotNone(client.base_url, f"models.{role}.base_url is not set")
        host = urlsplit(client.base_url).hostname
        self.assertEqual(host, STACK_FORWARD,
                         f"models.{role}.base_url must go through the stack's gateway "
                         f"forward, not host {host!r}")
        statuses: list[int] = []
        hooks = client.http_client.event_hooks
        hooks["response"] = [*hooks.get("response", []),
                             lambda response: statuses.append(response.status_code)]
        client.http_client.event_hooks = hooks
        return settings, client, statuses

    def _chat_role_answers(self, role: str) -> None:
        _, client, statuses = self._client(role)
        started = time.monotonic()
        try:
            result = client.complete(PROMPT)
        finally:
            _timing_line(role, client.model, time.monotonic() - started)
        self.assertEqual(statuses, [200], f"{role}: HTTP status of the completion")
        # assertTrue, not assertEqual: the diff would print the response's value.
        self.assertTrue(result.get("model") == client.model,
                        f"{role}: the response names a different model")
        choices = result.get("choices") or []
        self.assertTrue(choices, f"{role} ({client.model}): the response has no choices")
        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = message.get("content")
        self.assertTrue(
            isinstance(content, str) and content.strip(),
            f"{role} ({client.model}) returned no content: "
            f"finish_reason={choice.get('finish_reason')!r}, "
            f"message keys={sorted(message)}")

    @model_calling
    def test_embed_role_answers(self):
        require_model_host(self)
        settings, client, statuses = self._client("embed")
        url = f"{client.base_url.rstrip('/')}/embeddings"
        started = time.monotonic()
        try:
            response = client.http_client.post(
                url, json={"model": client.model, "input": EMBED_INPUT})
        finally:
            _timing_line("embed", client.model, time.monotonic() - started)
        # Status and content type only, never the body (a server value).
        self.assertEqual(response.status_code, 200,
                         f"embed ({client.model}): HTTP {response.status_code}, "
                         f"content-type {response.headers.get('content-type')!r}")
        self.assertEqual(statuses, [200], "embed: HTTP status of the request")
        data = response.json().get("data") or []
        self.assertEqual(len(data), 1, f"embed: expected one data item, got {len(data)}")
        vector = data[0].get("embedding") or []
        self.assertEqual(len(vector), settings.models.embed.dim,
                         f"embed ({client.model}): vector length")

    @model_calling
    def test_compose_role_answers(self):
        require_model_host(self)
        self._chat_role_answers("compose")

    @model_calling
    def test_rewrite_role_answers(self):
        require_model_host(self)
        self._chat_role_answers("rewrite")

    @model_calling
    def test_audit_role_answers(self):
        require_model_host(self)
        self._chat_role_answers("audit")


def load_tests(loader: unittest.TestLoader, standard_tests: unittest.TestSuite,
               pattern: str | None) -> unittest.TestSuite:
    """embed (smallest load), compose and rewrite (one shared load), audit
    (largest) last (§2.4 *Model roles*, run order and cold loads)."""
    return unittest.TestSuite(ModelRolesTest(f"test_{role}_role_answers")
                              for role in ROLES_IN_ORDER)
