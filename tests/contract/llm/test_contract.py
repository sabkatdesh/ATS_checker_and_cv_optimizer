"""Behaviour every LLMProvider must show. Append new harnesses to HARNESSES."""

import asyncio
import threading
import time
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.adapters.llm._structured import REPAIR_TEXT
from app.ports.llm import CallMeta, CancelToken, LLMRequest, Message, Route, Usage
from app.ports.llm_errors import (
    LLMBadRequest,
    LLMCancelled,
    LLMError,
    LLMOutputInvalid,
    LLMOutputTruncated,
    LLMRefused,
    LLMTimeout,
)
from tests.contract.llm import harness as h
from tests.contract.llm.harnesses.anthropic import AnthropicHarness
from tests.contract.llm.harnesses.azure_openai import AzureOpenAIHarness
from tests.contract.llm.harnesses.bedrock import BedrockHarness
from tests.contract.llm.harnesses.fake import FakeHarness
from tests.contract.llm.harnesses.gemini import GeminiHarness
from tests.contract.llm.harnesses.ollama import OllamaHarness
from tests.contract.llm.harnesses.openai import OpenAIHarness

HARNESSES: list[type] = [
    FakeHarness,
    BedrockHarness,
    OpenAIHarness,
    AzureOpenAIHarness,
    AnthropicHarness,
    GeminiHarness,
    OllamaHarness,
]  # adapter tasks append here

SENTINEL = "SENTINEL-CV-7f3a"
MODEL = "contract-model"


class Answer(BaseModel):
    answer: str
    score: int


VALID = '{"answer": "yes", "score": 7}'


@pytest.fixture(params=HARNESSES, ids=lambda c: c.__name__)
def harness(request: pytest.FixtureRequest) -> h.ContractHarness:
    return request.param()


@pytest.fixture
def prices(harness: h.ContractHarness) -> PriceTable:
    price = ModelPrice(input_per_m=Decimal(3), output_per_m=Decimal(15))
    return PriceTable({(harness.name, MODEL): price})


def route(harness: h.ContractHarness, mode: str = "prompt") -> Route:
    return Route(
        step="contract",
        provider=harness.name,
        model=MODEL,
        max_tokens=321,
        temperature=0.0,
        timeout_s=30.0,
        max_attempts=4,
        structured_mode=mode,  # type: ignore[arg-type]
    )


def request(schema: type[BaseModel] | None = Answer, text: str = "hello") -> LLMRequest:
    return LLMRequest(
        step="contract",
        system="be brief",
        messages=[Message(role="user", content=text)],
        output_schema=schema,
        metadata=CallMeta(prompt_id=h.CONTRACT_PROMPT_ID),
    )


def call(harness, prices, retry, req=None, mode="prompt", cancel=None):
    provider = harness.provider(prices, BreakerRegistry(), retry)
    return asyncio.run(
        provider.complete(req or request(), route(harness, mode), cancel or CancelToken())
    )


def modes(harness: h.ContractHarness) -> list[str]:
    return ["prompt", "native"] if harness.supports_native else ["prompt"]


def test_structured_success(harness, prices, instant_retry):
    for mode in modes(harness):
        fresh = type(harness)()
        fresh.script(h.Ok(VALID))
        res = call(fresh, prices, instant_retry, mode=mode)
        assert res.output == Answer(answer="yes", score=7)
        assert res.repaired is False
        assert res.usage.input_tokens > 0 and res.usage.output_tokens > 0
        assert res.cost_usd == prices.cost(fresh.name, MODEL, res.usage)


def test_malformed_then_repaired(harness, prices, instant_retry):
    for mode in modes(harness):
        fresh = type(harness)()
        fresh.script(h.Ok("not json"), h.Ok(VALID))
        res = call(fresh, prices, instant_retry, mode=mode)
        assert res.repaired is True
        bodies = fresh.sent_bodies()
        assert len(bodies) == 2
        assert res.usage == Usage(input_tokens=20, output_tokens=10)
        last = bodies[1]["messages"][-1]
        assert last["role"] == "user" and REPAIR_TEXT in last["content"]


