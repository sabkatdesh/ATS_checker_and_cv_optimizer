"""Harness for API characterization tests. App wiring lives in _build_client only."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app
from tests.fakes.backend import FakeBackend
from tests.fakes.fake_auth import FakeAuth
from tests.fakes.fake_llm import FakeStructuredLLM
from tests.fakes.fake_pipeline import FakePipeline
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_store import MemoryStore


@pytest.fixture
def backend() -> FakeBackend:
    FakePdfRenderer.calls.clear()
    FakePdfRenderer.raise_on_render = None
    FakeCoverLetterRenderer.calls.clear()
    FakeCoverLetterRenderer.raise_on_render = None
    return FakeBackend(
        store=MemoryStore(),
        auth=FakeAuth(),
        pipeline=FakePipeline(),
        llm=FakeStructuredLLM(),
    )


def _build_client(backend: FakeBackend) -> TestClient:
    container = Container(
        AppSettings(_env_file=None, env="test"),
        store=backend.store,
        auth=backend.auth,
        pipeline=backend.pipeline,
        runner=InlineRunner(),
        llm_factory=lambda: backend.llm,
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )
    return TestClient(create_app(container), raise_server_exceptions=False, follow_redirects=False)


@pytest.fixture
def client(backend) -> TestClient:
    return _build_client(backend)
