"""The rebuilt graph end to end on a scripted gateway, through PipelineService."""

import warnings

import pytest

from app.adapters.llm.fake import DEFAULT_DIR
from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.jd.schemas import JDSkillBlock, JobDescriptionStructured
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapAnswers, GapQuestion, GapQuestions
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from tests.pipeline.helpers import deps_for, persona_answers, persona_cv, persona_jd_text, tech_jd
from tests.pipeline.scripted_gateway import Outcome, ScriptedGateway

QUESTIONS = GapQuestions(questions=[GapQuestion(id="q1", text="Kubernetes?")])


def _draft() -> RewrittenCV:
    return RewrittenCV.model_validate_json((DEFAULT_DIR / "rewrite.json").read_text("utf-8"))


def _script(eligibility: Eligibility, rewrites: int = 2, **extra: list[Outcome]) -> dict:
    return {
        "jd_extract": [tech_jd()],
        "cv_extract": [persona_cv()],
        "eligibility": [eligibility],
        "gap_questions": [QUESTIONS],
        "rewrite": [_draft() for _ in range(rewrites)],
        **extra,
    }


def _service(script: dict) -> tuple[ScriptedGateway, PipelineService]:
    gw, deps = deps_for(script)
    return gw, PipelineService(build_graph(deps, new_checkpointer()))


def _start(svc: PipelineService, options: RunOptions | None = None) -> dict:
    return svc.run(
        job_description=persona_jd_text(),
        user_resume_text="cv text",
        thread_id="t1",
        options=options or RunOptions(),
    )


ELIGIBLE = Eligibility(score=60, gaps=["Kubernetes"])


def test_happy_path():
    gw, svc = _service(_script(ELIGIBLE))
    _start(svc)
    state = svc.get_state("t1")
    assert state["next"] == ["await_answers"]
    assert state["interrupt"] == {
        "type": "gap_questions",
        "questions": [{"id": "q1", "text": "Kubernetes?"}],
    }
    final = svc.resume("t1", persona_answers().free_text)
    assert isinstance(final["tailored_cv"], RewrittenCV)
    assert final["answers"] == persona_answers()
    assert final["passes"] >= 1
    assert [r.step for r in gw.requests][:5] == [
        "jd_extract",
        "cv_extract",
        "eligibility",
        "gap_questions",
        "rewrite",
    ]
    assert svc.get_state("t1")["next"] == []
    assert svc.get_state("t1")["interrupt"] is None


def test_ineligible_ends_before_questions():
    gw, svc = _service(_script(Eligibility(score=10)))
    final = _start(svc)
    assert final["eligible"] is False
    steps = [r.step for r in gw.requests]
    assert "gap_questions" not in steps and "rewrite" not in steps
    assert svc.get_state("t1")["next"] == []


def test_rewrite_loop_cap():
    empty = [RewrittenCV() for _ in range(3)]
    hard_jd = tech_jd().model_copy(
        update={"skills": JDSkillBlock(hard_skills=["Rust", "Go"], tools=["Kafka"])}
    )
    gw, svc = _service({**_script(ELIGIBLE), "jd_extract": [hard_jd], "rewrite": list(empty)})
    _start(svc, RunOptions(max_passes=3))
    final = svc.resume("t1", "answers")
    assert (final["ats"].score or 0) < 90
    assert [r.step for r in gw.requests].count("rewrite") == 3
    assert final["passes"] == 3


def test_cover_letter_pause_then_resume():
    letter = CoverLetterStructured.model_validate_json(
        (DEFAULT_DIR / "cover_letter.json").read_text("utf-8")
    )
    gw, svc = _service(_script(ELIGIBLE, cover_letter=[letter]))
    _start(svc, RunOptions(cover_letter=True))
    svc.resume("t1", "answers")
    state = svc.get_state("t1")
    assert state["next"] == ["cover_letter_options"]
    assert state["interrupt"] == {"type": "cover_letter_options"}
    final = svc.resume_cover_letter("t1", "conversational", "short")
    assert final["cover_letter"] == letter
    assert final["options"].cover_letter_tone == "conversational"
    assert "Length: short (about 150 words" in gw.requests[-1].messages[0].content


def test_state_round_trips_checkpointer(recwarn: pytest.WarningsRecorder):
    warnings.simplefilter("always")
    _, svc = _service(_script(ELIGIBLE))
    _start(svc)
    svc.resume("t1", "answers")
    values = svc.get_state("t1")["values"]
    assert isinstance(values["jd"], JobDescriptionStructured)
    assert isinstance(values["answers"], GapAnswers)
    assert isinstance(values["options"], RunOptions)
    assert isinstance(values["questions"][0], GapQuestion)
    assert [str(w.message) for w in recwarn] == []


def test_summary_reports_jd_meta_and_scores():
    _, svc = _service(_script(ELIGIBLE))
    assert svc.summary("t1") is None
    _start(svc)
    svc.resume("t1", "answers")
    summary = svc.summary("t1")
    assert summary is not None
    assert summary.jd is not None and summary.jd.job_title == "Backend Engineer"
    assert summary.jd.company_name == "Example Company" and summary.jd.domain == "tech"
    assert summary.domain == "tech" and summary.eligibility_score == 60
    assert isinstance(summary.ats_before, int) and isinstance(summary.ats_after, int)
    assert summary.warnings == []
