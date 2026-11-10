import json
import logging
from io import StringIO

import structlog

from app.config.settings import ObsSettings
from app.observability.logging import _MARK, configure_logging


def test_json_line_has_request_id_from_contextvars():
    buf = StringIO()
    configure_logging(ObsSettings(), stream=buf)
    structlog.contextvars.bind_contextvars(request_id="req-12345678")
    try:
        structlog.get_logger("t").info("hello", count=2)
    finally:
        structlog.contextvars.clear_contextvars()
    line = json.loads(buf.getvalue().splitlines()[-1])
    assert line["request_id"] == "req-12345678"
    assert line["event"] == "hello"
    assert line["level"] == "info"


def test_stdlib_library_log_is_redacted():
    buf = StringIO()
    configure_logging(ObsSettings(), stream=buf)
    logging.getLogger("httpx").warning("to %s", "a@b.co")
    assert "[EMAIL]" in buf.getvalue()
    assert "a@b.co" not in buf.getvalue()


def test_configure_is_idempotent():
    configure_logging(ObsSettings(), stream=StringIO())
    configure_logging(ObsSettings(), stream=StringIO())
    ours = [h for h in logging.getLogger().handlers if getattr(h, _MARK, False)]
    assert len(ours) == 1
