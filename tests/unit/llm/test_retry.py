import asyncio

import pytest

from app.adapters.llm._retry import Deadline, RetryPolicy, backoff_s, call_with_retry
from app.ports.llm import CancelToken
from app.ports.llm_errors import (
    LLMAuthError,
    LLMBadRequest,
    LLMCancelled,
    LLMError,
    LLMThrottled,
    LLMUnavailable,
)


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def make(ft: FakeTime, **kw: float) -> RetryPolicy:
    return RetryPolicy(sleep=ft.sleep, rand=lambda: 1.0, **kw)


def run(ft: FakeTime, fn, *, seconds: float = 1000.0, cancel=None, failures=None):
    failed: list[LLMError] = failures if failures is not None else []
    out = asyncio.run(
        call_with_retry(
            fn,
            policy=make(ft),
            deadline=Deadline(seconds, ft.clock),
            cancel=cancel or CancelToken(),
            on_failure=failed.append,
        )
    )
    return out


def flaky(errors: list[LLMError], calls: list[float]):
    async def fn(timeout_s: float) -> str:
        calls.append(timeout_s)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return "ok"

    return fn


def test_backoff_sequence_full_jitter_upper_bounds() -> None:
    p = RetryPolicy(rand=lambda: 1.0)
    assert [backoff_s(a, p, None) for a in (1, 2, 3, 4)] == [1, 2, 4, 8]


def test_backoff_capped_at_20() -> None:
    p = RetryPolicy(rand=lambda: 1.0)
    assert backoff_s(10, p, None) == 20


def test_retry_after_honoured() -> None:
    p = RetryPolicy(rand=lambda: 1.0)
    assert backoff_s(1, p, 7) == 7
    assert backoff_s(1, p, 60) == 20


def test_retries_throttle_then_succeeds_attempts_2() -> None:
    ft, calls = FakeTime(), []
    result, attempts = run(ft, flaky([LLMThrottled("x")], calls))
    assert (result, attempts) == ("ok", 2)
    assert ft.sleeps == [1.0]


@pytest.mark.parametrize("err", [LLMBadRequest("x"), LLMAuthError("x")])
def test_never_retries_bad_request_or_auth(err: LLMError) -> None:
    ft, calls = FakeTime(), []
    with pytest.raises(type(err)):
        run(ft, flaky([err], calls))
    assert len(calls) == 1 and ft.sleeps == []


def test_gives_up_after_4_attempts_reraises_last() -> None:
    ft, calls = FakeTime(), []
    errs = [LLMThrottled(f"e{i}") for i in range(5)]
    with pytest.raises(LLMThrottled) as ei:
        run(ft, flaky(errs, calls))
    assert len(calls) == 4 and ei.value is errs[3]
    assert ft.sleeps == [1.0, 2.0, 4.0]


def test_stops_early_when_deadline_too_short() -> None:
    ft, calls = FakeTime(), []
    errs = [LLMUnavailable("a"), LLMUnavailable("b")]
    with pytest.raises(LLMUnavailable) as ei:
        run(ft, flaky(errs, calls), seconds=2.5)
    assert len(calls) == 2 and ei.value is errs[1]
    assert calls[0] == 2.5 and calls[1] == 1.5


def test_cancel_during_sleep_raises_cancelled() -> None:
    cancel = CancelToken()

    async def slow_sleep(_s: float) -> None:
        cancel.cancel()
        await asyncio.sleep(30)

    ft, calls = FakeTime(), []
    policy = RetryPolicy(sleep=slow_sleep, rand=lambda: 1.0)

    async def go() -> None:
        await call_with_retry(
            flaky([LLMThrottled("x")], calls),
            policy=policy,
            deadline=Deadline(100, ft.clock),
            cancel=cancel,
            on_failure=lambda e: None,
        )

    with pytest.raises(LLMCancelled):
        asyncio.run(asyncio.wait_for(go(), 5))
    assert len(calls) == 1


def test_cancel_checked_before_first_attempt() -> None:
    cancel = CancelToken()
    cancel.cancel()
    ft, calls = FakeTime(), []
    with pytest.raises(LLMCancelled):
        run(ft, flaky([], calls), cancel=cancel)
    assert calls == []


def test_on_failure_called_per_failed_attempt() -> None:
    ft, calls, seen = FakeTime(), [], []
    errs = [LLMThrottled("a"), LLMUnavailable("b")]
    run(ft, flaky(errs, calls), failures=seen)
    assert seen == errs


def test_expired_deadline_raises_timeout_without_calling_attempt() -> None:
    from app.ports.llm_errors import LLMTimeout

    ft, calls = FakeTime(), []
    with pytest.raises(LLMTimeout):
        run(ft, flaky([], calls), seconds=0.0)
    assert calls == []
