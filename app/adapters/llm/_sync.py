"""Run a gateway coroutine from sync code (LangGraph node threads, FastAPI threadpool routes).

Each call gets its own event loop, so nothing the router or providers keep between calls may be
bound to a loop: breakers and the provider registry use threading locks, CancelToken wraps a
threading.Event, httpx clients are built per call and boto3 calls run on their own threads.
"""

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any


def run_sync[R](coro: Coroutine[Any, Any, R]) -> R:
    """No running loop in this thread: asyncio.run. Otherwise run on a fresh thread and wait."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["ok"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the calling thread
            box["err"] = exc

    worker = threading.Thread(target=target, name="llm-run-sync", daemon=True)
    worker.start()
    worker.join()
    if "err" in box:
        raise box["err"]
    return box["ok"]  # type: ignore[no-any-return]
