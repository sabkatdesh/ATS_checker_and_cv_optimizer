"""Check the tailored CV's claims against the source: deterministic layer, then the LLM judge.

Still failing after the one revise, the job finishes with the claims kept and flagged (D3).
"""

from typing import Any, Literal

from app.domain.trust.claims import build_evidence
from app.domain.trust.judge import JudgeFindings, judge_claims
from app.domain.trust.matching import find_unsupported
from app.domain.trust.policy import next_action, status_for
from app.domain.trust.report import TrustReport
from app.domain.warnings import WarningCode
from app.pipeline.blocks import DataTag
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.draft_checks import answers_text
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_optional, skip_warning
from app.pipeline.state import PipelineState

# Warnings that show the job description, the CV or the output carried injected content.
INJECTION_CODES: frozenset[WarningCode] = frozenset(
    {"JD_INJECTION_MARKERS", "CV_INJECTION_MARKERS", "FOREIGN_CONTACT_REMOVED"}
)
# The judge compares facts; the change log and gap list would only distract it.
_NOT_JUDGED = {"change_log", "gaps_unaddressed"}


def _judge_blocks(state: PipelineState) -> list[tuple[DataTag, str]]:
    blocks: list[tuple[DataTag, str]] = [("cv", state["source_cv"].model_dump_json())]
    text = answers_text(state)
    if text:
        blocks.append(("answers", text))
    blocks.append(("rewritten_cv", state["tailored_cv"].model_dump_json(exclude=_NOT_JUDGED)))
    return blocks


def _injection_warnings(state: PipelineState) -> list[WarningCode]:
    codes = [w.code for w in state.get("warnings", []) if w.code in INJECTION_CODES]
    return list(dict.fromkeys(codes))


async def verify_claims(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    cv = state["tailored_cv"]
    evidence = build_evidence(state["source_cv"], state.get("answers"))
    claims, counts = find_unsupported(evidence, cv)
    out: dict[str, Any] = {}
    if deps.settings.judge_enabled:
        findings = await run_optional(
            "verify_claims",
            call_step(
                deps, ctx, step="verify_claims", schema=JudgeFindings, blocks=_judge_blocks(state)
            ),
        )
        if findings is None:
            out["warnings"] = [skip_warning("verify_claims")]
        else:
            claims = [*claims, *judge_claims(findings)]

    report = TrustReport(
        status=status_for(claims),
        unsupported_claims=claims,
        changes=cv.change_log,
        injection_warnings=_injection_warnings(state),
        sources=counts,
        revised=state.get("revised", False),
    )
    if next_action(report) == "finish_with_flags":
        report = report.model_copy(update={"status": "warn", "requires_review": True})
    out["trust_report"] = report
    return out


def route_after_verify(state: PipelineState) -> Literal["revise", "done"]:
    return "revise" if next_action(state["trust_report"]) == "revise" else "done"
