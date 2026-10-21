"""Egress guard (DR30, ADR-KE-010): an allowlist enforced before any socket opens."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import urlsplit

import httpx


class EgressDenied(Exception):
    """A request targeted a host that is not on the egress allowlist."""

    def __init__(self, host: str) -> None:
        super().__init__(f"egress denied: host {host!r} is not on the egress allowlist")
        self.host = host


def normalise_host(host: str) -> str:
    return host.strip().casefold().rstrip(".")


class EgressPolicy:
    """Exact, case-folded host match. No wildcards, no suffix match."""

    def __init__(self, allowlist: Iterable[str]) -> None:
        self.allowlist = frozenset(normalise_host(h) for h in allowlist)

    def allows(self, host: str) -> bool:
        return normalise_host(host) in self.allowlist

    def require(self, host: str) -> None:
        if not self.allows(host):
            raise EgressDenied(host)


class GuardedTransport(httpx.BaseTransport):
    """Checks the host of every request, redirect hops included, before the
    inner transport is called, so a denied host opens no socket."""

    def __init__(self, policy: EgressPolicy, inner: httpx.BaseTransport) -> None:
        self._policy = policy
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._policy.require(request.url.host)
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def host_of(value: str) -> str:
    """The host of a URL or of a bare `host[:port]`."""
    parts = urlsplit(value if "://" in value else f"//{value}")
    return parts.hostname or ""


def is_local_endpoint(url: str, service_names: Iterable[str]) -> bool:
    """Loopback (localhost, 127.0.0.0/8, ::1) or a compose service name."""
    host = normalise_host(host_of(url))
    if not host:
        return False
    if host == "localhost" or host in {normalise_host(n) for n in service_names}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
