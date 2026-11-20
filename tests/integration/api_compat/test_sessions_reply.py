import pytest

from app.domain.questions.schemas import GapQuestion
from app.pipeline.errors import NotAwaitingInput
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B

T1 = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"


def _reply(client):
    return client.post(f"/sessions/{T1}/reply", json={"user_qna": "answers"}, headers=auth_header())


def _session(backend, status="awaiting_input", user=USER_A, kind="questions"):
    backend.sessions.seed(user, T1, status=status, awaiting_kind=kind)


def _status(backend):
    return backend.sessions.raw(T1)["status"]


def test_reply_404_for_missing_and_foreign(client, backend):
    r = _reply(client)
    assert (r.status_code, r.json()) == (404, {"detail": "Session not found"})
    _session(backend, user=USER_B)
    r = _reply(client)
    assert (r.status_code, r.json()) == (404, {"detail": "Session not found"})
    assert backend.pipeline.calls == []


@pytest.mark.parametrize(
    ("status", "kind"), [("running", None), ("awaiting_input", "cover_letter_options")]
)
def test_reply_wrong_status_400(client, backend, status, kind):
    _session(backend, status=status, kind=kind)
    r = _reply(client)
    assert r.status_code == 400
    assert r.json() == {"detail": "Session is not waiting for your input"}


def test_reply_ok_response(client, backend):
    _session(backend)
    r = _reply(client)
    assert r.status_code == 200
    assert r.json() == {"status": "resumed", "message": "Pipeline resumed. Keep polling /status"}
    assert ("resume", (T1, "answers"), {}) in backend.pipeline.calls


def test_reply_then_cover_letter_options(client, backend):
    _session(backend)
    backend.pipeline.next_nodes = ["cover_letter_options"]
    _reply(client)
    row = backend.sessions.raw(T1)
    assert (row["status"], row["awaiting_kind"]) == ("awaiting_input", "cover_letter_options")


def test_reply_then_finalize(client, backend):
    _session(backend)
    backend.pipeline.result = {"eligible": True}
    _reply(client)
    assert _status(backend) == "succeeded"


def test_reply_error(client, backend):
    _session(backend)
    backend.pipeline.error = RuntimeError("boom")
    r = _reply(client)
    assert r.status_code == 200
    assert _status(backend) == "failed"


def _post(client, body):
    return client.post(f"/sessions/{T1}/reply", json=body, headers=auth_header())


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
    assert ("resume", (T1, expected), {}) in backend.pipeline.calls
    assert _status(backend) == "succeeded"


def test_reply_not_awaited_marks_error(client, backend):
    _session(backend)
    backend.pipeline.error = NotAwaitingInput()
    assert _post(client, {"skipped": True}).status_code == 200
    assert _status(backend) == "failed"


def test_pause_stores_question_texts_as_gaps(client, backend):
    _session(backend)
    backend.pipeline.next_nodes = ["await_answers"]
    backend.pipeline.values = {"questions": [GapQuestion(id="q1", text="Kubernetes?")]}
    _post(client, {"skipped": True})
    row = backend.sessions.raw(T1)
    assert (row["status"], row["awaiting_kind"]) == ("awaiting_input", "questions")
    assert row["score_breakdown"]["gaps"] == ["Kubernetes?"]
    status = client.get(f"/sessions/{T1}/status", headers=auth_header()).json()
    assert (status["status"], status["gaps"]) == ("awaiting_hitl", ["Kubernetes?"])
