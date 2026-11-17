"""CV rewrite output: every UniversalCV section plus a change log and unaddressed gaps (E2).

Length budgets live in the prompt, not in list caps: a cap violation would fail the whole job.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.cv.sections import SectionName
from app.domain.cv.universal_cv import UniversalCVStructured

TEXT_LIMIT = 200


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
