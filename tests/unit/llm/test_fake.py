import asyncio
from decimal import Decimal

import pytest
from pydantic import BaseModel, Field

from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.fake import Fail, Hang, Reply, build_fake_provider
from app.domain.match.schemas import Eligibility
from app.ports.llm import CallMeta, CancelToken, LLMRequest, Message, Route, Usage
from app.ports.llm_errors import LLMBadRequest, LLMThrottled


class Needs(BaseModel):
    name: str
    count: int
    tags: list[str]


PRICES = PriceTable({("fake", "m"): ModelPrice(input_per_m=Decimal(1), output_per_m=Decimal(1))})
ROUTE = Route(
    step="s",
    provider="fake",
    model="m",
    max_tokens=100,
    temperature=None,
    timeout_s=10,
    structured_mode="prompt",
)


async def _no_sleep(_d: float) -> None:
    return None


def _provider(script=None):
    return build_fake_provider(
        prices=PRICES,
        breakers=BreakerRegistry(),
        retry=RetryPolicy(sleep=_no_sleep, rand=lambda: 1.0),
        script=script,
    )


def _req(prompt_id: str, schema=None):
    return LLMRequest(
        step="s",
        messages=[Message(role="user", content="hi")],
        output_schema=schema,
        metadata=CallMeta(prompt_id=prompt_id),
    )


def _run(provider, req):
    return asyncio.run(provider.complete(req, ROUTE, CancelToken()))


def test_fake_is_deterministic():
    a = _run(_provider(), _req("eligibility", Eligibility))
    b = _run(_provider(), _req("eligibility", Eligibility))
    assert a.output == b.output and a.usage == b.usage == Usage(input_tokens=10, output_tokens=5)
    assert a.output.score == 60


def test_fake_records_requests():
    p = _provider()
    _run(p, _req("anything"))
    assert len(p.transport.sent) == 1
    assert p.transport.sent[0].messages[-1].content == "hi"


def test_scripted_outcomes_pop_first_then_defaults():
    p = _provider({"eligibility": [Fail(LLMThrottled, retry_after_s=0.1), Reply('{"score": 0}')]})
    res = _run(p, _req("eligibility", Eligibility))
    assert res.attempts == 2 and res.output.score == 0
    assert _run(p, _req("eligibility", Eligibility)).output.score == 60


def test_schema_default_instance_without_canned_file():
    res = _run(_provider(), _req("unknown.key", Needs))
    assert res.output == Needs(name="", count=0, tags=[])


def test_unknown_key_text_is_empty_object():
    assert _run(_provider(), _req("unknown.key")).output == "{}"


def test_key_falls_back_to_step():
    p = _provider({"s": [Reply("scripted")]})
    req = LLMRequest(
        step="s", messages=[Message(role="user", content="x")], metadata=CallMeta(prompt_id="")
    )
    assert _run(p, req).output == "scripted"


def test_hang_that_is_not_cancelled_falls_through_to_default():
    assert _run(_provider({"k": [Hang(0.01)]}), _req("k")).output == "{}"


@pytest.mark.parametrize("bad", ["../../pyproject", "a/b", "a\\b"])
def test_defaults_lookup_rejects_path_separators(bad):
    assert _run(_provider(), _req(bad)).output == "{}"


class Constrained(BaseModel):
    code: str = Field(min_length=3)


def test_transport_used_without_provider_fails_loudly():
    from app.adapters.llm.fake import FakeTransport

    transport = FakeTransport()
    from app.adapters.llm._base import WireRequest

    w = WireRequest(
        system="",
        messages=(Message(role="user", content="hi"),),
        model="m",
        max_tokens=10,
        temperature=None,
        json_schema=None,
        schema_name=None,
        cache_prefix=False,
        stream=False,
        timeout_s=1,
    )
    with pytest.raises(RuntimeError, match="FakeTransport must be used through FakeProvider"):
        asyncio.run(transport.send(w, CancelToken()))
    assert transport.sent == []


def test_default_instance_names_schema_when_constraints_block_it():
    from app.adapters.llm.fake import default_instance

    with pytest.raises(LLMBadRequest, match="Constrained") as info:
        default_instance(Constrained)
    assert "min_length" not in str(info.value) and "''" not in str(info.value)


def test_constrained_schema_without_script_surfaces_named_error_through_provider():
    with pytest.raises(LLMBadRequest, match="Constrained"):
        _run(_provider(), _req("unknown.key", Constrained))
