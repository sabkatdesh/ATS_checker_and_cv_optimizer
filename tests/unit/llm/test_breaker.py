import threading

import pytest

from app.adapters.llm._breaker import BreakerRegistry, CircuitBreaker
from app.ports.llm_errors import LLMCircuitOpen


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make() -> tuple[CircuitBreaker, Clock]:
    clock = Clock()
    return CircuitBreaker(key=("bedrock", "us.m"), clock=clock), clock


def trip(b: CircuitBreaker, n: int = 5) -> None:
    for _ in range(n):
        b.record_failure()


def test_opens_after_5_failures_within_60s() -> None:
    b, clock = make()
    trip(b, 4)
    assert b.state == "closed"
    clock.now += 10
    b.record_failure()
    assert b.state == "open"


def test_does_not_open_when_failures_spread_over_more_than_60s() -> None:
    b, clock = make()
    trip(b, 4)
    clock.now += 61
    b.record_failure()
    assert b.state == "closed"
    b.before_call()


def test_success_resets_count() -> None:
    b, _ = make()
    trip(b, 4)
    b.record_success()
    trip(b, 4)
    assert b.state == "closed"


def test_open_fails_fast_for_30s() -> None:
    b, clock = make()
    trip(b)
    clock.now += 29.9
    with pytest.raises(LLMCircuitOpen) as exc:
        b.before_call()
    assert exc.value.provider == "bedrock"
    assert exc.value.model == "us.m"


def test_half_open_after_30s_allows_one_probe() -> None:
    b, clock = make()
    trip(b)
    clock.now += 30
    assert b.state == "half_open"
    b.before_call()
    with pytest.raises(LLMCircuitOpen):
        b.before_call()


def test_probe_success_closes() -> None:
    b, clock = make()
    trip(b)
    clock.now += 30
    b.before_call()
    b.record_success()
    assert b.state == "closed"
    b.before_call()
    b.before_call()


def test_probe_failure_reopens_for_30s() -> None:
    b, clock = make()
    trip(b)
    clock.now += 30
    b.before_call()
    b.record_failure()
    assert b.state == "open"
    clock.now += 29.9
    with pytest.raises(LLMCircuitOpen):
        b.before_call()
    clock.now += 0.2
    b.before_call()


def test_registry_isolates_keys() -> None:
    reg = BreakerRegistry(clock=Clock())
    trip(reg.get("bedrock", "us."))
    assert reg.get("bedrock", "us.") is reg.get("bedrock", "us.")
    assert reg.get("bedrock", "us.").state == "open"
    assert reg.get("bedrock", "global.").state == "closed"
    reg.get("bedrock", "global.").before_call()


def test_thread_safety_smoke() -> None:
    b, _ = make()
    errors: list[BaseException] = []

    def work() -> None:
        try:
            for _ in range(100):
                b.record_failure()
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert b.state == "open"


def _half_open() -> tuple[CircuitBreaker, Clock]:
    b, clock = make()
    trip(b)
    clock.now += 30
    assert b.state == "half_open"
    return b, clock


def test_release_probe_frees_half_open_slot_without_outcome() -> None:
    b, _ = _half_open()
    gen = b.before_call()
    with pytest.raises(LLMCircuitOpen):
        b.before_call()
    b.release_probe(gen)
    assert b.state == "half_open"
    b.before_call()  # slot is free again


def test_release_probe_is_noop_when_not_the_probe() -> None:
    b, _ = make()
    stale = b.before_call()  # admitted while closed
    trip(b)
    b.release_probe(stale)
    assert b.state == "open"
    b2, _ = _half_open()
    probe = b2.before_call()
    b2.release_probe(stale)  # an older generation never frees the probe
    with pytest.raises(LLMCircuitOpen):
        b2.before_call()
    b2.record_success(probe)
    assert b2.state == "closed"


def test_stale_outcomes_do_not_close_or_reopen_half_open() -> None:
    b, clock = make()
    stale = b.before_call()
    trip(b)
    clock.now += 30
    probe = b.before_call()
    b.record_success(stale)
    assert b.state == "half_open"
    b.record_failure(stale)
    assert b.state == "half_open"
    b.record_failure(probe)
    assert b.state == "open"
