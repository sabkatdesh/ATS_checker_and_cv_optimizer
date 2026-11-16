import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.llm._base import WireRequest
from app.adapters.llm._http import post_json
from app.adapters.llm._openai_wire import chat_body, parse_chat
from app.adapters.llm.azure_openai import AzureOpenAITransport, build_azure_transport
from app.adapters.llm.openai_api import OpenAITransport, build_openai_transport
from app.adapters.llm.registry import DEFAULT_FACTORIES
from app.config.llm_settings import LlmSettings
from app.config.settings import AppSettings
from app.ports.llm import CancelToken, Message
from app.ports.llm_errors import LLMAuthError, LLMBadRequest, LLMThrottled

seen: list[httpx.Request] = []


def _wire(temperature: float | None = None) -> WireRequest:
    return WireRequest(
        system="SYS",
        messages=(Message(role="user", content="hi"),),
        model="m1",
        max_tokens=123,
        temperature=temperature,
        json_schema=None,
        schema_name=None,
        cache_prefix=False,
        stream=False,
        timeout_s=5,
    )


def _resp(finish: str = "stop", **message: object) -> dict:
    msg = {"role": "assistant", "content": "ok", **message}
    return {"choices": [{"message": msg, "finish_reason": finish}], "usage": {}}


def test_body_has_max_completion_tokens_and_system_first():
    body = chat_body(_wire(), include_model=True)
    assert body["max_completion_tokens"] == 123 and "max_tokens" not in body
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["model"] == "m1" and "temperature" not in body
    assert chat_body(_wire(0.2), include_model=False)["temperature"] == 0.2
    assert "model" not in chat_body(_wire(), include_model=False)


def test_parse_finish_reasons():
    assert parse_chat(_resp("stop")).stop == "end"
    assert parse_chat(_resp("length")).stop == "max_tokens"
    assert parse_chat(_resp("content_filter")).stop == "refused"
    assert parse_chat(_resp("stop", refusal="no")).stop == "refused"
    assert parse_chat(_resp("tool_calls")).stop == "other"
    raw = _resp()
    raw["usage"] = {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "prompt_tokens_details": {"cached_tokens": 4},
    }
    usage = parse_chat(raw).usage
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens) == (7, 3, 4)


def _mock() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_resp())

    return httpx.MockTransport(handler)


def _azure(endpoint: str, foundry: bool) -> AzureOpenAITransport:
    return AzureOpenAITransport(
        endpoint, SecretStr("k"), "dep", "2025-01-01-preview", foundry, transport=_mock()
    )


async def _capture(transport: AzureOpenAITransport) -> httpx.Request:
    await transport.send(_wire(), CancelToken())
    return seen[-1]


def test_azure_classic_and_foundry_urls():
    classic = asyncio.run(_capture(_azure("https://r.openai.azure.com/", False)))
    assert str(classic.url) == (
        "https://r.openai.azure.com/openai/deployments/dep/chat/completions"
        "?api-version=2025-01-01-preview"
    )
    assert classic.headers["api-key"] == "k" and "authorization" not in classic.headers
    assert "model" not in json.loads(classic.content)
    for ep, flag in (("https://r.services.ai.azure.com", False), ("https://x.test", True)):
        req = asyncio.run(_capture(_azure(ep, flag)))
        assert str(req.url) == f"{ep}/openai/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer k" and "api-key" not in req.headers
        assert json.loads(req.content)["model"] == "dep"


def _post(handler):
    return post_json(
        "https://x.test/v1",
        headers={},
        body={},
        timeout_s=5,
        provider="p",
        model="m",
        transport=httpx.MockTransport(handler),
    )


def test_retry_after_header_parsed():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "7"})

    with pytest.raises(LLMThrottled) as info:
        asyncio.run(_post(handler))
    assert info.value.retry_after_s == 7.0

    def date_handler(request):
        return httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})

    with pytest.raises(LLMThrottled) as info:
        asyncio.run(_post(date_handler))
    assert info.value.retry_after_s is None


def test_error_detail_excludes_body():
    def handler(request):
        return httpx.Response(400, text="SECRET-PROMPT-ECHO")

    with pytest.raises(LLMBadRequest) as info:
        asyncio.run(_post(handler))
    assert info.value.detail == "HTTP 400" and "SECRET" not in str(info.value)


def test_missing_key_raises_auth_on_send():
    assert {"openai", "azure_openai"} <= set(DEFAULT_FACTORIES)
    transports = [
        OpenAITransport(None, "https://x.test/v1", transport=_mock()),
        build_openai_transport(AppSettings(_env_file=None, llm=LlmSettings())),
        AzureOpenAITransport("https://r.openai.azure.com", None, "dep", "v", False),
        build_azure_transport(
            AppSettings(
                _env_file=None,
                azure_openai_endpoint="https://r.test",
                azure_openai_deployment="dep",
                azure_openai_key=None,
            )
        ),
    ]
    for transport in transports:
        with pytest.raises(LLMAuthError):
            asyncio.run(transport.send(_wire(), CancelToken()))
