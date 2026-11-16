"""A real bedrock-runtime client whose ConverseStream answers come from encoded event frames.

The request goes through botocore's parameter validation and signing (dummy static keys), then
a before-send hook returns an HTTP 200 whose body is AWS event-stream binary frames, so the
response is parsed by botocore's real EventStream (exception frames raise EventStreamError).
"""

import binascii
import json
import struct
from collections.abc import Iterator
from typing import Any

import boto3
from botocore.awsrequest import AWSResponse
from botocore.config import Config

_DUMMY = {"aws_access_key_id": "AKIDUMMYDUMMYDUMMY00", "aws_secret_access_key": "dummy-secret"}


def _frame(headers: dict[str, str], payload: bytes) -> bytes:
    head = b""
    for key, value in headers.items():
        kb, vb = key.encode(), value.encode()
        head += bytes([len(kb)]) + kb + b"\x07" + struct.pack(">H", len(vb)) + vb
    prelude = struct.pack(">II", 12 + len(head) + len(payload) + 4, len(head))
    prelude += struct.pack(">I", binascii.crc32(prelude) & 0xFFFFFFFF)
    message = prelude + head + payload
    return message + struct.pack(">I", binascii.crc32(message) & 0xFFFFFFFF)


def event(kind: str, body: dict[str, Any]) -> bytes:
    headers = {":event-type": kind, ":content-type": "application/json", ":message-type": "event"}
    return _frame(headers, json.dumps(body).encode())


def exception(kind: str, message: str) -> bytes:
    headers = {
        ":exception-type": kind,
        ":content-type": "application/json",
        ":message-type": "exception",
    }
    return _frame(headers, json.dumps({"message": message}).encode())


def text_events(text: str, stop: str = "end_turn") -> list[bytes]:
    return [
        event("messageStart", {"role": "assistant"}),
        event("contentBlockDelta", {"delta": {"text": text}, "contentBlockIndex": 0}),
        event("messageStop", {"stopReason": stop}),
        event("metadata", {"usage": {"inputTokens": 8, "outputTokens": 2, "totalTokens": 10}}),
    ]


class _Raw:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def stream(self, *_a: Any, **_k: Any) -> Iterator[bytes]:
        yield from self._chunks

    def close(self) -> None:
        return None


def stream_client(chunks: list[bytes]) -> Any:
    session = boto3.session.Session(region_name="us-east-1", **_DUMMY)
    client = session.client("bedrock-runtime", config=Config(retries={"total_max_attempts": 1}))
    sent: list[Any] = []

    def answer(request: Any, **_kw: Any) -> AWSResponse:
        sent.append(request)
        headers = {"content-type": "application/vnd.amazon.eventstream"}
        return AWSResponse(request.url, 200, headers, _Raw(chunks))  # type: ignore[arg-type]

    client.meta.events.register("before-send.bedrock-runtime.ConverseStream", answer)
    client.sent_requests = sent
    return client
