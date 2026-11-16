"""OpenAI contract harness (httpx.MockTransport, no network)."""

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import Transport
from app.adapters.llm.openai_api import OpenAITransport
from tests.contract.llm.harnesses._openai_mock import ChatMockHarness


class OpenAIHarness(ChatMockHarness):
    name = "openai"

    def build_transport(self, mock: httpx.AsyncBaseTransport) -> Transport:
        return OpenAITransport(SecretStr("sk-test"), "https://api.openai.test/v1", transport=mock)
