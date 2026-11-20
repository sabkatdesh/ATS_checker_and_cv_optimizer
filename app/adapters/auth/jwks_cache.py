import threading
from collections.abc import Callable
from typing import Any

import jwt

from app.ports.auth import AuthUnavailable, InvalidToken

_NO_KEYS = "Signing keys are unavailable"
_UNKNOWN_KID = "Unknown signing key"


class JwksCache:
    """Holds the provider's public keys; refetches on TTL expiry or one unknown kid at a time."""

    def __init__(
        self,
        url: str,
        ttl_s: int,
        fetch: Callable[[str], dict[str, Any]],
        clock: Callable[[], float],
        min_refetch_s: float = 30,
    ) -> None:
        self._url = url
        self._ttl_s = ttl_s
        self._fetch = fetch
        self._clock = clock
        self._min_refetch_s = min_refetch_s
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None
        self._lock = threading.Lock()

    def key_for(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            now = self._clock()
            if self._fetched_at is None:
                self._refresh(now, required=True)
            elif now - self._fetched_at >= self._ttl_s:
                self._refresh(now, required=False)
            key = self._keys.get(kid)
            if key is None and self._may_refetch(now):
                self._refresh(now, required=False)
                key = self._keys.get(kid)
            if key is None:
                raise InvalidToken(_UNKNOWN_KID)
            return key

    def _may_refetch(self, now: float) -> bool:
        return self._last_attempt is None or now - self._last_attempt >= self._min_refetch_s

    def _refresh(self, now: float, *, required: bool) -> None:
        self._last_attempt = now
        try:
            document = self._fetch(self._url)
            keys = self._parse(document)
        except Exception:
            if required or not self._keys:
                raise AuthUnavailable(_NO_KEYS) from None
            return  # keep serving the stale keys
        self._keys = keys
        self._fetched_at = now

    @staticmethod
    def _parse(document: dict[str, Any]) -> dict[str, jwt.PyJWK]:
        keys: dict[str, jwt.PyJWK] = {}
        for entry in document.get("keys", []):
            kid = entry.get("kid")
            if not kid:
                continue
            try:
                keys[str(kid)] = jwt.PyJWK(entry)
            except Exception:  # noqa: S112 - skip keys of unsupported type
                continue
        if not keys:
            raise ValueError("no usable keys")
        return keys
