import pytest

from app.adapters.llm.fake import Fail
from app.ports.llm import CancelToken
from app.ports.llm_errors import (
    LLMBadRequest,
    LLMCancelled,
    LLMThrottled,
)
from tests.unit.llm.router_support import (
    GLOBAL,
    PRIMARY,
    ROUTE,
    ScriptedTransport,
    _req,
    _router,
    _run,
)


def test_pre_cancelled_token_records_once_and_never_falls_back():
    router, t, sink = _router()
    token = CancelToken()
    token.cancel()
    with pytest.raises(LLMCancelled):
        _run(router, cancel=token)
    assert t.sent == []  # BaseProvider checks the token before the first send
    assert [(r.error_kind, r.fallback_used) for r in sink.records] == [("cancelled", False)]


def test_cancel_during_fallback_raises_cancelled_not_all_routes_failed():
    t = ScriptedTransport()
    t.push(PRIMARY, Fail(LLMThrottled), Fail(LLMThrottled))
    t.hang_on = GLOBAL
    router, _, sink = _router(t)
    with pytest.raises(LLMCancelled):
        _run(router, cancel=CancelToken())
    assert [(r.error_kind, r.fallback_used) for r in sink.records] == [
        ("throttled", False),
        ("cancelled", True),
    ]


def test_unknown_step_is_bad_request_and_not_recorded():
    router, t, sink = _router()
    with pytest.raises(LLMBadRequest):
        _run(router, _req("no_such_step"))
    assert t.sent == [] and sink.records == []


def test_unknown_provider_is_recorded_and_never_falls_back():
    route = ROUTE.model_copy(update={"provider": "openai"})
    router, t, sink = _router(route=route)
    with pytest.raises(LLMBadRequest, match="openai"):
        _run(router)
    assert t.sent == []
    assert [(r.provider, r.error_kind) for r in sink.records] == [("openai", "bad_request")]


def test_failing_recorder_does_not_mask_the_llm_error():
    class Broken:
        def record(self, *_a, **_k):
            raise RuntimeError("sink down")

    t = ScriptedTransport()
    t.push(PRIMARY, Fail(LLMBadRequest))
    router, _, _ = _router(t)
    router._recorder = Broken()
    with pytest.raises(LLMBadRequest):
        _run(router)


def test_failing_recorder_does_not_fail_a_successful_call():
    from structlog.testing import capture_logs

    class Broken:
        def record(self, *_a, **_k):
            raise RuntimeError("sink down")

    router, _, _ = _router()
    router._recorder = Broken()
    with capture_logs() as logs:
        result = _run(router)
    assert result.output == "ok"
    warn = [e for e in logs if e["event"] == "llm.usage_record_failed"]
    assert warn and warn[0]["log_level"] == "warning"
    assert "sink down" not in str(logs)
