from typing import Any

import jwt
from pydantic import SecretStr

from app.adapters.auth.jwks_cache import JwksCache
from app.ports.auth import InvalidToken, VerifiedUser

_INVALID = "Invalid token"
_ASYMMETRIC = ("ES256", "RS256")
_REQUIRED = ["exp", "sub", "aud", "iss"]


class JwksTokenVerifier:
    def __init__(
        self,
        cache: JwksCache,
        *,
        issuer: str,
        audience: str,
        leeway_s: int = 30,
        hs256_secret: SecretStr | None = None,
    ) -> None:
        self._cache = cache
        self._issuer = issuer
        self._audience = audience
        self._leeway_s = leeway_s
        self._hs256_secret = hs256_secret

    def verify(self, token: str) -> VerifiedUser:
        try:
            header = jwt.get_unverified_header(token)
        except Exception:
            raise InvalidToken(_INVALID) from None
        alg = header.get("alg")
        if alg in _ASYMMETRIC:
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise InvalidToken(_INVALID)
            key: Any = self._cache.key_for(kid).key
        elif alg == "HS256" and self._hs256_secret is not None:
            key = self._hs256_secret.get_secret_value()
        else:
            raise InvalidToken(_INVALID)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_s,
                options={"require": _REQUIRED},
            )
        except Exception:
            raise InvalidToken(_INVALID) from None
        return self._to_user(claims)

    @staticmethod
    def _to_user(claims: dict[str, Any]) -> VerifiedUser:
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise InvalidToken(_INVALID)
        meta = claims.get("app_metadata")
        role = meta.get("role") if isinstance(meta, dict) else None
        email = claims.get("email")
        auth_time = claims.get("auth_time")
        aal = claims.get("aal")
        return VerifiedUser(
            user_id=sub,
            email=email if isinstance(email, str) else None,
            is_admin=role == "admin",
            auth_time=auth_time if isinstance(auth_time, int) else None,
            aal=aal if isinstance(aal, str) else None,
        )
