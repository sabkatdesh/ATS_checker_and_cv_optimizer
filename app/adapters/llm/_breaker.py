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
        self._generation = 0

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

    def before_call(self) -> int:
        """Admit a call or raise LLMCircuitOpen. Returns the generation to pass back with the
        outcome, so results of calls admitted before the breaker last opened are ignored."""
        with self._lock:
            state = self._state_locked()
            if state == "closed":
                return self._generation
            if state == "half_open" and not self._probe_in_flight:
                self._probe_in_flight = True
                return self._generation
        raise LLMCircuitOpen("circuit open", provider=self._key[0], model=self._key[1])

    def _stale_locked(self, generation: int | None) -> bool:
        return generation is not None and generation != self._generation

    def _open_locked(self, now: float) -> None:
        self._opened_at = now
        self._generation += 1
        self._probe_in_flight = False

    def record_success(self, generation: int | None = None) -> None:
        with self._lock:
            if self._stale_locked(generation):
                return
            self._failures.clear()
            self._opened_at = None
            self._probe_in_flight = False

    def record_failure(self, generation: int | None = None) -> None:
        with self._lock:
            if self._stale_locked(generation):
                return
            now = self._clock()
            if self._opened_at is not None and self._probe_in_flight:
                self._open_locked(now)
                return
            if self._opened_at is not None:
                return
            self._failures.append(now)
            while self._failures and now - self._failures[0] > self._window_s:
                self._failures.popleft()
            if len(self._failures) >= self._threshold:
                self._open_locked(now)
                self._failures.clear()

    def release_probe(self, generation: int | None = None) -> None:
        """Free the half-open probe slot without recording an outcome (cancel, bad request).
        A no-op when the caller is not the probe (closed, or an older generation)."""
        with self._lock:
            if self._opened_at is None or self._stale_locked(generation):
                return
            self._probe_in_flight = False


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
