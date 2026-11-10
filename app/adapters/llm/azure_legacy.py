"""Azure OpenAI / AI Foundry chat client (legacy LLM path).

Foundry endpoints (*.services.ai.azure.com) use ChatOpenAI with a base_url; classic Azure OpenAI
(*.openai.azure.com) uses AzureChatOpenAI. All configuration is passed in; nothing reads os.environ.
"""

import logging
from typing import Any, TypeVar

from pydantic import BaseModel, SecretStr

from app.config.settings import AppSettings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MISSING_CREDENTIALS = (
    "Azure credentials missing. Set AZURE_OPENAI_ENDPOINT, "
    "AZURE_OPENAI_KEY, and AZURE_OPENAI_DEPLOYMENT in your .env file. "
    "See .env.example for the full list."
)


class AzureLLMClient:
    def __init__(
        self,
        endpoint: str,
        api_key: SecretStr,
        deployment: str,
        api_version: str,
        foundry: bool,
        max_retries: int = 3,
        timeout: int = 120,
        temperature: float | None = None,
    ) -> None:
        if not all([endpoint, api_key.get_secret_value(), deployment]):
            raise OSError(_MISSING_CREDENTIALS)

        extra: dict[str, Any] = {}
        if temperature is not None:
            extra["temperature"] = temperature

        if foundry or "services.ai.azure.com" in endpoint:
            from langchain_openai import ChatOpenAI

            self._chat: Any = ChatOpenAI(
                base_url=endpoint.rstrip("/") + "/openai/v1/",
                api_key=api_key,
                model=deployment,
                max_retries=max_retries,
                timeout=timeout,
                **extra,
            )
            logger.info("llm.client_ready mode=foundry deployment=%s", deployment)
        else:
            from langchain_openai import AzureChatOpenAI

            self._chat = AzureChatOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                azure_deployment=deployment,
                api_version=api_version,
                max_retries=max_retries,
                timeout=timeout,
                **extra,
            )
            logger.info("llm.client_ready mode=azure deployment=%s", deployment)

        self._deployment = deployment

    @property
    def llm(self) -> Any:
        """The underlying LangChain model for use in chains (template | llm | parser)."""
        return self._chat

    def invoke_structured(self, prompt: str, schema: type[T]) -> T:  # noqa: UP047
        """Structured output; on failure falls back to string output plus safe_parser."""
        from langchain_core.output_parsers import StrOutputParser

        from app.domain.parsing.safe_parser import safe_llm_parse

        try:
            return self._chat.with_structured_output(schema).invoke(prompt)  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("llm.structured_fallback error_type=%s", type(exc).__name__)
            raw = (self._chat | StrOutputParser()).invoke(prompt)
            return safe_llm_parse(raw, schema, schema())

    def log_usage(self, call_type: str, response_metadata: dict[str, Any]) -> None:
        usage = response_metadata.get("token_usage") or response_metadata.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        logger.info(
            "llm.usage call_type=%s model=%s in=%s out=%s total=%s",
            call_type,
            self._deployment,
            input_tokens,
            output_tokens,
            input_tokens + output_tokens,
        )


def build_azure_client(settings: AppSettings) -> AzureLLMClient:
    return AzureLLMClient(
        endpoint=settings.azure_openai_endpoint or "",
        api_key=settings.azure_openai_key or SecretStr(""),
        deployment=settings.azure_openai_deployment or "",
        api_version=settings.azure_openai_api_version,
        foundry=settings.azure_foundry,
    )
