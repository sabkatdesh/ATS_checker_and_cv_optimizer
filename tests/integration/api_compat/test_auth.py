import pytest

from tests.fakes.backend import auth_header

PROTECTED = [
    ("GET", "/profile", None),
    ("POST", "/profile", {"full_name": "A"}),
    ("POST", "/profile/import-cv", {"cv_text": "x"}),
    ("POST", "/sessions/start", {"job_description": "x"}),
    ("GET", "/sessions/t1/status", None),
    ("POST", "/sessions/t1/reply", {"user_qna": "x"}),
    ("POST", "/sessions/t1/cover-letter-options", {"tone": "formal", "length": "short"}),
    ("POST", "/sessions/t1/cover-letter", {"text": "x"}),
    ("GET", "/sessions/t1/cover-letter.pdf", None),
    ("GET", "/sessions", None),
    ("GET", "/settings", None),
    ("POST", "/settings", {"accent_color": "#112233"}),
    ("GET", "/billing/balance", None),
    ("GET", "/billing/history", None),
    ("POST", "/billing/add-coins", {"amount": 1}),
]


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_route_without_header_is_401(client, backend, method, path, body):
    r = client.request(method, path, json=body)
    assert r.status_code == 401
    assert r.json() == {"detail": "Not logged in"}
    assert backend.store.calls == []
    assert backend.pipeline.calls == []


def test_non_bearer_header_is_401(client):
    r = client.get("/profile", headers={"Authorization": "Token x"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Not logged in"}


def test_unknown_token_is_401(client):
    r = client.get("/profile", headers=auth_header("nope"))
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid or expired session. Please log in again."}


def test_invalid_body_beats_auth(client):
    r = client.post("/profile", json={"skills": "x"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)
