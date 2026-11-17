import traceback

import pytest

from app.domain.ats.checker import compute_final_match
from app.domain.cv.rewrite import RewrittenCV
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.nodes.ats_score import ats_score
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run, tech_jd


def test_ats_score_first_call_sets_before_and_current():
    _, deps = deps_for({})
    state = {"domain": "tech", "jd": tech_jd(), "source_cv": persona_cv()}
    out = run(ats_score(state, deps=deps, ctx=ctx()))
    expected = compute_final_match(state["jd"], state["source_cv"])
    assert out == {"ats": expected, "ats_before": expected}


def test_ats_score_later_call_scores_tailored_cv_and_keeps_before():
    _, deps = deps_for({})
    tailored = RewrittenCV.model_validate(persona_cv().model_dump(include={"domain", "meta"}))
    state = {
        "domain": "tech",
        "jd": tech_jd(),
        "source_cv": persona_cv(),
        "tailored_cv": tailored,
        "ats_before": {"overall_score": 1},
    }
    out = run(ats_score(state, deps=deps, ctx=ctx()))
    assert out == {"ats": compute_final_match(state["jd"], tailored)}


def test_ats_score_non_ats_domain_is_simplified():
    _, deps = deps_for({})
    state = {"domain": "medical", "jd": tech_jd(), "source_cv": persona_cv("nurse_icu")}
    out = run(ats_score(state, deps=deps, ctx=ctx()))
    assert out["ats"]["overall_score"] == 100
    assert out["ats"]["section_scores"] == {}
    assert out["ats_before"] == out["ats"]


def test_scorer_exception_surfaces_as_internal_failure(monkeypatch):
    def boom(jd, cv):
        raise ValueError("SENTINEL secret cv text")

    monkeypatch.setattr("app.pipeline.nodes.ats_score.compute_final_match", boom)
    _, deps = deps_for({})
    state = {"domain": "tech", "jd": tech_jd(), "source_cv": persona_cv()}
    with pytest.raises(PipelineStepFailed) as exc:
        run(ats_score(state, deps=deps, ctx=ctx()))
    assert (exc.value.step, exc.value.code) == ("ats_score", "INTERNAL")
    assert "SENTINEL" not in "".join(traceback.format_exception(exc.value))
