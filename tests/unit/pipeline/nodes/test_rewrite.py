from app.domain.cv.rewrite import RewrittenCV
from app.domain.questions.schemas import GapAnswers
from app.pipeline.nodes.rewrite import rewrite
from app.pipeline.prompts.domain_guidance import get_domain_guidance
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run, tech_jd


def _state(**extra) -> dict:
    return {"domain": "tech", "jd": tech_jd(), "source_cv": persona_cv(), "passes": 0, **extra}


def test_rewrite_first_pass_blocks_and_budget():
    draft = RewrittenCV(professional_summary="new")
    gw, deps = deps_for({"rewrite": [draft]})
    state = _state(answers=GapAnswers(free_text="k8s for a year"))
    out = run(rewrite(state, deps=deps, ctx=ctx()))
    assert out == {"tailored_cv": draft, "passes": 1}
    req = gw.requests[0]
    assert req.output_schema is RewrittenCV
    assert req.cache_prefix is True
    content = req.messages[0].content
    assert "<cv>\n" + state["source_cv"].model_dump_json() + "\n</cv>" in content
    assert "<job_requirements>\n" + state["jd"].model_dump_json() in content
    assert "<answers>\nk8s for a year\n</answers>" in content
    assert "<previous_draft>\n" not in content
    # tech with 4 years is the mid_senior budget tier
    assert "about 1000 words" in content
    assert "at most 5 work experience roles, 22 hard skills, 2 projects, 0 publications" in content
    assert get_domain_guidance("tech") in content


def test_rewrite_second_pass_sends_previous_draft_without_empty_answers():
    first = RewrittenCV(professional_summary="first")
    second = RewrittenCV(professional_summary="second")
    gw, deps = deps_for({"rewrite": [second]})
    state = _state(passes=1, tailored_cv=first, answers=GapAnswers(free_text=""))
    out = run(rewrite(state, deps=deps, ctx=ctx()))
    assert out == {"tailored_cv": second, "passes": 2}
    content = gw.requests[0].messages[0].content
    assert "<previous_draft>\n" + first.model_dump_json() + "\n</previous_draft>" in content
    assert "<answers>\n" not in content
