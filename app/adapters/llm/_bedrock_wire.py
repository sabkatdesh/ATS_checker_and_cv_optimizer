"""Bedrock Converse wire format: request kwargs, response and stream parsing, error mapping.

Error `detail` is the AWS error code (or exception class name) only. AWS error messages can
echo request content, so they are never copied into an LLMError.
"""

import json
import re
from collections.abc import Iterable
from typing import Any

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    CredentialRetrievalError,
    HTTPClientError,
    NoCredentialsError,
    NoRegionError,
    PartialCredentialsError,
    ReadTimeoutError,
    TokenRetrievalError,
)
from botocore.exceptions import ConnectionError as BotoConnectionError
from urllib3.exceptions import HTTPError as Urllib3HTTPError
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeout

from app.adapters.llm._base import RawCompletion, Stop, WireRequest
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import (
    LLMAuthError,
    LLMBadRequest,
    LLMCancelled,
    LLMError,
    LLMThrottled,
    LLMTimeout,
    LLMUnavailable,
)

PROVIDER = "bedrock"
CACHE_MIN_TOKENS = 2048

_STOPS: dict[str, Stop] = {
    "end_turn": "end",
    "stop_sequence": "end",
    "max_tokens": "max_tokens",
    "content_filtered": "refused",
    "guardrail_intervened": "refused",
}

_CODES: dict[str, type[LLMError]] = {
    "ThrottlingException": LLMThrottled,
    "ServiceQuotaExceededException": LLMThrottled,
    "ServiceUnavailableException": LLMUnavailable,
    "InternalServerException": LLMUnavailable,
    "ModelNotReadyException": LLMUnavailable,
    "ModelErrorException": LLMUnavailable,
    "ModelStreamErrorException": LLMUnavailable,
    "ModelTimeoutException": LLMTimeout,
    "ValidationException": LLMBadRequest,
    "ResourceNotFoundException": LLMBadRequest,
    "AccessDeniedException": LLMAuthError,
    "UnrecognizedClientException": LLMAuthError,
    "ExpiredTokenException": LLMAuthError,
}

# Checked in order: timeouts before the connection errors they subclass.
_EXCEPTIONS: tuple[tuple[type[Exception], type[LLMError]], ...] = (
    (ReadTimeoutError, LLMTimeout),
    (ConnectTimeoutError, LLMTimeout),
    (Urllib3ReadTimeout, LLMTimeout),  # raised raw while reading an event stream
    (NoCredentialsError, LLMAuthError),
    (PartialCredentialsError, LLMAuthError),
    (CredentialRetrievalError, LLMAuthError),
    (TokenRetrievalError, LLMAuthError),
    (NoRegionError, LLMBadRequest),
    (BotoConnectionError, LLMUnavailable),  # incl. endpoint, proxy and SSL errors
    (HTTPClientError, LLMUnavailable),  # incl. connection closed, response streaming
    (Urllib3HTTPError, LLMUnavailable),
)

# What the transport maps; anything else is a bug and is left to the base provider.
TRANSPORT_ERRORS: tuple[type[Exception], ...] = (BotoCoreError, ClientError, Urllib3HTTPError)

_SAFE_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9.]{0,63}$")


BLANK = "(empty)"


def estimate_tokens(text: str) -> int:
    """Rough token count (4 characters per token), used only to decide on caching."""
    return len(text) // 4


