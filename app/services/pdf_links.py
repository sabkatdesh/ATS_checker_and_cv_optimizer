"""Turn stored render paths into fresh short-lived signed URLs (never a public URL)."""

import structlog

from app.container import Container
from app.ports.blob_storage import RENDERS_BUCKET, signed_url_for_user

_log = structlog.get_logger("storage")


def signed_pdf_url(c: Container, user_id: str, stored: str | None) -> str | None:
    """Stored value is a bucket path; legacy public URLs and foreign paths yield None."""
    if not stored or "://" in stored:
        return None
    try:
        return signed_url_for_user(
            c.storage, user_id, RENDERS_BUCKET, stored, c.settings.storage.signed_url_ttl_s
        )
    except Exception:
        _log.warning("pdf_sign_failed")
        return None
