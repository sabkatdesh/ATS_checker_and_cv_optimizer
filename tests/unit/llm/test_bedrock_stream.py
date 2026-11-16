"""Bedrock streaming through a real botocore client and EventStream, plus attempt stop."""

import asyncio
import threading
import time
from typing import Any

import pytest

from app.adapters.llm import bedrock_converse as bc
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import LLMBadRequest, LLMThrottled, LLMTimeout, LLMUnavailable
from tests.unit.llm.bedrock_stream_support import exception, stream_client, text_events
from tests.unit.llm.test_bedrock_wire import SECRET, wire


def _send(client: Any, **over: Any):
    t = bc.BedrockConverseTransport(region="us-east-1", read_timeout_s=10, client=client)
    return asyncio.run(t.send(wire(stream=True, **over), CancelToken()))


def test_real_converse_stream_passes_validation_and_accumulates():
    client = stream_client(text_events("streamed text", stop="max_tokens"))
    raw = _send(client, temperature=0.3)
    assert raw.text == "streamed text" and raw.stop == "max_tokens"
    assert raw.usage == Usage(input_tokens=8, output_tokens=2)
    assert len(client.sent_requests) == 1
    assert "/converse-stream" in client.sent_requests[0].url


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("throttlingException", LLMThrottled),
        ("validationException", LLMBadRequest),
        ("serviceUnavailableException", LLMUnavailable),
        ("internalServerException", LLMUnavailable),
        ("modelStreamErrorException", LLMUnavailable),
    ],
)
def test_mid_stream_event_stream_error_is_mapped(code, kind):
    chunks = text_events("partial")[:2] + [exception(code, SECRET)]
    with pytest.raises(kind) as exc:
        _send(stream_client(chunks))
    assert type(exc.value) is kind
    assert exc.value.detail == code[0].upper() + code[1:]
    assert SECRET not in str(exc.value) and SECRET not in repr(exc.value)


class SlowStreamClient:
    """converse_stream yields one event every 50 ms for ~3 s and counts what is consumed."""

    def __init__(self) -> None:
        self.consumed = 0
        self.closed = threading.Event()

    def converse_stream(self, **_kw: Any) -> dict:
        def events():
            try:
                for _ in range(60):
                    time.sleep(0.05)
                    self.consumed += 1
                    yield {"contentBlockDelta": {"delta": {"text": "x"}, "contentBlockIndex": 0}}
            finally:
                self.closed.set()

        return {"stream": events()}


def test_stream_thread_stops_after_attempt_times_out():
    client = SlowStreamClient()
    t = bc.BedrockConverseTransport(region="r", read_timeout_s=10, client=client)

    async def attempt() -> None:
        await asyncio.wait_for(t.send(wire(stream=True), CancelToken()), 0.2)

    with pytest.raises(TimeoutError):
        asyncio.run(attempt())
    assert client.closed.wait(0.5), "stream still being consumed after the attempt timed out"
    seen = client.consumed
    time.sleep(0.3)
    assert client.consumed == seen


def test_programming_errors_are_not_mapped_to_llm_errors():
    class Broken:
        def converse(self, **_kw: Any) -> dict:
            raise TypeError("bug")

    t = bc.BedrockConverseTransport(region="r", read_timeout_s=10, client=Broken())
    with pytest.raises(TypeError):
        asyncio.run(t.send(wire(), CancelToken()))


def test_read_timeout_mid_stream_maps_to_timeout():
    from urllib3.exceptions import ReadTimeoutError

    class TimesOut:
        def converse_stream(self, **_kw: Any) -> dict:
            def events():
                yield {"contentBlockDelta": {"delta": {"text": "x"}, "contentBlockIndex": 0}}
                raise ReadTimeoutError(None, "https://bedrock", SECRET)  # type: ignore[arg-type]

            return {"stream": events()}

    t = bc.BedrockConverseTransport(region="r", read_timeout_s=10, client=TimesOut())
    with pytest.raises(LLMTimeout) as exc:
        asyncio.run(t.send(wire(stream=True), CancelToken()))
    assert SECRET not in str(exc.value)
