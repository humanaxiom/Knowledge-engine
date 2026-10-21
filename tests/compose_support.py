"""Compose-file helpers for the platform-stack tests (not a test module).

Parses every compose file in the repository root with a YAML loader that
understands Compose's `!reset` and `!override` tags (the verify overlay uses
`!reset` to drop published ports, architecture §2.2).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tests.engine_support import ROOT

MAIN_COMPOSE = ROOT / "docker-compose.yml"

# PS-2.1 and architecture §2.1.
STACK_SERVICES = ("gateway", "api", "worker", "postgres", "neo4j", "valkey", "phoenix")
ONE_SHOT_SERVICES = ("gates", "gates-it")

BIND_DEFAULT = "${KE_BIND_ADDRESS:-127.0.0.1}"
SOCKET_MARKERS = ("docker.sock", "//./pipe/docker_engine", r"\\.\pipe\docker_engine")

_DEFAULT = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?-([^}]*)\}")


def compose_files() -> list[Path]:
    found = {*ROOT.glob("docker-compose*.yml"), *ROOT.glob("docker-compose*.yaml"),
             *ROOT.glob("compose*.yml"), *ROOT.glob("compose*.yaml")}
    return sorted(found)


def _loader() -> Any:
    import yaml

    class ComposeLoader(yaml.SafeLoader):
        pass

    def tagged(loader: Any, node: Any) -> Any:
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node, deep=True)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node, deep=True)
        return loader.construct_scalar(node)

    ComposeLoader.add_constructor("!reset", tagged)
    ComposeLoader.add_constructor("!override", tagged)
    return ComposeLoader


def load(path: Path) -> dict[str, Any]:
    import yaml

    data = yaml.load(path.read_text(encoding="utf-8"), Loader=_loader())  # noqa: S506
    return data or {}


def services(path: Path = MAIN_COMPOSE) -> dict[str, dict[str, Any]]:
    return {name: (svc or {}) for name, svc in (load(path).get("services") or {}).items()}


def all_services() -> list[tuple[str, str, dict[str, Any]]]:
    """(file name, service name, service) over every compose file."""
    return [(path.name, name, svc) for path in compose_files()
            for name, svc in services(path).items()]


def is_stack_service(svc: dict[str, Any]) -> bool:
    """PS-2.12: a stack service is one without a compose profile."""
    return not svc.get("profiles")


def service_networks(svc: dict[str, Any]) -> list[str]:
    """Networks a service joins; none listed (and no network_mode) means `default`."""
    if "network_mode" in svc:
        return []
    networks = svc.get("networks")
    if networks is None:
        return ["default"]
    if isinstance(networks, dict):
        return list(networks)
    return list(networks)


def network_is_internal(name: str, path: Path = MAIN_COMPOSE) -> bool:
    definition = (load(path).get("networks") or {}).get(name) or {}
    return definition.get("internal") is True


def port_entries(svc: dict[str, Any]) -> list[Any]:
    return [p for p in (svc.get("ports") or []) if p is not None]


def environment(svc: dict[str, Any]) -> dict[str, str]:
    env = svc.get("environment") or {}
    if isinstance(env, dict):
        return {str(k): "" if v is None else str(v) for k, v in env.items()}
    out: dict[str, str] = {}
    for item in env:
        key, _, value = str(item).partition("=")
        out[key] = value
    return out


def volume_sources(svc: dict[str, Any]) -> list[tuple[str, str]]:
    """(type, source) of every volume: type is `bind` or `volume`."""
    found: list[tuple[str, str]] = []
    for volume in svc.get("volumes") or []:
        if isinstance(volume, dict):
            found.append((str(volume.get("type", "volume")), str(volume.get("source", ""))))
            continue
        text = str(volume)
        if re.match(r"^[A-Za-z]:[\\/]", text):  # Windows drive path
            found.append(("bind", text))
            continue
        source = text.split(":", 1)[0] if ":" in text else ""
        # Short syntax: a path-like source is a bind mount; a bare name is a
        # named volume; a lone target is an anonymous volume.
        if re.match(r"^(?:[./~$\\]|[A-Za-z]:[\\/])", source) or "/" in source:
            found.append(("bind", source))
        else:
            found.append(("volume", source))
    return found


def compose_defaults(text: str) -> list[tuple[str, str]]:
    """Every `${VAR:-default}` / `${VAR-default}` in a compose file's text."""
    return _DEFAULT.findall(text)
