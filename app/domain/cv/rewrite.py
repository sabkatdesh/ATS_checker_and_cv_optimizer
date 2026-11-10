"""
CV rewrite output schema.
Mirrors UniversalCVStructured but with max_length constraints on list fields
to enforce budget rules during the rewrite phase.
Built from the same base models — budget limits are applied at prompt level,
these constraints are a safety net.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.domain.common import NullSafeListMixin, SeniorityLevel
from app.domain.cv.domain_config import Domain
from app.domain.cv.universal_cv import (
    AwardEntry,
    CVQualityFlags,
    EmploymentType,
    LanguageEntry,
    LicenseEntry,
    PublicationEntry,
    TradeQualificationEntry,
    UniversalCVMeta,
)


class RewriteSkillBlock(NullSafeListMixin, BaseModel):
    hard_skills: list[str] = Field(default_factory=list, max_length=25)
    soft_skills: list[str] = Field(default_factory=list, max_length=5)
    tools: list[str] = Field(default_factory=list, max_length=15)
    frameworks: list[str] = Field(default_factory=list, max_length=10)
    cloud_platforms: list[str] = Field(default_factory=list, max_length=5)


class RewriteWorkEntry(NullSafeListMixin, BaseModel):
    job_title: str
    company_name: str | None = None
    employment_type: EmploymentType | None = None
    start_date: date | None = None
    end_date: date | None = None
    responsibilities: list[str] = Field(default_factory=list, max_length=5)
    achievements: list[str] = Field(default_factory=list, max_length=3)
    tools_used: list[str] = Field(default_factory=list, max_length=8)


class RewriteEducationEntry(BaseModel):
    degree: str | None = None
    field_of_study: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    grade: str | None = None


class RewriteCertEntry(BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None


class RewriteProjectEntry(NullSafeListMixin, BaseModel):
    title: str
    description: str | None = Field(default=None, max_length=400)
    technologies: list[str] = Field(default_factory=list, max_length=8)
    url: str | None = None


class RewriteExperienceSummary(BaseModel):
    total_years: float | None = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: str | None = None
    relevant_years: float | None = None


class RewrittenCV(NullSafeListMixin, BaseModel):
    """Output schema for the CV rewrite node. Enforces hard field limits."""

    domain: Domain = Domain.GENERAL

    meta: UniversalCVMeta = Field(default_factory=UniversalCVMeta)
    professional_summary: str | None = Field(default=None, max_length=700)
    skills: RewriteSkillBlock = Field(default_factory=RewriteSkillBlock)
    experience_summary: RewriteExperienceSummary = Field(default_factory=RewriteExperienceSummary)
    work_experience: list[RewriteWorkEntry] = Field(default_factory=list)
    education: list[RewriteEducationEntry] = Field(default_factory=list)
    certifications: list[RewriteCertEntry] = Field(default_factory=list, max_length=5)
    projects: list[RewriteProjectEntry] = Field(default_factory=list, max_length=3)
    publications: list[PublicationEntry] = Field(default_factory=list, max_length=10)
    licenses: list[LicenseEntry] = Field(default_factory=list)
    trade_qualifications: list[TradeQualificationEntry] = Field(default_factory=list)
    languages: list[LanguageEntry] = Field(default_factory=list)
    awards: list[AwardEntry] = Field(default_factory=list)
    quality_flags: CVQualityFlags = Field(default_factory=CVQualityFlags)
