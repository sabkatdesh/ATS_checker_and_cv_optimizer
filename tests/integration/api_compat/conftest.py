"""Harness for API characterization tests. Legacy wiring lives in _wire_legacy only."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.fakes.backend import FakeBackend
from tests.fakes.fake_auth import FakeAuth
from tests.fakes.fake_llm import FakeStructuredLLM
from tests.fakes.fake_pipeline import FakePipeline
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_store import MemoryStore

_ENV_DEFAULTS = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_KEY": "test",
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
    "AZURE_OPENAI_KEY": "test",
    "AZURE_OPENAI_DEPLOYMENT": "test",
}

_DB_NAMES = [
    "get_cv_profile", "save_cv_profile", "create_session", "update_session",
    "get_session", "get_user_sessions", "upload_pdf_to_storage", "get_cv_templates",
    "get_user_settings", "save_user_settings", "get_coin_balance", "deduct_coins",
    "add_coins", "get_coin_transactions",
]


class SyncThread:
    """Runs the target inline so background work finishes before the response returns."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


@pytest.fixture(scope="session")
def legacy_api():
    for key, value in _ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    with patch("supabase.create_client", return_value=MagicMock()):
        import api
    return api


def _wire_legacy(backend: FakeBackend, monkeypatch, api) -> None:
    for name in _DB_NAMES:
        monkeypatch.setattr(api, name, getattr(backend.store, name))
    monkeypatch.setattr(
        api, "supabase_client",
        SimpleNamespace(auth=SimpleNamespace(get_user=backend.auth.legacy_get_user)),
    )
    monkeypatch.setattr(api, "run_pipeline_for_user", backend.pipeline.run)
    monkeypatch.setattr(api, "get_pipeline_state", backend.pipeline.get_state)
    monkeypatch.setattr(api, "resume_pipeline_for_user", backend.pipeline.resume)
    monkeypatch.setattr(api, "resume_cover_letter_for_user", backend.pipeline.resume_cover_letter)
    monkeypatch.setattr(api, "threading", SimpleNamespace(Thread=SyncThread))
    monkeypatch.setattr("services.pdf_generator.PDFGenerator", FakePdfRenderer)
    monkeypatch.setattr("services.cover_letter.CoverLetterService", FakeCoverLetterRenderer)
    monkeypatch.setattr("core.llm_client.AzureLLMClient", lambda: backend.llm)


@pytest.fixture
def backend() -> FakeBackend:
    FakePdfRenderer.calls.clear()
    FakePdfRenderer.raise_on_render = None
    FakeCoverLetterRenderer.calls.clear()
    FakeCoverLetterRenderer.raise_on_render = None
    return FakeBackend(
        store=MemoryStore(), auth=FakeAuth(), pipeline=FakePipeline(), llm=FakeStructuredLLM(),
    )


@pytest.fixture
def client(backend, monkeypatch, legacy_api) -> TestClient:
    _wire_legacy(backend, monkeypatch, legacy_api)
    return TestClient(legacy_api.app, raise_server_exceptions=False, follow_redirects=False)
