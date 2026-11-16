"""Shared httpx.MockTransport harness for chat-completions style providers."""

import asyncio
import json
from collections import deque
from typing import Any

import httpx

from app.adapters.llm._base import BaseProvider, Transport
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from tests.contract.llm import harness as h


def completion(text: str, finish: str, in_tok: int = 10, out_tok: int = 5) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": in_tok, "completion_tokens": out_tok},
    }


class ChatMockHarness:
    name = "openai"
    supports_native = False

    def __init__(self) -> None:
        self._outcomes: deque[h.Outcome] = deque()
        self.requests: list[httpx.Request] = []
        self._sent: list[dict[str, Any]] = []

    def build_transport(self, mock: httpx.AsyncBaseTransport) -> Transport:
        raise NotImplementedError

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self._sent.append(json.loads(request.content))
        o = self._outcomes.popleft()
        match o:
            case h.Ok(text, usage):
                return httpx.Response(
                    200, json=completion(text, "stop", usage.input_tokens, usage.output_tokens)
                )
            case h.Throttle(retry_after):
                headers = {} if retry_after is None else {"Retry-After": str(retry_after)}
                return httpx.Response(429, headers=headers, json={"error": "slow down"})
            case h.ServerError():
                return httpx.Response(500, json={"error": "boom"})
            case h.BadRequest():
                return httpx.Response(400, json={"error": "bad input"})
            case h.Timeout():
                raise httpx.ReadTimeout("slow", request=request)
            case h.Hang():
                await asyncio.sleep(5)
                return httpx.Response(200, json=completion("{}", "stop"))
            case h.Refusal():
                return httpx.Response(200, json=completion("", "content_filter", 10, 0))
            case h.Empty():
                return httpx.Response(200, json=completion("", "stop"))
            case h.Truncated(text):
                return httpx.Response(200, json=completion(text, "length"))
        raise AssertionError(f"unknown outcome {o!r}")

    def provider(self, prices: PriceTable, breakers: BreakerRegistry, retry: RetryPolicy):
        transport = self.build_transport(httpx.MockTransport(self._handle))
        return BaseProvider(transport, prices=prices, breakers=breakers, retry=retry)

    def script(self, *outcomes: h.Outcome) -> None:
        self._outcomes.extend(outcomes)

    def sent_bodies(self) -> list[dict]:
        bodies = []
        for raw in self._sent:
            msgs = raw["messages"]
            has_system = bool(msgs) and msgs[0]["role"] == "system"
            rest = msgs[1:] if has_system else msgs
            bodies.append(
                {
                    "model": raw.get("model", ""),
                    "system": msgs[0]["content"] if has_system else "",
                    "max_tokens": raw["max_completion_tokens"],
                    "messages": [{"role": m["role"], "content": m["content"]} for m in rest],
                    "json_schema": None,
                    "raw": raw,
                }
            )
        return bodies

    def last_roles(self) -> list[str]:
        return [m["role"] for m in self.sent_bodies()[-1]["messages"]]
