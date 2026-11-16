import threading
import time

import pytest
from pydantic import BaseModel, ValidationError

from app.ports.llm import CallMeta, CancelToken, LLMRequest, Message, Usage
from app.ports.llm_errors import (
    LLMBadRequest,
    LLMCircuitOpen,
    LLMOutputInvalid,
    LLMOutputTruncated,
    LLMThrottled,
    LLMTimeout,
    LLMUnavailable,
)


class Out(BaseModel):
    x: int


def test_request_rejects_trailing_assistant_message() -> None:
    with pytest.raises(ValidationError):
        LLMRequest[Out](
            step="s",
            messages=[Message(role="user", content="a"), Message(role="assistant", content="b")],
            metadata=CallMeta(prompt_id="p"),
        )


def test_usage_add_sums_all_fields() -> None:
    a = Usage(input_tokens=1, output_tokens=2, cache_read_tokens=3, cache_write_tokens=4)
    b = Usage(input_tokens=10, output_tokens=20, cache_read_tokens=30, cache_write_tokens=40)
    assert a + b == Usage(
        input_tokens=11, output_tokens=22, cache_read_tokens=33, cache_write_tokens=44
    )


def test_error_flags() -> None:
    assert LLMThrottled.retryable and LLMThrottled.trips_breaker
    assert not LLMBadRequest.retryable
    assert issubclass(LLMOutputTruncated, LLMOutputInvalid)
    assert issubclass(LLMCircuitOpen, LLMUnavailable)
    assert not LLMCircuitOpen.retryable
    assert not LLMCircuitOpen.trips_breaker


def test_error_str_format() -> None:
    err = LLMTimeout("deadline exceeded", provider="bedrock", model="m")
    assert str(err) == "timeout provider=bedrock model=m: deadline exceeded"


def test_cancel_token_wait_returns_after_cancel_from_other_thread() -> None:
    import asyncio

    token = CancelToken()
    assert not token.is_cancelled
    threading.Timer(0.05, token.cancel).start()
    start = time.monotonic()
    asyncio.run(token.wait())
    assert token.is_cancelled
    assert time.monotonic() - start < 0.3
