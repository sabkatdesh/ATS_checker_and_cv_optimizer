"""Azure OpenAI contract harness (httpx.MockTransport, no network)."""

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import Transport
from app.adapters.llm.azure_openai import AzureOpenAITransport
from tests.contract.llm.harnesses._openai_mock import ChatMockHarness


class AzureOpenAIHarness(ChatMockHarness):
    name = "azure_openai"

    def build_transport(self, mock: httpx.AsyncBaseTransport) -> Transport:
        return AzureOpenAITransport(
            "https://res.openai.azure.test",
            SecretStr("az-test"),
            "dep1",
            "2025-01-01-preview",
            False,
            transport=mock,
        )
