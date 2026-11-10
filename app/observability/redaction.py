"""PII redaction for log events: sensitive keys are dropped, free text is masked."""

import re
import sys
import traceback
from collections.abc import MutableMapping
from typing import Any

REDACTED = "[REDACTED]"
EMAIL_RE = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
PHONE_RE = r"(?<![\w-])\(?\+?\d(?:[\s().-]{0,2}\d){8,14}(?![\w-])"

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "cv",
        "jd",
        "text",
        "content",
        "answers",
        "cv_text",
        "job_description",
        "user_resume",
        "user_resume_text",
        "user_qna",
        "resume_text",
        "cover_letter_text",
        "full_name",
        "candidate_name",
        "name",
        "email",
        "phone",
        "authorization",
        "cookie",
        "password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "dsn",
    }
)
SENSITIVE_SUFFIXES: tuple[str, ...] = (
    "_text",
    "_content",
    "_cv",
    "_jd",
    "_answers",
    "_token",
    "_secret",
    "_key",
)
PASSTHROUGH_KEYS: frozenset[str] = frozenset(
    {"timestamp", "level", "logger", "request_id", "status", "duration_ms", "method"}
)


def mask_text(value: str) -> str:
    value = re.sub(EMAIL_RE, "[EMAIL]", value)
    return re.sub(PHONE_RE, "[PHONE]", value)


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return k in SENSITIVE_KEYS or k.endswith(SENSITIVE_SUFFIXES)


def redact_value(key: str, value: object) -> object:
    if key in PASSTHROUGH_KEYS:
        return value
    if _is_sensitive(key):
        return REDACTED
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {str(k): redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(key, v) for v in value]
    return value


def redact_processor(
    logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    return {k: redact_value(k, v) for k, v in event_dict.items()}


def _frames(tb: Any) -> list[str]:
    return [f"{f.filename}:{f.lineno} in {f.name}" for f in traceback.extract_tb(tb)]


def safe_exc_processor(
    logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Replace exc_info with exception type and frames only (no message, no locals)."""
    exc_info = event_dict.pop("exc_info", None)
    if not exc_info:
        return event_dict
    if exc_info is True:
        exc_info = sys.exc_info()
    elif isinstance(exc_info, BaseException):
        exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
    if isinstance(exc_info, tuple) and exc_info[0] is not None:
        event_dict["exception"] = {"type": exc_info[0].__name__, "frames": _frames(exc_info[2])}
    return event_dict