def build_converse_kwargs(wire: WireRequest) -> dict[str, Any]:
    """Bedrock rejects blank text blocks, so a blank message becomes BLANK and a blank system
    prompt is left out."""
    inference: dict[str, Any] = {"maxTokens": wire.max_tokens}
    if wire.temperature is not None:
        inference["temperature"] = wire.temperature
    kwargs: dict[str, Any] = {
        "modelId": wire.model,
        "messages": [
            {"role": m.role, "content": [{"text": m.content if m.content.strip() else BLANK}]}
            for m in wire.messages
        ],
        "inferenceConfig": inference,
    }
    if wire.system.strip():
        system: list[dict[str, Any]] = [{"text": wire.system}]
        if wire.cache_prefix and estimate_tokens(wire.system) >= CACHE_MIN_TOKENS:
            system.append({"cachePoint": {"type": "default"}})
        kwargs["system"] = system
    if wire.json_schema is not None:
        name = wire.schema_name or "Output"
        kwargs["outputConfig"] = {
            "textFormat": {
                "type": "json_schema",
                "structure": {
                    "jsonSchema": {
                        "schema": json.dumps(wire.json_schema),
                        "name": name,
                        "description": f"{name} as JSON",
                    }
                },
            }
        }
    return kwargs


def _usage(raw: dict[str, Any] | None) -> Usage:
    raw = raw or {}
    return Usage(
        input_tokens=int(raw.get("inputTokens") or 0),
        output_tokens=int(raw.get("outputTokens") or 0),
        cache_read_tokens=int(raw.get("cacheReadInputTokens") or 0),
        cache_write_tokens=int(raw.get("cacheWriteInputTokens") or 0),
    )


def _completion(text: str, stop_reason: str, usage: Usage) -> RawCompletion:
    return RawCompletion(
        text=text,
        stop=_STOPS.get(stop_reason, "other"),
        raw_stop_reason=stop_reason,
        usage=usage,
    )


def parse_converse(resp: dict[str, Any]) -> RawCompletion:
    content = ((resp.get("output") or {}).get("message") or {}).get("content") or []
    text = "".join(block["text"] for block in content if isinstance(block.get("text"), str))
    return _completion(text, str(resp.get("stopReason") or ""), _usage(resp.get("usage")))


def accumulate_stream(events: Iterable[dict[str, Any]], cancel: CancelToken) -> RawCompletion:
    parts: list[str] = []
    stop_reason = ""
    usage = Usage()
    for event in events:
        if cancel.is_cancelled:
            raise LLMCancelled("cancelled", provider=PROVIDER)
        if "contentBlockDelta" in event:
            text = (event["contentBlockDelta"].get("delta") or {}).get("text")
            if isinstance(text, str):
                parts.append(text)
        elif "messageStop" in event:
            stop_reason = str(event["messageStop"].get("stopReason") or "")
        elif "metadata" in event:
            usage = _usage(event["metadata"].get("usage"))
    if cancel.is_cancelled:
        raise LLMCancelled("cancelled", provider=PROVIDER)
    return _completion("".join(parts), stop_reason, usage)


def _safe(code: str) -> str:
    return code if _SAFE_CODE.fullmatch(code) else "unrecognised error code"


def _by_status(status: int) -> type[LLMError]:
    if status == 429:
        return LLMThrottled
    if status in (401, 403):
        return LLMAuthError
    if 400 <= status < 500:
        return LLMBadRequest
    return LLMUnavailable  # 5xx, or no status at all (event-stream errors)


def map_error(exc: Exception, *, model: str) -> LLMError:
    """A fresh LLMError for a boto3/botocore failure; detail is the error code only."""
    if isinstance(exc, LLMError):
        return type(exc)(exc.detail, provider=PROVIDER, model=model)
    if isinstance(exc, ClientError):
        error = exc.response.get("Error") or {}
        code = str(error.get("Code") or "")
        code = code[:1].upper() + code[1:]  # stream errors use the member name: throttlingException
        meta = exc.response.get("ResponseMetadata") or {}
        status = int(meta.get("HTTPStatusCode") or 0)
        cls = _CODES.get(code) or _by_status(status)
        return cls(_safe(code), provider=PROVIDER, model=model)
    for exc_type, cls in _EXCEPTIONS:
        if isinstance(exc, exc_type):
            return cls(type(exc).__name__, provider=PROVIDER, model=model)
    return LLMUnavailable("unexpected transport error", provider=PROVIDER, model=model)
