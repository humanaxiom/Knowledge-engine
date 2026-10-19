"""Per-pass model client: a guarded httpx client for an OpenAI-compatible host."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from engine.config import Settings
from engine.egress import EgressPolicy, GuardedTransport
from harness_telemetry import llm_span, record_token_usage

PassName = Literal["compose", "rewrite", "audit", "embed"]


class ModelClient:
    """Holds the one httpx client a pass talks through.

    `trust_env=False` keeps proxy variables from rerouting it, and every
    request (and redirect hop) passes the egress allowlist first.
    """

    def __init__(self, settings: Settings, pass_name: PassName) -> None:
        config = settings.models.passes()[pass_name]
        self.pass_name = pass_name
        self.model = config.model
        self.base_url = str(config.base_url) if config.base_url else None
        policy = EgressPolicy(settings.egress_allowlist)
        self.http_client = httpx.Client(
            transport=GuardedTransport(policy, httpx.HTTPTransport()),
            trust_env=False,
            follow_redirects=True,
            timeout=config.timeout_s,
        )

    def complete(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """POST an OpenAI-compatible chat completion; the call is an LLM span."""
        if not self.base_url:
            raise ValueError(f"no base_url is configured for the {self.pass_name} pass")
        with llm_span(f"model.{self.pass_name}", input=messages, model=self.model) as span:
            response = self.http_client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json={"model": self.model, "messages": messages})
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            usage = result.get("usage") or {}
            prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if isinstance(prompt, int) and isinstance(completion, int):
                record_token_usage(span, prompt, completion)
            return result

    def probe(self, timeout: float) -> None:
        """GET `{base_url}/models` through the guarded client, bounded by
        `timeout`. Not an LLM call (no prompt, no tokens), so no `llm_span`;
        the caller's readiness span covers it. Raises on any failure."""
        if not self.base_url:
            raise ValueError(f"no base_url is configured for the {self.pass_name} pass")
        response = self.http_client.get(f"{self.base_url.rstrip('/')}/models", timeout=timeout)
        response.raise_for_status()

    def close(self) -> None:
        self.http_client.close()
