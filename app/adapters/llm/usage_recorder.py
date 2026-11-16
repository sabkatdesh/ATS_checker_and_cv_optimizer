"""Builds a usage record for every LLM call, writes it to the sink and logs it."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import structlog

from app.adapters.llm._pricing import PriceTable
from app.ports.llm import LLMRequest, LLMResult, Route, Usage
from app.ports.llm_errors import LLMError
from app.ports.usage import LlmCallRecord, UsageSink


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UsageRecorder:
    def __init__(
        self,
        sink: UsageSink,
        prices: PriceTable,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._sink = sink
        self._prices = prices
        self._clock = clock

    def record(
        self,
        req: LLMRequest,  # type: ignore[type-arg]
        route: Route,
        *,
        result: LLMResult | None,  # type: ignore[type-arg]
        error: LLMError | None,
        latency_ms: int,
        fallback_used: bool,
        attempts: int | None = None,
    ) -> LlmCallRecord:
        if result is not None:
            usage, cost = result.usage, result.cost_usd
            provider, model = result.provider, result.model
            n_attempts, repaired = result.attempts, result.repaired
            status, error_kind = "ok", None
        else:
            usage = (error.usage if error else None) or Usage()
            provider, model = route.provider, route.model
            cost = (
                self._prices.cost(provider, model, usage)
                if self._prices.has(provider, model)
                else Decimal(0)
            )
            n_attempts, repaired = (attempts if attempts is not None else 1), False
            status, error_kind = "error", error.kind if error else "error"
        meta = req.metadata
        rec = LlmCallRecord(
            at=self._clock(),
            step=req.step,
            prompt_id=meta.prompt_id,
            prompt_version=meta.prompt_version,
            provider=provider,
            model=model,
            status=status,  # type: ignore[arg-type]
            error_kind=error_kind,
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            attempts=n_attempts,
            repaired=repaired,
            fallback_used=fallback_used,
            user_id=meta.user_id,
            session_id=meta.session_id,
            job_id=meta.job_id,
        )
        self._sink.write(rec)
        structlog.get_logger("llm").info(
            "llm.call",
            step=rec.step,
            prompt_id=rec.prompt_id,
            provider=rec.provider,
            model=rec.model,
            status=rec.status,
            error_kind=rec.error_kind,
            tokens=usage.input_tokens + usage.output_tokens,
            cost_usd=str(rec.cost_usd),
            latency_ms=rec.latency_ms,
            attempts=rec.attempts,
            repaired=rec.repaired,
            fallback_used=rec.fallback_used,
        )
        return rec

    def record_embedding(
        self,
        *,
        provider: str,
        model: str,
        usage: Usage,
        latency_ms: int,
        attempts: int,
        error: LLMError | None = None,
    ) -> LlmCallRecord:
        """Record one embed call (all its texts) under step and prompt id "embed"."""
        cost = (
            self._prices.cost(provider, model, usage)
            if self._prices.has(provider, model)
            else Decimal(0)
        )
        rec = LlmCallRecord(
            at=self._clock(),
            step="embed",
            prompt_id="embed",
            prompt_version=1,
            provider=provider,
            model=model,
            status="error" if error else "ok",
            error_kind=error.kind if error else None,
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            attempts=attempts,
            repaired=False,
            fallback_used=False,
        )
        self._sink.write(rec)
        structlog.get_logger("llm").info(
            "llm.call",
            step="embed",
            provider=provider,
            model=model,
            status=rec.status,
            error_kind=rec.error_kind,
            tokens=usage.input_tokens,
            cost_usd=str(cost),
            latency_ms=latency_ms,
            attempts=attempts,
        )
        return rec
