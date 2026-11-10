"""Typed application settings. Env names follow the runbook (ENV, API__CORS_ORIGINS, ...)."""

import json
import re
from typing import Annotated, Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

Env = Literal["dev", "test", "staging", "prod"]

_ORIGIN_RE = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d{1,5})?$")
_LOCAL_HOSTS = ("localhost", "127.0.0.1")


class ConfigError(RuntimeError):
    """Invalid configuration. The message never contains input values."""


class ApiSettings(BaseModel):
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            text = v.strip()
            if text.startswith("["):
                try:
                    v = json.loads(text)
                except ValueError:
                    raise ValueError("must be a JSON list or comma-separated origins") from None
            else:
                v = [p.strip() for p in text.split(",") if p.strip()]
        return v

    @field_validator("cors_origins")
    @classmethod
    def _check_origins(cls, v: list[str]) -> list[str]:
        for origin in v:
            if origin == "*":
                raise ValueError("use explicit origins, '*' is not allowed")
            if not _ORIGIN_RE.fullmatch(origin):
                raise ValueError("each origin must look like https://host[:port]")
        return v


class AuthSettings(BaseModel):
    supabase_url: str | None = None


class ObsSettings(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    release: str | None = None


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    env: Env = "dev"
    api: ApiSettings = Field(default_factory=ApiSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    obs: ObsSettings = Field(default_factory=ObsSettings)
    sentry_dsn: SecretStr | None = None
    supabase_url_legacy: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_KEY"),
    )
    azure_openai_endpoint: str | None = None
    azure_openai_key: SecretStr | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2025-01-01-preview"
    azure_foundry: bool = False

    @model_validator(mode="after")
    def _no_localhost_in_deployed_envs(self) -> "AppSettings":
        if self.env in ("staging", "prod"):
            for origin in self.api.cors_origins:
                if any(host in origin for host in _LOCAL_HOSTS):
                    raise ValueError(
                        f"api.cors_origins: localhost origins are not allowed when env={self.env}"
                    )
        return self

    @property
    def supabase_url(self) -> str | None:
        return self.auth.supabase_url or self.supabase_url_legacy

    @property
    def dev_tools_enabled(self) -> bool:
        return self.env in ("dev", "test")


def _format_errors(exc: ValidationError) -> str:
    lines = ["Invalid configuration:"]
    for err in exc.errors(include_input=False, include_url=False):
        field = ".".join(str(p) for p in err["loc"]) or "settings"
        lines.append(f"  - {field}: {err['msg']}")
    return "\n".join(lines)


def load_settings(**overrides: Any) -> AppSettings:
    try:
        return AppSettings(**overrides)
    except ValidationError as exc:
        raise ConfigError(_format_errors(exc)) from None
    except SettingsError:
        raise ConfigError("Invalid configuration: could not parse environment values") from None
