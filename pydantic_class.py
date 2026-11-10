from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Literal, Any
from enum import Enum
from datetime import date

# ============================================================
# GLOBAL SAFE COERCION MIXIN
# ============================================================
# Add this to ANY model that has List fields the LLM might null-out
class NullSafeListMixin:
    """Mixin that coerces None → [] for all list fields automatically"""

    @model_validator(mode='before')
    @classmethod
    def coerce_none_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key, value in data.items():
            if value is None:
                # Get field annotation
                fields = cls.model_fields if hasattr(cls, 'model_fields') else {}
                if key in fields:
                    annotation = str(fields[key].annotation)
                    if 'List' in annotation or 'list' in annotation:
                        data[key] = []
        return data



# eligibility checking
class SummaryCV(NullSafeListMixin, BaseModel):
    summary: Optional[str] = Field(default=None, description="Summary of the given CV")
    tools: Optional[List[str]] = Field(default_factory=list, description="Tools used in the CV")
    Job: Optional[str] = Field(default=None, description="Profession of the user in the CV")
    project: Optional[str] = Field(default=None, description="Project of the user in the CV")
    hidden_tools: Optional[List[str]] = Field(default_factory=list, description="Tools or techniques that might have used or needed to do those projects", max_length=15)
    experience: Optional[int] = Field(default=None, description="Experience of the user in the CV")
    education: Optional[List[str]] = Field(default_factory=list, description="Education degrees found in CV")
    subject: Optional[List[str]] = Field(default_factory=list, description="Subject of education the user in the CV")

class SummaryJD(NullSafeListMixin, BaseModel):
    summary: Optional[str] = Field(default=None, description="Summary of the given Job description")
    tools: Optional[List[str]] = Field(default_factory=list, description="Tools using requirements in the Job description")
    Job: Optional[str] = Field(default=None, description="Which job the Job description is for?")
    responsiblity: Optional[str] = Field(default=None, description="What kind of work the Job description is for or, what the employee would need to do?")
    experience: Optional[int] = Field(default=None, description="Experience required for the CV")
    subject: Optional[List[str]] = Field(default_factory=list, description="Subject of education require in the CV")

class Match(NullSafeListMixin, BaseModel):
    score: Optional[Literal[0, 30, 60, 100]] = Field(default=None, description="Relevance Score of the CV to the Job Description e.g gradually increase for more relevance")
    verdict: Optional[Literal["Doesn't Align at all 0%", "Somewhat Align 30%", "Partially Align 60%", "Perfectly Align 100%"]] = Field(default=None, description="Is this CV aligns with the Job Description?")
    reason: Optional[List[str]] = Field(default_factory=list, description="Reason for matching", max_length=5)
    gaps_to_consider: Optional[List[str]] = Field(default_factory=list)


#The Job Description part
class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    UNKNOWN = "unknown"

class SkillBlock(NullSafeListMixin,BaseModel):
    hard_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    cloud_platforms: List[str] = Field(default_factory=list)

class ExperienceBlock(NullSafeListMixin,BaseModel):
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: Optional[str] = None  # IC / Lead / Manager

class EducationBlock(NullSafeListMixin,BaseModel):
    degree_required: Optional[str] = None
    degree_preferred: Optional[str] = None
    fields_of_study: List[str] = Field(default_factory=list)

class RequirementBlock(NullSafeListMixin,BaseModel):
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)

class ResponsibilityBlock(NullSafeListMixin,BaseModel):
    responsibilities: List[str] = Field(default_factory=list)

class JobDescriptionStructured(NullSafeListMixin,BaseModel):
    # Core Identity
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None  # Full-time, Contract, Remote

    # JD Content
    summary: Optional[str] = None
    responsibilities: ResponsibilityBlock
    requirements: RequirementBlock

    # Deep Extraction
    skills: SkillBlock
    experience: ExperienceBlock
    education: EducationBlock





#The User CV Part

class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"

class UserMeta(BaseModel):
    full_name: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None
    github: Optional[str] = None

class UserSkillBlock(NullSafeListMixin,BaseModel):
    hard_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    cloud_platforms: List[str] = Field(default_factory=list)

class WorkExperienceEntry(NullSafeListMixin,BaseModel):
    job_title: str
    company_name: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None  # None = Present
    responsibilities: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    tools_used: List[str] = Field(default_factory=list)

