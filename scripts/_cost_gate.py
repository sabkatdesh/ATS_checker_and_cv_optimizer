"""Shared spend guard for the paid-call scripts: worst-case pricing and a budgeted gateway."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._structured import json_instruction
from app.ports.llm import CancelToken, LLMGateway, LLMRequest, LLMResult, Route, Usage
from app.ports.llm_errors import LLMError

MARGIN = 1.3  # chars/4 under-counts JSON and prose; pad the input estimate


class BudgetExceeded(Exception):  # noqa: N818 - named in the plan
    """Raised before a call whose worst case would push the spend over the cap."""


def est_input_tokens(req: LLMRequest[Any]) -> int:
    model = req.output_schema
    schema = json_instruction(model.model_json_schema()) if model else ""
    chars = len(req.system) + len(schema) + sum(len(m.content) for m in req.messages)
    return int(chars / 4 * MARGIN) + 50


def worst_case_usd(
    route: Route, est_input_tokens: int, prices: PriceTable, *, provider: str
) -> Decimal:
    """One call at the route's max_tokens plus one repair (its input also carries the bad answer).

    The fallback route is not counted: the measuring scripts disable fallbacks.
    """
    cap = route.max_tokens
    main = prices.cost(
        provider, route.model, Usage(input_tokens=est_input_tokens, output_tokens=cap)
    )
    repair = Usage(input_tokens=est_input_tokens + cap, output_tokens=cap)
    return main + prices.cost(provider, route.model, repair)


class BudgetedGateway:
    """Wraps a gateway; a call is never started if spent + its worst case would exceed the cap."""

    def __init__(
        self,
        inner: LLMGateway,
        cap: Decimal,
        worst: Callable[[LLMRequest[Any]], Decimal],
        usage_cost: Callable[[LLMRequest[Any], Usage], Decimal] | None = None,
    ) -> None:
        self._inner = inner
        self._cap = cap
        self._worst = worst
        self._usage_cost = usage_cost
        self.spent = Decimal(0)

    async def complete(self, req: Any, cancel: CancelToken | None = None) -> LLMResult[Any]:
        worst = self._worst(req)
        if self.spent + worst > self._cap:
            raise BudgetExceeded(f"step {req.step}: spent {self.spent} + worst {worst} > cap")
        try:
            result = await self._inner.complete(req, cancel)
        except LLMError as err:
            if err.usage is not None and self._usage_cost is not None:
                self.spent += self._usage_cost(req, err.usage)
            else:
                self.spent += worst  # unknown billing: assume the worst
            raise
        self.spent += result.cost_usd
        return result
