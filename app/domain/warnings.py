"""Codes for non-fatal pipeline warnings; the domain owns them so reports can name them."""

from typing import Literal

WarningCode = Literal[
    "ELIGIBILITY_DETERMINISTIC",
    "QUESTIONS_SKIPPED",
    "COVER_LETTER_SKIPPED",
    "VERIFIER_JUDGE_SKIPPED",
    "REVISE_KEPT_PREVIOUS",
    "JD_INJECTION_MARKERS",
    "CV_INJECTION_MARKERS",
    "SECTION_RESTORED",
    "FOREIGN_CONTACT_REMOVED",
    "PROFILE_ENTRY_INVALID",
    "UNKNOWN_PROFILE_KEYS",
]
