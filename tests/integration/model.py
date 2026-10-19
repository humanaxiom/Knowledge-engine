"""The model-calling test helper (not a test module): PS-2.7 *Model-calling
tests run or skip by name*, docs/architecture.md §2.2 "Where (2b)".

A model-calling integration test is marked with `@model_calling` (on the
method or its class) and calls `require_model_host(self)` first:

- `KE_MODEL_UPSTREAM` empty or unset in the gates-it environment, or no
  operator entry in `KE_EGRESS_ALLOWLIST` (the app form is
  `gateway,<operator list>`, §2.4 Model wiring): skip, naming the key, "not
  configured", with no probe (umbrella ruling, PS-2.21).
- Otherwise one reachability probe per process (cached):
  `ModelClient(settings, "compose").probe(readiness.timeout_s)`, which goes
  through the egress guard. A failure skips with
  `model host unreachable: <KE_MODEL_UPSTREAM> (<reason>)`, the reason from
  `engine.readiness.classify`, the same vocabulary as `/readyz`.
- A test that is not marked model-calling never skips on network grounds:
  calling the helper from one fails it (ADR-KE-009, PS-2.7).
"""

from __future__ import annotations

import os
import unittest
from typing import TypeVar

T = TypeVar("T")

NOT_CONFIGURED = ("model host not configured: {key} is empty (set it and {other} in the "
                  "caller environment or .env)")
UNREACHABLE = "model host unreachable: {upstream} ({reason})"
STACK_FORWARD = "gateway"  # the stack's own model forward, in the app allowlist by topology

_probe_cache: dict[str, str | None] = {}


def model_calling(obj: T) -> T:
    """Mark a test method or class as calling the model host."""
    setattr(obj, "model_calling", True)
    return obj


def reset_probe_cache() -> None:
    _probe_cache.clear()


def _is_marked(test: unittest.TestCase) -> bool:
    method = getattr(test, test._testMethodName, None)
    return bool(getattr(type(test), "model_calling", False)
                or getattr(method, "model_calling", False))


def _probe_reason() -> str | None:
    """None when the model host answered; otherwise a vocabulary reason."""
    if "reason" in _probe_cache:
        return _probe_cache["reason"]
    from engine.config import Settings
    from engine.llm.client import ModelClient
    from engine.readiness import classify

    settings = Settings()
    reason: str | None
    if settings.models.compose.base_url is None:
        reason = "not_configured"
    else:
        client = ModelClient(settings, "compose")
        try:
            client.probe(settings.readiness.timeout_s)
        except Exception as exc:  # noqa: BLE001 - classified, never re-raised
            reason = classify(exc)
        else:
            reason = None
        finally:
            client.close()
    _probe_cache["reason"] = reason
    return reason


def require_model_host(test: unittest.TestCase) -> None:
    if not _is_marked(test):
        test.fail("require_model_host() called from a test that is not marked @model_calling: "
                  "only model-calling tests may depend on the model host, and no other test "
                  "may skip on network grounds (PS-2.7, ADR-KE-009)")
    upstream = os.environ.get("KE_MODEL_UPSTREAM", "").strip()
    if not upstream:
        raise unittest.SkipTest(NOT_CONFIGURED.format(key="KE_MODEL_UPSTREAM",
                                                      other="KE_EGRESS_ALLOWLIST"))
    operator = [h.strip() for h in os.environ.get("KE_EGRESS_ALLOWLIST", "").split(",")
                if h.strip() and h.strip().lower() != STACK_FORWARD]
    if not operator:
        raise unittest.SkipTest(NOT_CONFIGURED.format(key="KE_EGRESS_ALLOWLIST",
                                                      other="KE_MODEL_UPSTREAM"))
    reason = _probe_reason()
    if reason is not None:
        raise unittest.SkipTest(UNREACHABLE.format(upstream=upstream, reason=reason))
