"""Gemini generateContent transport (prompt-mode JSON; no native schema)."""

from typing import Any

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import RawCompletion, Stop, WireRequest
from app.adapters.llm._http import post_json
from app.adapters.llm._openai_wire import secret_value
from app.config.settings import AppSettings
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import LLMUnavailable

PROVIDER = "gemini"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_REFUSED = {"SAFETY", "RECITATION", "PROHIBITED_CONTENT"}
_STOPS: dict[str, Stop] = {"STOP": "end", "MAX_TOKENS": "max_tokens"}


def generate_body(wire: WireRequest) -> dict[str, Any]:
    config: dict[str, Any] = {"maxOutputTokens": wire.max_tokens}
    if wire.temperature is not None:
        config["temperature"] = wire.temperature
    body: dict[str, Any] = {
        "contents": [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in wire.messages
        ],
        "generationConfig": config,
    }
    if wire.system:
        body["systemInstruction"] = {"parts": [{"text": wire.system}]}
    return body


def parse_generate(resp: dict[str, Any]) -> RawCompletion:
    try:
        feedback = resp.get("promptFeedback") or {}
        candidates = resp.get("candidates") or []
        candidate = candidates[0] if candidates else {}
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
        reason = str(candidate.get("finishReason") or "")
        meta = resp.get("usageMetadata") or {}
        usage = Usage(
            input_tokens=int(meta.get("promptTokenCount") or 0),
            output_tokens=int(meta.get("candidatesTokenCount") or 0),
            cache_read_tokens=int(meta.get("cachedContentTokenCount") or 0),
        )
    except (TypeError, AttributeError, ValueError):
        raise LLMUnavailable("malformed response", provider=PROVIDER) from None
    if feedback.get("blockReason"):
        return RawCompletion(
            text=text, stop="refused", raw_stop_reason=str(feedback["blockReason"]), usage=usage
        )
    stop: Stop = "refused" if reason in _REFUSED else _STOPS.get(reason, "other")
    return RawCompletion(text=text, stop=stop, raw_stop_reason=reason, usage=usage)


class GeminiTransport:
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
            f"{BASE_URL}/{wire.model}:generateContent",
            headers={"x-goog-api-key": key},
            body=generate_body(wire),
            timeout_s=wire.timeout_s,
            provider=PROVIDER,
            model=wire.model,
            transport=self._transport,
        )
        return parse_generate(data)


def build_gemini_transport(settings: AppSettings) -> GeminiTransport:
    """Cheap: no network or credential check; a missing key fails on the first send."""
    return GeminiTransport(settings.llm.gemini_api_key)
