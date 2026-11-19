import psycopg
from fastapi.testclient import TestClient

from app.adapters.db.template_repo import PgTemplateRepo
from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app
from tests.fakes.recording_pool import RecordingPool


def _client(pool) -> TestClient:
    c = Container(AppSettings(_env_file=None, env="test"), pool=pool)
    return TestClient(create_app(c), raise_server_exceptions=False)


def test_health_deep_ok():
    r = _client(RecordingPool()).get("/health/deep")
    assert r.status_code == 200
    assert r.json() == {"db": "ok"}


def test_health_deep_503_when_db_down():
    pool = RecordingPool()
    pool.raise_on_connect = psycopg.OperationalError("password=secret")
    r = _client(pool).get("/health/deep")
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "DB_DOWN"
    assert "secret" not in r.text


def test_health_deep_503_without_dsn():
    c = Container(AppSettings(_env_file=None, env="test"))
    r = TestClient(create_app(c), raise_server_exceptions=False).get("/health/deep")
    assert r.status_code == 503
    assert r.json()["code"] == "DB_DOWN"


def test_plain_health_does_not_touch_db():
    pool = RecordingPool()
    pool.raise_on_connect = RuntimeError("must not be called")
    r = _client(pool).get("/health")
    assert r.json() == {"status": "ok"}


def test_db_error_in_route_returns_503_problem():
    pool = RecordingPool()
    pool.raise_on_connect = psycopg.OperationalError("password=secret")
    c = Container(
        AppSettings(_env_file=None, env="test"), pool=pool, templates=PgTemplateRepo(pool)
    )
    r = TestClient(create_app(c), raise_server_exceptions=False).get("/templates")
    assert r.status_code == 503
    assert r.json()["code"] == "DB_UNAVAILABLE"
    assert "secret" not in r.text
