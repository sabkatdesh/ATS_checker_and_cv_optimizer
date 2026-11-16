"""LLMGateway: per-step routing with one fallback hop and a usage record for every call."""

import time
from collections.abc import Callable

import structlog

from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.usage_recorder import UsageRecorder
from app.config.llm_routes import RouteTable
from app.ports.llm import CancelToken, LLMRequest, LLMResult, Route, T, Usage
from app.ports.llm_errors import LLMAllRoutesFailed, LLMCancelled, LLMCircuitOpen, LLMError


def _falls_back(err: LLMError) -> bool:
    # A retryable error reaching here means the provider already spent its retries.
    return isinstance(err, LLMCircuitOpen) or err.retryable


class LLMRouter:
    def __init__(
        self,
        table: RouteTable,
        providers: ProviderRegistry,
        recorder: UsageRecorder,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._table = table
        self._providers = providers
        self._recorder = recorder
        self._clock = clock

    async def complete(self, req: LLMRequest[T], cancel: CancelToken | None = None) -> LLMResult[T]:
        cancel = cancel or CancelToken()
        primary = self._table.resolve(req.step)
        try:
            return await self._call(req, primary, cancel, fallback_used=False)
        except LLMError as err:
            fallback = self._table.fallback_for(req.step)
            # A caller who cancelled wants the call to stop, not a second route billed for it.
            if fallback is None or not _falls_back(err) or cancel.is_cancelled:
                raise
            first = err
        try:
            return await self._call(req, fallback, cancel, fallback_used=True)
        except LLMCancelled:
            raise
        except LLMError as fb_err:
            raise LLMAllRoutesFailed(
                "primary and fallback routes failed",
                kinds=(first.kind, fb_err.kind),
                provider=fallback.provider,
                model=fallback.model,
                usage=(first.usage or Usage()) + (fb_err.usage or Usage()),
                attempts=(first.attempts or 0) + (fb_err.attempts or 0),
            ) from fb_err

    async def _call(
        self, req: LLMRequest[T], route: Route, cancel: CancelToken, *, fallback_used: bool
    ) -> LLMResult[T]:
        start = self._clock()
        try:
            provider = self._providers.get(route.provider)
            result = await provider.complete(req, route, cancel)
        except LLMError as err:
            try:
                self._recorder.record(
                    req,
                    route,
                    result=None,
                    error=err,
                    latency_ms=int((self._clock() - start) * 1000),
                    fallback_used=fallback_used,
                    attempts=err.attempts,
                )
            except Exception:  # a broken sink must not hide the LLM error; log no content
                structlog.get_logger("llm").warning(
                    "llm.usage_record_failed", step=req.step, provider=route.provider
                )
            raise
        if fallback_used:
            result = result.model_copy(update={"fallback_used": True})
        self._recorder.record(
            req,
            route,
            result=result,
            error=None,
            latency_ms=result.latency_ms,
            fallback_used=fallback_used,
        )
        return result
