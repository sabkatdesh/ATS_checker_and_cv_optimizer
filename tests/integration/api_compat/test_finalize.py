"""Finalization is exercised through /sessions/start with a pipeline that ends immediately."""

from types import SimpleNamespace

from app.domain.ats.schemas import AtsMatch
from app.pipeline.state import RunOptions
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer

JD = (
    "About the role: we are hiring a senior Python engineer to join our team. "
    "Responsibilities include building backend services. Requirements: five years of experience, "
    "strong skills, remote friendly. Benefits and salary are competitive. Candidates should apply. "
) * 3
CV = {"full_name": "Test Person"}


def _run(client, backend, result, profile=None):
    backend.master_profiles.default[USER_A] = {
        "full_name": "Test Person",
        "email": "test@example.com",
        "education": [{"degree": "BSc"}],
        **(profile or {}),
    }
    backend.pipeline.next_nodes = []
    backend.pipeline.result = result
    r = client.post("/sessions/start", json={"job_description": JD}, headers=auth_header())
    assert r.status_code == 200
    tid = r.json()["thread_id"]
    status = client.get(f"/sessions/{tid}/status", headers=auth_header()).json()
    return tid, status


def _signed(tid, kind):
    return f"https://signed.test/renders/user-a/{tid}/{kind}.pdf?ttl=600"


def _eligible(**extra):
    return {
        "eligible": True,
        "ats": AtsMatch(applies=True, score=82),
        "eligibility": SimpleNamespace(score=70),
        "tailored_cv": CV,
        "domain": "tech",
        **extra,
    }


def test_ineligible(client, backend):
    result = {
        "eligible": False,
        "eligibility": SimpleNamespace(score=20),
        "tailored_cv": CV,
    }
    _, row = _run(client, backend, result)
    assert row["status"] == "ineligible"
    assert row["eligibility_score"] == 20
    assert backend.storage.objects == {}
    assert backend.renders.rows == {}
    assert FakePdfRenderer.calls == []
    assert backend.credits.ledger_rows == []


def test_complete_cv_only(client, backend):
    tid, row = _run(client, backend, _eligible())
    assert row["status"] == "complete"
    assert row["ats_score"] == 82
    assert row["eligibility_score"] == 70
    assert row["pdf_url"] == _signed(tid, "cv")
    assert row["domain"] == "tech"
    assert row["cover_letter_text"] is None
    assert row["cover_letter_pdf_url"] is None
    assert FakePdfRenderer.calls == [
        (
            "render",
            (CV,),
            {
                "template_id": "classic",
                "accent_color": "#4361ee",
                "bangla": False,
                "domain": "tech",
            },
        )
    ]
    assert backend.credits.ledger_rows == []  # generation is free until M5


def test_complete_records_a_render_row_keyed_by_content_hash(client, backend):
    import hashlib

    tid, _ = _run(client, backend, _eligible())
    stored = backend.sessions.raw(tid)
    render = backend.renders.rows[stored["current_render_id"]]
    data, _ = backend.storage.objects[("renders", f"user-a/{tid}/cv.pdf")]
    assert render["content_hash"] == hashlib.sha256(data).hexdigest()
    assert (render["user_id"], render["session_id"]) == (USER_A, tid)
    assert render["pdf_path"] == f"user-a/{tid}/cv.pdf"
    assert render["template_id"] == "classic"


def test_complete_uses_profile_template(client, backend):
    _run(
        client,
        backend,
        _eligible(),
        profile={
            "preferred_template": "modern",
            "accent_color": "#000000",
            "bangla_mode": True,
        },
    )
    assert FakePdfRenderer.calls[0][2] == {
        "template_id": "modern",
        "accent_color": "#000000",
        "bangla": True,
        "domain": "tech",
    }


def test_complete_with_cover_letter(client, backend):
    tid, row = _run(
        client,
        backend,
        _eligible(
            cover_letter={"body": "x"},
            options=RunOptions(cover_letter=True, cover_letter_tone="conversational"),
        ),
    )
    render = [c for c in FakeCoverLetterRenderer.calls if c[0] == "render_to_pdf"][0]
    assert render[2]["tone"] == "conversational"
    assert render[2]["candidate_name"] == "Test Person"
    assert row["status"] == "complete"
    assert row["cover_letter_text"] == "PLAIN COVER LETTER"
    assert row["cover_letter_pdf_url"] == _signed(tid, "cover_letter")
    markers = sorted(r["template_id"] for r in backend.renders.rows.values())
    assert markers == ["classic", "cover_letter"]


def test_pdf_failure_still_completes(client, backend):
    FakePdfRenderer.raise_on_render = RuntimeError("render failed")
    _, row = _run(client, backend, _eligible())
    assert row["status"] == "complete"
    assert row["pdf_url"] is None


def test_no_structured_cv_completes_without_pdf(client, backend):
    result = _eligible()
    del result["tailored_cv"]
    _, row = _run(client, backend, result)
    assert row["status"] == "complete"
    assert row["pdf_url"] is None
    assert FakePdfRenderer.calls == []


def test_requested_but_skipped_cover_letter_completes_with_cv_only(client, backend):
    from app.pipeline.warnings import PipelineWarning

    tid, row = _run(
        client,
        backend,
        _eligible(
            cover_letter=None,
            options=RunOptions(cover_letter=True, cover_letter_tone="formal"),
            warnings=[PipelineWarning(code="COVER_LETTER_SKIPPED", step="cover_letter")],
        ),
    )
    assert row["status"] == "complete"
    assert row["pdf_url"] == _signed(tid, "cv")
    assert [c[0] for c in FakePdfRenderer.calls] == ["render"]
    assert FakeCoverLetterRenderer.calls == []
    assert row["cover_letter_text"] is None and row["cover_letter_pdf_url"] is None
