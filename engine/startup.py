"""Startup refusals and the traced startup (PS-1.5, PS-1.7, DR39)."""

from __future__ import annotations

import logging
import os
import unicodedata

from pydantic import BaseModel, SecretStr

from engine.config import ConfigError, Settings
from engine.config.loader import STANDARD_VARS, env_name
from engine.egress import EgressPolicy, host_of, is_local_endpoint
from engine.errors import StartupRefused
from engine.telemetry import configure_tracing, verify_provider
from harness_telemetry import chain_span

__all__ = ["StartupRefused", "check", "check_egress", "startup"]

log = logging.getLogger("engine.startup")

PLACEHOLDER_PREFIX = "changeme"
# Invisible characters must not hide a placeholder (L1, L1b).
_STRIPPED_CATEGORIES = {"Cf", "Cc", "Zs", "Zl", "Zp"}
_HANGUL_FILLERS = {chr(c) for c in (0x3164, 0x115F, 0x1160, 0xFFA0)}
_COMBINING_GRAPHEME_JOINER = chr(0x034F)


def _visible(value: str) -> str:
    """NFKC-normalise, then drop invisible characters anywhere (L1b)."""
    return "".join(
        ch for ch in unicodedata.normalize("NFKC", value)
        if unicodedata.category(ch) not in _STRIPPED_CATEGORIES
        and ch not in _HANGUL_FILLERS and ch != _COMBINING_GRAPHEME_JOINER)


def _refuse_or_warn(settings: Settings, setting: str, reason: str) -> None:
    if settings.env == "dev":
        log.warning("%s: %s", setting, reason)
    else:
        raise StartupRefused(setting, f"{reason} (env={settings.env})")


def _secrets(model: BaseModel, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], SecretStr]]:
    found: list[tuple[tuple[str, ...], SecretStr]] = []
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, SecretStr):
            found.append(((*prefix, name), value))
        elif isinstance(value, BaseModel):
            found.extend(_secrets(value, (*prefix, name)))
    return found


def _configured_model_hosts(settings: Settings) -> list[str]:
    hosts = [host_of(str(p.base_url)) for p in settings.models.passes().values() if p.base_url]
    if settings.models.model_upstream:
        hosts.append(host_of(settings.models.model_upstream))
    return hosts


def check_egress(settings: Settings) -> None:
    """Every configured model host must be on the allowlist (DR30)."""
    hosts = _configured_model_hosts(settings)
    with chain_span("engine.egress.startup_check") as span:
        span.set_attribute("ke.hosts_checked", hosts)
        policy = EgressPolicy(settings.egress_allowlist)
        for host in hosts:
            if not policy.allows(host):
                raise StartupRefused("egress_allowlist", f"host {host!r} is not on the allowlist")


def check(settings: Settings) -> None:
    """Raise StartupRefused on the first unsafe setting; warn instead in dev
    for auth and the hide flags."""
    if not settings.auth.enabled:
        _refuse_or_warn(settings, "auth.enabled", "authentication is disabled")

    telemetry = settings.telemetry
    endpoint = str(telemetry.collector_endpoint)
    if telemetry.tracing == "otlp" and not is_local_endpoint(
            endpoint, settings.stack.service_names):
        raise StartupRefused(
            "telemetry.collector_endpoint",
            f"traces would be exported to non-local host {host_of(endpoint)!r}")

    for flag, hidden in (("OPENINFERENCE_HIDE_INPUTS", telemetry.hide_inputs),
                         ("OPENINFERENCE_HIDE_OUTPUTS", telemetry.hide_outputs)):
        if not hidden:
            _refuse_or_warn(settings, flag, "span values are not hidden")

    check_egress(settings)

    if settings.env != "dev":
        for path, secret in _secrets(settings):
            if _visible(secret.get_secret_value()).lower().startswith(PLACEHOLDER_PREFIX):
                raise StartupRefused(
                    env_name(path), "secret still has the placeholder prefix; set a real value")


def _overridden_env_names() -> list[str]:
    names = {n for n in os.environ if n.upper().startswith("KE_")}
    names |= {n for n in STANDARD_VARS if n in os.environ}
    return sorted(names)


def startup() -> Settings:
    """Load settings from the environment and run every refusal, traced.

    Order (L6): pre-flight load and `check()`, then `configure_tracing` only
    if they passed, then the traced block, which repeats both so a refusal
    is recorded on the spans.
    """
    try:
        preflight: Settings | None = Settings()
    except ConfigError:
        preflight = None
    # M3: verify the installed provider before any span can reach it.
    # Without settings only loopback counts as local.
    verify_provider(preflight.stack.service_names if preflight else [])
    if preflight is not None:
        try:
            check(preflight)
        except StartupRefused:
            pass  # the traced block below raises the same error, inside its spans
        else:
            configure_tracing(preflight)
    with chain_span("engine.startup") as root:
        with chain_span("engine.config.load") as load_span:
            load_span.set_attribute("ke.overridden_env", _overridden_env_names())
            settings = Settings()
        root.set_attribute("ke.env", settings.env)
        with chain_span("engine.startup.refusals") as refusals:
            try:
                check(settings)
            except StartupRefused as exc:
                refusals.set_attribute("ke.refused_setting", exc.setting)
                raise
    return settings
