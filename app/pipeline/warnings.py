"""Non-fatal pipeline warnings: a code and a step name, never user text."""

from typing import Literal

from pydantic import BaseModel

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


class PipelineWarning(BaseModel, frozen=True):
    code: WarningCode
    step: str
