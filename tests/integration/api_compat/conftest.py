"""Harness for API characterization tests. App wiring lives in _build_client only."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.adapters.background.inline_runner import InlineRunner
from app.config.db_settings import BonusSettings
from app.config.settings import ApiSettings, AppSettings
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


PEPPER = SecretStr("test-pepper")


def _build_client(
    backend: FakeBackend,
    *,
    pepper: SecretStr | None = PEPPER,
    hops: int = 0,
    ip_header: str | None = None,
) -> TestClient:
    container = Container(
        AppSettings(
            _env_file=None,
            env="test",
            bonus=BonusSettings(hash_pepper=pepper),
            api=ApiSettings(trusted_proxy_hops=hops, client_ip_header=ip_header),
        ),
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
