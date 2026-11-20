import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import install_error_handlers
from app.observability.redaction import redact_processor
from app.observability.sentry import scrub_event

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1MSJ9.c2lnbmF0dXJl"
DSN = "postgresql://app_user:hunter2pw@db.example.com:5432/postgres"


def _redact(**kw):
    return redact_processor(None, "info", dict(kw))


def test_bearer_header_masked():
    out = _redact(event="sent Authorization: Bearer abc.def-ghi_123 ok")
    assert "abc.def" not in out["event"]
    assert "Bearer [redacted]" in out["event"]


def test_jwt_shape_masked_anywhere_in_string():
    out = _redact(event=f"bad token {JWT} in call", nested={"msg": [f"x={JWT}"]})
    assert out["event"] == "bad token [jwt] in call"
    assert out["nested"]["msg"] == ["x=[jwt]"]


def test_supabase_secret_key_masked():
    payload = base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip("=")
    legacy = ".".join(["eyJ" + "hbGciOiJIUzI1NiJ9", payload, "sig_nature-1"])
    out = _redact(
        a="key sb_secret_AbC123_xyz-9 used",
        b="pub sb_publishable_AbC123_xyz-9",
        c=f"legacy {legacy}",
    )
    assert out["a"] == "key [key] used"
    assert out["b"] == "pub [key]"
    assert "service_role" not in out["c"] and "eyJ" not in out["c"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgresql://u:pw@h", "postgresql://u:***@h"),
        ("postgres://u:p%40ss@h:5432/db", "postgres://u:***@h:5432/db"),
        ("postgresql+psycopg://u:pw@h/db", "postgresql+psycopg://u:***@h/db"),
        (
            "host=h dbname=d user=u password=s3cret sslmode=require",
            "host=h dbname=d user=u password=*** sslmode=require",
        ),
    ],
)
def test_dsn_password_masked(raw, expected):
    assert _redact(event=f"connect {raw} failed")["event"] == f"connect {expected} failed"


def test_signed_url_token_masked():
    url = "https://x.supabase.co/storage/v1/object/sign/b/f.pdf?token=abc.def&download=1"
    out = _redact(event=f"{url} and https://h/p?a=1&token=zzz9")["event"]
    assert "abc.def" not in out and "zzz9" not in out
    assert "?token=[redacted]&download=1" in out
    assert "&token=[redacted]" in out


@pytest.mark.parametrize("key", ["Authorization", "password", "secret", "token", "api_key"])
def test_sensitive_dict_keys_redacted(key):
    assert _redact(ctx={key: "v"})["ctx"][key] == "[REDACTED]"


def test_sentry_before_send_applies_same_scrubber():
    event = {
        "message": f"fail {DSN}",
        "logentry": {"message": f"Bearer {JWT}"},
        "exception": {"values": [{"type": "OperationalError", "value": DSN}]},
        "breadcrumbs": {"values": [{"message": f"GET ?token=abc {JWT}", "data": {"url": DSN}}]},
        "request": {"url": "https://h/p?token=abc", "data": {"a": JWT}},
    }
    out = str(scrub_event(event, {}))
    for leaked in ("hunter2pw", "abc", JWT, "eyJ"):
        assert leaked not in out


def _app(exc: Exception) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_db_exception_body_is_constant():
    import psycopg

    r = _app(psycopg.OperationalError(f"connection failed: {DSN} password=hunter2pw")).get("/boom")
    assert r.status_code == 503
    assert "hunter2pw" not in r.text and "postgresql" not in r.text
    assert r.json()["code"] == "DB_UNAVAILABLE"


def test_unhandled_exception_returns_constant_500():
    r = _app(RuntimeError(f"boom {DSN} {JWT}")).get("/boom")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "INTERNAL_ERROR"
    assert "hunter2pw" not in r.text and "eyJ" not in r.text and "boom" not in r.text
