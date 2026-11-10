"""Stage 1/2 extraction and eligibility-verdict prompts."""

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured, SummaryJD
from app.domain.match.schemas import Match, SummaryCV

parser_quick_cv: PydanticOutputParser[SummaryCV] = PydanticOutputParser(pydantic_object=SummaryCV)
parser_quick_jd: PydanticOutputParser[SummaryJD] = PydanticOutputParser(pydantic_object=SummaryJD)
parser_verdict: PydanticOutputParser[Match] = PydanticOutputParser(pydantic_object=Match)
parser_detailed_jd: PydanticOutputParser[JobDescriptionStructured] = PydanticOutputParser(
    pydantic_object=JobDescriptionStructured
)
parser_detailed_cv: PydanticOutputParser[UniversalCVStructured] = PydanticOutputParser(
    pydantic_object=UniversalCVStructured
)


# ── Stage 1 — Quick extraction prompts ──────────────────────────────────────────

QUICK_CV_PROMPT = PromptTemplate(
    template=(
        "Extract a concise summary from this CV. "
        "Also classify the profession into one of these domains: "
        "tech (software engineers, data scientists, IT), "
        "medical (doctors, nurses, healthcare workers), "
        "education (teachers, lecturers, professors, academics), "
        "trades (electricians, plumbers, mechanics, construction workers), "
        "finance (accountants, analysts, bankers, auditors), "
        "legal (lawyers, advocates, barristers, legal counsel), "
        "creative (designers, artists, copywriters, marketers), "
        "general (anything else). "
        "Set the domain field accordingly.\n\n"
        "CV:\n{user_resume}\n\n"
        "{format_instructions}"
    ),
    input_variables=["user_resume"],
    partial_variables={"format_instructions": parser_quick_cv.get_format_instructions()},
)

QUICK_JD_PROMPT = PromptTemplate(
    template=(
        "Extract a concise summary from this Job Description. "
        "Also classify the profession into one of these domains: "
        "tech, medical, education, trades, finance, legal, creative, general. "
        "Set the domain field accordingly.\n\n"
        "Job Description:\n{job_description}\n\n"
        "{format_instructions}"
    ),
    input_variables=["job_description"],
    partial_variables={"format_instructions": parser_quick_jd.get_format_instructions()},
)


# ── Stage 1 — Eligibility verdict prompt ────────────────────────────────────────

VERDICT_PROMPT = PromptTemplate(
    template=(
        "Assess whether this candidate is eligible for this position.\n\n"
        "Profession Domain: {domain}\n\n"
        "Job Description:\n"
        "  Title: {jd_job}\n"
        "  Required Experience: {jd_experience} years\n"
        "  Key Requirements: {jd_tools}\n"
        "  Summary: {jd_summary}\n\n"
        "Candidate:\n"
        "  Current Role: {cv_job}\n"
        "  Experience: {cv_experience} years\n"
        "  Key Competencies: {cv_tools}\n"
        "  Summary: {cv_summary}\n"
        "  Education: {cv_education}\n"
        "  Projects / Portfolio: {cv_project}\n\n"
        "Domain-aware focus:\n"
        "  - For 'tech': weight tools, frameworks, and experience level.\n"
        "  - For 'medical': weight clinical experience, licenses, and specialisation — not cloud tools.\n"
        "  - For 'education': weight teaching experience, subject expertise, and qualifications.\n"
        "  - For 'trades': weight trade certifications, safety training, and hands-on experience.\n"
        "  - For 'finance': weight analytical skills, regulatory knowledge, and domain certifications.\n"
        "  - For 'legal': weight bar membership, practice areas, and case experience.\n"
        "  - For 'creative': weight portfolio quality, design skills, and relevant software.\n"
        "  - For 'general': use balanced judgement across all dimensions.\n\n"
        "Provide a score and list the top gaps to address.\n\n"
        "{format_instructions}"
    ),
    input_variables=[
        "domain",
        "jd_job",
        "jd_experience",
        "jd_tools",
        "jd_summary",
        "cv_job",
        "cv_experience",
        "cv_tools",
        "cv_summary",
        "cv_education",
        "cv_project",
    ],
    partial_variables={"format_instructions": parser_verdict.get_format_instructions()},
)


# ── Stage 2 — Detailed extraction prompts ───────────────────────────────────────

DETAILED_JD_PROMPT = PromptTemplate(
    template=(
        "Extract all information from this Job Description into the structured format. "
        "Include the profession domain.\n\n"
        "Job Description:\n{job_description}\n\n"
        "{format_instructions}"
    ),
    input_variables=["job_description"],
    partial_variables={"format_instructions": parser_detailed_jd.get_format_instructions()},
)

DETAILED_CV_PROMPT = PromptTemplate(
    template=(
        "Extract all information from this CV into the structured format. "
        "This is a {domain} professional — populate the domain-appropriate optional blocks "
        "(licenses, clinical_practice, trade_qualifications, publications, etc.) where present.\n\n"
        "CV:\n{user_resume}\n\n"
        "{format_instructions}"
    ),
    input_variables=["user_resume", "domain"],
    partial_variables={"format_instructions": parser_detailed_cv.get_format_instructions()},
)
