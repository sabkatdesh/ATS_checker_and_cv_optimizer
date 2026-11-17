"""Shared call behaviour for every LLM provider: deadline, retry, breaker, cancel and repair.

Errors raised here carry constant phrases and schema paths only, never prompt or reply text.
"""

import asyncio
import dataclasses
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.adapters.llm._breaker import BreakerRegistry, CircuitBreaker
from app.adapters.llm._call_state import CallState, enrich, first_of
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import Deadline, RetryPolicy, call_with_retry
from app.adapters.llm._structured import (
    json_instruction,
    parse_structured,
    provider_schema,
    repair_turns,
)
from app.ports.llm import CancelToken, LLMRequest, LLMResult, Message, Route, T, Usage
from app.ports.llm_errors import (
    LLMError,
    LLMOutputInvalid,
    LLMOutputTruncated,
    LLMRefused,
    LLMTimeout,
    LLMUnavailable,
)

Stop = Literal["end", "max_tokens", "refused", "other"]


@dataclass(frozen=True)
class WireRequest:
    system: str
    messages: tuple[Message, ...]
    model: str
    max_tokens: int
    temperature: float | None
    json_schema: dict[str, Any] | None
    schema_name: str | None
    cache_prefix: bool
    stream: bool
    timeout_s: float


@dataclass(frozen=True)
class RawCompletion:
    text: str
    stop: Stop
    raw_stop_reason: str
    usage: Usage


class Transport(Protocol):
    name: str
    supports_native_schema: bool

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        """Raise only fresh LLMError instances (one per failure, never shared) and let
        asyncio.CancelledError propagate. Anything else is reported as LLMUnavailable."""
        ...


class BaseProvider:
    """Implements LLMProvider on top of a Transport that only knows the wire format."""

    def __init__(
        self,
        transport: Transport,
        *,
        prices: PriceTable,
        breakers: BreakerRegistry,
        retry: RetryPolicy = RetryPolicy(),  # noqa: B008 - frozen dataclass, safe default
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self.name = transport.name
        self._prices = prices
        self._breakers = breakers
        self._retry = retry
        self._clock = clock

    async def complete(self, req: LLMRequest[T], route: Route, cancel: CancelToken) -> LLMResult[T]:
        start = self._clock()
        state = CallState(Deadline(route.timeout_s, self._clock))
        schema = req.output_schema
        wire = self._wire(req, route)
        try:
            raw = await self._send(wire, route, cancel, state)
            self._classify(raw, route, structured=schema is not None)
            repaired = False
            output: T | str
            if schema is None:
                output = raw.text
            else:
                try:
                    output = parse_structured(raw.text, schema)
                except LLMOutputInvalid as bad:
                    if state.deadline.expired:  # no time left for the repair
                        raise bad
                    turns = repair_turns(list(wire.messages), raw.text, bad.detail)
                    raw = await self._send(
                        dataclasses.replace(wire, messages=tuple(turns)), route, cancel, state
                    )
                    self._classify(raw, route, structured=True)
                    output = self._parse_again(raw.text, schema, route)
                    repaired = True
        except LLMError as err:
            enrich(err, state, self.name, route.model)
            raise
        return LLMResult[T](
            output=output,
            usage=state.usage,
            cost_usd=self._prices.cost(self.name, route.model, state.usage),
            provider=self.name,
            model=route.model,
            latency_ms=int((self._clock() - start) * 1000),
            repaired=repaired,
            stop_reason=raw.stop,
            attempts=state.attempts,
        )

    def _wire(self, req: LLMRequest[T], route: Route) -> WireRequest:
        schema = req.output_schema
        system, json_schema, schema_name = req.system, None, None
        if schema is not None:
            native = route.structured_mode == "native" and self._transport.supports_native_schema
            if native:
                json_schema, schema_name = provider_schema(schema), schema.__name__
            else:
                instruction = json_instruction(schema.model_json_schema())
                system = f"{system}\n\n{instruction}" if system else instruction
        return WireRequest(
            system=system,
            messages=tuple(req.messages),
            model=route.model,
            max_tokens=route.max_tokens,
            temperature=route.temperature,
            json_schema=json_schema,
            schema_name=schema_name,
            cache_prefix=req.cache_prefix,
            stream=route.stream,
            timeout_s=route.timeout_s,
        )

    async def _send(
        self, wire: WireRequest, route: Route, cancel: CancelToken, state: CallState
    ) -> RawCompletion:
        breaker = self._breakers.get(self.name, route.model)

        async def attempt(timeout_s: float) -> RawCompletion:
            state.attempts += 1
            return await self._attempt(
                dataclasses.replace(wire, timeout_s=timeout_s), breaker, cancel
            )

        raw, _ = await call_with_retry(
            attempt,
            policy=dataclasses.replace(self._retry, max_attempts=route.max_attempts),
            deadline=state.deadline,
            cancel=cancel,
            on_failure=lambda _err: None,
        )
        state.usage = state.usage + raw.usage
        return raw

    async def _attempt(
        self, wire: WireRequest, breaker: CircuitBreaker, cancel: CancelToken
    ) -> RawCompletion:
        generation = breaker.before_call()
        outcome: Literal["success", "failure", "release"] = "release"
        try:
            raw = await asyncio.wait_for(
                first_of(self._transport.send(wire, cancel), cancel), wire.timeout_s
            )
            outcome = "success"
            return raw
        except TimeoutError:
            outcome = "failure"
            raise LLMTimeout("deadline exceeded", provider=self.name, model=wire.model) from None
        except LLMError as err:
            if err.trips_breaker:
                outcome = "failure"
            raise
        except Exception:  # transport bug: keep none of its text; CancelledError still propagates
            outcome = "failure"
            raise LLMUnavailable(
                "unexpected transport error", provider=self.name, model=wire.model
            ) from None
        finally:
            if outcome == "success":
                breaker.record_success(generation)
            elif outcome == "failure":
                breaker.record_failure(generation)
            else:  # cancelled, caller error, or anything unexpected: free a half-open probe
                breaker.release_probe(generation)

    def _classify(self, raw: RawCompletion, route: Route, *, structured: bool) -> None:
        p, m = self.name, route.model
        if raw.stop == "refused":
            raise LLMRefused("model refused", provider=p, model=m)
        if structured and raw.stop == "max_tokens":
            raise LLMOutputTruncated("structured output hit max_tokens", provider=p, model=m)
        if not structured and not raw.text.strip():
            raise LLMOutputInvalid("empty response", provider=p, model=m)

    def _parse_again(self, text: str, schema: type[T], route: Route) -> T:
        try:
            return parse_structured(text, schema)
        except LLMOutputInvalid as bad:
            raise LLMOutputInvalid(bad.detail, provider=self.name, model=route.model) from None
