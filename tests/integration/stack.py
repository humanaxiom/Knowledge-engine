"""Helpers for the integration tests (not a test module).

Ports come from the container environment first, then from the committed
defaults (.env.example for compose keys, config/defaults.yaml for app keys),
so the tests follow the same single source per port as the stack (§2.4).
"""

from __future__ import annotations

import os
import socket
import unittest

from tests.engine_support import DEFAULTS, read_env_example

WHERE = ("tests/integration runs only in the gates-it compose service on the "
         "backend network, against a launched stack (PS-2.7, ADR-KE-009). Is "
         "gates-it wired in the compose file and the stack up?")


def env_example_value(name: str, test: unittest.TestCase) -> str:
    value = os.environ.get(name) or read_env_example().get(name)
    if not value:
        test.fail(f"{name} is set neither in the gates-it environment nor in .env.example (§2.4)")
    return str(value)


def api_port() -> int:
    if os.environ.get("KE_API__LISTEN_PORT"):
        return int(os.environ["KE_API__LISTEN_PORT"])
    import yaml

    return int(yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))["api"]["listen_port"])


def require_reachable(test: unittest.TestCase, host: str, port: int, what: str) -> None:
    """Fail (never skip) with a clear reason if host:port does not accept."""
    try:
        with socket.create_connection((host, port), timeout=5):
            return
    except OSError as exc:
        test.fail(f"{what} at {host}:{port} is not reachable from this container "
                  f"({type(exc).__name__}: {exc}). {WHERE}")
