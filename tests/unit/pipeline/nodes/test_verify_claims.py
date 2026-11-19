import pytest

from app.domain.cv.rewrite import RewrittenCV
from app.domain.questions.schemas import GapAnswers, GapQuestion
from app.domain.trust.judge import JudgeFinding, JudgeFindings
from app.domain.trust.report import TrustReport
from app.pipeline.nodes.verify_claims import route_after_verify, verify_claims
from app.pipeline.warnings import PipelineWarning
from app.ports.llm_errors import LLMCancelled, LLMOutputInvalid, LLMUnavailable
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run

MBA = {"degree": "MBA", "institution": "Example University", "graduation_year": 2022}


def _copy(**update) -> RewrittenCV:
    return RewrittenCV.model_validate({**persona_cv().model_dump(mode="json"), **update})


def _with_mba() -> RewrittenCV:
    education = persona_cv().model_dump(mode="json")["education"]
    return _copy(education=[*education, MBA])


def _state(cv: RewrittenCV, **extra) -> dict:
    return {"source_cv": persona_cv(), "tailored_cv": cv, "warnings": [], **extra}


def _finding(issue: str, quote: str = "Built REST services") -> JudgeFindings:
    return JudgeFindings(
        findings=[
            JudgeFinding(section="work_experience", output_text=quote, issue=issue, reason="r")
        ]
    )


def test_clean_copy_passes_and_sends_the_judge_blocks():
    answers = GapAnswers(answers={"q1": "Two years of Kubernetes"})
    state = _state(_copy(), questions=[GapQuestion(id="q1", text="K8s?")], answers=answers)
    gw, deps = deps_for({"verify_claims": [JudgeFindings()]})
    out = run(verify_claims(state, deps=deps, ctx=ctx()))
    report = out["trust_report"]
    assert (report.status, report.revised, report.requires_review) == ("pass", False, False)
    assert report.sources.cv > 0
    req = gw.requests[0]
    assert (req.step, req.output_schema) == ("verify_claims", JudgeFindings)
    content = req.messages[0].content
    assert "<cv>\n" + persona_cv().model_dump_json() + "\n</cv>" in content
    assert "<answers>\n" in content and "Two years of Kubernetes" in content
    assert "<rewritten_cv>\n" in content and "change_log" not in content
    assert "warnings" not in out


def test_deterministic_hard_claim_fails():
    _, deps = deps_for({"verify_claims": [JudgeFindings()]})
    report = run(verify_claims(_state(_with_mba()), deps=deps, ctx=ctx()))["trust_report"]
    assert report.status == "fail"
    assert [(c.kind, c.layer) for c in report.unsupported_claims] == [("degree", "deterministic")]


@pytest.mark.parametrize(("issue", "status"), [("fabrication", "fail"), ("inflation", "warn")])
def test_judge_findings_are_added(issue: str, status: str):
    _, deps = deps_for({"verify_claims": [_finding(issue)]})
    report = run(verify_claims(_state(_copy()), deps=deps, ctx=ctx()))["trust_report"]
    assert report.status == status
    assert [c.layer for c in report.unsupported_claims] == ["judge"]


def test_judge_finding_that_quotes_nothing_in_the_cv_is_dropped():
    _, deps = deps_for({"verify_claims": [_finding("fabrication", quote="Led a team of 40")]})
    report = run(verify_claims(_state(_copy()), deps=deps, ctx=ctx()))["trust_report"]
    assert (report.status, report.unsupported_claims) == ("pass", [])


@pytest.mark.parametrize("err", [LLMOutputInvalid("x"), LLMUnavailable("x")])
def test_judge_failure_is_skipped_with_a_warning(err):
    _, deps = deps_for({"verify_claims": [err]})
    out = run(verify_claims(_state(_with_mba()), deps=deps, ctx=ctx()))
    assert out["warnings"] == [PipelineWarning(code="VERIFIER_JUDGE_SKIPPED", step="verify_claims")]
    assert [c.kind for c in out["trust_report"].unsupported_claims] == ["degree"]


def test_judge_cancellation_propagates():
    _, deps = deps_for({"verify_claims": [LLMCancelled("c")]})
    with pytest.raises(LLMCancelled):
        run(verify_claims(_state(_copy()), deps=deps, ctx=ctx()))


def test_judge_disabled_makes_no_call():
    gw, deps = deps_for({}, judge_enabled=False)
    report = run(verify_claims(_state(_copy()), deps=deps, ctx=ctx()))["trust_report"]
    assert report.status == "pass" and gw.requests == []


def test_still_failing_after_a_revise_finishes_flagged():
    _, deps = deps_for({}, judge_enabled=False)
    state = _state(_with_mba(), revised=True)
    report = run(verify_claims(state, deps=deps, ctx=ctx()))["trust_report"]
    assert (report.status, report.requires_review, report.revised) == ("warn", True, True)
    assert route_after_verify({"trust_report": report}) == "done"


def test_report_carries_changes_and_injection_warnings():
    cv = _copy(change_log=[{"section": "skills", "reason": "trimmed"}])
    warnings = [
        PipelineWarning(code="JD_INJECTION_MARKERS", step="jd_extract"),
        PipelineWarning(code="SECTION_RESTORED", step="rewrite"),
        PipelineWarning(code="JD_INJECTION_MARKERS", step="jd_extract"),
    ]
    _, deps = deps_for({}, judge_enabled=False)
    state = _state(cv, warnings=warnings)
    report = run(verify_claims(state, deps=deps, ctx=ctx()))["trust_report"]
    assert [c.reason for c in report.changes] == ["trimmed"]
    assert report.injection_warnings == ["JD_INJECTION_MARKERS"]


@pytest.mark.parametrize(
    ("status", "revised", "route"),
    [("pass", False, "done"), ("warn", False, "done"), ("fail", False, "revise")],
)
def test_route_after_verify(status: str, revised: bool, route: str):
    report = TrustReport(status=status, revised=revised)
    assert route_after_verify({"trust_report": report}) == route
