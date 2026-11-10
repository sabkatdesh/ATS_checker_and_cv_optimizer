import json
import logging
from io import StringIO

import pytest

from app.config.settings import ObsSettings
from app.observability.logging import configure_logging
from app.observability.redaction import REDACTED, mask_text, redact_processor


def _redact(**kw):
    return redact_processor(None, "info", dict(kw))


@pytest.mark.parametrize(
    "key", ["job_description", "cv_text", "user_qna", "cover_letter_text", "full_name"]
)
def test_sensitive_key_dropped(key):
    assert _redact(**{key: "secret"})[key] == REDACTED


@pytest.mark.parametrize("key", ["resume_text", "idempotency_key"])
def test_suffix_rule(key):
    assert _redact(**{key: "x"})[key] == REDACTED


def test_nested_values():
    out = _redact(payload={"items": [{"email": "a@b.co", "note": "mail a@b.co"}]})
    item = out["payload"]["items"][0]
    assert item["email"] == REDACTED
    assert item["note"] == "mail [EMAIL]"


def test_email_masked_in_event():
    assert _redact(event="sent to test.person@example.com")["event"] == "sent to [EMAIL]"


@pytest.mark.parametrize(
    "phone",
    ["+8801712345678", "+880 1712-345678", "01712345678", "(017) 1234 5678", "০১৭১২৩৪৫৬৭৮"],
)
def test_phone_formats_masked(phone):
    assert mask_text(f"call {phone} now") == "call [PHONE] now"


@pytest.mark.parametrize(
    "value",
    ["thread_6f1c9a4be2d34f0a8c7e1b2d3a4f5678", "550e8400-e29b-41d4-a716-446655440000"],
)
def test_uuid_and_thread_id_not_masked(value):
    assert mask_text(value) == value


def test_passthrough_keys_untouched():
    assert _redact(timestamp="2026-11-10T12:00:00Z")["timestamp"] == "2026-11-10T12:00:00Z"


def test_exception_message_dropped():
    buf = StringIO()
    configure_logging(ObsSettings(), stream=buf)
    try:
        raise ValueError("cv says test.person@example.com")
    except ValueError:
        logging.getLogger("x").error("boom", exc_info=True)
    out = buf.getvalue()
    assert "ValueError" in out
    assert "test.person" not in out
    assert json.loads(out.splitlines()[-1])["exception"]["type"] == "ValueError"
