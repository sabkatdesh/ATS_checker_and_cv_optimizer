from unittest.mock import patch

from pydantic import SecretStr

from app.config.settings import AppSettings
from app.observability.redaction import REDACTED
from app.observability.sentry import init_sentry, scrub_event


def test_no_dsn_no_init():
    with patch("app.observability.sentry.sentry_sdk.init") as init:
        assert init_sentry(AppSettings(_env_file=None, env="test")) is False
    init.assert_not_called()


def test_init_flags():
    settings = AppSettings(
        _env_file=None, env="test", sentry_dsn=SecretStr("https://k@o.example/1")
    )
    with patch("app.observability.sentry.sentry_sdk.init") as init:
        assert init_sentry(settings) is True
    kwargs = init.call_args.kwargs
    assert kwargs["send_default_pii"] is False
    assert kwargs["max_request_body_size"] == "never"
    assert kwargs["before_send"] is scrub_event


def test_scrub_removes_body_headers_and_exception_values():
    event = {
        "request": {
            "data": {"cv": "x"},
            "cookies": "a=b",
            "query_string": "q=1",
            "headers": {"Authorization": "Bearer t", "Accept": "*/*"},
        },
        "exception": {"values": [{"type": "ValueError", "value": "a@b.co"}]},
        "extra": {"email": "a@b.co"},
    }
    out = scrub_event(event, {})
    assert set(out["request"]) == {"headers"}
    assert out["request"]["headers"] == {"Accept": "*/*"}
    assert out["exception"]["values"][0]["value"] == REDACTED
    assert out["extra"]["email"] == REDACTED


def test_scrub_drops_frame_vars_and_messages():
    event = {
        "message": "cv text",
        "logentry": {"message": "cv text"},
        "exception": {
            "values": [{"value": "x", "stacktrace": {"frames": [{"vars": {"cv": "x"}}]}}]
        },
    }
    out = scrub_event(event, {})
    assert "message" not in out
    assert "logentry" not in out
    assert "vars" not in out["exception"]["values"][0]["stacktrace"]["frames"][0]
