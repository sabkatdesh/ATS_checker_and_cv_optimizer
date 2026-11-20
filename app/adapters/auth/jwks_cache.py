import threading
from collections.abc import Callable
from typing import Any

import jwt

from app.ports.auth import AuthUnavailable, InvalidToken

_NO_KEYS = "Signing keys are unavailable"
_INVALID = "Invalid token"


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
        self._in_flight = False
        self._lock = threading.Lock()

    def key_for(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            now = self._clock()
            expired = self._fetched_at is None or now - self._fetched_at >= self._ttl_s
            wanted = expired or kid not in self._keys
            cold = not self._keys
            may_fetch = (
                wanted
                and not self._in_flight
                and (self._last_attempt is None or now - self._last_attempt >= self._min_refetch_s)
            )
            if may_fetch:
                self._in_flight = True
                self._last_attempt = now
            elif cold:
                raise AuthUnavailable(_NO_KEYS)
        if may_fetch:
            self._refresh(now)
        with self._lock:
            key = self._keys.get(kid)
        if key is None:
            raise InvalidToken(_INVALID)
        return key

    def _refresh(self, now: float) -> None:
        """Network call runs without the lock; concurrent callers use what is cached."""
        try:
            keys = self._parse(self._fetch(self._url))
        except Exception:
            keys = None
        with self._lock:
            self._in_flight = False
            if keys is not None:
                self._keys = keys
                self._fetched_at = now
            elif not self._keys:
                raise AuthUnavailable(_NO_KEYS) from None
            # otherwise keep serving the stale keys until the next allowed attempt

    @staticmethod
    def _parse(document: dict[str, Any]) -> dict[str, jwt.PyJWK]:
        keys: dict[str, jwt.PyJWK] = {}
        for entry in document.get("keys", []):
            try:
                if not isinstance(entry, dict) or not entry.get("kid"):
                    continue
                if entry.get("kty") == "oct" or entry.get("use", "sig") != "sig":
                    continue
                keys[str(entry["kid"])] = jwt.PyJWK(entry)
            except Exception:  # noqa: S112 - skip one bad entry, keep the rest
                continue
        if not keys:
            raise ValueError("no usable keys")
        return keys