class ExperienceSummary(NullSafeListMixin,BaseModel):
    total_years: Optional[float] = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: Optional[str] = None  # IC / Lead / Manager
    relevant_years: Optional[float] = None

class EducationEntry(NullSafeListMixin,BaseModel):
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = None

class Certification(NullSafeListMixin,BaseModel):
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None

class ProjectEntry(NullSafeListMixin,BaseModel):
    title: str
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list, description="Technologies used in the Project")

class CVQualityFlags(BaseModel):
    missing_dates: bool = False
    missing_skills: bool = False
    weak_metrics: bool = False
    low_confidence_extraction: bool = False

class UserCVStructured(NullSafeListMixin,BaseModel):
    meta: UserMeta

    professional_summary: Optional[str] = None

    skills: UserSkillBlock

    experience_summary: ExperienceSummary
    work_experience: List[WorkExperienceEntry] = Field(default_factory=list)

    education: List[EducationEntry] = Field(default_factory=list)
    certifications: List[Certification] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)

    quality_flags: CVQualityFlags



#CV Writing part

class Re_write_EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"

class Re_write_UserMeta(BaseModel):
    full_name: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None
    github: Optional[str] = None

class Re_write_UserSkillBlock(NullSafeListMixin,BaseModel):
    hard_skills: List[str] = Field(default_factory=list, max_length=25)
    soft_skills: List[str] = Field(default_factory=list, max_length=5)
    tools: List[str] = Field(default_factory=list, max_length=15)
    frameworks: List[str] = Field(default_factory=list, max_length=10)
    cloud_platforms: List[str] = Field(default_factory=list, max_length=5)

class Re_write_WorkExperienceEntry(NullSafeListMixin,BaseModel):
    job_title: str
    company_name: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    responsibilities: List[str] = Field(default_factory=list, max_length=4)
    achievements: List[str] = Field(default_factory=list, max_length=2)

    tools_used: List[str] = Field(default_factory=list, max_length=8)

class Re_write_ExperienceSummary(BaseModel):
    total_years: Optional[float] = None
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    role_type: Optional[str] = None  # IC / Lead / Manager
    relevant_years: Optional[float] = None

class Re_write_EducationEntry(BaseModel):
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = None

class Re_write_Certification(BaseModel):
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None

class Re_write_ProjectEntry(NullSafeListMixin,BaseModel):
    title: str
    description: Optional[str] = Field(default=None, max_length=400)
    technologies: List[str] = Field(default_factory=list, max_length=8)

class Re_write_CVQualityFlags(BaseModel):
    missing_dates: bool = False
    missing_skills: bool = False
    weak_metrics: bool = False
    low_confidence_extraction: bool = False

class Re_write_UserCVStructured(NullSafeListMixin,BaseModel):
    meta: Re_write_UserMeta

    professional_summary: Optional[str] = Field(default=None, max_length=700)

    skills: Re_write_UserSkillBlock

    experience_summary: Re_write_ExperienceSummary

    work_experience: List[Re_write_WorkExperienceEntry] = Field(default_factory=list)

    education: List[Re_write_EducationEntry] = Field(default_factory=list)

    certifications: List[Re_write_Certification] = Field(default_factory=list, max_length=3)

    projects: List[Re_write_ProjectEntry] = Field(default_factory=list, max_length=2)

    quality_flags: Re_write_CVQualityFlags

#Budget
BUDGET_RULES = {
    "fresher": {
        "target_words": 650,
        "max_roles": 1,
        "max_recent_bullets": 4,
        "max_old_bullets": 0,
        "max_skills": 12,
        "max_projects": 2,
        "max_certs": 1
    },
    "junior_mid": {
        "target_words": 850,
        "max_roles": 3,
        "max_recent_bullets": 5,
        "max_old_bullets": 3,
        "max_skills": 18,
        "max_projects": 2,
        "max_certs": 2
    },
    "mid_senior": {
        "target_words": 1000,
        "max_roles": 5,
        "max_recent_bullets": 6,
        "max_old_bullets": 4,
        "max_skills": 22,
        "max_projects": 2,
        "max_certs": 3
    },
    "senior": {
        "target_words": 1100,
        "max_roles": 6,
        "max_recent_bullets": 6,
        "max_old_bullets": 3,
        "max_skills": 25,
        "max_projects": 2,
        "max_certs": 3
    }
}