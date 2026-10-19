"""Shared helpers for the platform-config tests (tests/test_engine_*.py).

Not a test module (no `test` prefix), so scripts/test.sh never runs it on its
own. Nothing here imports `engine`, pydantic or httpx at module import time:
each test imports them itself, so a missing package or dependency fails every
test separately instead of hiding them behind one module import error.
"""

from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = ROOT / "config" / "defaults.yaml"
ENV_EXAMPLE = ROOT / ".env.example"

# The two secrets the design names (ADR-KE-010, §2.3 "Secrets"). Any further
# SecretStr field on Settings is discovered by secret_env_names().
KNOWN_SECRETS = ("KE_STORES__POSTGRES__PASSWORD", "KE_STORES__NEO4J__PASSWORD")

# A value no placeholder check may refuse and no message may contain.
SAFE_SECRET = "s3cr3t-value-never-in-messages"


def settings_cls() -> Any:
    from engine.config import Settings

    return Settings


def config_error() -> type[Exception]:
    from engine.config import ConfigError

    return ConfigError


def _secret_paths(model: Any, prefix: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
    import typing

    from pydantic import BaseModel, SecretStr

    for name, field in model.model_fields.items():
        annotation = field.annotation
        candidates = typing.get_args(annotation) or (annotation,)
        for candidate in candidates:
            if candidate is SecretStr:
                yield (*prefix, name)
                break
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                yield from _secret_paths(candidate, (*prefix, name))
                break


def secret_env_names() -> list[str]:
    """`KE_A__B__C` for every SecretStr field of Settings, at any depth."""
    return sorted("KE_" + "__".join(p).upper() for p in _secret_paths(settings_cls(), ()))


def base_env(**overrides: str) -> dict[str, str]:
    """A complete, safe environment: defaults file, every secret, tracing off."""
    env = {
        "KE_CONFIG_FILE": str(DEFAULTS),
        "HARNESS_TRACING": "off",
        "PATH": os.environ.get("PATH", ""),
    }
    for name in {*KNOWN_SECRETS, *secret_env_names()}:
        env[name] = SAFE_SECRET
    env.update(overrides)
    return env


@contextmanager
def environ(env: dict[str, str]) -> Iterator[None]:
    """Replace the whole process environment (no stray KE_ variables)."""
    with mock.patch.dict(os.environ, env, clear=True):
        yield


def load_settings(environment: dict[str, str] | None = None, **init: Any) -> Any:
    """Build Settings under `environment` (default: base_env()).

    The first parameter is deliberately not `env`: `env=` is a Settings init
    kwarg that test_config_init_args_take_precedence passes through **init."""
    with environ(base_env() if environment is None else environment):
        return settings_cls()(**init)


class SocketSpy:
    """Records every attempt to resolve or connect, and refuses all of them.

    Unit tests run with no network: anything that reaches the socket layer is
    both recorded (so a test can assert zero attempts) and stopped."""

    def __init__(self) -> None:
        self.attempts: list[tuple[str, tuple[Any, ...]]] = []

    def _refuse(self, kind: str):
        def refuse(*args: Any, **kwargs: Any) -> Any:
            self.attempts.append((kind, args))
            raise OSError(f"network disabled in unit tests ({kind})")

        return refuse

    @contextmanager
    def active(self) -> Iterator["SocketSpy"]:
        with mock.patch.object(socket.socket, "connect", self._refuse("connect")), \
                mock.patch.object(socket.socket, "connect_ex", self._refuse("connect_ex")), \
                mock.patch.object(socket, "create_connection", self._refuse("create_connection")), \
                mock.patch.object(socket, "getaddrinfo", self._refuse("getaddrinfo")):
            yield self


def read_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.split(" #", 1)[0].strip().strip('"').strip("'")
    return values
