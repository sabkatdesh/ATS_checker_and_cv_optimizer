"""Full-jitter retry with a per-call deadline and cancel-aware sleeping."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.ports.llm import CancelToken
from app.ports.llm_errors import LLMCancelled, LLMError


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_s: float = 1.0
    cap_s: float = 20.0
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    rand: Callable[[], float] = random.random


class Deadline:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._end = clock() + seconds

    def remaining(self) -> float:
        return max(0.0, self._end - self._clock())

    @property
    def expired(self) -> bool:
        return self.remaining() <= 0.0


def backoff_s(attempt: int, policy: RetryPolicy, retry_after_s: float | None) -> float:
    delay = policy.rand() * min(policy.cap_s, policy.base_s * 2 ** (attempt - 1))
    if retry_after_s:
        delay = max(delay, retry_after_s)
    return min(delay, policy.cap_s)


async def _cancellable_sleep(policy: RetryPolicy, delay: float, cancel: CancelToken) -> None:
    sleeper = asyncio.ensure_future(policy.sleep(delay))
    waiter = asyncio.ensure_future(cancel.wait())
    try:
        await asyncio.wait({sleeper, waiter}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sleeper, waiter):
            if not task.done():
                task.cancel()
    if cancel.is_cancelled:
        raise LLMCancelled("cancelled during backoff")
    sleeper.result()


async def call_with_retry[R](
    attempt_fn: Callable[[float], Awaitable[R]],
    *,
    policy: RetryPolicy,
    deadline: Deadline,
    cancel: CancelToken,
    on_failure: Callable[[LLMError], None],
) -> tuple[R, int]:
    attempt = 0
    while True:
        if cancel.is_cancelled:
            raise LLMCancelled("cancelled before attempt")
        attempt += 1
        try:
            return await attempt_fn(deadline.remaining()), attempt
        except LLMError as err:
            on_failure(err)
            if not err.retryable or attempt >= policy.max_attempts:
                raise
            delay = backoff_s(attempt, policy, err.retry_after_s)
            if delay >= deadline.remaining():
                raise
            await _cancellable_sleep(policy, delay, cancel)
