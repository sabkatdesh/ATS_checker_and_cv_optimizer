"""Per-(provider, model) circuit breaker with a single half-open probe."""

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Literal

from app.ports.llm_errors import LLMCircuitOpen

State = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(
        self,
        *,
        key: tuple[str, str],
        threshold: int = 5,
        window_s: float = 60,
        cooldown_s: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._key = key
        self._threshold = threshold
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None
        self._probe_in_flight = False

    def _state_locked(self) -> State:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self._cooldown_s:
            return "half_open"
        return "open"

    @property
    def state(self) -> State:
        with self._lock:
            return self._state_locked()

    def before_call(self) -> None:
        with self._lock:
            state = self._state_locked()
            if state == "closed":
                return
            if state == "half_open" and not self._probe_in_flight:
                self._probe_in_flight = True
                return
        raise LLMCircuitOpen("circuit open", provider=self._key[0], model=self._key[1])

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._opened_at = None
            self._probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            if self._opened_at is not None and self._probe_in_flight:
                self._opened_at = now
                self._probe_in_flight = False
                return
            if self._opened_at is not None:
                return
            self._failures.append(now)
            while self._failures and now - self._failures[0] > self._window_s:
                self._failures.popleft()
            if len(self._failures) >= self._threshold:
                self._opened_at = now
                self._failures.clear()


class BreakerRegistry:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._breakers: dict[tuple[str, str], CircuitBreaker] = {}

    def get(self, provider: str, model: str) -> CircuitBreaker:
        key = (provider, model)
        with self._lock:
            breaker = self._breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker(key=key, clock=self._clock)
                self._breakers[key] = breaker
            return breaker
