"""Auth admin operations with the service key (supabase-py auth.admin). Constant error messages."""

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.ports.user_admin import UserAdminError
from supabase import Client

_log = logging.getLogger(__name__)
TIMEOUT_S = 10
RETRIES = 2


def _status(exc: Exception) -> int | None:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if isinstance(status, str) and status.isdigit():
        return int(status)
    return status if isinstance(status, int) else None


def _is_not_found(exc: Exception) -> bool:
    code = str(getattr(exc, "code", "") or "").lower()
    return _status(exc) == 404 or code == "user_not_found"


def _retryable(exc: Exception) -> bool:
    status = _status(exc)
    if status is not None:
        return status >= 500
    return isinstance(exc, httpx.TransportError | TimeoutError | ConnectionError)


class SupabaseAdmin:
    def __init__(
        self,
        client: Client,
        *,
        retries: int = RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._retries = retries
        self._sleep = sleep
        self.timeout_applied = self._apply_timeout(client)

    @staticmethod
    def _apply_timeout(client: Client) -> bool:
        """supabase-py has no public auth timeout option, so set it on the admin's httpx client."""
        try:
            admin: Any = client.auth.admin
            admin._http_client.timeout = httpx.Timeout(TIMEOUT_S)
            return True
        except Exception:
            _log.warning("Auth admin timeout could not be applied; client default in use")
            return False

    def delete_user(self, user_id: str) -> bool:
        """True when deleted; False when Auth no longer has the user (already purged)."""
        for attempt in range(self._retries + 1):
            try:
                self._client.auth.admin.delete_user(user_id)
                return True
            except Exception as exc:
                if _is_not_found(exc):
                    return False
                if attempt < self._retries and _retryable(exc):
                    self._sleep(0.5 * (attempt + 1))
                    continue
                raise UserAdminError("Auth user deletion failed") from None
        raise UserAdminError("Auth user deletion failed")  # pragma: no cover
