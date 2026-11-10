"""Cover letter nodes: options HITL, gate and generation."""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.types import interrupt

from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.parsing.safe_parser import safe_llm_parse
from app.pipeline.chains import Chains
from app.pipeline.nodes._helpers import _safe_json
from app.pipeline.state import CombinedState

log = structlog.get_logger(__name__)


def cover_letter_hitl_node(state: CombinedState) -> dict[str, Any]:
    """
    Second HITL interrupt: pauses so the user can confirm tone + length.
    - If cover_letter_requested=False -> sets hitl_done=False, graph routes to END.
    - If tone+length already set -> sets hitl_done=True, graph routes to generate.
    - Otherwise -> interrupts pipeline, waiting for POST /cover-letter-options.
    """
    if not state.get("cover_letter_requested"):
        return {"cover_letter_hitl_done": False}

    tone = state.get("cover_letter_tone")
    length = state.get("cover_letter_length")

    if tone and length:
        log.info("pipeline.stage", stage="cover_letter_hitl", tone=tone, length=length)
        return {"cover_letter_hitl_done": True}

    log.info("pipeline.stage", stage="cover_letter_hitl_paused")

    interrupt(
        {
            "type": "cover_letter_options",
            "message": (
                "Choose cover letter options:\n"
                "  tone:   'formal' or 'conversational'\n"
                "  length: 'short' (~150 words) or 'standard' (~300 words)"
            ),
        }
    )

    return {"cover_letter_hitl_done": True}


def check_cover_letter_gate(state: CombinedState) -> str:
    """Conditional edge after cover_letter_hitl: route to generate or END."""
    return "generate" if state.get("cover_letter_hitl_done") else "done"


def _fallback_cover_letter() -> CoverLetterStructured:
    return CoverLetterStructured(
        salutation="Dear Hiring Manager,",
        opening_paragraph="I am excited to apply for this position.",
        body_paragraphs=[],
        closing_paragraph="Thank you for your consideration.",
        sign_off="Sincerely,",
    )


def generate_cover_letter_node(state: CombinedState, *, chains: Chains) -> dict[str, Any]:
    """Generate the cover letter using the LLM."""
    tone = state.get("cover_letter_tone") or "formal"
    length = state.get("cover_letter_length") or "standard"
    word_target = 150 if length == "short" else 300

    structured_cv = state.get("structured_cv")
    structured_jd = state.get("structured_jd")
    gaps = state.get("gaps_identified", [])

    log.info(
        "pipeline.stage",
        stage="generate_cover_letter",
        tone=tone,
        length=length,
        word_target=word_target,
    )

    raw = chains.cover_letter.invoke(
        {
            "tone": tone,
            "length": length,
            "word_target": word_target,
            "cv_text": _safe_json(structured_cv) if structured_cv else state.get("user_resume", ""),
            "jd_text": _safe_json(structured_jd)
            if structured_jd
            else state.get("job_description", ""),
            "gaps": "\n".join(f"- {g}" for g in gaps) if gaps else "None",
        }
    )

    result = safe_llm_parse(raw, CoverLetterStructured, _fallback_cover_letter())
    log.info("pipeline.stage", stage="generate_cover_letter_done")

    return {"cover_letter_result": result}
