"""
CV rewrite output schema.
Mirrors UniversalCVStructured but with max_length constraints on list fields
to enforce budget rules during the rewrite phase.
Built from the same base models — budget limits are applied at prompt level,
these constraints are a safety net.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from core.schemas.universal_cv import (
    NullSafeListMixin,
    SeniorityLevel,
    EmploymentType,
    UniversalCVMeta,
    CVQualityFlags,
    LicenseEntry,
    TradeQualificationEntry,
    PublicationEntry,
    AwardEntry,
    LanguageEntry,
)
from core.schemas.domain_config import Domain


class RewriteSkillBlock(NullSafeListMixin, BaseModel):
    hard_skills: List[str] = Field(default_factory=list, max_length=25)
    soft_skills: List[str] = Field(default_factory=list, max_length=5)
    tools: List[str] = Field(default_factory=list, max_length=15)
    frameworks: List[str] = Field(default_factory=list, max_length=10)
    cloud_platforms: List[str] = Field(default_factory=list, max_length=5)


class RewriteWorkEntry(NullSafeListMixin, BaseModel):
    job_title: str
    company_name: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    responsibilities: List[str] = Field(default_factory=list, max_length=5)
    achievements: List[str] = Field(default_factory=list, max_length=3)
    tools_used: List[str] = Field(default_factory=list, max_length=8)


class RewriteEducationEntry(BaseModel):
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = None
    grade: Optional[str] = None


class RewriteCertEntry(BaseModel):
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None


class RewriteProjectEntry(NullSafeListMixin, BaseModel):
    title: str
    description: Optional[str] = Field(default=None, max_length=400)
    technologies: List[str] = Field(default_factory=list, max_length=8)
    url: Optional[str] = None


class RewriteExperienceSummary(BaseModel):
    total_years: Optional[float] = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: Optional[str] = None
    relevant_years: Optional[float] = None


class RewrittenCV(NullSafeListMixin, BaseModel):
    """Output schema for the CV rewrite node. Enforces hard field limits."""
    domain: Domain = Domain.GENERAL

    meta: UniversalCVMeta = Field(default_factory=UniversalCVMeta)
    professional_summary: Optional[str] = Field(default=None, max_length=700)
    skills: RewriteSkillBlock = Field(default_factory=RewriteSkillBlock)
    experience_summary: RewriteExperienceSummary = Field(default_factory=RewriteExperienceSummary)
    work_experience: List[RewriteWorkEntry] = Field(default_factory=list)
    education: List[RewriteEducationEntry] = Field(default_factory=list)
    certifications: List[RewriteCertEntry] = Field(default_factory=list, max_length=5)
    projects: List[RewriteProjectEntry] = Field(default_factory=list, max_length=3)
    publications: List[PublicationEntry] = Field(default_factory=list, max_length=10)
    licenses: List[LicenseEntry] = Field(default_factory=list)
    trade_qualifications: List[TradeQualificationEntry] = Field(default_factory=list)
    languages: List[LanguageEntry] = Field(default_factory=list)
    awards: List[AwardEntry] = Field(default_factory=list)
    quality_flags: CVQualityFlags = Field(default_factory=CVQualityFlags)
