import pytest

from app.domain.ats.schemas import AtsMatch, SectionScore, compute_ats, non_ats_match
from app.domain.cv.rewrite import RewrittenCV
from app.domain.questions.schemas import GapAnswers
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.nodes.rewrite import rewrite
from app.pipeline.prompts.domain_guidance import get_domain_guidance
from app.pipeline.warnings import PipelineWarning
from app.ports.llm_errors import LLMRefused
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run, tech_jd


def _state(**extra) -> dict:
    return {"domain": "tech", "jd": tech_jd(), "source_cv": persona_cv(), "passes": 0, **extra}


def test_rewrite_first_pass_blocks_and_budget():
    draft = RewrittenCV(professional_summary="new")
    gw, deps = deps_for({"rewrite": [draft]})
    state = _state(answers=GapAnswers(free_text="k8s for a year"))
    out = run(rewrite(state, deps=deps, ctx=ctx()))
    assert out["passes"] == 1
    assert out["tailored_cv"].professional_summary == "new"
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
    assert out["passes"] == 2 and out["tailored_cv"].professional_summary == "second"
    content = gw.requests[0].messages[0].content
    assert "<previous_draft>\n" + first.model_dump_json() + "\n</previous_draft>" in content
    assert "<answers>\n" not in content


def test_rewrite_refusal_fails_the_job():
    _, deps = deps_for({"rewrite": [LLMRefused("x")]})
    with pytest.raises(PipelineStepFailed) as exc:
        run(rewrite(_state(), deps=deps, ctx=ctx()))
    assert (exc.value.step, exc.value.code) == ("rewrite", "CONTENT_REFUSED")


def test_rewrite_request_has_no_missing_keyword_list():
    gw, deps = deps_for({"rewrite": [RewrittenCV()]})
    state = _state(ats=compute_ats(tech_jd(), persona_cv()))
    run(rewrite(state, deps=deps, ctx=ctx()))
    req = gw.requests[0]
    assert "keyword" not in req.messages[0].content.lower()
    assert "<ats_feedback>\n" not in req.messages[0].content
    assert "keyword" not in req.system.lower().replace("keyword stuffing", "")


def test_second_pass_sends_unevidenced_requirements_as_ats_feedback():
    first = RewrittenCV.model_validate(persona_cv().model_dump())
    ats = AtsMatch(
        applies=True,
        score=40,
        breakdown={
            "must_have": SectionScore(score=50, matched=["Python"], missing=["SQL"]),
            "skills": SectionScore(score=0, matched=[], missing=["Go", "SQL"]),
            "tools": SectionScore(score=0, matched=[], missing=["Kafka"]),
        },
        hard_gaps=["SQL"],
    )
    gw, deps = deps_for({"rewrite": [RewrittenCV()]})
    run(rewrite(_state(passes=1, tailored_cv=first, ats=ats), deps=deps, ctx=ctx()))
    content = gw.requests[0].messages[0].content
    assert "<ats_feedback>\n- SQL\n- Go\n- Kafka\n</ats_feedback>" in content
    assert "keyword" not in content.lower()


def test_second_pass_without_ats_applying_sends_no_feedback():
    first = RewrittenCV.model_validate(persona_cv().model_dump())
    gw, deps = deps_for({"rewrite": [RewrittenCV()]})
    run(rewrite(_state(passes=1, tailored_cv=first, ats=non_ats_match()), deps=deps, ctx=ctx()))
    assert "<ats_feedback>\n" not in gw.requests[0].messages[0].content


def test_rewrite_prompt_version_4_recorded():
    gw, deps = deps_for({"rewrite": [RewrittenCV()]})
    run(rewrite(_state(), deps=deps, ctx=ctx()))
    req = gw.requests[0]
    assert req.metadata.prompt_version == 4
    assert "gaps_unaddressed" in req.system and "change_log" in req.system
    assert "Never add employers, titles, dates, degrees, certifications, tools or skills" in (
        req.system
    )


def test_rewrite_restores_dropped_sections_with_a_warning():
    source = persona_cv()
    draft = RewrittenCV.model_validate(source.model_dump(exclude={"education", "certifications"}))
    _, deps = deps_for({"rewrite": [draft]})
    out = run(rewrite(_state(), deps=deps, ctx=ctx()))
    assert out["tailored_cv"].education == source.education
    assert out["tailored_cv"].certifications == source.certifications
    assert out["warnings"] == [PipelineWarning(code="SECTION_RESTORED", step="rewrite")]


def test_rewrite_keeping_every_section_has_no_warning():
    draft = RewrittenCV.model_validate(persona_cv().model_dump())
    _, deps = deps_for({"rewrite": [draft]})
    out = run(rewrite(_state(), deps=deps, ctx=ctx()))
    assert "warnings" not in out


def test_rewrite_prompt_asks_for_verbatim_identifying_fields():
    gw, deps = deps_for({"rewrite": [RewrittenCV()]})
    run(rewrite(_state(), deps=deps, ctx=ctx()))
    assert "copied verbatim" in gw.requests[0].system


def test_rewrite_removes_invented_contacts_and_markup_after_restore():
    source = persona_cv()
    draft = RewrittenCV.model_validate(source.model_dump(exclude={"education"}))
    role = draft.work_experience[0].model_copy(
        update={"responsibilities": ["**Built** REST services https://evil.example/apply"]}
    )
    draft = draft.model_copy(update={"work_experience": [role]})
    _, deps = deps_for({"rewrite": [draft]})
    out = run(rewrite(_state(), deps=deps, ctx=ctx()))
    cv = out["tailored_cv"]
    assert cv.work_experience[0].responsibilities == ["Built REST services"]
    assert cv.education == source.education
    assert out["warnings"] == [
        PipelineWarning(code="SECTION_RESTORED", step="rewrite"),
        PipelineWarning(code="FOREIGN_CONTACT_REMOVED", step="rewrite"),
    ]
