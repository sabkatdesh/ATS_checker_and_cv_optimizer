from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.api.errors import AppError
from app.config.settings import AppSettings
from app.container import build_container
from app.main import create_app


def test_health_ok():
    app = create_app(build_container(AppSettings(_env_file=None)))
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_app_error_is_problem_json():
    app = create_app(build_container(AppSettings(_env_file=None)))
    router = APIRouter()

    @router.get("/_boom")
    def boom():
        raise AppError("JD_INVALID", 400, "Invalid job description", "too short")

    app.include_router(router)
    r = TestClient(app).get("/_boom")
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert set(body) == {"type", "title", "status", "code", "detail", "request_id"}
    assert body["type"] == "/problems/jd-invalid"
    assert body["code"] == "JD_INVALID"


def test_legacy_http_exception_body_unchanged():
    app = create_app(build_container(AppSettings(_env_file=None)))
    r = TestClient(app).get("/profile")
    assert r.status_code == 401
    assert r.json() == {"detail": "Not logged in"}
    assert r.headers["content-type"] == "application/json"
