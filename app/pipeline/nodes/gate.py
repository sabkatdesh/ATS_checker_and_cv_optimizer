"""Route after eligibility: ineligible runs end before any question or rewrite."""

from typing import Literal

from app.pipeline.state import PipelineState


def route_after_eligibility(state: PipelineState) -> Literal["questions", "ineligible"]:
    return "questions" if state.get("eligible") else "ineligible"
