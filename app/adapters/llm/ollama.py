"""Ollama /api/chat transport for a local server (prompt-mode JSON; no key)."""

from typing import Any

import httpx

from app.adapters.llm._base import RawCompletion, Stop, WireRequest
from app.adapters.llm._http import post_json
from app.config.settings import AppSettings
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import LLMUnavailable

PROVIDER = "ollama"
_STOPS: dict[str, Stop] = {"stop": "end", "length": "max_tokens", "content_filter": "refused"}


def chat_body(wire: WireRequest) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if wire.system:
        messages.append({"role": "system", "content": wire.system})
    messages.extend({"role": m.role, "content": m.content} for m in wire.messages)
    options: dict[str, Any] = {"num_predict": wire.max_tokens}
    if wire.temperature is not None:
        options["temperature"] = wire.temperature
    return {"model": wire.model, "messages": messages, "stream": False, "options": options}


def parse_chat(resp: dict[str, Any]) -> RawCompletion:
    try:
        text = (resp.get("message") or {}).get("content") or ""
        if not isinstance(text, str):
            raise TypeError("content")
        reason = str(resp.get("done_reason") or "")
        usage = Usage(
            input_tokens=int(resp.get("prompt_eval_count") or 0),
            output_tokens=int(resp.get("eval_count") or 0),
        )
    except (TypeError, AttributeError, ValueError):
        raise LLMUnavailable("malformed response", provider=PROVIDER) from None
    return RawCompletion(
        text=text, stop=_STOPS.get(reason, "other"), raw_stop_reason=reason, usage=usage
    )


class OllamaTransport:
    name = PROVIDER
    supports_native_schema = False

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        data = await post_json(
            f"{self._base_url}/api/chat",
            headers={},
            body=chat_body(wire),
            timeout_s=wire.timeout_s,
            provider=PROVIDER,
            model=wire.model,
            transport=self._transport,
        )
        return parse_chat(data)


def build_ollama_transport(settings: AppSettings) -> OllamaTransport:
    """Cheap: no network check; an unreachable server fails on the first send."""
    return OllamaTransport(settings.llm.ollama_base_url)
