"""The claim verifier and the one revise through the real graph on a scripted gateway."""

from pathlib import Path

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.domain.cv.rewrite import RewrittenCV
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.domain.trust.judge import JudgeFindings
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from app.ports.llm_errors import LLMOutputInvalid
from app.services.finalize import finalize_session
from tests.fakes.fake_auth import USER_A, FakeAuth
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_store import MemoryStore
from tests.pipeline.helpers import deps_for, persona_answers, persona_cv, persona_jd_text, tech_jd
from tests.pipeline.scripted_gateway import Outcome, ScriptedGateway

INJECTION = Path(__file__).resolve().parents[2] / "fixtures" / "injection"
MBA = {"degree": "MBA", "institution": "Example University", "graduation_year": 2022}


def _clean() -> RewrittenCV:
    return RewrittenCV.model_validate(persona_cv().model_dump())


def _with_mba() -> RewrittenCV:
    data = persona_cv().model_dump(mode="json")
    return RewrittenCV.model_validate({**data, "education": [*data["education"], MBA]})


def _with_skill(skill: str) -> RewrittenCV:
    cv = _clean()
    tools = [*cv.skills.tools, skill]
    return cv.model_copy(update={"skills": cv.skills.model_copy(update={"tools": tools})})


def _service(draft: RewrittenCV, **steps: list[Outcome]) -> tuple[ScriptedGateway, PipelineService]:
    script: dict[str, list[Outcome]] = {
        "jd_extract": [tech_jd()],
        "cv_extract": [persona_cv()],
        "eligibility": [Eligibility(score=60, gaps=["Kubernetes"])],
        "gap_questions": [GapQuestions(questions=[GapQuestion(id="q1", text="K8s?")])],
        "rewrite": [draft for _ in range(3)],
        "verify_claims": [JudgeFindings(), JudgeFindings()],
        **steps,
    }
    gw, deps = deps_for(script)
    return gw, PipelineService(build_graph(deps, new_checkpointer()))


def _finish(svc: PipelineService, jd: str | None = None, reply: str | None = None) -> dict:
    svc.run(
        job_description=jd or persona_jd_text(),
        user_resume_text="cv text",
        thread_id="t1",
        options=RunOptions(),
    )
    return svc.resume("t1", persona_answers().free_text if reply is None else reply)


def _steps(gw: ScriptedGateway) -> list[str]:
    return [r.step for r in gw.requests]


def test_verifier_pass_no_revise():
    gw, svc = _service(_clean())
    final = _finish(svc)
    assert final["trust_report"].status == "pass"
    assert "revise_flagged" not in _steps(gw)
    assert _steps(gw).count("verify_claims") == 1


def test_fail_revise_pass():
    gw, svc = _service(_with_mba(), revise_flagged=[_clean()])
    final = _finish(svc)
    assert _steps(gw).count("revise_flagged") == 1
    report = final["trust_report"]
    assert (report.status, report.revised) == ("pass", True)
    assert final["revised"] is True
    assert "MBA" not in final["tailored_cv"].model_dump_json()
    flagged = gw.requests[_steps(gw).index("revise_flagged")].messages[0].content
    assert "<flagged_claims>" in flagged and "MBA" in flagged


def _pdf_container(svc: PipelineService) -> Container:
    FakePdfRenderer.calls.clear()
    FakePdfRenderer.raise_on_render = None
    store = MemoryStore()
    store.balances[USER_A] = 5
    return Container(
        AppSettings(_env_file=None, env="test"),
        store=store,
        auth=FakeAuth(),
        pipeline=svc,
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )


def test_fail_twice_warns_and_keeps_claims():
    gw, svc = _service(_with_mba(), revise_flagged=[_with_mba(), _clean()])
    final = _finish(svc)
    assert _steps(gw).count("revise_flagged") == 1
    report = final["trust_report"]
    assert (report.status, report.requires_review, report.revised) == ("warn", True, True)
    assert [c.kind for c in report.unsupported_claims if c.severity == "hard"] == ["degree"]
    assert "MBA" in final["tailored_cv"].model_dump_json()  # D3: kept and flagged
    assert svc.get_state("t1")["next"] == []
    summary = svc.summary("t1")
    assert summary is not None and summary.trust_report == report

    container = _pdf_container(svc)
    finalize_session(container, "t1", final, USER_A)
    assert container.store.sessions["t1"]["status"] == "complete"
    assert container.store.sessions["t1"]["pdf_url"]
    rendered = FakePdfRenderer.calls[0][1][0]
    assert "MBA" in rendered.model_dump_json()


def test_judge_invalid_keeps_deterministic():
    gw, svc = _service(
        _with_mba(),
        verify_claims=[LLMOutputInvalid("x"), LLMOutputInvalid("x")],
        revise_flagged=[_with_mba()],
    )
    final = _finish(svc)
    assert "VERIFIER_JUDGE_SKIPPED" in {w.code for w in final["warnings"]}
    claims = final["trust_report"].unsupported_claims
    assert [(c.kind, c.layer) for c in claims] == [("degree", "deterministic")]


def test_judge_disabled_makes_no_call():
    gw, deps = deps_for(
        {
            "jd_extract": [tech_jd()],
            "cv_extract": [persona_cv()],
            "eligibility": [Eligibility(score=60, gaps=["Kubernetes"])],
            "gap_questions": [GapQuestions(questions=[GapQuestion(id="q1", text="K8s?")])],
            "rewrite": [_clean() for _ in range(3)],
        },
        judge_enabled=False,
    )
    svc = PipelineService(build_graph(deps, new_checkpointer()))
    final = _finish(svc)
    assert "verify_claims" not in _steps(gw)
    assert final["trust_report"].status == "pass"


def test_injection_add_skill_is_flagged():
    jd = (INJECTION / "05_add_skill.txt").read_text(encoding="utf-8")
    gw, svc = _service(_with_skill("Kubernetes"))
    final = _finish(svc, jd=jd, reply="")  # skipped answers: nothing supports Kubernetes
    report = final["trust_report"]
    skills = [c for c in report.unsupported_claims if c.kind == "skill"]
    assert [c.text for c in skills] == ["Kubernetes"]
    assert report.status == "warn" and "JD_INJECTION_MARKERS" in report.injection_warnings
    assert "revise_flagged" not in _steps(gw)  # a skill is soft: highlighted, not revised
