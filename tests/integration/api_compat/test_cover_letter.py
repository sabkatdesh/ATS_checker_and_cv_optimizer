import pytest

from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B

ROUTES = [
    ("POST", "/sessions/t1/cover-letter-options", {"tone": "formal", "length": "short"}),
    ("POST", "/sessions/t1/cover-letter", {"text": "Hi"}),
    ("GET", "/sessions/t1/cover-letter.pdf", None),
]


def _session(backend, **extra):
    row = {"thread_id": "t1", "user_id": USER_A, "status": "awaiting_cover_letter_options", **extra}
    backend.store.sessions["t1"] = row
    return row


def _options(client, body):
    return client.post("/sessions/t1/cover-letter-options", json=body, headers=auth_header())


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_missing_session_404(client, method, path, body):
    r = client.request(method, path, json=body, headers=auth_header())
    assert (r.status_code, r.json()) == (404, {"detail": "Session not found"})


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_foreign_session_403(client, backend, method, path, body):
    backend.store.sessions["t1"] = {"thread_id": "t1", "user_id": USER_B}
    r = client.request(method, path, json=body, headers=auth_header())
    assert (r.status_code, r.json()) == (403, {"detail": "Not your session"})


def test_options_wrong_status_400(client, backend):
    _session(backend)
    backend.store.sessions["t1"]["status"] = "running"
    r = _options(client, {"tone": "formal", "length": "short"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session is not waiting for cover letter options"}


def test_options_coerces_invalid_values(client, backend):
    _session(backend)
    r = _options(client, {"tone": "loud", "length": "huge"})
    assert r.status_code == 200
    assert r.json() == {"status": "resumed", "message": "Generating cover letter. Keep polling /status."}
    assert ("resume_cover_letter", ("t1", "formal", "standard"), {}) in backend.pipeline.calls


def test_options_missing_field_422(client, backend):
    _session(backend)
    assert _options(client, {"tone": "formal"}).status_code == 422


def test_edit_blank_400(client, backend):
    _session(backend)
    r = client.post("/sessions/t1/cover-letter", json={"text": "  "}, headers=auth_header())
    assert r.status_code == 400
    assert r.json() == {"detail": "Cover letter text is empty"}


def test_edit_saves_stripped(client, backend):
    _session(backend)
    r = client.post("/sessions/t1/cover-letter", json={"text": " Hi "}, headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"message": "Cover letter saved successfully"}
    assert backend.store.sessions["t1"]["cover_letter_text"] == "Hi"


def test_pdf_missing_404(client, backend):
    _session(backend)
    r = client.get("/sessions/t1/cover-letter.pdf", headers=auth_header())
    assert r.status_code == 404
    assert r.json() == {
        "detail": "No cover letter PDF found for this session. "
                  "Either it was not requested or generation failed."
    }


def test_pdf_redirects(client, backend):
    _session(backend, cover_letter_pdf_url="https://storage.test/cl.pdf")
    r = client.get("/sessions/t1/cover-letter.pdf", headers=auth_header())
    assert r.status_code == 307
    assert r.headers["location"] == "https://storage.test/cl.pdf"
