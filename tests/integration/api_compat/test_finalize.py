"""Finalization is exercised through /sessions/start with a pipeline that ends immediately."""
from types import SimpleNamespace

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
    backend.store.profiles[USER_A] = {"user_id": USER_A, "full_name": "Test Person", **(profile or {})}
    backend.pipeline.next_nodes = []
    backend.pipeline.result = result
    r = client.post("/sessions/start", json={"job_description": JD}, headers=auth_header())
    assert r.status_code == 200
    tid = r.json()["thread_id"]
    return tid, backend.store.sessions[tid]


def _eligible(**extra):
    return {
        "is_eligible": True, "final_match": {"overall_score": 82},
        "eligibility_verdict": SimpleNamespace(score=70), "structured_cv": CV,
        "detected_domain": "tech", **extra,
    }


def test_ineligible(client, backend):
    result = {"is_eligible": False, "eligibility_verdict": SimpleNamespace(score=20), "structured_cv": CV}
    _, row = _run(client, backend, result)
    assert row["status"] == "ineligible"
    assert row["eligibility_score"] == 20
    assert backend.store.uploads == []
    assert FakePdfRenderer.calls == []
    assert not [c for c in backend.store.calls if c[0] == "deduct_coins"]


def test_complete_cv_only(client, backend):
    tid, row = _run(client, backend, _eligible())
    assert row["status"] == "complete"
    assert row["ats_score"] == 82
    assert row["eligibility_score"] == 70
    assert row["pdf_url"] == f"https://storage.test/user-a/{tid}.pdf"
    assert row["cover_letter_text"] is None
    assert row["cover_letter_pdf_url"] is None
    assert FakePdfRenderer.calls == [("render", (CV,), {
        "template_id": "classic", "accent_color": "#4361ee", "bangla": False, "domain": "tech",
    })]
    deducts = [c for c in backend.store.calls if c[0] == "deduct_coins"]
    assert [c[1] for c in deducts] == [(USER_A, 0, f"CV generation - thread {tid}")]


def test_complete_uses_profile_template(client, backend):
    _run(client, backend, _eligible(), profile={
        "preferred_template": "modern", "accent_color": "#000000", "bangla_mode": True,
    })
    assert FakePdfRenderer.calls[0][2] == {
        "template_id": "modern", "accent_color": "#000000", "bangla": True, "domain": "tech",
    }


def test_complete_with_cover_letter(client, backend):
    tid, row = _run(client, backend, _eligible(
        cover_letter_result={"body": "x"}, cover_letter_tone="conversational",
    ))
    render = [c for c in FakeCoverLetterRenderer.calls if c[0] == "render_to_pdf"][0]
    assert render[2]["tone"] == "conversational"
    assert render[2]["candidate_name"] == "Test Person"
    assert row["status"] == "complete"
    assert row["cover_letter_text"] == "PLAIN COVER LETTER"
    assert row["cover_letter_pdf_url"].endswith(f"/{tid}_cover_letter.pdf")


def test_pdf_failure_still_completes(client, backend):
    FakePdfRenderer.raise_on_render = RuntimeError("render failed")
    _, row = _run(client, backend, _eligible())
    assert row["status"] == "complete"
    assert row["pdf_url"] is None


def test_no_structured_cv_completes_without_pdf(client, backend):
    result = _eligible()
    del result["structured_cv"]
    _, row = _run(client, backend, result)
    assert row["status"] == "complete"
    assert row["pdf_url"] is None
    assert FakePdfRenderer.calls == []
