"""OpenAI chat-completions wire format shared by the OpenAI and Azure transports."""

from typing import Any

from pydantic import SecretStr

from app.adapters.llm._base import RawCompletion, Stop, WireRequest
from app.ports.llm import Usage
from app.ports.llm_errors import LLMAuthError, LLMUnavailable

_STOPS: dict[str, Stop] = {"stop": "end", "length": "max_tokens", "content_filter": "refused"}


def chat_body(wire: WireRequest, *, include_model: bool) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if wire.system:
        messages.append({"role": "system", "content": wire.system})
    messages.extend({"role": m.role, "content": m.content} for m in wire.messages)
    body: dict[str, Any] = {"messages": messages, "max_completion_tokens": wire.max_tokens}
    if include_model:
        body["model"] = wire.model
    if wire.temperature is not None:
        body["temperature"] = wire.temperature
    return body


def parse_chat(resp: dict[str, Any], *, provider: str = "openai") -> RawCompletion:
    try:
        choice = resp["choices"][0]
        message = choice.get("message") or {}
        reason = str(choice.get("finish_reason") or "")
        text = message.get("content") or ""
        if not isinstance(text, str):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        usage = resp.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        parsed = Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cache_read_tokens=int(details.get("cached_tokens") or 0),
        )
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise LLMUnavailable("malformed response", provider=provider) from None
    stop: Stop = _STOPS.get(reason, "other")
    if message.get("refusal"):
        stop = "refused"
    return RawCompletion(text=text, stop=stop, raw_stop_reason=reason, usage=parsed)


def secret_value(key: SecretStr | None, *, provider: str, model: str) -> str:
    value = key.get_secret_value() if key is not None else ""
    if not value:
        raise LLMAuthError("missing api key", provider=provider, model=model)
    return value
