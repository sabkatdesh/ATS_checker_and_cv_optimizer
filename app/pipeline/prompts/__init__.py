"""All LLM prompt templates, re-exported from their topic modules."""

from app.pipeline.prompts.cover_letter import COVER_LETTER_PROMPT, parser_cover_letter
from app.pipeline.prompts.extraction import (
    DETAILED_CV_PROMPT,
    DETAILED_JD_PROMPT,
    QUICK_CV_PROMPT,
    QUICK_JD_PROMPT,
    VERDICT_PROMPT,
    parser_detailed_cv,
    parser_detailed_jd,
    parser_quick_cv,
    parser_quick_jd,
    parser_verdict,
)
from app.pipeline.prompts.rewrite import (
    DOMAIN_REWRITE_GUIDANCE,
    REWRITE_PROMPT,
    get_domain_guidance,
    parser_rewrite,
)

__all__ = [
    "COVER_LETTER_PROMPT",
    "DETAILED_CV_PROMPT",
    "DETAILED_JD_PROMPT",
    "DOMAIN_REWRITE_GUIDANCE",
    "QUICK_CV_PROMPT",
    "QUICK_JD_PROMPT",
    "REWRITE_PROMPT",
    "VERDICT_PROMPT",
    "get_domain_guidance",
    "parser_cover_letter",
    "parser_detailed_cv",
    "parser_detailed_jd",
    "parser_quick_cv",
    "parser_quick_jd",
    "parser_rewrite",
    "parser_verdict",
]
