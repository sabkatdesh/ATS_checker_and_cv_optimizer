"""BlobStorage over supabase-py storage (service key). Errors carry constant messages only."""

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.ports.blob_storage import StorageError, checked_user_prefix
from supabase import Client

TIMEOUT_S = 15
RETRIES = 2
_PAGE = 100


def _retryable(exc: Exception) -> bool:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    if isinstance(status, int):
        return status >= 500
    return isinstance(exc, httpx.TransportError | TimeoutError | ConnectionError)


class SupabaseBlobStorage:
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
        try:
            client.storage.session.timeout = httpx.Timeout(TIMEOUT_S)
        except Exception:  # noqa: S110 - a client without a session keeps its own default
            pass

    def _call(self, what: str, fn: Callable[[], Any]) -> Any:
        for attempt in range(self._retries + 1):
            try:
                return fn()
            except Exception as exc:
                if attempt < self._retries and _retryable(exc):
                    self._sleep(0.5 * (attempt + 1))
                    continue
                raise StorageError(f"Storage {what} failed") from None
        raise StorageError(f"Storage {what} failed")  # pragma: no cover

    def put(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        opts: Any = {"content-type": content_type, "upsert": "true"}
        self._call("upload", lambda: self._client.storage.from_(bucket).upload(path, data, opts))

    def signed_url(self, bucket: str, path: str, ttl_s: int) -> str:
        res = self._call(
            "signing", lambda: self._client.storage.from_(bucket).create_signed_url(path, ttl_s)
        )
        url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
        if not isinstance(url, str) or not url:
            raise StorageError("Storage signing failed")
        return url

    def _list_page(self, bucket: str, folder: str, offset: int) -> list[dict[str, Any]]:
        opts: Any = {"limit": _PAGE, "offset": offset}
        api = self._client.storage.from_(bucket)
        return self._call("listing", lambda: api.list(folder, opts))  # type: ignore[no-any-return]

    def _remove(self, bucket: str, paths: list[str]) -> None:
        api = self._client.storage.from_(bucket)
        self._call("delete", lambda: api.remove(paths))

    def _list(self, bucket: str, folder: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._list_page(bucket, folder, offset)
            out.extend(page)
            if len(page) < _PAGE:
                return out
            offset += _PAGE

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        prefix = checked_user_prefix(prefix)
        files: list[str] = []
        stack = [prefix]
        while stack:
            folder = stack.pop()
            for entry in self._list(bucket, folder):
                full = f"{folder}/{entry['name']}"
                (files if entry.get("id") else stack).append(full)
        for i in range(0, len(files), _PAGE):
            chunk = files[i : i + _PAGE]
            self._remove(bucket, chunk)
        return len(files)
