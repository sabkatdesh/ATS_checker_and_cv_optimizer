"""Harness for API characterization tests. App wiring lives in _build_client only."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app
from tests.fakes.backend import FakeBackend
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer


@pytest.fixture
def backend() -> FakeBackend:
    FakePdfRenderer.calls.clear()
    FakePdfRenderer.raise_on_render = None
    FakeCoverLetterRenderer.calls.clear()
    FakeCoverLetterRenderer.raise_on_render = None
    return FakeBackend()


def _build_client(backend: FakeBackend) -> TestClient:
    container = Container(
        AppSettings(_env_file=None, env="test"),
        **backend.repos(),
        pipeline=backend.pipeline,
        runner=InlineRunner(),
        llm=backend.llm,
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )
    return TestClient(create_app(container), raise_server_exceptions=False, follow_redirects=False)


@pytest.fixture
def client(backend) -> TestClient:
    return _build_client(backend)
