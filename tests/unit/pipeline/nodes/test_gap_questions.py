import pytest

from app.domain.match.schemas import Match
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.nodes.gap_questions import gap_questions
from app.pipeline.warnings import PipelineWarning
from app.ports.llm_errors import LLMOutputInvalid, LLMRefused, LLMUnavailable
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run, tech_jd


def test_gap_questions_asks_about_eligibility_gaps():
    qs = GapQuestions(questions=[GapQuestion(id="q1", text="Kubernetes?")])
    gw, deps = deps_for({"gap_questions": [qs]})
    state = {
        "source_cv": persona_cv(),
        "jd": tech_jd(),
        "eligibility": Match(score=60, gaps_to_consider=["Kubernetes", "Go"]),
    }
    out = run(gap_questions(state, deps=deps, ctx=ctx()))
    assert out == {"questions": qs.questions}
    req = gw.requests[0]
    assert req.output_schema is GapQuestions
    content = req.messages[0].content
    assert "<gaps>\n- Kubernetes\n- Go\n</gaps>" in content
    assert "<cv>\n" in content and "<job_requirements>\n" in content
    assert "up to 5 short questions" in content


def test_gap_questions_without_gaps_skips_the_call():
    gw, deps = deps_for({})
    state = {"source_cv": persona_cv(), "jd": tech_jd(), "eligibility": Match(score=60)}
    assert run(gap_questions(state, deps=deps, ctx=ctx())) == {"questions": []}
    assert gw.requests == []


def _state() -> dict:
    return {
        "source_cv": persona_cv(),
        "jd": tech_jd(),
        "eligibility": Match(score=60, gaps_to_consider=["Kubernetes"]),
    }


def test_gap_questions_invalid_skips_with_warning():
    _, deps = deps_for({"gap_questions": [LLMOutputInvalid("x")]})
    out = run(gap_questions(_state(), deps=deps, ctx=ctx()))
    assert out == {
        "questions": [],
        "warnings": [PipelineWarning(code="QUESTIONS_SKIPPED", step="gap_questions")],
    }


def test_gap_questions_refusal_fails_the_job():
    _, deps = deps_for({"gap_questions": [LLMRefused("x")]})
    with pytest.raises(PipelineStepFailed) as exc:
        run(gap_questions(_state(), deps=deps, ctx=ctx()))
    assert (exc.value.step, exc.value.code) == ("gap_questions", "CONTENT_REFUSED")


def test_gap_questions_unavailable_fails_the_job():
    _, deps = deps_for({"gap_questions": [LLMUnavailable("x")]})
    with pytest.raises(PipelineStepFailed) as exc:
        run(gap_questions(_state(), deps=deps, ctx=ctx()))
    assert exc.value.code == "LLM_UNAVAILABLE"
