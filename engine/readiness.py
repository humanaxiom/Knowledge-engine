"""Readiness probes, the reason vocabulary and the `--wait-for` CLI (PS-2.5).

Architecture §2.4 "/readyz". Each store is probed in two steps, a raw TCP dial
(which gives `refused`, `timeout` and `unreachable` the same way for every
driver) and then the driver's own protocol check. The result never carries
exception text, a DSN, a host or a port: only the fixed vocabulary of
`classify`. Every I/O call goes through its module attribute
(`socket.create_connection`, `psycopg.connect`, ...) so tests can stub it.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import socket
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

import httpx
import neo4j
import neo4j.exceptions
import psycopg
import psycopg.errors
import redis
import redis.exceptions
from opentelemetry.trace import Status, StatusCode

from engine.config import ConfigError, Settings
from engine.egress import EgressDenied
from engine.llm.client import ModelClient
from harness_telemetry import tool_span

__all__ = ["check_all", "classify", "main"]

STORES = ("postgres", "neo4j", "valkey")
DEPENDENCIES = (*STORES, "model_host")
# The CLI runs inside `api` and asks the route of the same container.
LOCAL_HOST = "127.0.0.1"


def _causes(exc: BaseException) -> list[BaseException]:
    """The exception's cause/context chain (excluding itself), cycle-safe."""
    chain: list[BaseException] = [exc]
    current: BaseException | None = exc.__cause__ or exc.__context__
    while current is not None and all(current is not seen for seen in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain[1:]


def classify(exc: BaseException) -> str:
    """Map an exception to one word of the fixed vocabulary; never its text."""
    if isinstance(exc, EgressDenied):
        return "egress_denied"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (401, 403):
            return "auth_failed"
        return f"error:{type(exc).__name__}"
    if isinstance(exc, (neo4j.exceptions.AuthError, redis.exceptions.AuthenticationError)):
        return "auth_failed"
    sqlstate = getattr(exc, "sqlstate", None)
    if isinstance(sqlstate, str) and sqlstate.startswith("28"):
        return "auth_failed"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException, psycopg.errors.ConnectionTimeout)):
        return "timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    if isinstance(exc, httpx.ConnectError):
        causes = _causes(exc)
        if any(isinstance(c, ConnectionRefusedError) for c in causes):
            return "refused"
        if any(isinstance(c, TimeoutError) for c in causes):
            return "timeout"
        if any(isinstance(c, OSError) for c in causes):
            return "unreachable"
    if isinstance(exc, OSError):
        return "unreachable"
    return f"error:{type(exc).__name__}"


def _probe_postgres(settings: Settings, timeout: float) -> None:
    pg = settings.stores.postgres
    with psycopg.connect(
            host=pg.host, port=pg.port, dbname=pg.database, user=pg.user,
            password=pg.password.get_secret_value(), gssencmode="disable",
            connect_timeout=max(2, math.ceil(timeout))) as conn:
        conn.execute("SELECT 1")


def _probe_neo4j(settings: Settings, timeout: float) -> None:
    n4 = settings.stores.neo4j
    driver = neo4j.GraphDatabase.driver(
        f"bolt://{n4.host}:{n4.port}",
        auth=(n4.user, n4.password.get_secret_value()),
        connection_timeout=timeout, connection_acquisition_timeout=timeout)
    try:
        with driver.session() as session:
            session.run("RETURN 1").consume()
    finally:
        driver.close()


def _probe_valkey(settings: Settings, timeout: float) -> None:
    vk = settings.stores.valkey
    client = redis.Redis(host=vk.host, port=vk.port,
                         socket_connect_timeout=timeout, socket_timeout=timeout)
    try:
        client.ping()
    finally:
        client.close()


_DRIVER_STEPS: dict[str, Callable[[Settings, float], None]] = {
    "postgres": _probe_postgres, "neo4j": _probe_neo4j, "valkey": _probe_valkey}


def _probe_store(settings: Settings, store: str, timeout: float) -> str | None:
    target = getattr(settings.stores, store)
    socket.create_connection((target.host, target.port), timeout).close()
    _DRIVER_STEPS[store](settings, timeout)
    return None


def _probe_model_host(settings: Settings, timeout: float) -> str | None:
    """None when it answered, else the reason. Not configured: no I/O."""
    if settings.models.compose.base_url is None or not settings.models.model_upstream:
        return "not_configured"
    client = ModelClient(settings, "compose")
    try:
        client.probe(timeout)
    finally:
        client.close()
    return None


def _run_check(name: str, run: Callable[[], str | None], required: bool) -> dict[str, Any]:
    with tool_span(f"readyz.{name}") as span:
        try:
            reason = run()
        except Exception as exc:  # noqa: BLE001 - only the classified word leaves
            reason = classify(exc)
        ok = reason is None
        span.set_attribute("ke.readyz.ok", ok)
        if not required:
            span.set_attribute("ke.readyz.required", False)
        if reason is not None:
            span.set_attribute("ke.readyz.reason", reason)
            span.set_status(Status(StatusCode.ERROR, reason))
    result: dict[str, Any] = {"ok": ok, "reason": reason}
    if not required:
        result["required"] = False
    return result


def check_all(settings: Settings) -> dict[str, Any]:
    """Probe postgres, neo4j, valkey and the model host, in that order."""
    timeout = settings.readiness.timeout_s
    checks: dict[str, dict[str, Any]] = {}
    for store in STORES:
        checks[store] = _run_check(
            store, functools.partial(_probe_store, settings, store, timeout), required=True)
    checks["model_host"] = _run_check(
        "model_host", lambda: _probe_model_host(settings, timeout), required=False)
    return {"ready": all(checks[s]["ok"] for s in STORES), "checks": checks}


# --- the CLI the smoke runs inside `api` ---------------------------------

def _met(condition: str, status: int | None, body: dict[str, Any] | None) -> bool:
    if status is None or body is None:
        return False
    if condition == "ready":
        return status == 200 and body.get("ready") is True
    dep = condition.split(":", 1)[1]
    check = (body.get("checks") or {}).get(dep) or {}
    return status == 503 and check.get("ok") is False


def _valid_condition(condition: str) -> bool:
    return condition == "ready" or (
        condition.startswith("not-ready:") and condition.split(":", 1)[1] in DEPENDENCIES)


def _fetch(url: str) -> tuple[int | None, str]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=3) as response:
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - reported as a class name only
        return None, f"unreachable ({type(exc).__name__})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.readiness")
    parser.add_argument("--wait-for", required=True, dest="condition",
                        help="ready | not-ready:<postgres|neo4j|valkey|model_host>")
    parser.add_argument("--within", type=float, default=60.0, help="seconds")
    args = parser.parse_args(argv)
    if not _valid_condition(args.condition):
        print(f"usage: unknown condition {args.condition!r}", file=sys.stderr)
        return 2
    try:
        port = Settings().api.listen_port
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    url = f"http://{LOCAL_HOST}:{port}/readyz"
    deadline = time.monotonic() + args.within
    while True:
        status, text = _fetch(url)
        try:
            parsed = json.loads(text)
            body = parsed if isinstance(parsed, dict) else None
        except ValueError:
            body = None
        if _met(args.condition, status, body):
            return 0
        if time.monotonic() + 1 > deadline:
            break
        time.sleep(1)
    print(f"not met within {args.within:g}s: {args.condition}; "
          f"last status {status if status is not None else 'none'}: {text}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
