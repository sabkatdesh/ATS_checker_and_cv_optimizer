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

from pydantic import BaseModel, Field

from app.domain.common import NullSafeListMixin, SeniorityLevel
from app.domain.cv.domain_config import Domain

# ─── Meta ───────────────────────────────────────────────────────────────────────


class UniversalCVMeta(BaseModel):
    full_name: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    # Optional profession-specific links stored as {label: url} pairs
    # e.g. {"GitHub": "github.com/x", "Portfolio": "x.com", "BNMC": "reg#12345"}
    optional_links: dict[str, str] | None = Field(default_factory=dict)


# ─── Skills ─────────────────────────────────────────────────────────────────────


class UniversalSkillBlock(NullSafeListMixin, BaseModel):
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    # Kept for tech/finance; empty for other domains
    frameworks: list[str] = Field(default_factory=list)
    cloud_platforms: list[str] = Field(default_factory=list)


# ─── Work experience ────────────────────────────────────────────────────────────


class EmploymentType(str, Enum):  # noqa: UP042
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    VOLUNTEER = "volunteer"


class WorkExperienceEntry(NullSafeListMixin, BaseModel):
    job_title: str
    company_name: str | None = None
    employment_type: EmploymentType | None = None
    start_date: date | None = None
    end_date: date | None = None  # None = Present
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)


class ExperienceSummary(BaseModel):
    total_years: float | None = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: str | None = None  # IC / Lead / Manager / Clinician / etc.
    relevant_years: float | None = None


# ─── Education ──────────────────────────────────────────────────────────────────


class EducationEntry(NullSafeListMixin, BaseModel):
    degree: str | None = None
    field_of_study: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    grade: str | None = None  # CGPA, GPA, distinction, etc.


# ─── Certifications ─────────────────────────────────────────────────────────────


class CertificationEntry(NullSafeListMixin, BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None
    expiry_year: int | None = None
    credential_id: str | None = None


# ─── Projects (tech / creative) ─────────────────────────────────────────────────


class ProjectEntry(NullSafeListMixin, BaseModel):
    title: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


# ─── Publications (academic / medical / legal) ──────────────────────────────────


class PublicationEntry(BaseModel):
    title: str
    journal_or_venue: str | None = None
    year: int | None = None
    authors: str | None = None  # "Author A, Author B, ..."
    doi_or_url: str | None = None


# ─── Licenses & registrations (medical / trades / legal) ────────────────────────


class LicenseEntry(BaseModel):
    name: str  # e.g. "BNMC Registered Nurse"
    issuing_body: str | None = None
    license_number: str | None = None
    valid_until: str | None = None  # date string or "Active"


# ─── Clinical practice (medical) ────────────────────────────────────────────────


class ClinicalEntry(NullSafeListMixin, BaseModel):
    setting: str  # e.g. "ICU", "General Surgery Ward"
    role: str | None = None
    institution: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    responsibilities: list[str] = Field(default_factory=list)


# ─── Trade qualifications (trades) ──────────────────────────────────────────────


class TradeQualificationEntry(BaseModel):
    qualification: str  # e.g. "BTEB NC-3 Electrical Technology"
    certifying_body: str | None = None
    year: int | None = None


# ─── Languages ──────────────────────────────────────────────────────────────────


class LanguageEntry(BaseModel):
    language: str
    proficiency: str | None = None  # Native / Fluent / Professional / Basic


# ─── Volunteering ───────────────────────────────────────────────────────────────


class VolunteerEntry(NullSafeListMixin, BaseModel):
    organization: str
    role: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None


# ─── Awards ─────────────────────────────────────────────────────────────────────


class AwardEntry(BaseModel):
    title: str
    issuer: str | None = None
    year: int | None = None
    description: str | None = None


# ─── Quality flags ──────────────────────────────────────────────────────────────


class CVQualityFlags(BaseModel):
    missing_dates: bool = False
    missing_contact: bool = False
    weak_metrics: bool = False
    low_confidence_extraction: bool = False
    detected_language: str | None = None  # "en" / "bn" / "mixed"


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
    professional_summary: str | None = None
    skills: UniversalSkillBlock = Field(default_factory=UniversalSkillBlock)
    experience_summary: ExperienceSummary = Field(default_factory=ExperienceSummary)
    work_experience: list[WorkExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)

    # ── Optional (domain-driven) ─────────────────────────────────────────────────
    certifications: list[CertificationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)  # tech / creative
    publications: list[PublicationEntry] = Field(
        default_factory=list
    )  # medical / education / legal
    licenses: list[LicenseEntry] = Field(default_factory=list)  # medical / trades / legal
    clinical_practice: list[ClinicalEntry] = Field(default_factory=list)  # medical
    trade_qualifications: list[TradeQualificationEntry] = Field(default_factory=list)  # trades
    languages: list[LanguageEntry] = Field(default_factory=list)  # all (shown when non-trivial)
    volunteering: list[VolunteerEntry] = Field(default_factory=list)  # general / education
    awards: list[AwardEntry] = Field(default_factory=list)  # education / finance / legal
    references_available: bool = False

    quality_flags: CVQualityFlags = Field(default_factory=CVQualityFlags)
