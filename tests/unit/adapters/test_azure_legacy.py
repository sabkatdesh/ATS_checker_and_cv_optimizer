import os

import pytest
from pydantic import SecretStr

from app.adapters.llm.azure_legacy import AzureLLMClient, build_azure_client
from app.config.settings import AppSettings

MISSING = (
    "Azure credentials missing. Set AZURE_OPENAI_ENDPOINT, "
    "AZURE_OPENAI_KEY, and AZURE_OPENAI_DEPLOYMENT in your .env file. "
    "See .env.example for the full list."
)


def _client(endpoint: str, foundry: bool = False) -> AzureLLMClient:
    return AzureLLMClient(
        endpoint=endpoint,
        api_key=SecretStr("k"),
        deployment="m",
        api_version="2025-01-01-preview",
        foundry=foundry,
    )


def test_build_without_credentials_raises_same_message(monkeypatch):
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(EnvironmentError) as exc:
        build_azure_client(AppSettings(_env_file=None))
    assert str(exc.value) == MISSING


def test_foundry_detected_from_endpoint():
    assert type(_client("https://x.services.ai.azure.com").llm).__name__ == "ChatOpenAI"


def test_classic_endpoint_uses_azure_chat():
    assert type(_client("https://x.openai.azure.com").llm).__name__ == "AzureChatOpenAI"


def test_foundry_flag_forces_foundry_mode():
    assert type(_client("https://custom.example.com", foundry=True).llm).__name__ == "ChatOpenAI"


def test_build_passes_settings_through():
    client = build_azure_client(
        AppSettings(
            _env_file=None,
            azure_openai_endpoint="https://custom.example.com",
            azure_openai_key="k",
            azure_openai_deployment="m",
            azure_foundry=True,
        )
    )
    assert type(client.llm).__name__ == "ChatOpenAI"


def test_no_env_reads(monkeypatch):
    monkeypatch.setitem(os.environ, "AZURE_OPENAI_ENDPOINT", "https://e.openai.azure.com")
    monkeypatch.setitem(os.environ, "AZURE_OPENAI_KEY", "k")
    monkeypatch.setitem(os.environ, "AZURE_OPENAI_DEPLOYMENT", "d")
    monkeypatch.setitem(os.environ, "AZURE_FOUNDRY", "true")
    with pytest.raises(EnvironmentError):
        AzureLLMClient(
            endpoint="", api_key=SecretStr(""), deployment="", api_version="v", foundry=False
        )
    # Explicit non-foundry endpoint stays classic even though AZURE_FOUNDRY=true in os.environ.
    assert type(_client("https://x.openai.azure.com").llm).__name__ == "AzureChatOpenAI"
