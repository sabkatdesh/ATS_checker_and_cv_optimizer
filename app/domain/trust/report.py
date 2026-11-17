"""Trust report: the verifier's verdict on a rewritten CV, stored in the pipeline state."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.cv.rewrite import TEXT_LIMIT, ChangeLogEntry
from app.domain.cv.sections import SectionName

# The pipeline's warning codes; warnings.py imports nothing, so this creates no import cycle.
from app.pipeline.warnings import WarningCode

ClaimKind = Literal[
    "employer",
    "title",
    "date",
    "degree",
    "institution",
    "certification",
    "licence",
    "skill",
    "number",
]
TrustStatus = Literal["pass", "warn", "fail"]


class UnsupportedClaim(BaseModel):
    text: str
    section: SectionName
    kind: ClaimKind
    reason: Literal["not_in_source", "number_not_in_source", "date_changed"]
    layer: Literal["deterministic", "judge"]
    severity: Literal["hard", "soft"]

    @field_validator("text", mode="before")
    @classmethod
    def _truncate(cls, value: Any) -> Any:
        return value[:TEXT_LIMIT] if isinstance(value, str) else value


class SourceCounts(BaseModel):
    """Supported claims by where the support came from (E4/H7 transparency)."""

    cv: int = 0
    answers: int = 0


class TrustReport(BaseModel):
    status: TrustStatus
    unsupported_claims: list[UnsupportedClaim] = Field(default_factory=list)
    changes: list[ChangeLogEntry] = Field(default_factory=list)
    injection_warnings: list[WarningCode] = Field(default_factory=list)
    sources: SourceCounts = Field(default_factory=SourceCounts)
    revised: bool = False
    requires_review: bool = False
