"""The one typed settings object (ADR-KE-010, architecture 2.3)."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, SecretStr, ValidationError, field_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from engine.config.loader import (
    ConfigError,
    StandardVarsSource,
    YamlDefaultsSource,
    describe,
    describe_parse_failure,
)


def _no_userinfo(value: Any) -> None:
    """Refuse credentials in a URL; the message never carries them (M4)."""
    text = str(value)
    try:
        netloc = urlsplit(text if "://" in text else f"//{text}").netloc
    except ValueError:
        return
    if "@" in netloc:
        raise ValueError("must not contain credentials (user:password@)")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class Auth(_Section):
    enabled: bool


class Stack(_Section):
    service_names: list[str]


class Api(_Section):
    listen_port: int


class Postgres(_Section):
    host: str
    port: int
    database: str
    user: str
    password: SecretStr


class Neo4j(_Section):
    host: str
    port: int
    user: str
    password: SecretStr


class Valkey(_Section):
    host: str
    port: int


class Stores(_Section):
    postgres: Postgres
    neo4j: Neo4j
    valkey: Valkey


class ChatPass(_Section):
    base_url: AnyHttpUrl | None
    model: str
    fallback_model: str
    timeout_s: float

    @field_validator("base_url", mode="before")
    @classmethod
    def _base_url_no_userinfo(cls, value: Any) -> Any:
        if value is not None:
            _no_userinfo(value)
        return value


class EmbedPass(_Section):
    base_url: AnyHttpUrl | None
    model: str
    dim: int
    timeout_s: float

    @field_validator("base_url", mode="before")
    @classmethod
    def _base_url_no_userinfo(cls, value: Any) -> Any:
        if value is not None:
            _no_userinfo(value)
        return value


class Models(_Section):
    model_upstream: str | None
    compose: ChatPass
    rewrite: ChatPass
    audit: ChatPass
    embed: EmbedPass

    @field_validator("model_upstream")
    @classmethod
    def _host_parses(cls, value: str | None) -> str | None:
        if value is not None:
            _no_userinfo(value)
            try:
                urlsplit(value if "://" in value else f"//{value}").hostname
            except ValueError:
                raise ValueError("not a valid host or URL") from None
        return value

    def passes(self) -> dict[str, ChatPass | EmbedPass]:
        return {"compose": self.compose, "rewrite": self.rewrite,
                "audit": self.audit, "embed": self.embed}


class Telemetry(_Section):
    tracing: Literal["otlp", "console", "off"]
    collector_endpoint: AnyHttpUrl
    hide_inputs: bool
    hide_outputs: bool


class Readiness(_Section):
    timeout_s: float


class _EnvSource(EnvSettingsSource):
    """KE_ variables, minus the nested spelling of the model upstream:
    KE_MODEL_UPSTREAM is its only name (F2, no aliases)."""

    def __call__(self) -> dict[str, Any]:
        data = super().__call__()
        models = data.get("models")
        if isinstance(models, dict):
            models.pop("model_upstream", None)
        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KE_",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="forbid",
        protected_namespaces=(),
    )

    env: Literal["dev", "ci", "prod"]
    auth: Auth
    egress_allowlist: Annotated[list[str], NoDecode]
    stack: Stack
    api: Api
    stores: Stores
    models: Models
    telemetry: Telemetry
    readiness: Readiness

    @field_validator("egress_allowlist", mode="before")
    @classmethod
    def _split_commas(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    def __init__(self, **values: Any) -> None:
        try:
            super().__init__(**values)
        except ValidationError as exc:
            raise ConfigError(describe(exc)) from None
        except ValueError as exc:  # pydantic-settings parse errors (SettingsError)
            raise ConfigError(describe_parse_failure(exc)) from None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _EnvSource(settings_cls),
            StandardVarsSource(settings_cls),
            YamlDefaultsSource(settings_cls),
        )
