"""Shared pieces for the no-leak tests: sentinel text, a fake-backed router, a loopback guard."""

import asyncio
import json
import socket

import pytest
from pydantic import BaseModel
from structlog.testing import capture_logs

from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.fake import FakeTransport
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.config.llm_routes import RouteTable
from app.config.settings import AppSettings
from app.ports.llm import CallMeta, CancelToken, LLMRequest, Message, Route
from tests.unit.llm.router_support import EMB, PRICE, ListSink

SENTINEL = "SENTINEL-JD-91c2"
EMAIL = "jane.doe@example.com"
PHONE = "+8801712345678"
SECRETS = (SENTINEL, EMAIL, PHONE)
TEXT = f"JD: senior engineer {SENTINEL}. CV: Jane {EMAIL} call {PHONE}."

_ROUTE = Route(
    step="s", provider="fake", model="m1", max_tokens=100, temperature=0, timeout_s=5,
    max_attempts=2, structured_mode="prompt",
)  # fmt: skip
_FALLBACK = _ROUTE.model_copy(update={"model": "m2"})
PRICES = PriceTable({("fake", "m1"): PRICE, ("fake", "m2"): PRICE})


class Out(BaseModel):
    answer: str
    score: int


async def _no_sleep(_d: float) -> None:
    return None


def build(script, *, fallback: bool = False):
    transport = FakeTransport(script, defaults_dir=None)
    table = RouteTable({"s": _ROUTE}, {"s": _FALLBACK} if fallback else {}, EMB)
    registry = ProviderRegistry(
        AppSettings(_env_file=None),
        prices=PRICES,
        breakers=BreakerRegistry(),
        retry=RetryPolicy(sleep=_no_sleep, rand=lambda: 0.0),
        factories={"fake": lambda _s: transport},
    )
    sink = ListSink()
    return LLMRouter(table, registry, UsageRecorder(sink, PRICES)), sink


def request(schema: type[BaseModel] | None = Out) -> LLMRequest:
    return LLMRequest(
        step="s",
        system=f"system {SENTINEL}",
        messages=[Message(role="user", content=TEXT)],
        output_schema=schema,
        metadata=CallMeta(prompt_id="p1", user_id="u1"),
    )


def run_captured(router: LLMRouter, req: LLMRequest) -> tuple[str, str]:
    """Run one call; return (everything logged, text of the raised error or '')."""
    raised = ""
    with capture_logs() as logs:
        try:
            asyncio.run(router.complete(req, CancelToken()))
        except Exception as err:  # noqa: BLE001 - any error type must be leak-free
            raised = f"{err!s}|{err!r}|{getattr(err, 'detail', '')}"
    return json.dumps(logs, default=str), raised


def assert_clean(*blobs: str) -> None:
    for blob in blobs:
        for secret in SECRETS:
            assert secret not in blob, f"{secret!r} leaked into {blob[:200]!r}"


@pytest.fixture
def loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and address and address[0] in {"127.0.0.1", "::1"}:
            return real_connect(self, address)  # type: ignore[arg-type]
        raise AssertionError("no network allowed in this test")

    monkeypatch.setattr(socket.socket, "connect", guarded)
