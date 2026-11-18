"""Gap questions through the real graph: one pause, empty or skipped replies proceed."""

import pytest
from langgraph.errors import GraphInterrupt

import app.pipeline.nodes.await_answers as await_mod
from app.domain.cv.rewrite import RewrittenCV
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.domain.trust.judge import JudgeFindings
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.errors import NotAwaitingInput
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from tests.pipeline.helpers import deps_for, persona_cv, persona_jd_text, tech_jd

ELIGIBLE = Eligibility(score=60, gaps=["Kubernetes"])
QUESTIONS = GapQuestions(
    questions=[GapQuestion(id="x", text="Kubernetes?"), GapQuestion(id="y", text="Go?")]
)


def _service(questions: GapQuestions = QUESTIONS, eligibility: Eligibility = ELIGIBLE):
    gw, deps = deps_for(
        {
            "jd_extract": [tech_jd()],
            "cv_extract": [persona_cv()],
            "eligibility": [eligibility],
            "gap_questions": [questions],
            "rewrite": [RewrittenCV() for _ in range(3)],
            "verify_claims": [JudgeFindings()],
        }
    )
    return gw, PipelineService(build_graph(deps, new_checkpointer()), deps.runs)


def _start(svc: PipelineService) -> None:
    svc.run(
        job_description=persona_jd_text(),
        user_resume_text="cv text",
        thread_id="t1",
        options=RunOptions(),
    )


@pytest.fixture
def pauses(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """One entry per real pause (interrupt() raising), across the whole run."""
    seen: list[int] = []
    real = await_mod.interrupt

    def counting(value):
        try:
            return real(value)
        except GraphInterrupt:
            seen.append(1)
            raise

    monkeypatch.setattr(await_mod, "interrupt", counting)
    return seen


@pytest.mark.parametrize(
    "reply",
    ["", "   ", "\u00a0\u200b", None, {"answers": {"q1": "  "}}, {"skipped": True}, {}],
)
def test_skipped_proceeds_once(reply, pauses):
    gw, svc = _service()
    _start(svc)
    final = svc.resume("t1", reply)
    assert final["answers"].skipped is True
    assert svc.get_state("t1")["next"] == []
    assert len(pauses) == 1
    rewrite = next(r for r in gw.requests if r.step == "rewrite")
    assert "<answers>\n" not in rewrite.messages[0].content


def test_answered_proceeds():
    gw, svc = _service()
    _start(svc)
    assert [q.id for q in svc.get_state("t1")["values"]["questions"]] == ["q1", "q2"]
    final = svc.resume("t1", {"answers": {"q1": " two years ", "q2": ""}})
    assert final["answers"].answers == {"q1": "two years"}
    rewrite = next(r for r in gw.requests if r.step == "rewrite")
    assert "<answers>\nQ: Kubernetes?\nA: two years\n</answers>" in rewrite.messages[0].content


def test_no_questions_no_interrupt(pauses):
    _, svc = _service(GapQuestions(questions=[]))
    _start(svc)
    assert svc.get_state("t1")["next"] == []
    assert pauses == []


def test_resume_when_not_paused_raises():
    _, svc = _service(eligibility=Eligibility(score=10))
    _start(svc)
    with pytest.raises(NotAwaitingInput):
        svc.resume("t1", "late")
    with pytest.raises(NotAwaitingInput):
        svc.resume("never-started", "late")
