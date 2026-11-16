"""Shared httpx.MockTransport harness for the thin JSON-over-HTTP providers."""

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


class ThinMockHarness:
    name = ""
    supports_native = False

    def __init__(self) -> None:
        self._outcomes: deque[h.Outcome] = deque()
        self.requests: list[httpx.Request] = []
        self._sent: list[dict[str, Any]] = []

    def build_transport(self, mock: httpx.AsyncBaseTransport) -> Transport:
        raise NotImplementedError

    def body(self, text: str, stop: str, in_tok: int = 10, out_tok: int = 5) -> dict:
        """Provider response; stop is one of end, max_tokens, refused."""
        raise NotImplementedError

    def normalize(self, raw: dict[str, Any], request: httpx.Request) -> dict[str, Any]:
        """Map a sent request to model, system, max_tokens and role/content messages."""
        raise NotImplementedError

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self._sent.append(json.loads(request.content))
        o = self._outcomes.popleft()
        match o:
            case h.Ok(text, usage):
                return httpx.Response(
                    200, json=self.body(text, "end", usage.input_tokens, usage.output_tokens)
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
                return httpx.Response(200, json=self.body("{}", "end"))
            case h.Refusal():
                return httpx.Response(200, json=self.body("", "refused", 10, 0))
            case h.Empty():
                return httpx.Response(200, json=self.body("", "end"))
            case h.Truncated(text):
                return httpx.Response(200, json=self.body(text, "max_tokens"))
        raise AssertionError(f"unknown outcome {o!r}")

    def provider(self, prices: PriceTable, breakers: BreakerRegistry, retry: RetryPolicy):
        transport = self.build_transport(httpx.MockTransport(self._handle))
        return BaseProvider(transport, prices=prices, breakers=breakers, retry=retry)

    def script(self, *outcomes: h.Outcome) -> None:
        self._outcomes.extend(outcomes)

    def sent_bodies(self) -> list[dict]:
        return [
            {**self.normalize(raw, req), "json_schema": None, "raw": raw}
            for raw, req in zip(self._sent, self.requests, strict=True)
        ]

    def last_roles(self) -> list[str]:
        return [m["role"] for m in self.sent_bodies()[-1]["messages"]]
