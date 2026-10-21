"""Errors shared by startup and telemetry (kept apart to avoid an import cycle)."""

from __future__ import annotations


class StartupRefused(Exception):
    """The configuration is unsafe; names the setting, never a secret value."""

    def __init__(self, setting: str, reason: str) -> None:
        super().__init__(f"startup refused: {setting}: {reason}")
        self.setting = setting
        self.reason = reason
