"""Private object storage port. Buckets are private; access is by short-lived signed URLs."""

import re
from typing import Literal, Protocol

RENDERS_BUCKET = "renders"


class StorageError(Exception):
    """Constant message only: never a URL, token or path."""


_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_USER_PREFIX = re.compile(rf"^{_UUID}(/{_UUID})?/?$")


def checked_user_prefix(prefix: str) -> str:
    """Normalised 'user_id' or 'user_id/session_id' (no trailing slash), else StorageError.

    Guards bulk deletes against an empty, root or non-user prefix."""
    if not _USER_PREFIX.match(prefix):
        raise StorageError("Storage prefix is not a user prefix")
    return prefix.rstrip("/")


class BlobStorage(Protocol):
    def put(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...

    def signed_url(self, bucket: str, path: str, ttl_s: int) -> str: ...

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        """Remove every object under prefix; returns the number removed.

        Real adapters must reject (StorageError) an empty or '/'-only prefix and any prefix that
        is not 'user_id' or 'user_id/session_id' (see checked_user_prefix). Matching is by whole
        path segment: 'u1/s1' never matches 'u1/s10/...'."""
        ...


def render_path(user_id: str, session_id: str, kind: Literal["cv", "cover_letter"]) -> str:
    return f"{user_id}/{session_id}/{kind}.pdf"


def signed_url_for_user(
    storage: BlobStorage, user_id: str, bucket: str, path: str, ttl_s: int
) -> str:
    """Sign only objects inside the caller's own prefix; '.' and '..' segments are refused."""
    prefix = f"{user_id}/"
    rest = path[len(prefix) :] if user_id and path.startswith(prefix) else ""
    segments = rest.split("/")
    if not rest or any(seg in ("", ".", "..") for seg in segments):
        raise StorageError("Storage path is not owned by this user")
    return storage.signed_url(bucket, path, ttl_s)
