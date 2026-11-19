import json

import pytest

from app.domain.cv.rewrite import RewrittenCV
from app.domain.trust.report import TrustReport, UnsupportedClaim
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.nodes.revise_flagged import revise_flagged
from app.pipeline.warnings import PipelineWarning
from app.ports.llm_errors import LLMOutputInvalid, LLMRefused
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run


def _claim(kind: str, severity: str, text: str) -> UnsupportedClaim:
    return UnsupportedClaim(
        text=text,
        section="education",
        kind=kind,
        reason="not_in_source",
        layer="deterministic",
        severity=severity,
    )


def _state() -> dict:
    report = TrustReport(
        status="fail",
        unsupported_claims=[_claim("degree", "hard", "MBA"), _claim("skill", "soft", "Go")],
    )
    draft = RewrittenCV.model_validate(persona_cv().model_dump())
    return {"source_cv": persona_cv(), "tailored_cv": draft, "trust_report": report}


def test_revise_sends_hard_claims_and_returns_the_checked_draft():
    revised = RewrittenCV(professional_summary="Clean **summary**")  # drops every section
    gw, deps = deps_for({"revise_flagged": [revised]})
    out = run(revise_flagged(_state(), deps=deps, ctx=ctx()))
    assert out["revised"] is True
    cv = out["tailored_cv"]
    assert cv.professional_summary == "Clean summary"
    assert cv.work_experience == persona_cv().work_experience  # restored from the source
    assert out["warnings"] == [PipelineWarning(code="SECTION_RESTORED", step="revise_flagged")]
    req = gw.requests[0]
    assert (req.step, req.output_schema) == ("revise_flagged", RewrittenCV)
    content = req.messages[0].content
    assert "<cv>\n" in content and "<rewritten_cv>\n" in content
    flagged = content.split("<flagged_claims>\n")[1].split("\n</flagged_claims>")[0]
    assert [c["text"] for c in json.loads(flagged)] == ["MBA"]


def test_invalid_output_keeps_the_previous_draft():
    _, deps = deps_for({"revise_flagged": [LLMOutputInvalid("x")]})
    out = run(revise_flagged(_state(), deps=deps, ctx=ctx()))
    assert out == {
        "revised": True,
        "warnings": [PipelineWarning(code="REVISE_KEPT_PREVIOUS", step="revise_flagged")],
    }


def test_other_failures_fail_the_job():
    _, deps = deps_for({"revise_flagged": [LLMRefused("x")]})
    with pytest.raises(PipelineStepFailed) as exc:
        run(revise_flagged(_state(), deps=deps, ctx=ctx()))
    assert (exc.value.step, exc.value.code) == ("revise_flagged", "CONTENT_REFUSED")
