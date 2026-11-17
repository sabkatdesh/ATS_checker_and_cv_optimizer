import json

from app.domain.cv.domain_config import Domain
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import Match
from app.pipeline.nodes.eligibility import eligibility
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run, tech_jd


def _state(cv_domain: str = "tech", jd_domain: str = "tech") -> dict:
    cv = persona_cv().model_copy(update={"domain": Domain(cv_domain)})
    jd = JobDescriptionStructured(domain=jd_domain, job_title="Engineer")
    return {"source_cv": cv, "jd": jd}


def test_eligibility_scores_and_sends_json_blocks():
    verdict = Match(score=60, gaps_to_consider=["Kubernetes"])
    gw, deps = deps_for({"eligibility": [verdict]})
    state = {"source_cv": persona_cv(), "jd": tech_jd()}
    out = run(eligibility(state, deps=deps, ctx=ctx()))
    assert out == {"domain": "tech", "eligibility": verdict, "eligible": True}
    content = gw.requests[0].messages[0].content
    assert "<job_requirements>\n" + state["jd"].model_dump_json() in content
    assert "<cv>\n" + state["source_cv"].model_dump_json() in content
    assert json.loads(state["jd"].model_dump_json())["job_title"] == "Backend Engineer"


def test_eligibility_threshold_boundary():
    _, deps = deps_for({"eligibility": [Match(score=30)]}, eligibility_threshold=30)
    assert run(eligibility(_state(), deps=deps, ctx=ctx()))["eligible"] is True
    _, deps = deps_for({"eligibility": [Match(score=30)]}, eligibility_threshold=31)
    assert run(eligibility(_state(), deps=deps, ctx=ctx()))["eligible"] is False


def test_eligibility_missing_score_is_ineligible():
    _, deps = deps_for({"eligibility": [Match()]})
    assert run(eligibility(_state(), deps=deps, ctx=ctx()))["eligible"] is False


def test_domain_cv_wins_then_jd_then_general():
    for cv_d, jd_d, want in [
        ("medical", "tech", "medical"),
        ("general", "finance", "finance"),
        ("general", "general", "general"),
    ]:
        gw, deps = deps_for({"eligibility": [Match(score=60)]})
        out = run(eligibility(_state(cv_d, jd_d), deps=deps, ctx=ctx()))
        assert out["domain"] == want
        assert f"Profession domain: {want}." in gw.requests[0].messages[0].content
