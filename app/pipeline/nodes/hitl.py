"""First HITL interrupt: confirm identified gaps with the user."""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.types import interrupt

from app.pipeline.state import CombinedState

log = structlog.get_logger(__name__)


def hitl_node(state: CombinedState) -> dict[str, Any]:
    """HITL node: pauses when gaps exist and no user feedback yet."""
    gaps = state.get("gaps_identified", [])
    user_qna = state.get("user_qna")

    if user_qna:
        log.info("pipeline.stage", stage="hitl", feedback_already_provided=True)
        return {"hitl_awaiting_input": False, "user_qna": user_qna}

    if not gaps:
        return {"hitl_awaiting_input": False, "user_qna": "No gaps identified"}

    log.info("pipeline.stage", stage="hitl_paused", gaps=len(gaps))

    interrupt(
        {
            "type": "gap_confirmation",
            "gaps": gaps,
            "message": "Please provide user feedback on the listed gaps",
        }
    )

    return {
        "hitl_awaiting_input": False,
        "user_qna": state.get("user_qna", ""),
    }
