import asyncio
import time
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.adapters.llm._base import BaseProvider, RawCompletion, WireRequest
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm._structured import JSON_INSTRUCTION, provider_schema
from app.ports.llm import CallMeta, CancelToken, LLMRequest, Message, Route, Usage
from app.ports.llm_errors import (
    LLMBadRequest,
    LLMCancelled,
    LLMCircuitOpen,
    LLMError,
    LLMOutputInvalid,
    LLMOutputTruncated,
    LLMRefused,
    LLMThrottled,
    LLMTimeout,
    LLMUnavailable,
)

HANG = "hang"


class Out(BaseModel):
    x: int


class Script:
    """Transport that replays scripted replies: RawCompletion, LLMError or HANG."""

    name = "bedrock"

    def __init__(self, *replies: object, native: bool = True) -> None:
        self.supports_native_schema = native
        self.replies = list(replies)
        self.wires: list[WireRequest] = []
        self.cancelled_sends = 0

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        self.wires.append(wire)
        item = self.replies.pop(0)
        if item == HANG:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.cancelled_sends += 1
                raise
        if isinstance(item, LLMError):
            raise item
        assert isinstance(item, RawCompletion)
        return item


def ok(text: str, stop: str = "end", inp: int = 10, out: int = 5) -> RawCompletion:
    usage = Usage(input_tokens=inp, output_tokens=out)
    return RawCompletion(text=text, stop=stop, raw_stop_reason=stop, usage=usage)  # type: ignore[arg-type]


def route(**kw: object) -> Route:
    base: dict[str, object] = dict(
        step="rewrite", provider="bedrock", model="m1", max_tokens=321, temperature=0.2,
        timeout_s=5, max_attempts=3, structured_mode="prompt",
    )  # fmt: skip
    return Route(**{**base, **kw})  # type: ignore[arg-type]


def req(schema: type[BaseModel] | None = Out, system: str = "SECRET-SYSTEM") -> LLMRequest:  # type: ignore[type-arg]
    return LLMRequest(
        step="rewrite", system=system, output_schema=schema,
        messages=[Message(role="user", content="SECRET-CV-TEXT")],
        metadata=CallMeta(prompt_id="rewrite.v1"),
    )  # fmt: skip


PRICES = PriceTable(
    {("bedrock", "m1"): ModelPrice(input_per_m=Decimal(3), output_per_m=Decimal(15))}
)


async def _nosleep(_: float) -> None:
    await asyncio.sleep(0)


def provider(t: Script, breakers: BreakerRegistry | None = None) -> BaseProvider:
    return BaseProvider(
        t, prices=PRICES, breakers=breakers or BreakerRegistry(),
        retry=RetryPolicy(sleep=_nosleep, rand=lambda: 0.0),
    )  # fmt: skip


def call(p: BaseProvider, r: Route, rq: LLMRequest | None = None, cancel=None):  # type: ignore[type-arg]
    return asyncio.run(p.complete(rq or req(), r, cancel or CancelToken()))


def test_native_mode_sends_schema_prompt_mode_sends_instruction() -> None:
    native = Script(ok('{"x": 1}'))
    call(provider(native), route(structured_mode="native"))
    w = native.wires[0]
    assert w.json_schema == provider_schema(Out) and w.schema_name == "Out"
    assert w.system == "SECRET-SYSTEM"
    for t, r in ((Script(ok('{"x": 1}')), route()),
                 (Script(ok('{"x": 1}'), native=False), route(structured_mode="native"))):  # fmt: skip
        call(provider(t), r)
        w = t.wires[0]
        assert w.json_schema is None and w.schema_name is None
        assert w.system.startswith("SECRET-SYSTEM") and JSON_INSTRUCTION in w.system


def test_max_tokens_always_in_wire() -> None:
    t = Script(ok('{"x": 1}'), ok("hello"))
    p = provider(t)
    call(p, route())
    call(p, route(stream=True), req(schema=None))
    assert [w.max_tokens for w in t.wires] == [321, 321]
    w = t.wires[1]
    assert (w.model, w.temperature, w.stream, w.json_schema) == ("m1", 0.2, True, None)
    assert 0 < w.timeout_s <= 5 and w.messages[-1].role == "user"


def test_breaker_open_skips_transport() -> None:
    breakers = BreakerRegistry()
    b = breakers.get("bedrock", "m1")
    for _ in range(5):
        b.record_failure()
    t = Script(ok('{"x": 1}'))
    with pytest.raises(LLMCircuitOpen) as ei:
        call(provider(t, breakers), route())
    assert t.wires == [] and ei.value.attempts == 1


def test_cancel_wins_over_hanging_send_under_1_5s() -> None:
    t = Script(HANG)

    async def go() -> None:
        cancel = CancelToken()
        asyncio.get_running_loop().call_later(0.1, cancel.cancel)
        try:
            await provider(t).complete(req(), route(timeout_s=60), cancel)
        finally:
            assert asyncio.all_tasks() == {asyncio.current_task()}

    start = time.monotonic()
    with pytest.raises(LLMCancelled):
        asyncio.run(go())
    assert time.monotonic() - start < 1.5
    assert t.cancelled_sends == 1


