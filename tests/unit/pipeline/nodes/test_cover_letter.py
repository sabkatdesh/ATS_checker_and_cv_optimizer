import pytest

from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.nodes.cover_letter import cover_letter
from app.pipeline.state import RunOptions
from app.pipeline.warnings import PipelineWarning
from app.ports.llm_errors import LLMOutputInvalid, LLMRefused, LLMUnavailable
from tests.pipeline.helpers import ctx, deps_for, run, tech_jd

LETTER = CoverLetterStructured(
    salutation="Dear Hiring Manager,",
    opening_paragraph="Hook.",
    body_paragraphs=["Body."],
    closing_paragraph="Close.",
    sign_off="Sincerely,",
)


def _state(length: str) -> dict:
    opts = RunOptions(cover_letter=True, cover_letter_tone="formal", cover_letter_length=length)
    return {"options": opts, "jd": tech_jd(), "tailored_cv": RewrittenCV(professional_summary="x")}


def test_cover_letter_uses_tailored_cv_and_options():
    gw, deps = deps_for({"cover_letter": [LETTER]})
    state = _state("short")
    out = run(cover_letter(state, deps=deps, ctx=ctx()))
    assert out == {"cover_letter": LETTER}
    req = gw.requests[0]
    assert req.output_schema is CoverLetterStructured
    content = req.messages[0].content
    cv_json = state["tailored_cv"].model_dump_json(exclude={"change_log", "gaps_unaddressed"})
    assert "<cv>\n" + cv_json + "\n</cv>" in content
    assert "<gaps>" not in content
    assert "<job_requirements>\n" + state["jd"].model_dump_json() in content
    assert "Tone: formal. Length: short (about 150 words" in content


def test_cover_letter_standard_length_targets_300_words():
    gw, deps = deps_for({"cover_letter": [LETTER]})
    run(cover_letter(_state("standard"), deps=deps, ctx=ctx()))
    assert "about 300 words" in gw.requests[0].messages[0].content


def test_cover_letter_invalid_skips():
    _, deps = deps_for({"cover_letter": [LLMOutputInvalid("x")]})
    out = run(cover_letter(_state("short"), deps=deps, ctx=ctx()))
    assert out == {
        "cover_letter": None,
        "warnings": [PipelineWarning(code="COVER_LETTER_SKIPPED", step="cover_letter")],
    }


def test_cover_letter_unavailable_skips():
    _, deps = deps_for({"cover_letter": [LLMUnavailable("x")]})
    out = run(cover_letter(_state("short"), deps=deps, ctx=ctx()))
    assert out["cover_letter"] is None and out["warnings"][0].code == "COVER_LETTER_SKIPPED"


def test_cover_letter_refusal_fails_the_job():
    _, deps = deps_for({"cover_letter": [LLMRefused("x")]})
    with pytest.raises(PipelineStepFailed) as exc:
        run(cover_letter(_state("short"), deps=deps, ctx=ctx()))
    assert exc.value.code == "CONTENT_REFUSED"


def test_cover_letter_sends_unaddressed_gaps_and_records_version_2():
    gw, deps = deps_for({"cover_letter": [LETTER]})
    state = _state("short")
    state["tailored_cv"] = RewrittenCV(gaps_unaddressed=["Kubernetes", "Go"])
    run(cover_letter(state, deps=deps, ctx=ctx()))
    req = gw.requests[0]
    assert "<gaps>\n- Kubernetes\n- Go\n</gaps>" in req.messages[0].content
    assert req.metadata.prompt_version == 3


def test_cover_letter_drops_invented_contacts_and_markup():
    letter = LETTER.model_copy(update={"body_paragraphs": ["**Hire** me at https://evil.example."]})
    _, deps = deps_for({"cover_letter": [letter]})
    out = run(cover_letter(_state("short"), deps=deps, ctx=ctx()))
    assert out["cover_letter"].body_paragraphs == ["Hire me at."]
    assert out["warnings"] == [PipelineWarning(code="FOREIGN_CONTACT_REMOVED", step="cover_letter")]
