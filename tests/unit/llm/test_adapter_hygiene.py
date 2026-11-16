import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.llm._base import WireRequest
from app.adapters.llm._http import post_json
from app.adapters.llm._openai_wire import parse_chat
from app.adapters.llm.azure_openai import AzureOpenAITransport
from app.adapters.llm.gemini import GeminiTransport, parse_generate
from app.ports.llm import CancelToken, Message
from app.ports.llm_errors import LLMBadRequest, LLMThrottled, LLMUnavailable

seen: list[httpx.Request] = []
_OK = {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}


def _wire(model: str = "m1") -> WireRequest:
    return WireRequest(
        system="",
        messages=(Message(role="user", content="hi"),),
        model=model,
        max_tokens=5,
        temperature=None,
        json_schema=None,
        schema_name=None,
        cache_prefix=False,
        stream=False,
        timeout_s=5,
    )


def _ok_mock(payload: dict) -> httpx.MockTransport:
    seen.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def _post(handler, url: str = "https://x.test/v1"):
    return post_json(
        url,
        headers={},
        body={},
        timeout_s=5,
        provider="p",
        model="m",
        transport=httpx.MockTransport(handler),
    )


def test_openai_cached_tokens_are_not_double_counted():
    raw = {
        "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "prompt_tokens_details": {"cached_tokens": 4},
        },
    }
    u = parse_chat(raw).usage
    assert (u.input_tokens, u.output_tokens, u.cache_read_tokens) == (3, 3, 4)
    raw["usage"]["prompt_tokens_details"]["cached_tokens"] = 99
    assert parse_chat(raw).usage.input_tokens == 0


def test_gemini_cached_and_thought_tokens():
    raw = {
        "candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": "STOP"}],
        "usageMetadata": {
            "promptTokenCount": 10,
            "cachedContentTokenCount": 4,
            "candidatesTokenCount": 2,
            "thoughtsTokenCount": 3,
        },
    }
    u = parse_generate(raw).usage
    assert (u.input_tokens, u.output_tokens, u.cache_read_tokens) == (6, 5, 4)


def test_gemini_missing_usage_is_zero():
    u = parse_generate({"candidates": []}).usage
    assert (u.input_tokens, u.output_tokens, u.cache_read_tokens) == (0, 0, 0)


@pytest.mark.parametrize("model", ["m?key=1", "a/../../x"])
def test_gemini_model_is_quoted_into_the_path(model):
    t = GeminiTransport(SecretStr("k"), transport=_ok_mock({"candidates": []}))
    asyncio.run(t.send(_wire(model), CancelToken()))
    url = seen[-1].url
    assert not url.query and url.raw_path.startswith(b"/v1beta/models/")
    assert url.raw_path.endswith(b":generateContent") and url.raw_path.count(b"/") == 3


def _azure(endpoint: str, deployment: str = "dep", version: str = "v1", foundry=False):
    return AzureOpenAITransport(
        endpoint, SecretStr("k"), deployment, version, foundry, transport=_ok_mock(_OK)
    )


def test_azure_deployment_and_version_are_quoted():
    asyncio.run(
        _azure("https://r.openai.azure.com", "a/b?x", "2025&k=1").send(_wire(), CancelToken())
    )
    url = seen[-1].url
    assert url.raw_path.split(b"?")[0] == b"/openai/deployments/a%2Fb%3Fx/chat/completions"
    assert dict(url.params) == {"api-version": "2025&k=1"}


def test_azure_foundry_detected_by_host_only():
    asyncio.run(_azure("https://evil.test/services.ai.azure.com").send(_wire(), CancelToken()))
    assert "/openai/deployments/" in str(seen[-1].url)
    asyncio.run(_azure("https://r.services.ai.azure.com").send(_wire(), CancelToken()))
    assert str(seen[-1].url) == "https://r.services.ai.azure.com/openai/v1/chat/completions"


def test_azure_foundry_endpoint_with_v1_suffix_not_doubled():
    asyncio.run(_azure("https://r.services.ai.azure.com/openai/v1/").send(_wire(), CancelToken()))
    assert str(seen[-1].url) == "https://r.services.ai.azure.com/openai/v1/chat/completions"
    assert json.loads(seen[-1].content)["model"] == "dep"


def test_invalid_url_is_bad_request():
    def handler(request):
        return httpx.Response(200, json={})

    with pytest.raises(LLMBadRequest, match="invalid url"):
        asyncio.run(_post(handler, url="http://x.test:abc/"))


@pytest.mark.parametrize(
    ("status", "kind"), [(408, LLMUnavailable), (425, LLMUnavailable), (409, LLMBadRequest)]
)
def test_status_mapping(status, kind):
    def handler(request):
        return httpx.Response(status)

    with pytest.raises(kind):
        asyncio.run(_post(handler))


def test_non_json_200_is_unavailable():
    def handler(request):
        return httpx.Response(200, text="<html>")

    with pytest.raises(LLMUnavailable):
        asyncio.run(_post(handler))


@pytest.mark.parametrize("value", ["-5", "1e999", "nan"])
def test_odd_retry_after_ignored(value):
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": value})

    with pytest.raises(LLMThrottled) as info:
        asyncio.run(_post(handler))
    assert info.value.retry_after_s is None
