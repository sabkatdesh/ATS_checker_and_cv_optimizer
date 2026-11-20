import uuid
from types import SimpleNamespace

from app.domain.parsing.input_validator import validate_jd
from app.domain.questions.schemas import GapQuestion
from app.pipeline.state import RunOptions
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A

JD = (
    "About the role: we are hiring a senior Python engineer to join our team. "
    "Responsibilities include building backend services. Requirements: five years of experience, "
    "strong skills, remote friendly. Benefits and salary are competitive. Candidates should apply. "
) * 3


def _start(client, **body):
    return client.post(
        "/sessions/start", json={"job_description": JD, **body}, headers=auth_header()
    )


COMPLETE = {
    "user_id": USER_A,
    "full_name": "Test Person",
    "email": "test@example.com",
    "education": [{"degree": "BSc", "institution": "Example University"}],
}


def _ready(backend, profile=None):
    backend.master_profiles.upsert_default(USER_A, profile or dict(COMPLETE))


def _row(backend, r):
    return backend.sessions.raw(r.json()["thread_id"])


def _creates(backend):
    return [c for c in backend.sessions.calls if c[0] == "create"]


def test_invalid_jd_400_before_profile_check(client):
    r = client.post("/sessions/start", json={"job_description": "too short"}, headers=auth_header())
    assert r.status_code == 400
    assert r.json() == {"detail": validate_jd("too short").user_message}


def test_no_profile_400(client):
    r = _start(client)
    assert r.status_code == 400
    assert r.json() == {"detail": "Please complete your profile first before generating a CV"}


def test_start_needs_no_credits_while_generation_is_free(client, backend):
    _ready(backend)
    assert backend.credits.balance(USER_A) == (0, 0)
    assert _start(client).status_code == 200


def test_start_response_shape(client, backend):
    _ready(backend)
    r = _start(client)
    assert r.status_code == 200
    body = r.json()
    assert uuid.UUID(body["thread_id"]).version == 7
    assert backend.sessions.get(USER_A, body["thread_id"]) is not None
    assert body["status"] == "running"
    assert body["message"] == (
        "CV generation started. Poll /sessions/{thread_id}/status to check progress."
    )


def test_start_creates_session_with_cover_letter_args(client, backend):
    _ready(backend)
    r = _start(client, cover_letter=True, cover_letter_tone="formal", cover_letter_length="short")
    (_, args, kwargs), *_ = _creates(backend)
    assert args == (USER_A, r.json()["thread_id"])
    assert kwargs == {
        "jd_text": JD,
        "source_cv": {k: v for k, v in COMPLETE.items() if k != "user_id"},
        "options": {
            "cover_letter": True,
            "cover_letter_tone": "formal",
            "cover_letter_length": "short",
        },
        "template_id": "classic",
    }


def test_start_pauses_at_hitl(client, backend):
    _ready(backend)
    backend.pipeline.next_nodes = ["await_answers"]
    backend.pipeline.values = {
        "questions": [GapQuestion(id="q1", text="g1")],
        "eligibility": SimpleNamespace(score=55),
    }
    row = _row(backend, _start(client))
    assert (row["status"], row["awaiting_kind"]) == ("awaiting_input", "questions")
    assert row["score_breakdown"] == {"eligibility_score": 55, "gaps": ["g1"]}


def test_start_pauses_for_cover_letter_options(client, backend):
    _ready(backend)
    backend.pipeline.next_nodes = ["cover_letter_options"]
    row = _row(backend, _start(client))
    assert (row["status"], row["awaiting_kind"]) == ("awaiting_input", "cover_letter_options")


def test_start_pipeline_error_sets_error(client, backend):
    _ready(backend)
    backend.pipeline.error = RuntimeError("boom")
    r = _start(client)
    assert r.status_code == 200
    assert _row(backend, r)["status"] == "failed"


def test_start_passes_the_profile_dict_to_pipeline(client, backend):
    _ready(backend)
    _start(client)
    name, _, kwargs = backend.pipeline.calls[0]
    assert name == "run"
    assert kwargs["profile"] == backend.master_profiles.get_default(USER_A)
    assert "user_resume_text" not in kwargs


def test_incomplete_profile_is_422_before_session(client, backend):
    _ready(backend, profile={"user_id": USER_A, "full_name": "Test Person"})
    r = _start(client)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "PROFILE_INCOMPLETE"
    assert body["missing"] == ["CONTACT", "EXPERIENCE_OR_EDUCATION"]
    assert "Test Person" not in r.text
    assert backend.sessions.rows == {}
    assert _creates(backend) == []
    assert backend.pipeline.calls == []


def test_incomplete_profile_without_a_name_is_422(client, backend):
    _ready(backend, profile={"user_id": USER_A, "email": "test@example.com"})
    r = _start(client)
    assert r.status_code == 422
    assert r.json()["missing"] == ["NAME", "EXPERIENCE_OR_EDUCATION"]


def test_start_builds_run_options(client, backend):
    _ready(backend)
    _start(client, cover_letter=True, cover_letter_tone="casual", cover_letter_length="short")
    options = backend.pipeline.calls[0][2]["options"]
    assert options == RunOptions(
        cover_letter=True, cover_letter_tone=None, cover_letter_length="short", max_passes=2
    )


def test_zero_width_name_is_422_before_session(client, backend):
    _ready(backend, profile={**COMPLETE, "full_name": "​‌⁠﻿"})
    r = _start(client)
    assert r.status_code == 422
    assert r.json()["code"] == "PROFILE_INCOMPLETE"
    assert r.json()["missing"] == ["NAME"]
    assert backend.sessions.rows == {}
    assert _creates(backend) == []
