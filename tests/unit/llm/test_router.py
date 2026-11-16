import asyncio
import threading
import time
from decimal import Decimal

import pytest

from app.adapters.llm._base import RawCompletion, WireRequest
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.fake import Fail, FakeProvider, Reply
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.config.llm_routes import EmbeddingRoute, RouteTable
from app.config.settings import AppSettings
from app.ports.llm import CallMeta, CancelToken, LLMRequest, Message, Route, Usage
from app.ports.llm_errors import (
    LLMAllRoutesFailed,
    LLMAuthError,
    LLMBadRequest,
    LLMRefused,
    LLMThrottled,
    LLMUnavailable,
)
from app.ports.usage import LlmCallRecord

PRIMARY = "us.anthropic.claude-sonnet-4-6"
GLOBAL = "global.anthropic.claude-sonnet-4-6"
PRICE = ModelPrice(input_per_m=Decimal(3), output_per_m=Decimal(15))
PRICES = PriceTable({("bedrock", PRIMARY): PRICE, ("bedrock", GLOBAL): PRICE})
ROUTE = Route(
    step="jd_extract",
    provider="bedrock",
    model=PRIMARY,
    max_tokens=2000,
    temperature=0,
    timeout_s=30,
    max_attempts=2,
    structured_mode="prompt",
)
FALLBACK = ROUTE.model_copy(update={"model": GLOBAL})
EMB = EmbeddingRoute(provider="fake", model="e", dimensions=8, timeout_s=5)


class ScriptedTransport:
    """Stands in for bedrock: outcomes queued per model, then a default reply."""

    supports_native_schema = True

    def __init__(self, name: str = "bedrock") -> None:
        self.name = name
        self.script: dict[str, list[Reply | Fail]] = {}
        self.sent: list[WireRequest] = []

    def push(self, model: str, *outcomes: Reply | Fail) -> None:
        self.script.setdefault(model, []).extend(outcomes)

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        self.sent.append(wire)
        queue = self.script.get(wire.model)
        if queue:
            o = queue.pop(0)
            if isinstance(o, Fail):
                raise o.error("scripted failure")
            return RawCompletion(o.text, o.stop, o.stop, o.usage)  # type: ignore[arg-type]
        return RawCompletion("ok", "end", "end", Usage(input_tokens=100, output_tokens=10))


class ListSink:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    def write(self, record: LlmCallRecord) -> None:
        self.records.append(record)


async def _no_sleep(_d: float) -> None:
    return None


RETRY = RetryPolicy(sleep=_no_sleep, rand=lambda: 0.0)


def _router(transport=None, *, fallback=FALLBACK, breakers=None, factories=None):
    transport = transport or ScriptedTransport()
    table = RouteTable({"jd_extract": ROUTE}, {"jd_extract": fallback}, EMB)
    registry = ProviderRegistry(
        AppSettings(),
        prices=PRICES,
        breakers=breakers or BreakerRegistry(),
        retry=RETRY,
        factories=factories or {"bedrock": lambda _s: transport},
    )
    sink = ListSink()
    return LLMRouter(table, registry, UsageRecorder(sink, PRICES)), transport, sink


def _req(step: str = "jd_extract") -> LLMRequest:
    return LLMRequest(
        step=step,
        messages=[Message(role="user", content="hi")],
        metadata=CallMeta(prompt_id="jd.extract", user_id="u1"),
    )


def _run(router, req=None):
    return asyncio.run(router.complete(req or _req()))


def test_routes_step_to_configured_provider_and_params():
    router, transport, sink = _router()
    res = _run(router)
    assert (res.provider, res.model, res.output, res.fallback_used) == (
        "bedrock",
        PRIMARY,
        "ok",
        False,
    )
    wire = transport.sent[0]
    assert (wire.model, wire.max_tokens, wire.temperature) == (PRIMARY, 2000, 0)
    assert wire.timeout_s <= 30
    assert [(r.step, r.status, r.fallback_used) for r in sink.records] == [
        ("jd_extract", "ok", False)
    ]


def test_breaker_open_uses_fallback():
    breakers = BreakerRegistry()
    breaker = breakers.get("bedrock", PRIMARY)
    for _ in range(5):
        breaker.record_failure()
    router, transport, sink = _router(breakers=breakers)
    res = _run(router)
    assert res.fallback_used and res.model.startswith("global.")
    assert [w.model for w in transport.sent] == [GLOBAL]
    assert [(r.error_kind, r.fallback_used) for r in sink.records] == [
        ("circuit_open", False),
        (None, True),
    ]


