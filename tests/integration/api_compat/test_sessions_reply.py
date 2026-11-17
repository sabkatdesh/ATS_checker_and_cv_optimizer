import pytest

from app.domain.questions.schemas import GapQuestion
from app.pipeline.errors import NotAwaitingInput
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B


def _reply(client):
    return client.post("/sessions/t1/reply", json={"user_qna": "answers"}, headers=auth_header())


def _session(backend, status="awaiting_hitl", user=USER_A):
    backend.store.sessions["t1"] = {"thread_id": "t1", "user_id": user, "status": status}


def test_reply_404_403(client, backend):
    r = _reply(client)
    assert (r.status_code, r.json()) == (404, {"detail": "Session not found"})
    _session(backend, user=USER_B)
    r = _reply(client)
    assert (r.status_code, r.json()) == (403, {"detail": "Not your session"})


def test_reply_wrong_status_400(client, backend):
    _session(backend, status="running")
    r = _reply(client)
    assert r.status_code == 400
    assert r.json() == {"detail": "Session is not waiting for your input"}


def test_reply_ok_response(client, backend):
    _session(backend)
    r = _reply(client)
    assert r.status_code == 200
    assert r.json() == {"status": "resumed", "message": "Pipeline resumed. Keep polling /status"}
    assert ("resume", ("t1", "answers"), {}) in backend.pipeline.calls


def test_reply_then_cover_letter_options(client, backend):
    _session(backend)
    backend.pipeline.next_nodes = ["cover_letter_options"]
    _reply(client)
    assert backend.store.sessions["t1"]["status"] == "awaiting_cover_letter_options"


def test_reply_then_finalize(client, backend):
    _session(backend)
    backend.pipeline.result = {"eligible": True}
    _reply(client)
    assert backend.store.sessions["t1"]["status"] == "complete"


def test_reply_error(client, backend):
    _session(backend)
    backend.pipeline.error = RuntimeError("boom")
    r = _reply(client)
    assert r.status_code == 200
    assert backend.store.sessions["t1"]["status"] == "error"


def _post(client, body):
    return client.post("/sessions/t1/reply", json=body, headers=auth_header())


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"user_qna": ""}, ""),
        ({}, None),
        ({"skipped": True}, {"skipped": True}),
        ({"answers": {"q1": "x"}}, {"answers": {"q1": "x"}, "free_text": None}),
        ({"user_qna": "Q1: a\nA1: b"}, "Q1: a\nA1: b"),
    ],
)
def test_reply_forms_resume_and_complete(client, backend, body, expected):
    _session(backend)
    backend.pipeline.result = {"eligible": True}
    assert _post(client, body).status_code == 200
    assert ("resume", ("t1", expected), {}) in backend.pipeline.calls
    assert backend.store.sessions["t1"]["status"] == "complete"


def test_reply_not_awaited_marks_error(client, backend):
    _session(backend)
    backend.pipeline.error = NotAwaitingInput()
    assert _post(client, {"skipped": True}).status_code == 200
    assert backend.store.sessions["t1"]["status"] == "error"


def test_pause_stores_question_texts_as_gaps(client, backend):
    _session(backend)
    backend.pipeline.next_nodes = ["await_answers"]
    backend.pipeline.values = {"questions": [GapQuestion(id="q1", text="Kubernetes?")]}
    _post(client, {"skipped": True})
    assert backend.store.sessions["t1"]["gaps"] == ["Kubernetes?"]
