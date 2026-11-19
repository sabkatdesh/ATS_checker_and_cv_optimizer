"""Scripted LLMGateway for pipeline tests: per-step queues of outputs or errors."""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.ports.llm import CancelToken, LLMRequest, LLMResult, Usage
from app.ports.llm_errors import LLMCancelled, LLMError


@dataclass(frozen=True)
class Hang:
    seconds: float


Outcome = BaseModel | LLMError | Hang


class ScriptedGateway:
    def __init__(self, script: dict[str, list[Outcome]]) -> None:
        self._script = {step: list(outcomes) for step, outcomes in script.items()}
        self.requests: list[LLMRequest[Any]] = []
        self.cancel_tokens: list[CancelToken | None] = []

    def push(self, step: str, *outcomes: Outcome) -> None:
        self._script.setdefault(step, []).extend(outcomes)

    async def complete(
        self, req: LLMRequest[Any], cancel: CancelToken | None = None
    ) -> LLMResult[Any]:
        self.requests.append(req)
        self.cancel_tokens.append(cancel)
        queue = self._script.get(req.step)
        if not queue:
            raise AssertionError(f"unscripted step: {req.step}")
        outcome = queue.pop(0)
        if isinstance(outcome, LLMError):
            raise outcome
        if isinstance(outcome, Hang):
            await _hang(outcome.seconds, cancel)
            raise AssertionError(f"hang elapsed without cancel: {req.step}")
        return LLMResult(
            output=outcome,
            usage=Usage(),
            cost_usd=Decimal("0"),
            provider="scripted",
            model="scripted",
            latency_ms=0,
            repaired=False,
            stop_reason="end_turn",
            attempts=1,
        )


async def _hang(seconds: float, cancel: CancelToken | None) -> None:
    waited = 0.0
    while waited < seconds:
        if cancel is not None and cancel.is_cancelled:
            raise LLMCancelled("cancelled")
        await asyncio.sleep(0.01)
        waited += 0.01
