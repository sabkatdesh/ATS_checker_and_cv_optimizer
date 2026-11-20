import pytest
from fastapi.testclient import TestClient

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app
from tests.fakes.backend import FakeBackend, auth_header


def _client(env: str) -> TestClient:
    extra = {"api": {"cors_origins": ["https://app.example.com"]}} if env == "prod" else {}
    settings = AppSettings(_env_file=None, env=env, **extra)
    backend = FakeBackend()
    container = Container(
        settings, **backend.repos(), pipeline=backend.pipeline, runner=InlineRunner()
    )
    return TestClient(create_app(container), raise_server_exceptions=False)


@pytest.mark.parametrize("env", ["dev", "test", "prod"])
@pytest.mark.parametrize("authed", [False, True])
def test_add_coins_absent_in_every_env(env, authed):
    headers = auth_header() if authed else {}
    r = _client(env).post("/billing/add-coins", json={"amount": 5}, headers=headers)
    assert r.status_code == 404


def test_balance_present_in_prod():
    r = _client("prod").get("/billing/balance", headers=auth_header())
    assert r.status_code == 200
