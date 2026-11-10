"""
Job Description extraction schemas.
Used in Stage 1 (quick summary) and Stage 2 (detailed extraction).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.common import NullSafeListMixin, SeniorityLevel
from app.domain.cv.domain_config import Domain

# ─── Quick extraction (Stage 1 — eligibility check) ─────────────────────────────


class SummaryJD(NullSafeListMixin, BaseModel):
    """Lightweight JD summary used for fast eligibility check."""

    domain: Domain = Domain.GENERAL
    summary: str | None = None
    tools: list[str] = Field(default_factory=list)
    Job: str | None = None
    responsiblity: str | None = None
    experience: int | None = None
    subject: list[str] = Field(default_factory=list)


# ─── Detailed extraction (Stage 2 — ATS + rewrite) ──────────────────────────────


class JDSkillBlock(NullSafeListMixin, BaseModel):
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    cloud_platforms: list[str] = Field(default_factory=list)


class JDExperienceBlock(NullSafeListMixin, BaseModel):
    min_years: int | None = None
    max_years: int | None = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: str | None = None


class JDEducationBlock(NullSafeListMixin, BaseModel):
    degree_required: str | None = None
    degree_preferred: str | None = None
    fields_of_study: list[str] = Field(default_factory=list)


class JDRequirementBlock(NullSafeListMixin, BaseModel):
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)


class JDResponsibilityBlock(NullSafeListMixin, BaseModel):
    responsibilities: list[str] = Field(default_factory=list)


class JobDescriptionStructured(NullSafeListMixin, BaseModel):
    """Full structured JD used for ATS scoring and rewriting."""

    domain: Domain = Domain.GENERAL
    job_title: str | None = None
    company_name: str | None = None
    location: str | None = None
    employment_type: str | None = None
    summary: str | None = None

    responsibilities: JDResponsibilityBlock = Field(default_factory=JDResponsibilityBlock)
    requirements: JDRequirementBlock = Field(default_factory=JDRequirementBlock)
    skills: JDSkillBlock = Field(default_factory=JDSkillBlock)
    experience: JDExperienceBlock = Field(default_factory=JDExperienceBlock)
    education: JDEducationBlock = Field(default_factory=JDEducationBlock)
