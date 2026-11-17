"""Lazy composition root; default builders are module functions so later tasks can repoint them."""

import threading
from collections.abc import Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.adapters.background.thread_runner import ThreadRunner
from app.adapters.db.supabase_client import make_supabase_client
from app.adapters.db.supabase_legacy_store import SupabaseLegacyStore
from app.adapters.db.supabase_token_verifier import SupabaseTokenVerifier
from app.adapters.llm.legacy_structured import GatewayStructuredLLM
from app.adapters.llm.stack import LlmStack
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.usage.memory_sink import MemoryUsageSink
from app.config.llm_routes import RouteTable
from app.config.settings import AppSettings, ConfigError, load_settings
from app.pipeline.deps import PipelineDeps
from app.pipeline.graph import build_graph
from app.pipeline.prompts.loader import PromptLibrary
from app.pipeline.service import PipelineService
from app.ports.auth import TokenVerifier
from app.ports.background import BackgroundRunner
from app.ports.embeddings import EmbeddingProvider
from app.ports.legacy_store import LegacyStore
from app.ports.llm import LLMGateway
from app.ports.llm_legacy import StructuredLLM
from app.ports.pipeline import PipelineRunner
from app.ports.rendering import CoverLetterRenderer, CvPdfRenderer
from app.ports.usage import UsageSink
from supabase import Client


def _default_store(settings: AppSettings, supabase: Callable[[], Client]) -> LegacyStore:
    return SupabaseLegacyStore(supabase())


def _default_auth(settings: AppSettings, supabase: Callable[[], Client]) -> TokenVerifier:
    return SupabaseTokenVerifier(supabase())


def _default_llm(settings: AppSettings, gateway: LLMGateway) -> StructuredLLM:
    return GatewayStructuredLLM(gateway)


def _default_pdf() -> CvPdfRenderer:
    from app.rendering.cv_pdf import PDFGenerator

    return PDFGenerator()


def _default_cover_letter() -> CoverLetterRenderer:
    from app.rendering.cover_letter_pdf import CoverLetterService

    return CoverLetterService()


def _default_pipeline(settings: AppSettings, gateway: LLMGateway) -> PipelineRunner:
    deps = PipelineDeps(gateway=gateway, prompts=PromptLibrary(), settings=settings.pipeline)
    return PipelineService(build_graph(deps, MemorySaver(serde=JsonPlusSerializer())))


def _default_runner(settings: AppSettings) -> BackgroundRunner:
    return ThreadRunner()


class Container:
    def __init__(
        self,
        settings: AppSettings,
        *,
        store: LegacyStore | None = None,
        auth: TokenVerifier | None = None,
        pipeline: PipelineRunner | None = None,
        runner: BackgroundRunner | None = None,
        llm_factory: Callable[[], StructuredLLM] | None = None,
        pdf_factory: Callable[[], CvPdfRenderer] | None = None,
        cover_letter_factory: Callable[[], CoverLetterRenderer] | None = None,
        llm: LLMGateway | None = None,
        embeddings: EmbeddingProvider | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        self.settings = settings
        # Reentrant: a default builder may read another lazy property (e.g. pipeline -> store).
        self._lock = threading.RLock()
        self._store = store
        self._auth = auth
        self._pipeline = pipeline
        self._runner = runner
        self._supabase: Client | None = None
        self._llm = llm
        self._embeddings = embeddings
        self.usage_sink: UsageSink = usage_sink if usage_sink is not None else MemoryUsageSink()
        self._llm_stack = LlmStack(settings, self.usage_sink)
        self._llm_factory = llm_factory or (lambda: _default_llm(self.settings, self.llm))
        self._pdf_factory = pdf_factory or _default_pdf
        self._cover_letter_factory = cover_letter_factory or _default_cover_letter

    def _supabase_client(self) -> Client:
        """One Supabase client shared by the default store and token verifier."""
        with self._lock:
            if self._supabase is None:
                url, key = self.settings.supabase_url, self.settings.supabase_secret_key
                if not url or key is None:
                    raise ConfigError(
                        "Database access needs AUTH__SUPABASE_URL (or SUPABASE_URL) "
                        "and SUPABASE_SECRET_KEY"
                    )
                self._supabase = make_supabase_client(url, key)
            return self._supabase

    @property
    def store(self) -> LegacyStore:
        with self._lock:
            if self._store is None:
                self._store = _default_store(self.settings, self._supabase_client)
            return self._store

    @property
    def auth(self) -> TokenVerifier:
        with self._lock:
            if self._auth is None:
                self._auth = _default_auth(self.settings, self._supabase_client)
            return self._auth

    @property
    def pipeline(self) -> PipelineRunner:
        with self._lock:
            if self._pipeline is None:
                self._pipeline = _default_pipeline(self.settings, self.llm)
            return self._pipeline

    @property
    def runner(self) -> BackgroundRunner:
        with self._lock:
            if self._runner is None:
                self._runner = _default_runner(self.settings)
            return self._runner

    @property
    def llm(self) -> LLMGateway:
        """One shared router, so every call sees the same breakers and providers."""
        with self._lock:
            if self._llm is None:
                self._llm = self._llm_stack.router
            return self._llm

    @property
    def embeddings(self) -> EmbeddingProvider:
        with self._lock:
            if self._embeddings is None:
                self._embeddings = self._llm_stack.build_embeddings()
            return self._embeddings

    @property
    def usage(self) -> UsageRecorder:
        return self._llm_stack.recorder

    def validate_llm_config(self) -> RouteTable:
        """Load prices and routes; raises ConfigError. Needs no credentials or network."""
        return self._llm_stack.routes

    def make_llm_client(self) -> StructuredLLM:
        return self._llm_factory()

    def make_pdf_renderer(self) -> CvPdfRenderer:
        return self._pdf_factory()

    def make_cover_letter_renderer(self) -> CoverLetterRenderer:
        return self._cover_letter_factory()


def build_container(settings: AppSettings | None = None) -> Container:
    return Container(settings if settings is not None else load_settings())
