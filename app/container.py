"""Lazy composition root; default builders are module functions so later tasks can repoint them."""

import threading
from collections.abc import Callable

from app.adapters.background.thread_runner import ThreadRunner
from app.adapters.legacy_bridge import (
    LegacyModuleStore,
    LegacyPipeline,
    LegacyTokenVerifier,
    legacy_cover_letter,
    legacy_llm,
    legacy_pdf,
)
from app.config.settings import AppSettings, load_settings
from app.ports.auth import TokenVerifier
from app.ports.background import BackgroundRunner
from app.ports.legacy_store import LegacyStore
from app.ports.llm_legacy import StructuredLLM
from app.ports.pipeline import PipelineRunner
from app.ports.rendering import CoverLetterRenderer, CvPdfRenderer


def _default_store(settings: AppSettings) -> LegacyStore:
    return LegacyModuleStore()


def _default_auth(settings: AppSettings) -> TokenVerifier:
    return LegacyTokenVerifier()


def _default_pipeline(settings: AppSettings) -> PipelineRunner:
    return LegacyPipeline()


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
    ) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._store = store
        self._auth = auth
        self._pipeline = pipeline
        self._runner = runner
        self._llm_factory = llm_factory or legacy_llm
        self._pdf_factory = pdf_factory or legacy_pdf
        self._cover_letter_factory = cover_letter_factory or legacy_cover_letter

    @property
    def store(self) -> LegacyStore:
        with self._lock:
            if self._store is None:
                self._store = _default_store(self.settings)
            return self._store

    @property
    def auth(self) -> TokenVerifier:
        with self._lock:
            if self._auth is None:
                self._auth = _default_auth(self.settings)
            return self._auth

    @property
    def pipeline(self) -> PipelineRunner:
        with self._lock:
            if self._pipeline is None:
                self._pipeline = _default_pipeline(self.settings)
            return self._pipeline

    @property
    def runner(self) -> BackgroundRunner:
        with self._lock:
            if self._runner is None:
                self._runner = _default_runner(self.settings)
            return self._runner

    def make_llm_client(self) -> StructuredLLM:
        return self._llm_factory()

    def make_pdf_renderer(self) -> CvPdfRenderer:
        return self._pdf_factory()

    def make_cover_letter_renderer(self) -> CoverLetterRenderer:
        return self._cover_letter_factory()


def build_container(settings: AppSettings | None = None) -> Container:
    return Container(settings if settings is not None else load_settings())
