"""Where LangGraph keeps thread state: one saver per run, a shared reader, and thread deletion."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.pipeline.checkpoint_types import checkpoint_serde


class CheckpointerFactory(Protocol):
    def open_async(self) -> AbstractAsyncContextManager[BaseCheckpointSaver]:
        """A saver for one run, entered inside the coroutine run_sync runs (so it lives on that
        loop and is closed with it)."""
        ...

    def reader(self) -> BaseCheckpointSaver:
        """A sync saver for get_state and summaries, safe to share across threads."""
        ...

    def delete_thread(self, thread_id: str) -> None: ...


class MemoryCheckpointerFactory:
    """One in-memory saver shared by every run, so a paused thread can resume (tests, fake mode)."""

    def __init__(self) -> None:
        self._saver: MemorySaver = MemorySaver(serde=checkpoint_serde())

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[BaseCheckpointSaver]:
        yield self._saver

    def open_async(self) -> AbstractAsyncContextManager[BaseCheckpointSaver]:
        return self._open()

    def reader(self) -> BaseCheckpointSaver:
        return self._saver

    def delete_thread(self, thread_id: str) -> None:
        self._saver.delete_thread(thread_id)
