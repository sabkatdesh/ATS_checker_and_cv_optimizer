import asyncio
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.ports.llm import CallMeta, LLMRequest, LLMResult, Message, Route, Usage
from app.ports.llm_errors import LLMTimeout
from scripts._cost_gate import BudgetedGateway, BudgetExceeded, worst_case_usd

PRICES = PriceTable({("p", "m"): ModelPrice(input_per_m=Decimal("3"), output_per_m=Decimal("15"))})
ROUTE = Route(
    step="s",
    provider="p",
    model="m",
    max_tokens=1000,
    temperature=0,
    timeout_s=10,
    structured_mode="prompt",
)


class Out(BaseModel):
    ok: bool = True


def _req() -> LLMRequest[Out]:
    return LLMRequest[Out](
        step="s",
        messages=[Message(role="user", content="x")],
        output_schema=Out,
        metadata=CallMeta(prompt_id="s"),
    )


class _Inner:
    def __init__(self, *, cost: str = "0.05", error: Exception | None = None) -> None:
        self.cost = Decimal(cost)
        self.error = error
        self.calls = 0

    async def complete(self, req, cancel=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.error is not None:
            raise self.error
        return LLMResult[Out](
            output=Out(),
            usage=Usage(),
            cost_usd=self.cost,
            provider="p",
            model="m",
            latency_ms=1,
            repaired=False,
            stop_reason="end_turn",
            attempts=1,
        )


def _worst(_req: LLMRequest[Out]) -> Decimal:
    return Decimal("0.06")


def test_worst_case_is_main_plus_repair():
    # main: 2000 in + 1000 out = 0.006 + 0.015; repair: 3000 in + 1000 out = 0.009 + 0.015
    assert worst_case_usd(ROUTE, 2000, PRICES, provider="p") == Decimal("0.045000")


def test_budget_refuses_call_over_cap():
    inner = _Inner(cost="0.05")
    gate = BudgetedGateway(inner, Decimal("0.10"), _worst)
    asyncio.run(gate.complete(_req()))
    with pytest.raises(BudgetExceeded):
        asyncio.run(gate.complete(_req()))
    assert inner.calls == 1


def test_budget_adds_actual_cost():
    gate = BudgetedGateway(_Inner(cost="0.012"), Decimal("1"), _worst)
    asyncio.run(gate.complete(_req()))
    asyncio.run(gate.complete(_req()))
    assert gate.spent == Decimal("0.024")


def test_budget_unknown_billing_adds_worst():
    gate = BudgetedGateway(_Inner(error=LLMTimeout("slow")), Decimal("1"), _worst)
    with pytest.raises(LLMTimeout):
        asyncio.run(gate.complete(_req()))
    assert gate.spent == Decimal("0.06")


def test_budget_known_usage_on_error_adds_that_cost():
    err = LLMTimeout("slow", usage=Usage(input_tokens=1000, output_tokens=100))
    gate = BudgetedGateway(
        _Inner(error=err), Decimal("1"), _worst, usage_cost=lambda _r, _u: Decimal("0.004")
    )
    with pytest.raises(LLMTimeout):
        asyncio.run(gate.complete(_req()))
    assert gate.spent == Decimal("0.004")
