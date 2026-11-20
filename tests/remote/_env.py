"""Opt-in switch and settings for the remote suite (dev project only; never CI).

Values come from the process environment, else from the env file named by M4_ENV_FILE
(default `.env`). Only names are ever reported; values are never printed.
"""

import os
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ENABLE_VAR = "M4_REMOTE"
ENV_FILE_VAR = "M4_ENV_FILE"
SKIP_REASON = f"remote suite: set {ENABLE_VAR}=1 to run against the dev project"
PAUSED_MESSAGE = "dev project paused — restore it in the dashboard"

# (accepted names, in priority order) per setting.
REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "db_dsn": ("DB__DSN",),
    "supabase_url": ("AUTH__SUPABASE_URL", "SUPABASE_URL"),
    "secret_key": ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_KEY"),
    "publishable_key": ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"),
}


def remote_enabled(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(ENABLE_VAR, "").strip() == "1"


class RemoteEnv(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    db_dsn: SecretStr = Field(validation_alias=AliasChoices(*REQUIRED_VARS["db_dsn"]))
    supabase_url: str = Field(validation_alias=AliasChoices(*REQUIRED_VARS["supabase_url"]))
    secret_key: SecretStr = Field(validation_alias=AliasChoices(*REQUIRED_VARS["secret_key"]))
    publishable_key: SecretStr = Field(
        validation_alias=AliasChoices(*REQUIRED_VARS["publishable_key"])
    )

    @property
    def base_url(self) -> str:
        return self.supabase_url.rstrip("/")


def missing_names(exc: ValidationError) -> list[str]:
    """'DB__DSN' or 'AUTH__SUPABASE_URL|SUPABASE_URL' per missing field; never values."""
    out = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = str(err["loc"][0]) if err["loc"] else ""
        # pydantic reports the field name, or the first alias when aliases are set.
        names = REQUIRED_VARS.get(loc) or next(
            (n for n in REQUIRED_VARS.values() if loc.upper() in n), None
        )
        out.append("|".join(names) if names else loc)
    return sorted(set(out))


def load_remote_env() -> RemoteEnv:
    """Raises RuntimeError naming the missing variables (no values)."""
    env_file = os.environ.get(ENV_FILE_VAR, ".env")
    use_file = env_file if env_file and Path(env_file).is_file() else None
    try:
        return RemoteEnv(_env_file=use_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        raise RuntimeError(
            "remote suite needs these variables: " + ", ".join(missing_names(exc))
        ) from None
