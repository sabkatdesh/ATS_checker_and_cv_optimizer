import base64
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

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


def test_undefined_column_is_500_with_type_and_sqlstate_logged():
    import psycopg

    exc = psycopg.errors.UndefinedColumn(f"column x does not exist {DSN}")
    with capture_logs() as logs:
        r = _app(exc).get("/boom")
    assert r.status_code == 500 and r.json()["code"] == "INTERNAL_ERROR"
    assert "hunter2pw" not in r.text
    logged = [e for e in logs if e.get("error_type") == "UndefinedColumn"]
    assert logged and logged[0]["sqlstate"] == "42703"
    assert "hunter2pw" not in json.dumps(logs, default=str)


def test_operational_error_503_logs_type_only():
    import psycopg

    with capture_logs() as logs:
        r = _app(psycopg.OperationalError(f"fail {DSN}")).get("/boom")
    assert r.status_code == 503
    assert any(e.get("error_type") == "OperationalError" for e in logs)
    assert "hunter2pw" not in json.dumps(logs, default=str)


def test_pool_timeout_is_503():
    from psycopg_pool import PoolTimeout

    assert _app(PoolTimeout("x")).get("/boom").status_code == 503


def test_adversarial_input_is_fast():
    nasty = "eyJ" + "a." * 20000 + "Bearer " + "A" * 50000 + " postgres://" + "u:" * 20000
    t = time.perf_counter()
    _redact(event=nasty)
    assert time.perf_counter() - t < 1


def test_bearer_prose_and_non_secrets_untouched():
    text = "missing bearer token; id 123e4567-e89b-12d3-a456-426614174000 b64 " + "QUJD" * 30
    assert _redact(event=text)["event"] == text


@pytest.mark.parametrize("name", ["access_token", "X-Amz-Signature", "sig", "signature", "token"])
def test_url_secret_params_masked(name):
    out = _redact(event=f"https://h/p?a=1&{name}=SECRETVAL123&b=2")["event"]
    assert "SECRETVAL123" not in out and "&b=2" in out


def test_sslpassword_and_at_in_password_masked():
    out = _redact(event="sslpassword=topsecret1 postgresql://u:p@ss@host.example.com/db")["event"]
    assert "topsecret1" not in out and "p@ss" not in out
    assert "postgresql://u:***@host.example.com/db" in out


def test_sentry_strict_no_secret_anywhere():
    event = {
        "message": DSN,
        "tags": {"url": f"https://h/p?token=SECRETVAL123 {JWT}"},
        "user": {"email": "a@b.co", "id": "u1", "ip_address": "1.2.3.4"},
        "transaction": "/x?token=SECRETVAL123",
        "request": {
            "url": "https://h/p?token=SECRETVAL123",
            "headers": {"X-Custom": f"Bearer {JWT}", "Accept": "*/*"},
            "env": {"REMOTE_ADDR": "1.2.3.4", "K": "sb_secret_SECRETVAL123"},
        },
        "exception": {"values": [{"value": DSN}]},
        "breadcrumbs": {"values": [{"message": f"Bearer {JWT}"}]},
        "extra": {"dsn": DSN},
    }
    out = json.dumps(scrub_event(event, {}))
    for leaked in ("hunter2pw", "SECRETVAL123", JWT, "a@b.co"):
        assert leaked not in out
    assert "Accept" in out
