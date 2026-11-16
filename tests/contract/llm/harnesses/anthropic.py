"""Anthropic contract harness (httpx.MockTransport, no network)."""

from typing import Any

import httpx
from pydantic import SecretStr

from app.adapters.llm._base import Transport
from app.adapters.llm.anthropic_api import AnthropicTransport
from tests.contract.llm.harnesses._thin_mock import ThinMockHarness

_STOP = {"end": "end_turn", "max_tokens": "max_tokens", "refused": "refusal"}


class AnthropicHarness(ThinMockHarness):
    name = "anthropic"

    def build_transport(self, mock: httpx.AsyncBaseTransport) -> Transport:
        return AnthropicTransport(SecretStr("sk-ant-test"), transport=mock)

    def body(self, text: str, stop: str, in_tok: int = 10, out_tok: int = 5) -> dict:
        content = [{"type": "text", "text": text}] if text else []
        return {
            "content": content,
            "stop_reason": _STOP[stop],
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
        }

    def normalize(self, raw: dict[str, Any], request: httpx.Request) -> dict[str, Any]:
        return {
            "model": raw["model"],
            "system": raw.get("system", ""),
            "max_tokens": raw["max_tokens"],
            "messages": [{"role": m["role"], "content": m["content"]} for m in raw["messages"]],
        }
