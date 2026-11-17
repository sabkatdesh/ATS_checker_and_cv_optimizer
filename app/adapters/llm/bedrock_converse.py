"""Bedrock Converse transport, the default LLM provider.

The boto3 client is built on first use (so a missing credential shows up as LLMAuthError on the
first call, not at boot) and shared across threads. Each blocking boto3 call runs on its own
daemon thread: on cancel the awaiting task is abandoned at once, the thread ends when botocore's
read timeout fires (so an abandoned thread lives at most connect + read_timeout_s), and neither
the event loop nor interpreter shutdown waits for it. The shared client pools up to
MAX_POOL_CONNECTIONS connections, which also bounds how many such threads can hold one. An
abandoned attempt (cancel or deadline) also sets a per-call stop flag, so a stream stops being
read at its next event.
"""

import asyncio
import threading
from collections.abc import Callable
from typing import Any

import boto3
from botocore.config import Config

from app.adapters.llm._base import RawCompletion, WireRequest
from app.adapters.llm._bedrock_wire import (
    PROVIDER,
    TRANSPORT_ERRORS,
    accumulate_stream,
    build_converse_kwargs,
    map_error,
    parse_converse,
)
from app.config.settings import AppSettings
from app.ports.llm import CancelToken
from app.ports.llm_errors import LLMError

CONNECT_TIMEOUT_S = 5
MAX_POOL_CONNECTIONS = 50  # shared client: one pooled connection per concurrent call


class _AttemptCancel(CancelToken):
    """Set when this attempt is abandoned; also reports the caller's token."""

    def __init__(self, caller: CancelToken) -> None:
        super().__init__()
        self._caller = caller

    @property
    def is_cancelled(self) -> bool:
        return super().is_cancelled or self._caller.is_cancelled


async def in_daemon_thread[R](fn: Callable[[], R]) -> R:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[R] = loop.create_future()

    def deliver(ok: R | None, err: BaseException | None) -> None:
        if future.done():  # the caller gave up (cancel or deadline)
            return
        if err is not None:
            future.set_exception(err)
        else:
            future.set_result(ok)  # type: ignore[arg-type]

    def run() -> None:
        ok: R | None = None
        err: BaseException | None = None
        try:
            ok = fn()
        except BaseException as exc:  # noqa: BLE001 - handed to the awaiting task
            err = exc
        try:
            loop.call_soon_threadsafe(deliver, ok, err)
        except RuntimeError:  # loop already closed: the result is no longer wanted
            pass

    threading.Thread(target=run, name="bedrock-call", daemon=True).start()
    return await future


class BedrockConverseTransport:
    name = PROVIDER
    supports_native_schema = True

    def __init__(self, *, region: str, read_timeout_s: float, client: Any | None = None) -> None:
        self._region = region
        self._read_timeout_s = read_timeout_s
        self._client = client
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    config = Config(
                        connect_timeout=CONNECT_TIMEOUT_S,
                        read_timeout=self._read_timeout_s,
                        max_pool_connections=MAX_POOL_CONNECTIONS,
                        retries={"mode": "adaptive", "total_max_attempts": 1},
                    )
                    session = boto3.session.Session()
                    self._client = session.client(
                        "bedrock-runtime", region_name=self._region, config=config
                    )
        return self._client

    def _call(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        kwargs = build_converse_kwargs(wire)
        try:
            client = self._get_client()
            if not wire.stream:
                return parse_converse(client.converse(**kwargs))
            stream = client.converse_stream(**kwargs)["stream"]
            try:
                return accumulate_stream(stream, cancel)
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
        except LLMError as err:
            if err.model is None:
                err.model = wire.model
            raise
        except TRANSPORT_ERRORS as exc:  # AWS/HTTP failure: keep the code, drop the message
            raise map_error(exc, model=wire.model) from None

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        attempt = _AttemptCancel(cancel)
        try:
            return await in_daemon_thread(lambda: self._call(wire, attempt))
        except asyncio.CancelledError:  # deadline or caller cancel: stop reading the stream
            attempt.cancel()
            raise


def build_bedrock_transport(settings: AppSettings) -> BedrockConverseTransport:
    """Cheap: no session, client or credential lookup happens here."""
    return BedrockConverseTransport(
        region=settings.llm.aws_region, read_timeout_s=settings.llm.bedrock_read_timeout_s
    )


if __name__ == "__main__":
    from app.adapters.llm import _smoke

    raise SystemExit(_smoke.main())
