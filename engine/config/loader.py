"""Settings sources and the ConfigError type (ADR-KE-010).

Precedence, highest first: init arguments, KE_ environment variables, the
standard tool variables, then config/defaults.yaml. Messages name keys and
never values.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from pydantic_settings import PydanticBaseSettingsSource

CONFIG_FILE_VAR = "KE_CONFIG_FILE"
DEFAULT_CONFIG_FILE = "config/defaults.yaml"

# Variables other tools already read keep their own names (F2 ruling):
# variable -> path into the settings tree.
STANDARD_VARS: dict[str, tuple[str, ...]] = {
    "PHOENIX_COLLECTOR_ENDPOINT": ("telemetry", "collector_endpoint"),
    "HARNESS_TRACING": ("telemetry", "tracing"),
    "OPENINFERENCE_HIDE_INPUTS": ("telemetry", "hide_inputs"),
    "OPENINFERENCE_HIDE_OUTPUTS": ("telemetry", "hide_outputs"),
    "KE_MODEL_UPSTREAM": ("models", "model_upstream"),
}


class ConfigError(Exception):
    """Configuration could not be loaded; the message names the key, not the value."""


def env_name(loc: tuple[int | str, ...]) -> str:
    """`KE_A__B` for the settings path ("a", "b")."""
    return "KE_" + "__".join(str(part).upper() for part in loc)


def var_name(loc: tuple[int | str, ...]) -> str:
    """The variable the user set for a settings path: the KE_ name if set, else
    the standard tool name if set, else the KE_ name. KE_MODEL_UPSTREAM is the
    only name for the model upstream."""
    path = tuple(str(part) for part in loc)
    if path == ("models", "model_upstream"):
        return "KE_MODEL_UPSTREAM"
    name = env_name(loc)
    if name in os.environ:
        return name
    for var, target in STANDARD_VARS.items():
        if target == path and var in os.environ:
            return var
    return name


def describe(error: ValidationError) -> str:
    """One line per failing key: its variable, its dotted path and pydantic's
    reason. pydantic's `input` (the offending value) is deliberately dropped."""
    lines = []
    for item in error.errors(include_input=False, include_url=False):
        loc = tuple(item["loc"])
        dotted = ".".join(str(part) for part in loc)
        lines.append(f"{var_name(loc)} ({dotted}): {item['msg']}")
    return "invalid configuration: " + "; ".join(lines)


def describe_parse_failure(error: Exception) -> str:
    """For a pydantic-settings parse error (message names only the top-level
    field): list the KE_ variables of that field, never their values."""
    match = re.search(r'field "(\w+)"', str(error))
    if not match:
        return "invalid configuration: a setting could not be parsed"
    prefix = env_name((match.group(1),))
    names = sorted(n for n in os.environ if n.upper() == prefix or n.upper().startswith(prefix + "__"))
    shown = ", ".join(names) if names else prefix
    return f"invalid configuration: {shown} ({match.group(1)}): value could not be parsed"


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_FILE_VAR) or DEFAULT_CONFIG_FILE)


def _nest(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    for part in reversed(path):
        value = {part: value}
    return value  # type: ignore[no-any-return]


class StandardVarsSource(PydanticBaseSettingsSource):
    """The standard tool variable names and KE_MODEL_UPSTREAM."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for var, path in STANDARD_VARS.items():
            value = os.environ.get(var)
            if value:
                _merge(data, _nest(path, value))
        return data


class YamlDefaultsSource(PydanticBaseSettingsSource):
    """config/defaults.yaml, located through KE_CONFIG_FILE."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = config_path()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read the defaults file {path}: {exc.strerror}") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"the defaults file {path} is not valid YAML") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"the defaults file {path} must be a mapping")
        return data


def _merge(into: dict[str, Any], extra: dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            _merge(into[key], value)
        else:
            into[key] = value
