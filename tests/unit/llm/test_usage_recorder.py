from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel
from structlog.testing import capture_logs

from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.usage.memory_sink import MemoryUsageSink
from app.ports.llm import CallMeta, LLMRequest, LLMResult, Message, Route, Usage
from app.ports.llm_errors import LLMOutputInvalid, LLMTimeout
from app.ports.usage import LlmCallRecord

ALLOWED = {
    "event", "log_level", "step", "prompt_id", "provider", "model", "status",
    "error_kind", "tokens", "cost_usd", "latency_ms", "attempts", "repaired",
    "fallback_used",
}  # fmt: skip
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class Out(BaseModel):
    x: int = 1


def _req() -> LLMRequest[Out]:
    return LLMRequest(
        step="tailor",
        system="SECRET-SYSTEM",
        messages=[Message(role="user", content="SECRET-CV-TEXT")],
        metadata=CallMeta(prompt_id="tailor.v1", prompt_version=3, user_id="u1"),
    )


def _route() -> Route:
    return Route(
        step="tailor", provider="bedrock", model="m1", max_tokens=100, temperature=None,
        timeout_s=10, structured_mode="native",
    )  # fmt: skip


def _prices() -> PriceTable:
    return PriceTable(
        {("bedrock", "m1"): ModelPrice(input_per_m=Decimal(3), output_per_m=Decimal(15))}
    )


def _recorder(sink: MemoryUsageSink) -> UsageRecorder:
    return UsageRecorder(sink, _prices(), clock=lambda: NOW)


def _result() -> LLMResult[Out]:
    return LLMResult(
        output="SECRET-OUTPUT", usage=Usage(input_tokens=10, output_tokens=5),
        cost_usd=Decimal("0.0001"), provider="bedrock", model="m1", latency_ms=7,
        repaired=True, stop_reason="end_turn", attempts=2,
    )  # fmt: skip


def test_success_record_fields():
    sink = MemoryUsageSink()
    rec = _recorder(sink).record(
        _req(), _route(), result=_result(), error=None, latency_ms=42, fallback_used=True
    )
    assert sink.records() == [rec]
    assert rec.status == "ok" and rec.error_kind is None
    assert rec.at == NOW and rec.step == "tailor" and rec.prompt_id == "tailor.v1"
    assert rec.prompt_version == 3 and rec.user_id == "u1"
    assert rec.provider == "bedrock" and rec.model == "m1"
    assert rec.usage == Usage(input_tokens=10, output_tokens=5)
    assert rec.cost_usd == Decimal("0.0001")
    assert rec.latency_ms == 42 and rec.attempts == 2
    assert rec.repaired is True and rec.fallback_used is True


def test_error_record_uses_error_usage_and_cost():
    sink = MemoryUsageSink()
    err = LLMOutputInvalid("bad", usage=Usage(input_tokens=1_000_000, output_tokens=0))
    rec = _recorder(sink).record(
        _req(), _route(), result=None, error=err, latency_ms=5, fallback_used=False
    )
    assert rec.status == "error" and rec.error_kind == "output_invalid"
    assert rec.usage.input_tokens == 1_000_000
    assert rec.cost_usd == Decimal("3.000000")
    assert rec.repaired is False


def test_error_without_usage_costs_zero():
    rec = _recorder(MemoryUsageSink()).record(
        _req(), _route(), result=None, error=LLMTimeout("t"), latency_ms=1, fallback_used=False
    )
    assert rec.usage == Usage() and rec.cost_usd == Decimal(0)


def test_sink_is_bounded():
    sink = MemoryUsageSink(maxlen=2)
    rec = _recorder(sink)
    for i in range(3):
        rec.record(_req(), _route(), result=_result(), error=None, latency_ms=i,
                   fallback_used=False)  # fmt: skip
    assert [r.latency_ms for r in sink.records()] == [1, 2]
    assert all(isinstance(r, LlmCallRecord) for r in sink.records())


def test_log_event_has_no_content_keys():
    with capture_logs() as logs:
        _recorder(MemoryUsageSink()).record(
            _req(), _route(), result=_result(), error=None, latency_ms=1, fallback_used=False
        )
    assert len(logs) == 1 and logs[0]["event"] == "llm.call"
    assert set(logs[0]) <= ALLOWED
    assert "SECRET" not in str(logs[0])
