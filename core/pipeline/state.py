"""
CombinedState TypedDict — single source of truth for all pipeline state.
"""
from __future__ import annotations

from typing import Any, List, Optional, TypedDict


class CombinedState(TypedDict):
    # ── Inputs ──────────────────────────────────────────────────────────────────
    job_description: str
    user_resume: str

    # ── Domain (Phase 4) ────────────────────────────────────────────────────────
    # Set by eligibility_check from the quick-extraction domain fields.
    # Values match Domain enum: "tech" | "medical" | "education" | "trades" |
    # "finance" | "legal" | "creative" | "general"
    detected_domain: str

    # ── Stage 1 — Quick extraction + eligibility ────────────────────────────────
    quick_jd: Optional[Any]              # SummaryJD
    quick_cv: Optional[Any]              # SummaryCV
    eligibility_verdict: Optional[Any]   # Match
    is_eligible: bool
    eligibility_message: Optional[str]

    # ── Stage 2 — Detailed extraction + ATS + rewrite ───────────────────────────
    structured_jd: Optional[Any]         # JobDescriptionStructured
    structured_cv: Optional[Any]         # UniversalCVStructured (or RewrittenCV after rewrite)
    final_match: Optional[dict]

    # ── HITL ────────────────────────────────────────────────────────────────────
    gaps_identified: List[str]
    user_qna: Optional[str]
    hitl_session_id: str
    hitl_awaiting_input: bool

    # ── Cover Letter (Phase 6) ───────────────────────────────────────────────────
    cover_letter_requested: bool
    cover_letter_tone: Optional[str]      # "formal" | "conversational"
    cover_letter_length: Optional[str]    # "short" | "standard"
    cover_letter_result: Optional[Any]    # CoverLetterStructured
    cover_letter_hitl_done: bool

    # ── Control ─────────────────────────────────────────────────────────────────
    re_write_cv: Optional[str]
    counter: int
    max_iterations: int
