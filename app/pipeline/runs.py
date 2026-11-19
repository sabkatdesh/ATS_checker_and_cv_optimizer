"""Open runs by session id, so a cancel from any thread reaches the run's token and hooks."""

import threading

from app.pipeline.context import RunContext
from app.pipeline.hooks import NodeHooks, NoopHooks
from app.ports.llm import CancelToken


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunContext] = {}
        self._lock = threading.Lock()

    def open(self, session_id: str, hooks: NodeHooks | None = None) -> RunContext:
        """Start tracking a run. A context already open (cancelled while paused) keeps its token."""
        with self._lock:
            existing = self._runs.get(session_id)
            token = existing.cancel if existing is not None else CancelToken()
            ctx = RunContext(session_id=session_id, cancel=token, hooks=hooks or NoopHooks())
            self._runs[session_id] = ctx
            return ctx

    def get(self, session_id: str) -> RunContext:
        """The open run's context, or a fresh default one (not tracked) when none is open."""
        with self._lock:
            ctx = self._runs.get(session_id)
        return ctx if ctx is not None else RunContext(session_id=session_id, cancel=CancelToken())

    def cancel(self, session_id: str) -> bool:
        with self._lock:
            ctx = self._runs.get(session_id)
        if ctx is None:
            return False
        ctx.cancel.cancel()
        return True

    def close(self, session_id: str) -> None:
        with self._lock:
            self._runs.pop(session_id, None)