def test_wait_for_timeout_maps_to_llm_timeout() -> None:
    t = Script(HANG)
    breakers = BreakerRegistry()
    with pytest.raises(LLMTimeout) as ei:
        call(provider(t, breakers), route(timeout_s=0.2, max_attempts=1))
    assert t.cancelled_sends == 1 and ei.value.provider == "bedrock"
    assert ei.value.attempts == 1


def test_repair_usage_is_summed_and_cost_computed() -> None:
    t = Script(ok("not json at all", inp=10, out=5), ok('{"x": 2}', inp=20, out=7))
    res = call(provider(t), route())
    assert res.output == Out(x=2) and res.repaired is True
    assert res.usage == Usage(input_tokens=30, output_tokens=12)
    assert res.cost_usd == PRICES.cost("bedrock", "m1", res.usage)
    assert (res.attempts, res.provider, res.model, res.stop_reason) == (2, "bedrock", "m1", "end")
    repair = t.wires[1]
    assert repair.messages[-1].role == "user" and repair.messages[1].role == "assistant"
    assert repair.messages[1].content == "not json at all"


def test_second_repair_failure_raises_with_summed_usage() -> None:
    t = Script(ok("nope SECRET-RESPONSE"), ok('{"x": "SECRET-RESPONSE"}'))
    with pytest.raises(LLMOutputInvalid) as ei:
        call(provider(t), route())
    err = ei.value
    assert type(err) is LLMOutputInvalid and err.usage == Usage(input_tokens=20, output_tokens=10)
    assert err.attempts == 2 and len(t.wires) == 2
    assert "SECRET" not in str(err) and "SECRET" not in err.detail


def test_refusal_not_retried_not_repaired() -> None:
    t = Script(ok("I can't help", stop="refused"))
    with pytest.raises(LLMRefused) as ei:
        call(provider(t), route())
    assert len(t.wires) == 1 and ei.value.usage == Usage(input_tokens=10, output_tokens=5)
    assert "help" not in str(ei.value)


def test_structured_max_tokens_is_truncated_without_repair() -> None:
    t = Script(ok('{"x": ', stop="max_tokens"))
    with pytest.raises(LLMOutputTruncated):
        call(provider(t), route())
    assert len(t.wires) == 1


def test_text_output_empty_invalid_and_max_tokens_returned() -> None:
    with pytest.raises(LLMOutputInvalid, match="empty response"):
        call(provider(Script(ok("  "))), route(), req(schema=None))
    res = call(provider(Script(ok("partial", stop="max_tokens"))), route(), req(schema=None))
    assert (res.output, res.stop_reason, res.repaired) == ("partial", "max_tokens", False)


def test_retries_infra_errors_and_reports_attempts() -> None:
    t = Script(LLMThrottled("slow"), ok('{"x": 3}'))
    res = call(provider(t), route())
    assert res.output == Out(x=3) and res.attempts == 2
    t2 = Script(LLMUnavailable("down"), LLMUnavailable("down"))
    with pytest.raises(LLMUnavailable) as ei:
        call(provider(t2), route(max_attempts=2))
    assert ei.value.attempts == 2


def test_failures_trip_breaker_only_for_infra_errors() -> None:
    breakers = BreakerRegistry()
    p = provider(Script(*[LLMBadRequest("bad")] * 5, *[ok("x", stop="refused")] * 5), breakers)
    for _ in range(10):
        with pytest.raises((LLMBadRequest, LLMRefused)):
            call(p, route(max_attempts=1))
    assert breakers.get("bedrock", "m1").state == "closed"
    p2 = provider(Script(*[LLMUnavailable("down")] * 5), breakers)
    for _ in range(5):
        with pytest.raises(LLMUnavailable):
            call(p2, route(max_attempts=1))
    assert breakers.get("bedrock", "m1").state == "open"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize("outcome", ["bad_request", "cancel"])
def test_half_open_probe_released_on_non_tripping_end(outcome: str) -> None:
    clock = Clock()
    breakers = BreakerRegistry(clock=clock)
    b = breakers.get("bedrock", "m1")
    for _ in range(5):
        b.record_failure()
    clock.now += 30
    cancel = CancelToken()
    if outcome == "cancel":
        t = Script(HANG)

        async def go() -> None:
            asyncio.get_running_loop().call_later(0.05, cancel.cancel)
            await provider(t, breakers).complete(req(), route(), cancel)

        with pytest.raises(LLMCancelled):
            asyncio.run(go())
    else:
        with pytest.raises(LLMBadRequest):
            call(provider(Script(LLMBadRequest("bad")), breakers), route())
    assert b.state == "half_open"
    b.before_call()  # the probe slot is free again
