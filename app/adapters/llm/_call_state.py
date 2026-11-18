"""Per-call state and helpers used by BaseProvider: the shared deadline, totals and the race."""

import asyncio
import dataclasses
from collections.abc import Awaitable
from dataclasses import dataclass

from app.adapters.llm._retry import Deadline
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import LLMCancelled, LLMError


async def first_of[R](work: Awaitable[R], cancel: CancelToken) -> R:
    """Run `work` until it finishes or `cancel` fires; never leaves a task behind."""
    send = asyncio.ensure_future(work)
    waiter = asyncio.ensure_future(cancel.wait())
    try:
        await asyncio.wait({send, waiter}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (send, waiter):
            if not task.done():
                task.cancel()
        await asyncio.gather(send, waiter, return_exceptions=True)
    if cancel.is_cancelled:
        err = LLMCancelled("cancelled")
        # A send that completed as the cancel arrived was still billed: keep its usage (A11).
        if send.done() and not send.cancelled() and send.exception() is None:
            usage = getattr(send.result(), "usage", None)
            if isinstance(usage, Usage):
                err.usage = usage
        raise err
    return send.result()


@dataclass
class CallState:
    """One complete() on one route: the first send and the repair share `deadline`."""

    deadline: Deadline
    attempts: int = 0
    usage: Usage = dataclasses.field(default_factory=Usage)


def enrich(err: LLMError, state: CallState, provider: str, model: str) -> None:
    """Add call totals once; an instance seen again (a shared error) is left as it is."""
    if getattr(err, "_enriched", False):
        return
    err._enriched = True  # type: ignore[attr-defined]
    err.usage = state.usage + (err.usage or Usage())
    err.attempts = state.attempts
    if err.provider is None:
        err.provider = provider
    if err.model is None:
        err.model = model
