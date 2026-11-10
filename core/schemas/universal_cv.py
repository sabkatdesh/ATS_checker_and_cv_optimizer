"""
Universal CV schema — works for all professions.

Core blocks (all domains):
    meta, professional_summary, skills, work_experience, education

Optional blocks (domain-dependent, all default to empty list):
    projects, publications, licenses, certifications,
    clinical_practice, trade_qualifications, languages,
    volunteering, awards

The domain field drives which blocks the pipeline populates and
which sections the PDF renderer includes.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator

from core.schemas.domain_config import Domain


# ─── Null-safe mixin ────────────────────────────────────────────────────────────

class NullSafeListMixin:
    """Coerces None → [] for all List fields. Guards against LLM returning null."""

    @model_validator(mode="before")
    @classmethod
    def coerce_none_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        fields = cls.model_fields if hasattr(cls, "model_fields") else {}
        for key, value in data.items():
            if value is None and key in fields:
                annotation = str(fields[key].annotation)
                if "List" in annotation or "list" in annotation:
                    data[key] = []
        return data


# ─── Seniority ──────────────────────────────────────────────────────────────────

class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    UNKNOWN = "unknown"


# ─── Meta ───────────────────────────────────────────────────────────────────────

class UniversalCVMeta(BaseModel):
    full_name: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    # Optional profession-specific links stored as {label: url} pairs
    # e.g. {"GitHub": "github.com/x", "Portfolio": "x.com", "BNMC": "reg#12345"}
    optional_links: Optional[dict[str, str]] = Field(default_factory=dict)


# ─── Skills ─────────────────────────────────────────────────────────────────────

class UniversalSkillBlock(NullSafeListMixin, BaseModel):
    hard_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    # Kept for tech/finance; empty for other domains
    frameworks: List[str] = Field(default_factory=list)
    cloud_platforms: List[str] = Field(default_factory=list)


# ─── Work experience ────────────────────────────────────────────────────────────

class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    VOLUNTEER = "volunteer"


class WorkExperienceEntry(NullSafeListMixin, BaseModel):
    job_title: str
    company_name: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None  # None = Present
    responsibilities: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    tools_used: List[str] = Field(default_factory=list)


class ExperienceSummary(BaseModel):
    total_years: Optional[float] = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: Optional[str] = None  # IC / Lead / Manager / Clinician / etc.
    relevant_years: Optional[float] = None


# ─── Education ──────────────────────────────────────────────────────────────────

class EducationEntry(NullSafeListMixin, BaseModel):
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = None
    grade: Optional[str] = None  # CGPA, GPA, distinction, etc.


# ─── Certifications ─────────────────────────────────────────────────────────────

class CertificationEntry(NullSafeListMixin, BaseModel):
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None
    expiry_year: Optional[int] = None
    credential_id: Optional[str] = None


# ─── Projects (tech / creative) ─────────────────────────────────────────────────

class ProjectEntry(NullSafeListMixin, BaseModel):
    title: str
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    url: Optional[str] = None


# ─── Publications (academic / medical / legal) ──────────────────────────────────

class PublicationEntry(BaseModel):
    title: str
    journal_or_venue: Optional[str] = None
    year: Optional[int] = None
    authors: Optional[str] = None  # "Author A, Author B, ..."
    doi_or_url: Optional[str] = None


# ─── Licenses & registrations (medical / trades / legal) ────────────────────────

class LicenseEntry(BaseModel):
    name: str                          # e.g. "BNMC Registered Nurse"
    issuing_body: Optional[str] = None
    license_number: Optional[str] = None
    valid_until: Optional[str] = None  # date string or "Active"


# ─── Clinical practice (medical) ────────────────────────────────────────────────

class ClinicalEntry(NullSafeListMixin, BaseModel):
    setting: str                       # e.g. "ICU", "General Surgery Ward"
    role: Optional[str] = None
    institution: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    responsibilities: List[str] = Field(default_factory=list)


# ─── Trade qualifications (trades) ──────────────────────────────────────────────

class TradeQualificationEntry(BaseModel):
    qualification: str                 # e.g. "BTEB NC-3 Electrical Technology"
    certifying_body: Optional[str] = None
    year: Optional[int] = None


# ─── Languages ──────────────────────────────────────────────────────────────────

class LanguageEntry(BaseModel):
    language: str
    proficiency: Optional[str] = None  # Native / Fluent / Professional / Basic


# ─── Volunteering ───────────────────────────────────────────────────────────────

class VolunteerEntry(NullSafeListMixin, BaseModel):
    organization: str
    role: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None


# ─── Awards ─────────────────────────────────────────────────────────────────────

class AwardEntry(BaseModel):
    title: str
    issuer: Optional[str] = None
    year: Optional[int] = None
    description: Optional[str] = None


# ─── Quality flags ──────────────────────────────────────────────────────────────

class CVQualityFlags(BaseModel):
    missing_dates: bool = False
    missing_contact: bool = False
    weak_metrics: bool = False
    low_confidence_extraction: bool = False
    detected_language: Optional[str] = None  # "en" / "bn" / "mixed"


# ─── Universal CV (top-level) ────────────────────────────────────────────────────

class UniversalCVStructured(NullSafeListMixin, BaseModel):
    """
    Single CV schema covering all professions.
    Core blocks are always populated; optional blocks are populated
    only when the domain and source data warrant it.
    """

    # Domain classification — set by pipeline during Stage 1 extraction
    domain: Domain = Domain.GENERAL

    # ── Core (all domains) ──────────────────────────────────────────────────────
    meta: UniversalCVMeta = Field(default_factory=UniversalCVMeta)
    professional_summary: Optional[str] = None
    skills: UniversalSkillBlock = Field(default_factory=UniversalSkillBlock)
    experience_summary: ExperienceSummary = Field(default_factory=ExperienceSummary)
    work_experience: List[WorkExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)

    # ── Optional (domain-driven) ─────────────────────────────────────────────────
    certifications: List[CertificationEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)             # tech / creative
    publications: List[PublicationEntry] = Field(default_factory=list)     # medical / education / legal
    licenses: List[LicenseEntry] = Field(default_factory=list)             # medical / trades / legal
    clinical_practice: List[ClinicalEntry] = Field(default_factory=list)   # medical
    trade_qualifications: List[TradeQualificationEntry] = Field(default_factory=list)  # trades
    languages: List[LanguageEntry] = Field(default_factory=list)           # all (shown when non-trivial)
    volunteering: List[VolunteerEntry] = Field(default_factory=list)       # general / education
    awards: List[AwardEntry] = Field(default_factory=list)                 # education / finance / legal
    references_available: bool = False

    quality_flags: CVQualityFlags = Field(default_factory=CVQualityFlags)
