"""One revise of the tailored CV that removes or corrects the verifier's hard claims."""

import json
from typing import Any

from app.domain.cv.rewrite import RewrittenCV
from app.pipeline.blocks import DataTag
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.draft_checks import answers_text, check_draft
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_optional, skip_warning
from app.pipeline.state import PipelineState

_CLAIM_FIELDS = {"section", "kind", "text", "reason"}


def _flagged(state: PipelineState) -> str:
    hard = [c for c in state["trust_report"].unsupported_claims if c.severity == "hard"]
    return json.dumps([c.model_dump(mode="json", include=_CLAIM_FIELDS) for c in hard])


def _blocks(state: PipelineState) -> list[tuple[DataTag, str]]:
    blocks: list[tuple[DataTag, str]] = [("cv", state["source_cv"].model_dump_json())]
    text = answers_text(state)
    if text:
        blocks.append(("answers", text))
    blocks.append(("rewritten_cv", state["tailored_cv"].model_dump_json()))
    blocks.append(("flagged_claims", _flagged(state)))
    return blocks


async def revise_flagged(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    cv = await run_optional(
        "revise_flagged",
        call_step(deps, ctx, step="revise_flagged", schema=RewrittenCV, blocks=_blocks(state)),
    )
    if cv is None:  # invalid output: the previous draft stays, verified once more
        return {"revised": True, "warnings": [skip_warning("revise_flagged")]}
    cv, warnings = check_draft(state["source_cv"], cv, "revise_flagged")
    out: dict[str, Any] = {"tailored_cv": cv, "revised": True}
    if warnings:
        out["warnings"] = warnings
    return out
