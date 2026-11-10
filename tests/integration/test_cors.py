from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app


def _client(origins: list[str] | None = None) -> TestClient:
    overrides = {"api": {"cors_origins": origins}} if origins else {}
    settings = AppSettings(_env_file=None, env="test", **overrides)
    return TestClient(create_app(Container(settings)))


def test_allowed_origin_echoed():
    r = _client().get("/", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_origin_has_no_cors_header():
    r = _client().get("/", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_unknown_origin_preflight_rejected():
    r = _client().options(
        "/profile",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 400


def test_custom_allow_list():
    client = _client(["https://app.example.com"])
    ok = client.get("/", headers={"Origin": "https://app.example.com"})
    assert ok.headers["access-control-allow-origin"] == "https://app.example.com"
    bad = client.get("/", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in bad.headers
