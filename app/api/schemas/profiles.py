from pydantic import BaseModel


class ProfileUpdateRequest(BaseModel):
    # Core fields
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    summary: str | None = None
    skills: dict | None = None
    experience: list | None = None
    education: list | None = None
    projects: list | None = None
    certifications: list | None = None
    # New universal fields (Phase 3)
    domain: str | None = None
    licenses: list | None = None
    publications: list | None = None
    clinical_practice: list | None = None
    trade_qualifications: list | None = None
    languages: list | None = None
    volunteering: list | None = None
    awards: list | None = None
    references_available: bool | None = None
    preferred_template: str | None = None
    accent_color: str | None = None
    bangla_mode: bool | None = None


class ImportCVRequest(BaseModel):
    cv_text: str
