"""Prompt-injection markers in untrusted text (spec 10 section 5): codes only, never the text."""

import re
from typing import Literal, get_args

from app.domain.text.invisible import strip_invisible

MarkerCode = Literal[
    "IGNORE_INSTRUCTIONS",
    "ROLE_TAG",
    "SYSTEM_PROMPT",
    "AS_AN_AI",
    "JSON_PAYLOAD",
    "SCORE_DEMAND",
    "DATA_TAG",
]
MARKER_CODES: tuple[MarkerCode, ...] = get_args(MarkerCode)

# Kept in step with app.pipeline.blocks.DataTag (the domain layer does not import the pipeline).
_DATA_TAGS = (
    "job_description|job_requirements|cv|answers|gaps|previous_draft|ats_feedback"
    "|rewritten_cv|flagged_claims"
)
_I = re.IGNORECASE

_PATTERNS: dict[MarkerCode, tuple[re.Pattern[str], ...]] = {
    "IGNORE_INSTRUCTIONS": (
        re.compile(
            r"\b(?:ignore|disregard)\s+(?:all\s+|any\s+)?(?:of\s+)?(?:the\s+|your\s+)?"
            r"(?:previous|prior|above|earlier|preceding)\s+"
            r"(?:instructions?|prompts?|directions?|rules)",
            _I,
        ),
        re.compile(r"\b(?:ignore|disregard)\s+(?:all\s+|the\s+)?instructions?\s+above", _I),
        re.compile(r"(?:আগের|পূর্বের|পূর্ববর্তী)\s+(?:সব\s+|সকল\s+)?নির্দেশ\S*\s+(?:উপেক্ষা|অগ্রাহ্য)"),
    ),
    "SYSTEM_PROMPT": (re.compile(r"^[ \t]*(?:system|assistant|user)[ \t]*:", _I | re.MULTILINE),),
    "ROLE_TAG": (
        re.compile(r"<\s*/?\s*(?:system|assistant|user)\s*>", _I),
        re.compile(r"\[/?INST\]|<<\s*/?SYS\s*>>|<\|im_(?:start|end)\|>", _I),
    ),
    "AS_AN_AI": (
        re.compile(
            r"\bas\s+an?\s+(?:ai\b|artificial\s+intelligence|(?:large\s+)?language\s+model)", _I
        ),
    ),
    "JSON_PAYLOAD": (re.compile(r"\{[^{}]*\"(?:score|verdict|overall_score)\"\s*:", _I),),
    "SCORE_DEMAND": (
        re.compile(r"\bscore\s+of\s+100\b", _I),
        re.compile(r"\bgive\b[^.\n]{0,60}?\bscore\b", _I),
    ),
    "DATA_TAG": (re.compile(rf"<\s*/?\s*(?:{_DATA_TAGS})\s*>", _I),),
}


def find_markers(text: str) -> tuple[MarkerCode, ...]:
    """Marker codes present in text (after invisible stripping), in the order of MarkerCode."""
    clean = strip_invisible(text)
    return tuple(code for code in MARKER_CODES if any(p.search(clean) for p in _PATTERNS[code]))
