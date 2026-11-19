"""Private object storage port. Buckets are private; access is by short-lived signed URLs."""

from typing import Literal, Protocol

RENDERS_BUCKET = "renders"


class StorageError(Exception):
    """Constant message only: never a URL, token or path."""


class BlobStorage(Protocol):
    def put(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...

    def signed_url(self, bucket: str, path: str, ttl_s: int) -> str: ...

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        """Remove every object under prefix; returns the number removed."""
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
