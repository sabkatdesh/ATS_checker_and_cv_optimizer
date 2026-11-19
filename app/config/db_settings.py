"""Database, auth, storage, bonus and deletion settings (M4)."""

from pydantic import BaseModel, SecretStr


class DbSettings(BaseModel):
    dsn: SecretStr | None = None
    pool_max: int = 4
    connect_timeout_s: float = 10
    statement_timeout_ms: int = 15000


class AuthSettings(BaseModel):
    supabase_url: str | None = None
    jwks_url: str | None = None
    jwt_audience: str = "authenticated"
    jwt_issuer: str | None = None
    hs256_secret: SecretStr | None = None
    jwks_ttl_s: int = 600

    @property
    def issuer(self) -> str | None:
        if self.jwt_issuer:
            return self.jwt_issuer
        if self.supabase_url:
            return self.supabase_url.rstrip("/") + "/auth/v1"
        return None


class StorageSettings(BaseModel):
    signed_url_ttl_s: int = 600


class BonusSettings(BaseModel):
    amount: int = 100
    ip_daily_max: int = 3
    device_max: int = 1
    hash_pepper: SecretStr | None = None


class DeletionSettings(BaseModel):
    grace_days: int = 7
