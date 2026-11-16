"""Behaviour every EmbeddingProvider must show."""

import asyncio
import math
from decimal import Decimal

import pytest

from app.ports.llm_errors import LLMBadRequest, LLMTimeout
from tests.contract.embeddings.harnesses import DIMS, MODEL, FakeHarness, TitanHarness, titan_prices

HARNESSES: list[type] = [TitanHarness, FakeHarness]


@pytest.fixture(params=HARNESSES, ids=lambda c: c.__name__)
def harness(request: pytest.FixtureRequest):
    return request.param()


def embed(harness, retry, texts, purpose="document"):
    return asyncio.run(harness.provider(retry).embed(texts, purpose))


def test_returns_one_512d_vector_per_text(harness, instant_retry):
    harness.script_ok(3)
    vecs = embed(harness, instant_retry, ["a", "b", "c"])
    assert len(vecs) == 3
    assert all(len(v) == DIMS for v in vecs)


def test_vectors_are_unit_norm(harness, instant_retry):
    harness.script_ok(2)
    for v in embed(harness, instant_retry, ["alpha", "beta"], "query"):
        assert abs(math.sqrt(sum(x * x for x in v)) - 1) < 1e-6


def test_same_text_same_vector(harness, instant_retry):
    harness.script_ok(2)
    one = embed(harness, instant_retry, ["hello"])
    two = embed(harness, instant_retry, ["hello"], "query")
    assert one == two


@pytest.mark.parametrize("bad", ["", "   \n", "x" * 50_001], ids=["empty", "blank", "long"])
def test_empty_text_rejected(harness, instant_retry, bad):
    with pytest.raises(LLMBadRequest) as info:
        embed(harness, instant_retry, ["fine", bad])
    assert "xxxxxxxxxxxxxxxxxxxx" not in str(info.value)


def test_throttled_then_success(instant_retry):
    h = TitanHarness()
    h.throttle()
    h.ok()
    vecs = embed(h, instant_retry, ["hi"])
    assert len(vecs) == 1
    h.stubber.assert_no_pending_responses()


def test_timeout_raises(instant_retry):
    h = TitanHarness()
    h.timeout()
    with pytest.raises(LLMTimeout):
        embed(h, instant_retry, ["hi"])


def test_usage_recorded_with_cost(instant_retry):
    h = TitanHarness()
    h.ok(1000)
    h.ok(500)
    embed(h, instant_retry, ["one", "two"])
    recs = h.sink.records()
    assert [r.step for r in recs] == ["embed"]
    rec = recs[0]
    assert rec.prompt_id == "embed" and rec.status == "ok"
    assert rec.usage.input_tokens == 1500
    assert rec.cost_usd == Decimal("0.00003")
    assert rec.cost_usd == titan_prices().cost("bedrock_titan", MODEL, rec.usage)


def test_error_message_has_no_input_text(instant_retry):
    h = TitanHarness()
    h.timeout()
    secret = "my-secret-resume-text"
    with pytest.raises(LLMTimeout) as info:
        embed(h, instant_retry, [secret])
    assert secret not in str(info.value)
