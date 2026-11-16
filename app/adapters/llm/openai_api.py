"""OpenAI chat-completions transport (prompt-mode JSON; no native schema)."""

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import RawCompletion, WireRequest
from app.adapters.llm._http import post_json
from app.adapters.llm._openai_wire import chat_body, parse_chat, secret_value
from app.config.settings import AppSettings
from app.ports.llm import CancelToken

PROVIDER = "openai"


class OpenAITransport:
    name = PROVIDER
    supports_native_schema = False

    def __init__(
        self,
        api_key: SecretStr | None,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        key = secret_value(self._api_key, provider=PROVIDER, model=wire.model)
        data = await post_json(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            body=chat_body(wire, include_model=True),
            timeout_s=wire.timeout_s,
            provider=PROVIDER,
            model=wire.model,
            transport=self._transport,
        )
        return parse_chat(data, provider=PROVIDER)


def build_openai_transport(settings: AppSettings) -> OpenAITransport:
    """Cheap: no network or credential check; a missing key fails on the first send."""
    return OpenAITransport(settings.llm.openai_api_key, settings.llm.openai_base_url)
