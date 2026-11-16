"""Ollama contract harness (httpx.MockTransport, no network)."""

from typing import Any

import httpx

from app.adapters.llm._base import Transport
from app.adapters.llm.ollama import OllamaTransport
from tests.contract.llm.harnesses._thin_mock import ThinMockHarness

_STOP = {"end": "stop", "max_tokens": "length", "refused": "content_filter"}


class OllamaHarness(ThinMockHarness):
    name = "ollama"

    def build_transport(self, mock: httpx.AsyncBaseTransport) -> Transport:
        return OllamaTransport("http://ollama.test:11434", transport=mock)

    def body(self, text: str, stop: str, in_tok: int = 10, out_tok: int = 5) -> dict:
        return {
            "message": {"role": "assistant", "content": text},
            "done": True,
            "done_reason": _STOP[stop],
            "prompt_eval_count": in_tok,
            "eval_count": out_tok,
        }

    def normalize(self, raw: dict[str, Any], request: httpx.Request) -> dict[str, Any]:
        msgs = raw["messages"]
        has_system = bool(msgs) and msgs[0]["role"] == "system"
        rest = msgs[1:] if has_system else msgs
        return {
            "model": raw["model"],
            "system": msgs[0]["content"] if has_system else "",
            "max_tokens": raw["options"]["num_predict"],
            "messages": [{"role": m["role"], "content": m["content"]} for m in rest],
        }
