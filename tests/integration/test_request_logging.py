import json
import re
from io import StringIO
from pathlib import Path

import pytest

from app.config.settings import ObsSettings
from app.observability.logging import configure_logging
from tests.fakes.backend import auth_header
from tests.integration.api_compat.conftest import backend, client  # noqa: F401

FIXTURES = Path(__file__).parent.parent / "fixtures"
JD = (FIXTURES / "jd_valid_backend.txt").read_text(encoding="utf-8")


@pytest.fixture
def buf(client):  # noqa: F811
    stream = StringIO()
    configure_logging(ObsSettings(), stream=stream)
    return stream


def _lines(buf: StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def _http_lines(buf: StringIO) -> list[dict]:
    return [rec for rec in _lines(buf) if rec["event"] == "http.request"]


def test_profile_post_logs_no_pii(client, buf):  # noqa: F811
    profile = json.loads((FIXTURES / "profile_basic.json").read_text(encoding="utf-8"))
    r = client.post("/profile", json=profile, headers=auth_header())
    assert r.status_code == 200
    (line,) = _http_lines(buf)
    assert line["request_id"] == r.headers["X-Request-ID"]
    assert line["status"] == 200
    assert line["path"] == "/profile"
    text = buf.getvalue()
    for needle in ("test.person@example.com", "+8801712345678", "Test Person"):
        assert needle not in text
    summary = profile.get("professional_summary") or profile.get("summary")
    if summary:
        assert summary[:40] not in text


def test_sessions_start_logs_no_jd_text(client, backend, buf):  # noqa: F811
    from tests.fakes.fake_auth import USER_A

    backend.store.profiles[USER_A] = {"user_id": USER_A, "full_name": "Test Person"}
    backend.pipeline.next_nodes = []
    client.post("/sessions/start", json={"job_description": JD}, headers=auth_header())
    words = JD.split()
    text = buf.getvalue()
    for i in range(0, len(words) - 6, 3):
        assert " ".join(words[i : i + 6]) not in text


def test_forged_request_id_replaced(client, buf):  # noqa: F811
    r = client.get("/health", headers={"X-Request-ID": "a@b.co\nlevel=error"})
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["X-Request-ID"])
    assert "a@b.co" not in buf.getvalue()
    assert all(isinstance(rec, dict) for rec in _lines(buf))


def test_valid_inbound_request_id_kept(client, buf):  # noqa: F811
    r = client.get("/health", headers={"X-Request-ID": "trace-abc12345"})
    assert r.headers["X-Request-ID"] == "trace-abc12345"
    assert _http_lines(buf)[0]["request_id"] == "trace-abc12345"


def test_500_is_logged_and_body_unchanged(client, backend, buf):  # noqa: F811
    backend.store.raise_on["get_user_sessions"] = RuntimeError("db down for a@b.co")
    r = client.get("/sessions", headers=auth_header())
    assert r.status_code == 500
    assert r.text == "Internal Server Error"
    (line,) = _http_lines(buf)
    assert line["status"] == 500
    assert "db down" not in buf.getvalue()
    assert "RuntimeError" in buf.getvalue()
