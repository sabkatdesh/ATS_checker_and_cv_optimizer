"""Shared fakes for the router tests: a scripted named transport and an in-memory sink."""

import asyncio
from decimal import Decimal

from app.adapters.llm._base import RawCompletion, WireRequest
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.fake import Fail, Reply
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.config.llm_routes import EmbeddingRoute, RouteTable
from app.config.settings import AppSettings
from app.ports.llm import CallMeta, CancelToken, LLMRequest, Message, Route, Usage
from app.ports.usage import LlmCallRecord

PRIMARY = "us.anthropic.claude-sonnet-4-6"
GLOBAL = "global.anthropic.claude-sonnet-4-6"
PRICE = ModelPrice(input_per_m=Decimal(3), output_per_m=Decimal(15))
PRICES = PriceTable({("bedrock", PRIMARY): PRICE, ("bedrock", GLOBAL): PRICE})
ROUTE = Route(
    step="jd_extract",
    provider="bedrock",
    model=PRIMARY,
    max_tokens=2000,
    temperature=0,
    timeout_s=30,
    max_attempts=2,
    structured_mode="prompt",
)
FALLBACK = ROUTE.model_copy(update={"model": GLOBAL})
EMB = EmbeddingRoute(provider="fake", model="e", dimensions=8, timeout_s=5)


class ScriptedTransport:
    """Stands in for bedrock: outcomes queued per model, then a default reply."""

    supports_native_schema = True

    def __init__(self, name: str = "bedrock") -> None:
        self.name = name
        self.script: dict[str, list[Reply | Fail]] = {}
        self.sent: list[WireRequest] = []
        self.hang_on: str | None = None  # model whose send cancels the caller's token, then hangs

    def push(self, model: str, *outcomes: Reply | Fail) -> None:
        self.script.setdefault(model, []).extend(outcomes)

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        self.sent.append(wire)
        if wire.model == self.hang_on:
            cancel.cancel()
            await asyncio.sleep(5)
        queue = self.script.get(wire.model)
        if queue:
            o = queue.pop(0)
            if isinstance(o, Fail):
                raise o.error("scripted failure")
            return RawCompletion(o.text, o.stop, o.stop, o.usage)  # type: ignore[arg-type]
        return RawCompletion("ok", "end", "end", Usage(input_tokens=100, output_tokens=10))


class ListSink:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    def write(self, record: LlmCallRecord) -> None:
        self.records.append(record)


async def _no_sleep(_d: float) -> None:
    return None


RETRY = RetryPolicy(sleep=_no_sleep, rand=lambda: 0.0)


def _router(transport=None, *, fallback=FALLBACK, breakers=None, factories=None, route=ROUTE):
    transport = transport or ScriptedTransport()
    table = RouteTable({"jd_extract": route}, {"jd_extract": fallback}, EMB)
    registry = ProviderRegistry(
        AppSettings(),
        prices=PRICES,
        breakers=breakers or BreakerRegistry(),
        retry=RETRY,
        factories=factories or {"bedrock": lambda _s: transport},
    )
    sink = ListSink()
    return LLMRouter(table, registry, UsageRecorder(sink, PRICES)), transport, sink


def _req(step: str = "jd_extract") -> LLMRequest:
    return LLMRequest(
        step=step,
        messages=[Message(role="user", content="hi")],
        metadata=CallMeta(prompt_id="jd.extract", user_id="u1"),
    )


def _run(router, req=None, cancel=None):
    return asyncio.run(router.complete(req or _req(), cancel))
