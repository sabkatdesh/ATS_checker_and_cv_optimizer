"""Typed pipeline state. Later tasks re-annotate the fields noted below."""

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import Match
from app.domain.questions.schemas import GapAnswers, GapQuestion
from app.pipeline.warnings import PipelineWarning


class RunOptions(BaseModel, frozen=True):
    cover_letter: bool = False
    cover_letter_tone: Literal["formal", "conversational"] | None = None
    cover_letter_length: Literal["short", "standard"] | None = None
    max_passes: int = Field(default=2, ge=1, le=3)


class PipelineState(TypedDict, total=False):
    session_id: str
    jd_text: str
    cv_text: str
    profile: dict[str, Any]
    options: RunOptions
    jd: JobDescriptionStructured
    source_cv: UniversalCVStructured
    domain: str
    eligibility: Match  # becomes Eligibility
    eligible: bool
    questions: list[GapQuestion]
    answers: GapAnswers
    ats_before: dict[str, Any]  # becomes AtsMatch
    ats: dict[str, Any]  # becomes AtsMatch
    tailored_cv: RewrittenCV
    passes: int
    revised: bool
    cover_letter: CoverLetterStructured | None
    warnings: Annotated[list[PipelineWarning], operator.add]
