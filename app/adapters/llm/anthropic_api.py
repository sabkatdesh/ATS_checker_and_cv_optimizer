"""Anthropic Messages API transport (prompt-mode JSON; no native schema)."""

from typing import Any

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import RawCompletion, Stop, WireRequest
from app.adapters.llm._http import post_json
from app.adapters.llm._openai_wire import secret_value
from app.config.settings import AppSettings
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import LLMUnavailable

PROVIDER = "anthropic"
URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
_STOPS: dict[str, Stop] = {"end_turn": "end", "max_tokens": "max_tokens", "refusal": "refused"}


def messages_body(wire: WireRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": wire.model,
        "max_tokens": wire.max_tokens,
        "messages": [{"role": m.role, "content": m.content} for m in wire.messages],
    }
    if wire.system:
        body["system"] = wire.system
    if wire.temperature is not None:
        body["temperature"] = wire.temperature
    return body


def parse_messages(resp: dict[str, Any]) -> RawCompletion:
    try:
        blocks = resp.get("content") or []
        text = "".join(
            str(b.get("text", ""))
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )
        reason = str(resp.get("stop_reason") or "")
        usage = resp.get("usage") or {}
        parsed = Usage(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
            cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        )
    except (TypeError, AttributeError, ValueError):
        raise LLMUnavailable("malformed response", provider=PROVIDER) from None
    return RawCompletion(
        text=text, stop=_STOPS.get(reason, "other"), raw_stop_reason=reason, usage=parsed
    )


class AnthropicTransport:
    name = PROVIDER
    supports_native_schema = False

    def __init__(
        self, api_key: SecretStr | None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api_key = api_key
        self._transport = transport

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        key = secret_value(self._api_key, provider=PROVIDER, model=wire.model)
        data = await post_json(
            URL,
            headers={"x-api-key": key, "anthropic-version": API_VERSION},
            body=messages_body(wire),
            timeout_s=wire.timeout_s,
            provider=PROVIDER,
            model=wire.model,
            transport=self._transport,
        )
        return parse_messages(data)


def build_anthropic_transport(settings: AppSettings) -> AnthropicTransport:
    """Cheap: no network or credential check; a missing key fails on the first send."""
    return AnthropicTransport(settings.llm.anthropic_api_key)
