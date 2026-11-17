"""Tailor the source CV to the job within the domain budget."""

from typing import Any

from app.domain.cv.domain_config import get_budget
from app.domain.cv.rewrite import RewrittenCV
from app.pipeline.blocks import DataTag
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_required
from app.pipeline.prompts.domain_guidance import get_domain_guidance
from app.pipeline.state import PipelineState

_BUDGET_DEFAULTS = {
    "target_words": 800,
    "max_roles": 4,
    "max_skills": 18,
    "max_projects": 0,
    "max_publications": 0,
}


def _task_params(state: PipelineState) -> dict[str, int | float | str]:
    domain = state["domain"]
    years = state["source_cv"].experience_summary.total_years or 0
    budget = get_budget(domain, years)
    params: dict[str, int | float | str] = {
        k: budget.get(k, v) for k, v in _BUDGET_DEFAULTS.items()
    }
    params["domain"] = domain
    params["domain_guidance"] = get_domain_guidance(domain)
    return params


def _blocks(state: PipelineState) -> list[tuple[DataTag, str]]:
    blocks: list[tuple[DataTag, str]] = [
        ("cv", state["source_cv"].model_dump_json()),
        ("job_requirements", state["jd"].model_dump_json()),
    ]
    answers = state.get("answers")
    if answers is not None and answers.free_text:
        blocks.append(("answers", answers.free_text))
    draft = state.get("tailored_cv")
    if state.get("passes", 0) >= 1 and draft is not None:
        blocks.append(("previous_draft", draft.model_dump_json()))
    return blocks


async def rewrite(state: PipelineState, *, deps: PipelineDeps, ctx: RunContext) -> dict[str, Any]:
    cv = await run_required(
        "rewrite",
        call_step(
            deps,
            ctx,
            step="rewrite",
            schema=RewrittenCV,
            blocks=_blocks(state),
            task_params=_task_params(state),
            cache_prefix=True,
        ),
    )

    return {"tailored_cv": cv, "passes": state.get("passes", 0) + 1}
