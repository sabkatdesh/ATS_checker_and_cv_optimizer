"""Typed pipeline state."""

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from app.domain.ats.schemas import AtsMatch
from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapAnswers, GapQuestion
from app.domain.trust.report import TrustReport
from app.pipeline.warnings import PipelineWarning


class RunOptions(BaseModel, frozen=True):
    cover_letter: bool = False
    cover_letter_tone: Literal["formal", "conversational"] | None = None
    cover_letter_length: Literal["short", "standard"] | None = None
    max_passes: int = Field(default=2, ge=1, le=3)


class PipelineState(TypedDict, total=False):
    session_id: str
    jd_text: str
    profile: dict[str, Any]
    options: RunOptions
    jd: JobDescriptionStructured
    source_cv: UniversalCVStructured
    domain: str
    eligibility: Eligibility
    eligible: bool
    questions: list[GapQuestion]
    answers: GapAnswers
    ats_before: AtsMatch
    ats: AtsMatch
    tailored_cv: RewrittenCV
    passes: int
    trust_report: TrustReport
    revised: bool
    cover_letter: CoverLetterStructured | None
    warnings: Annotated[list[PipelineWarning], operator.add]
