import pytest

from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B

T1 = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
ROUTES = [
    ("POST", f"/sessions/{T1}/cover-letter-options", {"tone": "formal", "length": "short"}),
    ("POST", f"/sessions/{T1}/cover-letter", {"text": "Hi"}),
    ("GET", f"/sessions/{T1}/cover-letter.pdf", None),
]


def _session(backend, user=USER_A, **extra):
    cols = {"status": "awaiting_input", "awaiting_kind": "cover_letter_options", **extra}
    return backend.sessions.seed(user, T1, **cols)


def _options(client, body):
    return client.post(f"/sessions/{T1}/cover-letter-options", json=body, headers=auth_header())


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_missing_session_404(client, method, path, body):
    r = client.request(method, path, json=body, headers=auth_header())
    assert (r.status_code, r.json()) == (404, {"detail": "Session not found"})


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_foreign_session_404(client, backend, method, path, body):
    _session(backend, user=USER_B, cover_letter_text="theirs")
    r = client.request(method, path, json=body, headers=auth_header())
    assert (r.status_code, r.json()) == (404, {"detail": "Session not found"})
    assert backend.sessions.raw(T1)["cover_letter_text"] == "theirs"
    assert backend.pipeline.calls == []


def test_options_wrong_status_400(client, backend):
    _session(backend, status="running", awaiting_kind=None)
    r = _options(client, {"tone": "formal", "length": "short"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Session is not waiting for cover letter options"}


def test_options_coerces_invalid_values(client, backend):
    _session(backend)
    r = _options(client, {"tone": "loud", "length": "huge"})
    assert r.status_code == 200
    assert r.json() == {
        "status": "resumed",
        "message": "Generating cover letter. Keep polling /status.",
    }
    assert ("resume_cover_letter", (T1, "formal", "standard"), {}) in backend.pipeline.calls


def test_options_missing_field_422(client, backend):
    _session(backend)
    assert _options(client, {"tone": "formal"}).status_code == 422


def test_edit_blank_400(client, backend):
    _session(backend)
    r = client.post(f"/sessions/{T1}/cover-letter", json={"text": "  "}, headers=auth_header())
    assert r.status_code == 400
    assert r.json() == {"detail": "Cover letter text is empty"}


def test_edit_saves_stripped(client, backend):
    _session(backend)
    r = client.post(f"/sessions/{T1}/cover-letter", json={"text": " Hi "}, headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"message": "Cover letter saved successfully"}
    assert backend.sessions.raw(T1)["cover_letter_text"] == "Hi"


def test_pdf_missing_404(client, backend):
    _session(backend)
    r = client.get(f"/sessions/{T1}/cover-letter.pdf", headers=auth_header())
    assert r.status_code == 404
    assert r.json() == {
        "detail": "No cover letter PDF found for this session. "
        "Either it was not requested or generation failed."
    }


def test_pdf_redirects(client, backend):
    _session(backend)
    path = f"user-a/{T1}/cover_letter.pdf"
    backend.renders.add(USER_A, T1, pdf_path=path, content_hash="h", template_id="cover_letter")
    r = client.get(f"/sessions/{T1}/cover-letter.pdf", headers=auth_header())
    assert r.status_code == 307
    assert r.headers["location"] == f"https://signed.test/renders/{path}?ttl=600"


def test_options_resumes_and_finalizes(client, backend):
    _session(backend)
    backend.pipeline.result = {"eligible": True}
    assert _options(client, {"tone": "formal", "length": "short"}).status_code == 200
    row = backend.sessions.raw(T1)
    assert (row["status"], row["awaiting_kind"]) == ("succeeded", None)
