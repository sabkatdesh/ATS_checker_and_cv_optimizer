"""Builds each configured LLM provider lazily, once, on first use.

Adapter modules are imported inside their factory, so a provider's SDK is only loaded when a
route actually uses it, and missing credentials surface on the first call, not at boot.
"""

import threading
from collections.abc import Callable, Mapping

from app.adapters.llm._base import BaseProvider, Transport
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.config.settings import AppSettings
from app.ports.llm import LLMProvider
from app.ports.llm_errors import LLMBadRequest

TransportFactory = Callable[[AppSettings], Transport]


def _fake(_settings: AppSettings) -> Transport:
    from app.adapters.llm.fake import FakeTransport

    return FakeTransport()


# One line per adapter; each factory imports its adapter lazily.
DEFAULT_FACTORIES: Mapping[str, TransportFactory] = {
    "fake": _fake,
}


def _wrap(
    name: str,
    transport: Transport,
    prices: PriceTable,
    breakers: BreakerRegistry,
    retry: RetryPolicy,
) -> BaseProvider:
    if name == "fake":
        from app.adapters.llm.fake import FakeProvider, FakeTransport

        if not isinstance(transport, FakeTransport):
            raise LLMBadRequest("the fake provider needs a FakeTransport", provider=name)
        return FakeProvider(transport, prices=prices, breakers=breakers, retry=retry)
    return BaseProvider(transport, prices=prices, breakers=breakers, retry=retry)


class ProviderRegistry:
    def __init__(
        self,
        settings: AppSettings,
        *,
        prices: PriceTable,
        breakers: BreakerRegistry,
        retry: RetryPolicy = RetryPolicy(),  # noqa: B008 - frozen dataclass, safe default
        factories: Mapping[str, TransportFactory] | None = None,
    ) -> None:
        self._settings = settings
        self._prices = prices
        self._breakers = breakers
        self._retry = retry
        self._factories = dict(DEFAULT_FACTORIES if factories is None else factories)
        self._lock = threading.Lock()
        self._providers: dict[str, LLMProvider] = {}

    def get(self, name: str) -> LLMProvider:
        with self._lock:
            provider = self._providers.get(name)
            if provider is None:
                provider = self._build(name)
                self._providers[name] = provider
            return provider

    def _build(self, name: str) -> LLMProvider:
        factory = self._factories.get(name)
        if factory is None:
            raise LLMBadRequest(f"provider {name!r} is not available in this build", provider=name)
        transport = factory(self._settings)
        if transport.name != name:
            raise LLMBadRequest(f"factory for {name!r} built a {transport.name!r} transport")
        return _wrap(name, transport, self._prices, self._breakers, self._retry)
