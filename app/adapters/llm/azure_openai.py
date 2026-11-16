"""Azure OpenAI transport: classic deployments and AI Foundry (prompt-mode JSON).

Ports the endpoint handling of the legacy client: a Foundry endpoint (flag, or a host under
services.ai.azure.com) uses the OpenAI-compatible /openai/v1 route with the deployment as the
model and a bearer token; classic Azure uses the deployment route, api-version and api-key header.
"""

from urllib.parse import quote, urlparse

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import RawCompletion, WireRequest
from app.adapters.llm._http import post_json
from app.adapters.llm._openai_wire import chat_body, parse_chat, secret_value
from app.config.settings import AppSettings
from app.ports.llm import CancelToken
from app.ports.llm_errors import LLMAuthError

PROVIDER = "azure_openai"


class AzureOpenAITransport:
    name = PROVIDER
    supports_native_schema = False

    def __init__(
        self,
        endpoint: str,
        api_key: SecretStr | None,
        deployment: str,
        api_version: str,
        foundry: bool,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._deployment = deployment
        self._api_version = api_version
        host = urlparse(self._endpoint).hostname or ""
        self._foundry = foundry or host.endswith("services.ai.azure.com")
        self._transport = transport

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        if not self._endpoint or not self._deployment:
            raise LLMAuthError("missing azure configuration", provider=PROVIDER, model=wire.model)
        key = secret_value(self._api_key, provider=PROVIDER, model=wire.model)
        body = chat_body(wire, include_model=False)
        if self._foundry:
            base = self._endpoint.removesuffix("/openai/v1")
            url = f"{base}/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            body["model"] = self._deployment
        else:
            url = (
                f"{self._endpoint}/openai/deployments/{quote(self._deployment, safe='')}"
                f"/chat/completions?api-version={quote(self._api_version, safe='')}"
            )
            headers = {"api-key": key}
        data = await post_json(
            url,
            headers=headers,
            body=body,
            timeout_s=wire.timeout_s,
            provider=PROVIDER,
            model=wire.model,
            transport=self._transport,
        )
        return parse_chat(data, provider=PROVIDER)


def build_azure_transport(settings: AppSettings) -> AzureOpenAITransport:
    """Cheap: no network or credential check; missing settings fail on the first send."""
    return AzureOpenAITransport(
        endpoint=settings.azure_openai_endpoint or "",
        api_key=settings.azure_openai_key,
        deployment=settings.azure_openai_deployment or "",
        api_version=settings.azure_openai_api_version,
        foundry=settings.azure_foundry,
    )
