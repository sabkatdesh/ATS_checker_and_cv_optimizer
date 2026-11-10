from fastapi.testclient import TestClient

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import FakeAuth
from tests.fakes.fake_llm import FakeStructuredLLM
from tests.fakes.fake_pipeline import FakePipeline
from tests.fakes.memory_store import MemoryStore


def _client(env: str) -> TestClient:
    extra = {"api": {"cors_origins": ["https://app.example.com"]}} if env == "prod" else {}
    settings = AppSettings(_env_file=None, env=env, **extra)
    container = Container(
        settings,
        store=MemoryStore(),
        auth=FakeAuth(),
        pipeline=FakePipeline(),
        runner=InlineRunner(),
        llm_factory=FakeStructuredLLM,
    )
    return TestClient(create_app(container), raise_server_exceptions=False)


def test_add_coins_mounted_in_test_env():
    r = _client("test").post("/billing/add-coins", json={"amount": 5}, headers=auth_header())
    assert r.status_code == 200


def test_add_coins_absent_in_prod():
    r = _client("prod").post("/billing/add-coins", json={"amount": 5}, headers=auth_header())
    assert r.status_code == 404


def test_balance_present_in_prod():
    r = _client("prod").get("/billing/balance", headers=auth_header())
    assert r.status_code == 200
