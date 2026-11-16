"""Builds the shared LLM objects (prices, routes, breakers, recorder, router, embeddings).

Nothing here touches the network or reads credentials: providers and boto3 clients are built
on first use. The container holds one LlmStack so every call shares breakers and providers.
"""

import threading

from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.config.llm_routes import RouteTable, load_route_table
from app.config.settings import AppSettings
from app.ports.embeddings import EmbeddingProvider
from app.ports.usage import UsageSink


class LlmStack:
    def __init__(self, settings: AppSettings, sink: UsageSink) -> None:
        self._settings = settings
        self.sink = sink
        self.breakers = BreakerRegistry()
        self._lock = threading.RLock()
        self._prices: PriceTable | None = None
        self._routes: RouteTable | None = None
        self._recorder: UsageRecorder | None = None
        self._router: LLMRouter | None = None

    @property
    def prices(self) -> PriceTable:
        with self._lock:
            if self._prices is None:
                self._prices = PriceTable.from_file(self._settings.llm.prices_file)
            return self._prices

    @property
    def routes(self) -> RouteTable:
        """Loads and validates the route table (raises ConfigError); offline."""
        with self._lock:
            if self._routes is None:
                self._routes = load_route_table(self._settings.llm, self.prices)
            return self._routes

    @property
    def recorder(self) -> UsageRecorder:
        with self._lock:
            if self._recorder is None:
                self._recorder = UsageRecorder(self.sink, self.prices)
            return self._recorder

    @property
    def router(self) -> LLMRouter:
        with self._lock:
            if self._router is None:
                providers = ProviderRegistry(
                    self._settings, prices=self.prices, breakers=self.breakers
                )
                self._router = LLMRouter(self.routes, providers, self.recorder)
            return self._router

    def build_embeddings(self) -> EmbeddingProvider:
        route = self.routes.embeddings
        if self._settings.llm.default_provider == "fake" or route.provider == "fake":
            from app.adapters.embeddings.fake import FakeEmbeddings

            return FakeEmbeddings(dimensions=route.dimensions)
        from app.adapters.embeddings.bedrock_titan import TitanEmbeddings

        return TitanEmbeddings(
            region=self._settings.llm.aws_region,
            retry=RetryPolicy(),
            breakers=self.breakers,
            recorder=self.recorder,
            prices=self.prices,
            model=route.model,
            dimensions=route.dimensions,
            timeout_s=route.timeout_s,
        )
