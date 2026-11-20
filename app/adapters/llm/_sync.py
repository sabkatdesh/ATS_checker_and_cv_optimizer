"""Run a gateway coroutine from sync code (LangGraph node threads, FastAPI threadpool routes).

Each call gets its own event loop, so nothing the router or providers keep between calls may be
bound to a loop: breakers and the provider registry use threading locks, CancelToken wraps a
threading.Event, httpx clients are built per call and boto3 calls run on their own threads.
"""

import asyncio
import sys
import threading
from collections.abc import Callable, Coroutine
from typing import Any


def _loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """psycopg's async driver cannot run on Windows' default Proactor loop; use a selector loop."""
    return asyncio.SelectorEventLoop if sys.platform == "win32" else None


def run_sync[R](coro: Coroutine[Any, Any, R]) -> R:
    """Run `coro` to completion from sync code and return its result.

    Never call this from async code: with a running loop in this thread it runs the coroutine on a
    fresh thread and blocks the calling loop until it finishes. Await the gateway there instead.
    No running loop in this thread: asyncio.run (a selector loop on Windows).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro, loop_factory=_loop_factory())

    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["ok"] = asyncio.run(coro, loop_factory=_loop_factory())
        except BaseException as exc:  # noqa: BLE001 - re-raised in the calling thread
            box["err"] = exc

    worker = threading.Thread(target=target, name="llm-run-sync", daemon=True)
    worker.start()
    worker.join()
    if "err" in box:
        raise box["err"]
    return box["ok"]  # type: ignore[no-any-return]
