"""
Single entry point for all LLM calls.

Supports two deployment types — set AZURE_FOUNDRY=true for Azure AI Foundry
(*.services.ai.azure.com), leave unset for classic Azure OpenAI (*.openai.azure.com).

Usage (drop-in for LangChain chains):
    from core.llm_client import get_llm
    llm = get_llm()
    chain = template | llm | StrOutputParser()

Usage (direct structured output):
    client = AzureLLMClient()
    result: MyModel = client.invoke_structured(prompt, MyModel)
"""
import logging
import os
from typing import Type, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: "AzureLLMClient | None" = None


class AzureLLMClient:
    """
    Wraps ChatOpenAI (Azure AI Foundry) or AzureChatOpenAI (classic Azure OpenAI).
    - Reads config from env if not passed
    - Temperature omitted by default (safe for reasoning models)
    - Token usage logging
    - Structured output helper with safe_parser fallback
    """

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
        max_retries: int = 3,
        timeout: int = 120,
        temperature: float | None = None,
    ) -> None:
        resolved_endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        resolved_key = api_key or os.environ.get("AZURE_OPENAI_KEY", "")
        resolved_deployment = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
        resolved_version = (
            api_version
            or os.environ.get("AZURE_OPENAI_API_VERSION")
            or "2025-01-01-preview"
        )

        if not all([resolved_endpoint, resolved_key, resolved_deployment]):
            raise EnvironmentError(
                "Azure credentials missing. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_KEY, and AZURE_OPENAI_DEPLOYMENT in your .env file. "
                "See .env.example for the full list."
            )

        # Azure AI Foundry (*.services.ai.azure.com) uses standard OpenAI client with base_url.
        # Classic Azure OpenAI (*.openai.azure.com) uses AzureChatOpenAI with azure_endpoint.
        is_foundry = (
            "services.ai.azure.com" in resolved_endpoint
            or os.environ.get("AZURE_FOUNDRY", "").lower() == "true"
        )

        extra: dict = {}
        if temperature is not None:
            extra["temperature"] = temperature

        if is_foundry:
            from langchain_openai import ChatOpenAI

            # Foundry base_url format: {endpoint}/openai/v1/
            base_url = resolved_endpoint.rstrip("/") + "/openai/v1/"
            self._chat = ChatOpenAI(
                base_url=base_url,
                api_key=resolved_key,
                model=resolved_deployment,
                max_retries=max_retries,
                timeout=timeout,
                **extra,
            )
            logger.info(f"[LLM] Azure AI Foundry mode | model={resolved_deployment}")
        else:
            from langchain_openai import AzureChatOpenAI

            self._chat = AzureChatOpenAI(
                azure_endpoint=resolved_endpoint,
                api_key=resolved_key,
                azure_deployment=resolved_deployment,
                api_version=resolved_version,
                max_retries=max_retries,
                timeout=timeout,
                **extra,
            )
            logger.info(f"[LLM] Azure OpenAI mode | deployment={resolved_deployment}")

        self._deployment = resolved_deployment

    @property
    def llm(self):
        """Return the underlying LangChain model for use in chains (template | llm | parser)."""
        return self._chat

    def invoke_structured(self, prompt: str, schema: Type[T]) -> T:
        """Call LLM with structured output. Falls back to string + safe_parser on failure."""
        from langchain_core.output_parsers import StrOutputParser
        from core.parsers.safe_parser import safe_llm_parse

        try:
            result = self._chat.with_structured_output(schema).invoke(prompt)
            return result
        except Exception as e:
            logger.warning(f"[LLM] Structured output failed ({e}), falling back to string parse")
            raw = (self._chat | StrOutputParser()).invoke(prompt)
            return safe_llm_parse(raw, schema, schema())

    def log_usage(self, call_type: str, response_metadata: dict) -> None:
        usage = response_metadata.get("token_usage") or response_metadata.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        logger.info(
            f"[LLM] {call_type} | model={self._deployment} "
            f"in={input_tokens} out={output_tokens} total={input_tokens + output_tokens}"
        )


def get_llm():
    """
    Return the shared LLM instance for use in LangChain chains.
    Creates the singleton on first call.

    Example:
        llm = get_llm()
        chain = template | llm | StrOutputParser()
    """
    global _client
    if _client is None:
        _client = AzureLLMClient()
    return _client.llm
