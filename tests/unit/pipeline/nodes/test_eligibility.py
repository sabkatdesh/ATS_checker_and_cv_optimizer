import json

import pytest

from app.domain.ats.schemas import compute_ats
from app.domain.cv.domain_config import Domain
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.deterministic import deterministic_eligibility
from app.domain.match.schemas import Eligibility
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.nodes.eligibility import eligibility
from app.pipeline.warnings import PipelineWarning
from app.ports.llm_errors import LLMOutputInvalid, LLMRefused
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run, tech_jd


def _state(cv_domain: str = "tech", jd_domain: str = "tech") -> dict:
    cv = persona_cv().model_copy(update={"domain": Domain(cv_domain)})
    jd = JobDescriptionStructured(domain=jd_domain, job_title="Engineer")
    return {"source_cv": cv, "jd": jd}


def test_eligibility_scores_and_sends_json_blocks():
    verdict = Eligibility(score=60, gaps=["Kubernetes"])
    gw, deps = deps_for({"eligibility": [verdict]})
    state = {"source_cv": persona_cv(), "jd": tech_jd()}
    out = run(eligibility(state, deps=deps, ctx=ctx()))
    assert out == {"domain": "tech", "eligibility": verdict, "eligible": True}
    content = gw.requests[0].messages[0].content
    assert "<job_requirements>\n" + state["jd"].model_dump_json() in content
    assert "<cv>\n" + state["source_cv"].model_dump_json() in content
    assert json.loads(state["jd"].model_dump_json())["job_title"] == "Backend Engineer"


def test_eligibility_threshold_boundary():
    _, deps = deps_for({"eligibility": [Eligibility(score=30)]}, eligibility_threshold=30)
    assert run(eligibility(_state(), deps=deps, ctx=ctx()))["eligible"] is True
    _, deps = deps_for({"eligibility": [Eligibility(score=30)]}, eligibility_threshold=31)
    assert run(eligibility(_state(), deps=deps, ctx=ctx()))["eligible"] is False


def test_domain_cv_wins_then_jd_then_general():
    for cv_d, jd_d, want in [
        ("medical", "tech", "medical"),
        ("general", "finance", "finance"),
        ("general", "general", "general"),
    ]:
        gw, deps = deps_for({"eligibility": [Eligibility(score=60)]})
        out = run(eligibility(_state(cv_d, jd_d), deps=deps, ctx=ctx()))
        assert out["domain"] == want
        assert f"Profession domain: {want}." in gw.requests[0].messages[0].content


def test_eligibility_invalid_uses_deterministic():
    _, deps = deps_for({"eligibility": [LLMOutputInvalid("x")]})
    state = {"source_cv": persona_cv(), "jd": tech_jd()}
    out = run(eligibility(state, deps=deps, ctx=ctx()))
    must_have = compute_ats(state["jd"], state["source_cv"]).breakdown["must_have"]
    assert out["eligibility"].score == round(must_have.score)
    assert out["eligibility"].rationale == ["Estimated from the job's listed requirements."]
    assert out["eligible"] is (out["eligibility"].score >= 30)
    assert out["warnings"] == [
        PipelineWarning(code="ELIGIBILITY_DETERMINISTIC", step="eligibility")
    ]


def test_deterministic_eligibility_without_must_haves_uses_the_ats_score():
    jd = tech_jd()
    jd = jd.model_copy(
        update={"requirements": jd.requirements.model_copy(update={"must_have": []})}
    )
    cv = persona_cv()
    assert deterministic_eligibility(jd, cv).score == round(compute_ats(jd, cv).score or 0)


def test_eligibility_refusal_still_fails_the_job():
    _, deps = deps_for({"eligibility": [LLMRefused("x")]})
    state = {"source_cv": persona_cv(), "jd": tech_jd()}
    with pytest.raises(PipelineStepFailed) as exc:
        run(eligibility(state, deps=deps, ctx=ctx()))
    assert (exc.value.step, exc.value.code) == ("eligibility", "CONTENT_REFUSED")


def test_eligibility_prompt_version_3_recorded():
    gw, deps = deps_for({"eligibility": [Eligibility(score=60)]})
    run(eligibility(_state(), deps=deps, ctx=ctx()))
    assert gw.requests[0].metadata.prompt_version == 3
    assert gw.requests[0].output_schema is Eligibility
