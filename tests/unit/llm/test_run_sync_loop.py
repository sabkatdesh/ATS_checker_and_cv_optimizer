"""run_sync loops must suit psycopg's async driver (no Proactor loop on Windows)."""

import asyncio
import sys

from app.adapters.llm import _sync
from app.adapters.llm._sync import run_sync


def test_windows_uses_selector_loop(monkeypatch):
    monkeypatch.setattr(_sync.sys, "platform", "win32")
    assert _sync._loop_factory() is asyncio.SelectorEventLoop


def test_other_platforms_keep_the_default_loop(monkeypatch):
    monkeypatch.setattr(_sync.sys, "platform", "linux")
    assert _sync._loop_factory() is None


async def _loop_type() -> type:
    return type(asyncio.get_running_loop())


def test_run_sync_loop_is_not_proactor():
    kind = run_sync(_loop_type())
    if sys.platform == "win32":
        assert issubclass(kind, asyncio.SelectorEventLoop)


def test_run_sync_from_a_running_loop_uses_the_same_factory():
    async def outer() -> type:
        return run_sync(_loop_type())

    kind = asyncio.run(outer())
    if sys.platform == "win32":
        assert issubclass(kind, asyncio.SelectorEventLoop)
