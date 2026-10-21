"""One TCP connect, one word: the `ci/offline` probe (PS-3.3, architecture §2.5).

    python -m engine.netprobe <ip> <port> --within <seconds>

Prints exactly one of `connected`, `no_route`, `refused`, `timeout` or
`error:<name>`, or `bad_arguments` for anything but an IPv4 literal, a port
1 to 65535 and a finite `--within` above 0 and at most 3600 (nothing is resolved or opened).
The exit code is 0 only for `connected`, so a shell can use the
word for the message and the code for the verdict.

It runs no `startup()`, opens no span (it is not an agent step) and reads
nothing but its arguments.
"""

from __future__ import annotations

import argparse
import errno
import ipaddress
import math
import socket
from typing import NoReturn

MAX_WITHIN = 3600.0  # seconds; settimeout() overflows on huge values (review NB1)
BAD_ARGUMENTS = "bad_arguments"
CONNECTED = "connected"
NO_ROUTE = "no_route"
REFUSED = "refused"
TIMEOUT = "timeout"

_NO_ROUTE_ERRNOS = frozenset({errno.ENETUNREACH, errno.EHOSTUNREACH})


def probe(host: str, port: int, within: float) -> str:
    """Connect once to host:port, waiting at most `within` seconds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(within)
        sock.connect((host, port))
    except TimeoutError:  # socket.timeout is TimeoutError since Python 3.10
        return TIMEOUT
    except OSError as exc:
        if exc.errno in _NO_ROUTE_ERRNOS:
            return NO_ROUTE
        if exc.errno == errno.ECONNREFUSED or isinstance(exc, ConnectionRefusedError):
            return REFUSED
        name = errno.errorcode.get(exc.errno or 0, type(exc).__name__)
        return f"error:{name}"
    finally:
        sock.close()
    return CONNECTED


class _BadArguments(Exception):
    """The command line is not `<ipv4> <port 1-65535> --within <0 < seconds <= 3600>`."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _BadArguments(message)


def _parse(argv: list[str] | None) -> tuple[str, int, float]:
    """Validate the arguments. A host is only ever an IPv4 literal (no lookup)."""
    parser = _Parser(prog="python -m engine.netprobe", description=__doc__, add_help=False, allow_abbrev=False)
    parser.add_argument("host", help="IPv4 address to connect to")
    parser.add_argument("port", help="TCP port, 1 to 65535")
    parser.add_argument("--within", required=True, help="connect timeout in seconds, above 0")
    args = parser.parse_args(argv)
    try:
        host = str(ipaddress.IPv4Address(args.host))
    except ValueError:
        raise _BadArguments("host") from None
    if not (args.port.isascii() and args.port.isdigit()) or not 1 <= int(args.port) <= 65535:
        raise _BadArguments("port")
    try:
        within = float(args.within)
    except ValueError:
        raise _BadArguments("within") from None
    if not math.isfinite(within) or not 0 < within <= MAX_WITHIN:
        raise _BadArguments("within")
    return host, int(args.port), within


def main(argv: list[str] | None = None) -> int:
    try:
        host, port, within = _parse(argv)
    except _BadArguments:
        print(BAD_ARGUMENTS)
        return 1
    word = probe(host, port, within)
    print(word)
    return 0 if word == CONNECTED else 1


if __name__ == "__main__":
    raise SystemExit(main())
