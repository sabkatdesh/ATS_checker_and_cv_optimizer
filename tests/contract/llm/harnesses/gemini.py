"""Gemini contract harness (httpx.MockTransport, no network)."""

from typing import Any

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import Transport
from app.adapters.llm.gemini import GeminiTransport
from tests.contract.llm.harnesses._thin_mock import ThinMockHarness

_STOP = {"end": "STOP", "max_tokens": "MAX_TOKENS", "refused": "SAFETY"}
_ROLES = {"user": "user", "model": "assistant"}


class GeminiHarness(ThinMockHarness):
    name = "gemini"

    def build_transport(self, mock: httpx.AsyncBaseTransport) -> Transport:
        return GeminiTransport(SecretStr("g-test"), transport=mock)

    def body(self, text: str, stop: str, in_tok: int = 10, out_tok: int = 5) -> dict:
        parts = [{"text": text}] if text else []
        return {
            "candidates": [{"content": {"parts": parts}, "finishReason": _STOP[stop]}],
            "usageMetadata": {"promptTokenCount": in_tok, "candidatesTokenCount": out_tok},
        }

    def normalize(self, raw: dict[str, Any], request: httpx.Request) -> dict[str, Any]:
        system = raw.get("systemInstruction", {}).get("parts", [{}])[0].get("text", "")
        return {
            "model": request.url.path.rsplit("/", 1)[-1].split(":")[0],
            "system": system,
            "max_tokens": raw["generationConfig"]["maxOutputTokens"],
            "messages": [
                {"role": _ROLES[c["role"]], "content": c["parts"][0]["text"]}
                for c in raw["contents"]
            ],
        }
