import asyncio
import functools
import json

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.llm._base import WireRequest
from app.adapters.llm.anthropic_api import AnthropicTransport, build_anthropic_transport
from app.adapters.llm.gemini import GeminiTransport, build_gemini_transport
from app.adapters.llm.ollama import OllamaTransport, build_ollama_transport
from app.adapters.llm.registry import DEFAULT_FACTORIES
from app.config.settings import AppSettings
from app.ports.llm import CancelToken, Message
from app.ports.llm_errors import LLMAuthError, LLMUnavailable

seen: list[httpx.Request] = []


def _sync(fn):
    @functools.wraps(fn)
    def run(*a, **k):
        return asyncio.run(fn(*a, **k))

    return run


def _wire(temperature: float | None = None) -> WireRequest:
    return WireRequest(
        system="SYS",
        messages=(Message(role="user", content="hi"), Message(role="assistant", content="a")),
        model="m1",
        max_tokens=123,
        temperature=temperature,
        json_schema=None,
        schema_name=None,
        cache_prefix=False,
        stream=False,
        timeout_s=5,
    )


def _mock(payload: dict) -> httpx.MockTransport:
    seen.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def _sent() -> dict:
    return json.loads(seen[-1].content)


@_sync
async def test_anthropic_body_and_parse():
    payload = {
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "max_tokens",
        "usage": {
            "input_tokens": 7,
            "output_tokens": 3,
            "cache_read_input_tokens": 2,
            "cache_creation_input_tokens": 1,
        },
    }
    t = AnthropicTransport(SecretStr("k1"), transport=_mock(payload))
    out = await t.send(_wire(0.3), CancelToken())
    req = seen[-1]
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "k1" and req.headers["anthropic-version"] == "2023-06-01"
    body = _sent()
    assert body["max_tokens"] == 123 and body["system"] == "SYS" and body["temperature"] == 0.3
    assert body["model"] == "m1"
    assert out.stop == "max_tokens" and out.text == "ok"
    u = out.usage
    assert (u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens) == (
        7,
        3,
        2,
        1,
    )
    assert t.supports_native_schema is False


@_sync
async def test_anthropic_refusal_maps_to_refused():
    p = {"content": [], "stop_reason": "refusal", "usage": {}}
    out = await AnthropicTransport(SecretStr("k"), transport=_mock(p)).send(_wire(), CancelToken())
    assert out.stop == "refused"
    assert "temperature" not in _sent()


@_sync
async def test_gemini_key_in_header_not_url():
    payload = {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
    }
    t = GeminiTransport(SecretStr("gk-secret"), transport=_mock(payload))
    out = await t.send(_wire(0.1), CancelToken())
    req = seen[-1]
    assert req.headers["x-goog-api-key"] == "gk-secret"
    assert "gk-secret" not in str(req.url) and not req.url.query
    assert req.url.path == "/v1beta/models/m1:generateContent"
    body = _sent()
    assert body["systemInstruction"] == {"parts": [{"text": "SYS"}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    assert body["generationConfig"]["maxOutputTokens"] == 123
    assert body["generationConfig"]["temperature"] == 0.1
    assert out.stop == "end" and (out.usage.input_tokens, out.usage.output_tokens) == (4, 2)


@_sync
async def test_gemini_block_reason_is_refusal():
    p = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {}}
    out = await GeminiTransport(SecretStr("k"), transport=_mock(p)).send(_wire(), CancelToken())
    assert out.stop == "refused" and out.text == ""


@pytest.mark.parametrize(
    ("reason", "stop"),
    [("MAX_TOKENS", "max_tokens"), ("RECITATION", "refused"), ("OTHER", "other")],
)
@_sync
async def test_gemini_finish_reasons(reason, stop):
    p = {"candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": reason}]}
    out = await GeminiTransport(SecretStr("k"), transport=_mock(p)).send(_wire(), CancelToken())
    assert out.stop == stop


@_sync
async def test_ollama_num_predict_set():
    payload = {
        "message": {"role": "assistant", "content": "ok"},
        "done_reason": "length",
        "prompt_eval_count": 9,
        "eval_count": 4,
    }
    t = OllamaTransport("http://box:11434/", transport=_mock(payload))
    out = await t.send(_wire(0.5), CancelToken())
    assert str(seen[-1].url) == "http://box:11434/api/chat"
    body = _sent()
    assert body["stream"] is False and body["options"] == {"num_predict": 123, "temperature": 0.5}
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert out.stop == "max_tokens" and (out.usage.input_tokens, out.usage.output_tokens) == (9, 4)


@_sync
async def test_ollama_connection_refused_is_unavailable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    t = OllamaTransport("http://box:11434", transport=httpx.MockTransport(refuse))
    with pytest.raises(LLMUnavailable):
        await t.send(_wire(), CancelToken())


@pytest.mark.parametrize("cls", [AnthropicTransport, GeminiTransport])
@_sync
async def test_missing_key_fails_on_send_not_build(cls):
    t = cls(None, transport=_mock({}))
    with pytest.raises(LLMAuthError):
        await t.send(_wire(), CancelToken())
    assert not seen


def test_registry_builds_all_three_lazily():
    s = AppSettings(_env_file=None)
    assert isinstance(DEFAULT_FACTORIES["anthropic"](s), AnthropicTransport)
    assert isinstance(DEFAULT_FACTORIES["gemini"](s), GeminiTransport)
    assert isinstance(DEFAULT_FACTORIES["ollama"](s), OllamaTransport)
    assert build_anthropic_transport(s).name == "anthropic"
    assert build_gemini_transport(s).name == "gemini"
    assert build_ollama_transport(s).name == "ollama"
