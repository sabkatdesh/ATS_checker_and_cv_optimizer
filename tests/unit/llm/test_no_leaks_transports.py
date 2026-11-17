import asyncio
import os

import httpx
import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr

from app.adapters.llm._base import WireRequest
from app.adapters.llm.anthropic_api import AnthropicTransport
from app.adapters.llm.azure_openai import AzureOpenAITransport
from app.adapters.llm.bedrock_converse import BedrockConverseTransport, build_bedrock_transport
from app.adapters.llm.gemini import GeminiTransport
from app.adapters.llm.ollama import OllamaTransport
from app.adapters.llm.openai_api import OpenAITransport
from app.config.settings import AppSettings
from app.ports.llm import CancelToken, Message
from app.ports.llm_errors import LLMAuthError, LLMError
from tests.unit.llm.leak_support import SENTINEL, TEXT, assert_clean, loopback_only  # noqa: F401


def _wire(stream: bool = False) -> WireRequest:
    return WireRequest(
        system=f"system {SENTINEL}", messages=(Message(role="user", content=TEXT),),
        model="m", max_tokens=50, temperature=0, json_schema=None, schema_name=None,
        cache_prefix=False, stream=stream, timeout_s=5,
    )  # fmt: skip


def _echo(status: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        return httpx.Response(status, json={"error": {"message": f"bad input: {body}"}})

    return httpx.MockTransport(handler)


def _transports(status: int):
    key, mock = SecretStr("k"), _echo(status)
    return {
        "openai": OpenAITransport(key, "http://x/v1", transport=mock),
        "azure": AzureOpenAITransport("http://x", key, "dep", "2025-01-01", False, transport=mock),
        "azure_foundry": AzureOpenAITransport("http://x", key, "dep", "v", True, transport=mock),
        "anthropic": AnthropicTransport(key, transport=mock),
        "gemini": GeminiTransport(key, transport=mock),
        "ollama": OllamaTransport("http://x", transport=mock),
    }


def _send(transport) -> LLMError:
    with pytest.raises(LLMError) as caught:
        asyncio.run(transport.send(_wire(), CancelToken()))
    return caught.value


@pytest.mark.parametrize("status", [400, 401, 429, 500])
@pytest.mark.parametrize(
    "name", ["openai", "azure", "azure_foundry", "anthropic", "gemini", "ollama"]
)
def test_http_adapter_errors_never_echo_request_text(name, status):
    err = _send(_transports(status)[name])
    assert_clean(str(err), repr(err), err.detail)


def test_http_error_check_can_fail():
    # Guards the guard: if the body were echoed into the message the check must trip.
    with pytest.raises(AssertionError):
        assert_clean(f"HTTP 400: {TEXT}")


@pytest.mark.parametrize(
    "code", ["ValidationException", "ThrottlingException", "AccessDeniedException"]
)
def test_bedrock_client_error_never_echoes_request_text(code):
    class Client:
        def converse(self, **_kw):
            raise ClientError(
                {
                    "Error": {"Code": code, "Message": f"invalid: {TEXT}"},
                    "ResponseMetadata": {"HTTPStatusCode": 400},
                },
                "Converse",
            )

    transport = BedrockConverseTransport(region="us-east-1", read_timeout_s=5, client=Client())
    err = _send(transport)
    assert_clean(str(err), repr(err), err.detail)


def test_first_bedrock_call_without_credentials_raises_auth_error(
    tmp_path,
    monkeypatch,
    loopback_only,  # noqa: F811
):
    for name in list(os.environ):
        if name.startswith(("AWS_", "AZURE_", "LLM__")):
            monkeypatch.delenv(name)
    empty = tmp_path / "empty"
    empty.write_text("")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(empty))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(empty))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    transport = build_bedrock_transport(AppSettings(_env_file=None))  # building must not raise
    err = _send(transport)
    assert isinstance(err, LLMAuthError)
    assert_clean(str(err), repr(err))
