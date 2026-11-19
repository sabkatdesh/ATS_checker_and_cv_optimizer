"""CV rewrite output: every UniversalCV section plus a change log and unaddressed gaps (E2).

Length budgets live in the prompt, not in list caps: a cap violation would fail the whole job.
Per-string anti-abuse caps fail validation instead (the gateway repairs once); change-log notes
are cut, never rejected.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.cv.sections import SectionName
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.text.strings import iter_strings

TEXT_LIMIT = 200
MAX_STRING_CHARS = 2000
MAX_SUMMARY_CHARS = 1200


class ChangeLogEntry(BaseModel):
    section: SectionName
    entry_id: str | None = None
    before: str | None = None
    after: str | None = None
    reason: str

    @field_validator("before", "after", "reason", mode="before")
    @classmethod
    def _truncate(cls, value: Any) -> Any:
        """Over-long notes are cut, never rejected: a long note must not fail the job."""
        return value[:TEXT_LIMIT] if isinstance(value, str) else value


class RewrittenCV(UniversalCVStructured):
    """Output schema of the rewrite node."""

    change_log: list[ChangeLogEntry] = Field(default_factory=list)
    gaps_unaddressed: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cap_strings(self) -> Self:
        """Messages name the field path only, never the text (they reach the repair prompt)."""
        if len(self.professional_summary or "") > MAX_SUMMARY_CHARS:
            raise ValueError(f"professional_summary is longer than {MAX_SUMMARY_CHARS} characters")
        for path, text in iter_strings(self, skip=("change_log",)):
            if len(text) > MAX_STRING_CHARS:
                raise ValueError(f"{path} is longer than {MAX_STRING_CHARS} characters")
        return self
