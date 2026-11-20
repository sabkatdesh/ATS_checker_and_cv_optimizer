import time
from typing import Any

import httpx

from app.adapters.auth.jwks_cache import JwksCache
from app.adapters.auth.jwks_verifier import JwksTokenVerifier
from app.config.db_settings import AuthSettings
from app.config.settings import ConfigError

_NO_CONFIG = "Auth needs AUTH__SUPABASE_URL or AUTH__JWKS_URL"


def fetch_jwks(url: str) -> dict[str, Any]:
    """Plain GET of the public key set (no credentials sent); one retry."""
    last: Exception | None = None
    for _ in range(2):
        try:
            response = httpx.get(url, timeout=5)
            response.raise_for_status()
            document = response.json()
            if isinstance(document, dict):
                return document
            raise ValueError("unexpected JWKS document")
        except Exception as exc:
            last = exc
    raise last  # type: ignore[misc]


def build_token_verifier(auth: AuthSettings, supabase_url: str | None = None) -> JwksTokenVerifier:
    base = auth.supabase_url or supabase_url
    issuer = auth.issuer or (base.rstrip("/") + "/auth/v1" if base else None)
    url = auth.jwks_url
    if url is None and base:
        url = base.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    if not url or not issuer:
        raise ConfigError(_NO_CONFIG)
    cache = JwksCache(url, auth.jwks_ttl_s, fetch_jwks, time.monotonic)
    return JwksTokenVerifier(
        cache,
        issuer=issuer,
        audience=auth.jwt_audience,
        hs256_secret=auth.hs256_secret,
    )
