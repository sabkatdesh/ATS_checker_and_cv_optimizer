"""LLM error hierarchy. `detail` is always a constant phrase, never provider or user text."""

from typing import ClassVar

from app.ports.llm import Usage


class LLMError(Exception):
    kind: ClassVar[str] = "error"
    retryable: ClassVar[bool] = False
    trips_breaker: ClassVar[bool] = False

    def __init__(
        self,
        detail: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        usage: Usage | None = None,
        retry_after_s: float | None = None,
        attempts: int | None = None,
    ) -> None:
        self.detail = detail
        self.attempts = attempts
        self.provider = provider
        self.model = model
        self.usage = usage
        self.retry_after_s = retry_after_s
        super().__init__(detail)

    def __str__(self) -> str:
        # Computed on demand so provider/model filled in later by an adapter show up.
        return f"{self.kind} provider={self.provider} model={self.model}: {self.detail}"


class LLMTimeout(LLMError):
    kind = "timeout"
    retryable = True
    trips_breaker = True


class LLMThrottled(LLMError):
    kind = "throttled"
    retryable = True
    trips_breaker = True


class LLMUnavailable(LLMError):
    kind = "unavailable"
    retryable = True
    trips_breaker = True


class LLMCircuitOpen(LLMUnavailable):
    kind = "circuit_open"
    retryable = False
    trips_breaker = False


class LLMAllRoutesFailed(LLMUnavailable):
    kind = "all_routes_failed"
    retryable = False
    trips_breaker = False

    def __init__(
        self,
        detail: str,
        *,
        kinds: tuple[str, ...] = (),
        provider: str | None = None,
        model: str | None = None,
        usage: Usage | None = None,
        retry_after_s: float | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(
            detail,
            provider=provider,
            model=model,
            usage=usage,
            retry_after_s=retry_after_s,
            attempts=attempts,
        )
        self.kinds = kinds


class LLMRefused(LLMError):
    kind = "refused"


class LLMOutputInvalid(LLMError):
    kind = "output_invalid"


class LLMOutputTruncated(LLMOutputInvalid):
    kind = "output_truncated"


class LLMBadRequest(LLMError):
    kind = "bad_request"


class LLMAuthError(LLMError):
    kind = "auth"


class LLMCancelled(LLMError):
    kind = "cancelled"