def test_retries_exhausted_uses_fallback():
    t = ScriptedTransport()
    t.push(PRIMARY, Fail(LLMThrottled), Fail(LLMThrottled))
    router, _, sink = _router(t)
    res = _run(router)
    assert res.fallback_used and res.model == GLOBAL
    assert [w.model for w in t.sent] == [PRIMARY, PRIMARY, GLOBAL]
    assert sink.records[0].attempts == 2 and sink.records[0].error_kind == "throttled"


@pytest.mark.parametrize(
    ("outcome", "error"),
    [(Reply("", stop="refused"), LLMRefused), (Fail(LLMBadRequest), LLMBadRequest)],
)
def test_refusal_and_bad_request_do_not_fall_back(outcome, error):
    t = ScriptedTransport()
    t.push(PRIMARY, outcome)
    router, _, sink = _router(t)
    with pytest.raises(error):
        _run(router)
    assert [w.model for w in t.sent] == [PRIMARY]
    assert len(sink.records) == 1 and sink.records[0].status == "error"


def test_fallback_also_failing_raises_all_routes_failed():
    t = ScriptedTransport()
    t.push(PRIMARY, Fail(LLMThrottled), Fail(LLMThrottled))
    t.push(GLOBAL, Fail(LLMUnavailable), Fail(LLMUnavailable))
    router, _, sink = _router(t)
    with pytest.raises(LLMAllRoutesFailed) as info:
        _run(router)
    assert info.value.kinds == ("throttled", "unavailable")
    assert isinstance(info.value.__cause__, LLMUnavailable)
    assert [(r.error_kind, r.fallback_used) for r in sink.records] == [
        ("throttled", False),
        ("unavailable", True),
    ]


def test_no_fallback_configured_reraises_primary():
    t = ScriptedTransport()
    t.push(PRIMARY, Fail(LLMThrottled), Fail(LLMThrottled))
    router, _, sink = _router(t, fallback=None)
    with pytest.raises(LLMThrottled):
        _run(router)
    assert [w.model for w in t.sent] == [PRIMARY, PRIMARY]
    assert len(sink.records) == 1


def test_every_call_is_recorded_with_cost():
    t = ScriptedTransport()
    router, _, sink = _router(t)
    res = _run(router)
    t.push(PRIMARY, Fail(LLMThrottled), Fail(LLMThrottled))
    _run(router)
    expected = PRICES.cost("bedrock", PRIMARY, Usage(input_tokens=100, output_tokens=10))
    assert res.cost_usd == expected > 0
    assert [(r.status, r.model, r.cost_usd) for r in sink.records] == [
        ("ok", PRIMARY, expected),
        ("error", PRIMARY, Decimal(0)),
        ("ok", GLOBAL, expected),
    ]
    assert all(r.prompt_id == "jd.extract" and r.user_id == "u1" for r in sink.records)


def test_registry_builds_each_provider_once_across_threads():
    calls: list[int] = []

    def slow_factory(_s: AppSettings) -> ScriptedTransport:
        calls.append(1)
        time.sleep(0.02)
        return ScriptedTransport()

    registry = ProviderRegistry(
        AppSettings(),
        prices=PRICES,
        breakers=BreakerRegistry(),
        factories={"bedrock": slow_factory},
    )
    assert calls == []
    got: list[object] = []
    threads = [
        threading.Thread(target=lambda: got.append(registry.get("bedrock"))) for _ in range(8)
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(calls) == 1 and len(got) == 8 and all(p is got[0] for p in got)


def test_missing_credentials_surface_on_first_call_not_build():
    def needs_creds(_s: AppSettings) -> ScriptedTransport:
        raise LLMAuthError("missing credentials", provider="bedrock")

    router, _, sink = _router(factories={"bedrock": needs_creds})  # building must not raise
    with pytest.raises(LLMAuthError):
        _run(router)
    assert [(r.status, r.error_kind, r.fallback_used) for r in sink.records] == [
        ("error", "auth", False)
    ]


def test_default_registry_serves_fake_and_names_unbuilt_providers():
    registry = ProviderRegistry(AppSettings(), prices=PRICES, breakers=BreakerRegistry())
    assert isinstance(registry.get("fake"), FakeProvider)
    with pytest.raises(LLMBadRequest, match="openai"):
        registry.get("openai")
