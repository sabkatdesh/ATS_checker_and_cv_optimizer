"""Resume endpoints use the canonical session id and only the CAS winner resumes."""

import pytest

from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A

T1 = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
REPLY = ("reply", {"user_qna": "answers"}, "questions", "resume")
OPTIONS = (
    "cover-letter-options",
    {"tone": "formal", "length": "short"},
    "cover_letter_options",
    "resume_cover_letter",
)


def _post(client, sid, route, body):
    return client.post(f"/sessions/{sid}/{route}", json=body, headers=auth_header())


@pytest.mark.parametrize(("route", "body", "kind", "call"), [REPLY, OPTIONS])
def test_upper_case_path_id_resumes_the_canonical_thread(client, backend, route, body, kind, call):
    backend.sessions.seed(USER_A, T1, status="awaiting_input", awaiting_kind=kind)
    r = _post(client, T1.upper(), route, body)
    assert r.status_code == 200
    resumed = [args for name, args, _ in backend.pipeline.calls if name == call]
    assert resumed and resumed[0][0] == T1
    assert backend.sessions.raw(T1)["status"] != "failed"


@pytest.mark.parametrize(("route", "body", "kind", "call"), [REPLY, OPTIONS])
def test_double_submit_resumes_once(client, backend, monkeypatch, route, body, kind, call):
    backend.sessions.seed(USER_A, T1, status="awaiting_input", awaiting_kind=kind)
    stale = backend.sessions.get(USER_A, T1)
    # The other request already won the transition; this one read the row before that.
    backend.sessions.raw(T1).update(status="running", awaiting_kind=None)
    monkeypatch.setattr(backend.sessions, "get", lambda *_a, **_k: stale)
    r = _post(client, T1, route, body)
    assert r.status_code == 400
    assert [n for n, _, _ in backend.pipeline.calls if n == call] == []
    assert backend.sessions.raw(T1)["status"] == "running"
