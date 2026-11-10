"""
Job Description extraction schemas.
Used in Stage 1 (quick summary) and Stage 2 (detailed extraction).
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from core.schemas.universal_cv import NullSafeListMixin
from core.schemas.domain_config import Domain


class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    UNKNOWN = "unknown"


# ─── Quick extraction (Stage 1 — eligibility check) ─────────────────────────────

class SummaryJD(NullSafeListMixin, BaseModel):
    """Lightweight JD summary used for fast eligibility check."""
    domain: Domain = Domain.GENERAL
    summary: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    Job: Optional[str] = None
    responsiblity: Optional[str] = None
    experience: Optional[int] = None
    subject: List[str] = Field(default_factory=list)


# ─── Detailed extraction (Stage 2 — ATS + rewrite) ──────────────────────────────

class JDSkillBlock(NullSafeListMixin, BaseModel):
    hard_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    cloud_platforms: List[str] = Field(default_factory=list)


class JDExperienceBlock(NullSafeListMixin, BaseModel):
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: Optional[str] = None


class JDEducationBlock(NullSafeListMixin, BaseModel):
    degree_required: Optional[str] = None
    degree_preferred: Optional[str] = None
    fields_of_study: List[str] = Field(default_factory=list)


class JDRequirementBlock(NullSafeListMixin, BaseModel):
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)


class JDResponsibilityBlock(NullSafeListMixin, BaseModel):
    responsibilities: List[str] = Field(default_factory=list)


class JobDescriptionStructured(NullSafeListMixin, BaseModel):
    """Full structured JD used for ATS scoring and rewriting."""
    domain: Domain = Domain.GENERAL
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    summary: Optional[str] = None

    responsibilities: JDResponsibilityBlock = Field(default_factory=JDResponsibilityBlock)
    requirements: JDRequirementBlock = Field(default_factory=JDRequirementBlock)
    skills: JDSkillBlock = Field(default_factory=JDSkillBlock)
    experience: JDExperienceBlock = Field(default_factory=JDExperienceBlock)
    education: JDEducationBlock = Field(default_factory=JDEducationBlock)
