"""CombinedState TypedDict: single source of truth for all pipeline state."""

from __future__ import annotations

from typing import Any, TypedDict


class CombinedState(TypedDict):
    # Inputs
    job_description: str
    user_resume: str

    # Domain: set by eligibility_check from the quick-extraction domain fields.
    # Values match Domain enum: "tech" | "medical" | "education" | "trades" |
    # "finance" | "legal" | "creative" | "general"
    detected_domain: str

    # Stage 1: quick extraction + eligibility
    quick_jd: Any | None  # SummaryJD
    quick_cv: Any | None  # SummaryCV
    eligibility_verdict: Any | None  # Match
    is_eligible: bool
    eligibility_message: str | None

    # Stage 2: detailed extraction + ATS + rewrite
    structured_jd: Any | None  # JobDescriptionStructured
    structured_cv: Any | None  # UniversalCVStructured (or RewrittenCV after rewrite)
    final_match: dict | None

    # HITL
    gaps_identified: list[str]
    user_qna: str | None
    hitl_session_id: str
    hitl_awaiting_input: bool

    # Cover letter
    cover_letter_requested: bool
    cover_letter_tone: str | None  # "formal" | "conversational"
    cover_letter_length: str | None  # "short" | "standard"
    cover_letter_result: Any | None  # CoverLetterStructured
    cover_letter_hitl_done: bool

    # Control
    re_write_cv: str | None
    counter: int
    max_iterations: int
