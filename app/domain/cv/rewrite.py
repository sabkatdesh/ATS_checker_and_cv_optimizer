"""CV rewrite output: every UniversalCV section plus a change log and unaddressed gaps (E2).

Length budgets live in the prompt, not in list caps: a cap violation would fail the whole job.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.cv.sections import SectionName
from app.domain.cv.universal_cv import UniversalCVStructured

_TEXT_LIMIT = 200


class ChangeLogEntry(BaseModel):
    section: SectionName
    entry_id: str | None = None
    before: str | None = Field(default=None, max_length=_TEXT_LIMIT)
    after: str | None = Field(default=None, max_length=_TEXT_LIMIT)
    reason: str = Field(max_length=_TEXT_LIMIT)


class RewrittenCV(UniversalCVStructured):
    """Output schema of the rewrite node."""

    change_log: list[ChangeLogEntry] = Field(default_factory=list)
    gaps_unaddressed: list[str] = Field(default_factory=list)
