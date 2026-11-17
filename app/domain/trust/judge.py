"""The LLM judge's output schema and how its findings become trust-report claims."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.cv.sections import SectionName
from app.domain.trust.report import UnsupportedClaim

JUDGE_TEXT_LIMIT = 300
MAX_FINDINGS = 20


def _cut(value: Any) -> Any:
    return value[:JUDGE_TEXT_LIMIT] if isinstance(value, str) else value


class JudgeFinding(BaseModel):
    section: SectionName
    output_text: str
    issue: Literal["fabrication", "inflation"]
    reason: str

    _cut_texts = field_validator("output_text", "reason", mode="before")(_cut)


class JudgeFindings(BaseModel):
    findings: list[JudgeFinding] = Field(default_factory=list)

    @field_validator("findings", mode="before")
    @classmethod
    def _first_findings(cls, value: Any) -> Any:
        return value[:MAX_FINDINGS] if isinstance(value, list) else value


def judge_claims(findings: JudgeFindings) -> list[UnsupportedClaim]:
    """Fabrication is hard (forces a revise); inflation is soft (highlighted only)."""
    return [
        UnsupportedClaim(
            text=f.output_text,
            section=f.section,
            kind="statement",
            reason="not_in_source" if f.issue == "fabrication" else "inflated",
            layer="judge",
            severity="hard" if f.issue == "fabrication" else "soft",
        )
        for f in findings.findings
    ]