def test_invalid_twice_raises_output_invalid(harness, prices, instant_retry):
    harness.script(h.Ok("nope"), h.Ok("still nope"))
    with pytest.raises(LLMOutputInvalid) as exc:
        call(harness, prices, instant_retry)
    assert exc.value.usage is not None and exc.value.usage.input_tokens > 0


def test_throttled_then_success(harness, prices, instant_retry):
    harness.script(h.Throttle(retry_after=0.01), h.Ok(VALID))
    res = call(harness, prices, instant_retry)
    assert res.attempts == 2


def test_server_error_then_success(harness, prices, instant_retry):
    harness.script(h.ServerError(), h.Ok(VALID))
    res = call(harness, prices, instant_retry)
    assert res.attempts == 2 and res.output == Answer(answer="yes", score=7)


def test_timeout_raises_after_max_attempts(harness, prices, instant_retry):
    harness.script(*[h.Timeout()] * 4)
    with pytest.raises(LLMTimeout):
        call(harness, prices, instant_retry)
    assert len(harness.sent_bodies()) == 4


def test_refusal_raises_refused(harness, prices, instant_retry):
    harness.script(h.Refusal())
    with pytest.raises(LLMRefused):
        call(harness, prices, instant_retry)
    assert len(harness.sent_bodies()) == 1


def test_bad_request_not_retried(harness, prices, instant_retry):
    harness.script(h.BadRequest())
    with pytest.raises(LLMBadRequest):
        call(harness, prices, instant_retry)
    assert len(harness.sent_bodies()) == 1


def test_empty_structured_repairs_once(harness, prices, instant_retry):
    harness.script(h.Empty(), h.Ok(VALID))
    res = call(harness, prices, instant_retry)
    assert res.repaired is True and len(harness.sent_bodies()) == 2


def test_empty_text_raises(harness, prices, instant_retry):
    harness.script(h.Empty())
    with pytest.raises(LLMOutputInvalid):
        call(harness, prices, instant_retry, req=request(schema=None))


def test_max_tokens_structured_raises_truncated(harness, prices, instant_retry):
    harness.script(h.Truncated('{"answer": "ye'))
    with pytest.raises(LLMOutputTruncated):
        call(harness, prices, instant_retry)
    assert len(harness.sent_bodies()) == 1


def test_max_tokens_text_returns_with_stop_reason(harness, prices, instant_retry):
    harness.script(h.Truncated("partial answer"))
    res = call(harness, prices, instant_retry, req=request(schema=None))
    assert res.output == "partial answer" and res.stop_reason == "max_tokens"


def test_cancel_within_1_5s(harness, prices, instant_retry):
    harness.script(h.Hang(5))
    cancel = CancelToken()
    timer = threading.Timer(0.2, cancel.cancel)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(LLMCancelled):
            call(harness, prices, instant_retry, cancel=cancel)
    finally:
        timer.cancel()
    assert time.monotonic() - started < 1.5


def test_wire_sets_max_tokens_and_ends_with_user(harness, prices, instant_retry):
    harness.script(h.Ok(VALID))
    call(harness, prices, instant_retry)
    assert harness.sent_bodies()[0]["max_tokens"] == 321
    assert harness.last_roles()[-1] == "user"


def test_error_messages_carry_no_prompt_text(harness, prices, instant_retry):
    cases: list[list[h.Outcome]] = [
        [h.ServerError()] * 4,
        [h.Timeout()] * 4,
        [h.Refusal()],
        [h.BadRequest()],
        [h.Truncated(SENTINEL)],
        [h.Ok(SENTINEL), h.Ok(SENTINEL)],
        [h.Empty(), h.Empty()],
    ]
    for outcomes in cases:
        fresh = type(harness)()
        fresh.script(*outcomes)
        with pytest.raises(LLMError) as exc:
            call(fresh, prices, instant_retry, req=request(text=SENTINEL))
        assert SENTINEL not in str(exc.value) and SENTINEL not in repr(exc.value)


def test_text_mode_returns_string(harness, prices, instant_retry):
    harness.script(h.Ok("plain words"))
    res = call(harness, prices, instant_retry, req=request(schema=None))
    assert res.output == "plain words"
