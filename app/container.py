"""Lazy composition root; default builders are module functions so later tasks can repoint them."""

import threading
from collections.abc import Callable

from psycopg_pool import ConnectionPool

from app.adapters.background.thread_runner import ThreadRunner
from app.adapters.db.credit_repo import PgCreditRepo
from app.adapters.db.errors import DbUnavailable
from app.adapters.db.master_profile_repo import PgMasterProfileRepo
from app.adapters.db.pool import make_pool
from app.adapters.db.profile_repo import PgProfileRepo
from app.adapters.db.render_repo import PgRenderRepo
from app.adapters.db.session_repo import PgSessionRepo
from app.adapters.db.supabase_client import make_supabase_client
from app.adapters.db.supabase_token_verifier import SupabaseTokenVerifier
from app.adapters.db.template_repo import PgTemplateRepo
from app.adapters.llm.stack import LlmStack
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.storage.supabase_storage import SupabaseBlobStorage
from app.adapters.usage.memory_sink import MemoryUsageSink
from app.config.llm_routes import RouteTable
from app.config.settings import AppSettings, ConfigError, load_settings
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.deps import PipelineDeps
from app.pipeline.graph import build_graph
from app.pipeline.prompts.loader import PromptLibrary
from app.pipeline.service import PipelineService
from app.ports.auth import TokenVerifier
from app.ports.background import BackgroundRunner
from app.ports.blob_storage import BlobStorage
from app.ports.embeddings import EmbeddingProvider
from app.ports.llm import LLMGateway
from app.ports.pipeline import PipelineRunner
from app.ports.rendering import CoverLetterRenderer, CvPdfRenderer
from app.ports.repositories import (
    CreditReadRepo,
    MasterProfileRepo,
    ProfileRepo,
    RenderRepo,
    SessionRepo,
    TemplateRepo,
)
from app.ports.usage import UsageSink
from supabase import Client


def _default_storage(settings: AppSettings, supabase: Callable[[], Client]) -> BlobStorage:
    return SupabaseBlobStorage(supabase())


def _default_auth(settings: AppSettings, supabase: Callable[[], Client]) -> TokenVerifier:
    return SupabaseTokenVerifier(supabase())


def _default_pdf() -> CvPdfRenderer:
    from app.rendering.cv_pdf import PDFGenerator

    return PDFGenerator()


def _default_cover_letter() -> CoverLetterRenderer:
    from app.rendering.cover_letter_pdf import CoverLetterService

    return CoverLetterService()


def _default_pipeline(
    settings: AppSettings, gateway: LLMGateway, prompts: PromptLibrary
) -> PipelineRunner:
    deps = PipelineDeps(gateway=gateway, prompts=prompts, settings=settings.pipeline)
    return PipelineService(build_graph(deps, new_checkpointer()), deps.runs)


def _default_runner(settings: AppSettings) -> BackgroundRunner:
    return ThreadRunner()


class Container:
    def __init__(
        self,
        settings: AppSettings,
        *,
        auth: TokenVerifier | None = None,
        storage: BlobStorage | None = None,
        pipeline: PipelineRunner | None = None,
        runner: BackgroundRunner | None = None,
        pdf_factory: Callable[[], CvPdfRenderer] | None = None,
        cover_letter_factory: Callable[[], CoverLetterRenderer] | None = None,
        llm: LLMGateway | None = None,
        embeddings: EmbeddingProvider | None = None,
        usage_sink: UsageSink | None = None,
        pool: ConnectionPool | None = None,
        profiles: ProfileRepo | None = None,
        master_profiles: MasterProfileRepo | None = None,
        templates: TemplateRepo | None = None,
        sessions: SessionRepo | None = None,
        renders: RenderRepo | None = None,
        credits: CreditReadRepo | None = None,
    ) -> None:
        self.settings = settings
        # Reentrant: a default builder may read another lazy property (e.g. pipeline -> llm).
        self._lock = threading.RLock()
        self._auth = auth
        self._storage = storage
        self._pipeline = pipeline
        self._runner = runner
        self._supabase: Client | None = None
        self._pool = pool
        self._closed = False
        self._profiles = profiles
        self._master_profiles = master_profiles
        self._templates = templates
        self._sessions = sessions
        self._renders = renders
        self._credits = credits
        self._llm = llm
        self._embeddings = embeddings
        self.prompts = PromptLibrary()
        self.usage_sink: UsageSink = usage_sink if usage_sink is not None else MemoryUsageSink()
        self._llm_stack = LlmStack(settings, self.usage_sink)
        self._pdf_factory = pdf_factory or _default_pdf
        self._cover_letter_factory = cover_letter_factory or _default_cover_letter

    def _supabase_client(self) -> Client:
        """One Supabase client shared by the default storage and token verifier."""
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
    def pool(self) -> ConnectionPool:
        """One shared sync pool, opened on first use (connections are made lazily)."""
        with self._lock:
            if self._closed:
                raise DbUnavailable  # shut down: never build a fresh, unclosed pool
            if self._pool is None:
                dsn = self.settings.db.dsn
                if dsn is None:
                    raise ConfigError("Database access needs DB__DSN")
                pool = make_pool(self.settings.db)
                pool.open(wait=False)
                self._pool = pool
            return self._pool

    @property
    def profiles(self) -> ProfileRepo:
        with self._lock:
            if self._profiles is None:
                self._profiles = PgProfileRepo(self.pool)
            return self._profiles

    @property
    def master_profiles(self) -> MasterProfileRepo:
        with self._lock:
            if self._master_profiles is None:
                self._master_profiles = PgMasterProfileRepo(self.pool)
            return self._master_profiles

    @property
    def templates(self) -> TemplateRepo:
        with self._lock:
            if self._templates is None:
                self._templates = PgTemplateRepo(self.pool)
            return self._templates

    @property
    def sessions(self) -> SessionRepo:
        with self._lock:
            if self._sessions is None:
                self._sessions = PgSessionRepo(self.pool)
            return self._sessions

    @property
    def renders(self) -> RenderRepo:
        with self._lock:
            if self._renders is None:
                self._renders = PgRenderRepo(self.pool)
            return self._renders

    @property
    def credits(self) -> CreditReadRepo:
        with self._lock:
            if self._credits is None:
                self._credits = PgCreditRepo(self.pool)
            return self._credits

    @property
    def storage(self) -> BlobStorage:
        with self._lock:
            if self._storage is None:
                self._storage = _default_storage(self.settings, self._supabase_client)
            return self._storage

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
                self._pipeline = _default_pipeline(self.settings, self.llm, self.prompts)
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

    def close(self) -> None:
        """Close the pool if it was opened; never opens one. Safe to call twice."""
        with self._lock:
            pool, self._pool = self._pool, None
            self._closed = True
        if pool is not None:
            pool.close()

    def make_pdf_renderer(self) -> CvPdfRenderer:
        return self._pdf_factory()

    def make_cover_letter_renderer(self) -> CoverLetterRenderer:
        return self._cover_letter_factory()


def build_container(settings: AppSettings | None = None) -> Container:
    return Container(settings if settings is not None else load_settings())
