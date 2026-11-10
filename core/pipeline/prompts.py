"""
All LLM prompt templates — centralized.

Import pattern:
    from core.pipeline.prompts import QUICK_CV_PROMPT, QUICK_JD_PROMPT, ...
"""
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from core.schemas.match_schemas import SummaryCV, Match
from core.schemas.jd_schemas import SummaryJD, JobDescriptionStructured
from core.schemas.universal_cv import UniversalCVStructured
from core.schemas.rewrite_schemas import RewrittenCV
from core.schemas.cover_letter_schemas import CoverLetterStructured


# ── Parsers ─────────────────────────────────────────────────────────────────────

parser_quick_cv = PydanticOutputParser(pydantic_object=SummaryCV)
parser_quick_jd = PydanticOutputParser(pydantic_object=SummaryJD)
parser_verdict = PydanticOutputParser(pydantic_object=Match)
parser_detailed_jd = PydanticOutputParser(pydantic_object=JobDescriptionStructured)
parser_detailed_cv = PydanticOutputParser(pydantic_object=UniversalCVStructured)
parser_rewrite = PydanticOutputParser(pydantic_object=RewrittenCV)
parser_cover_letter = PydanticOutputParser(pydantic_object=CoverLetterStructured)


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
        "jd_job", "jd_experience", "jd_tools", "jd_summary",
        "cv_job", "cv_experience", "cv_tools", "cv_summary",
        "cv_education", "cv_project",
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


# ── Stage 2 — CV rewrite prompt ─────────────────────────────────────────────────

REWRITE_PROMPT = PromptTemplate(
    template="""
╔══════════════════════════════════════════════════════════════════╗
║  CRITICAL — EVIDENCE-ONLY RULE (NON-NEGOTIABLE)                  ║
║  You may ONLY rewrite and reorder facts that already exist in    ║
║  the CV. Never invent job titles, dates, metrics, company names, ║
║  certifications, skills, or technologies not already present.    ║
║  If a JD requirement has no supporting evidence, skip it         ║
║  silently. Fabricating content is strictly forbidden.            ║
╚══════════════════════════════════════════════════════════════════╝

You are a senior CV strategist specialising in {domain} profession CVs.
Rewrite the CV to best match this job description while respecting strict limits.

═══════════════════════════════════════════════════════
DOMAIN: {domain}
═══════════════════════════════════════════════════════

BUDGET LIMITS (hard constraints):
• Target word count: {target_words}
• Max work experience roles: {max_roles}
• Max hard skills: {max_skills}
• Max projects: {max_projects} (0 = not applicable for this domain)
• Max publications: {max_publications} (0 = not applicable for this domain)
• Max certifications: {max_certs}

═══════════════════════════════════════════════════════
DOMAIN-SPECIFIC GUIDANCE
═══════════════════════════════════════════════════════

{domain_guidance}

═══════════════════════════════════════════════════════
ATS / KEYWORD GAPS (for ATS-relevant domains only)
═══════════════════════════════════════════════════════

Must-Have Missing: {must_have_missing}
Skills Missing: {skills_missing}
Tools Missing: {tools_missing}

═══════════════════════════════════════════════════════
USER FEEDBACK ON GAPS (from HITL checkpoint)
═══════════════════════════════════════════════════════

{user_feedback}

═══════════════════════════════════════════════════════
WRITING RULES
═══════════════════════════════════════════════════════

1. Use exact terminology from the JD where it truthfully matches the CV.
2. Improve measurable impact — add numbers where the CV hints at them.
3. Prioritise JD-relevant keywords in skills/tools fields.
4. Avoid repetition and keyword stuffing.
5. Keep tone professional and domain-appropriate.
6. Never leave empty section headings — if a block has nothing, omit it entirely.

═══════════════════════════════════════════════════════

CURRENT CV (JSON):
{cv_text}

JOB DESCRIPTION (JSON):
{jd_text}

ATS SCORE (current): {ats_score}%
Title Alignment Suggestion: {title_alignment}

═══════════════════════════════════════════════════════

Return ONLY a single valid JSON object — no markdown, no explanation, no code fences.
The JSON must have the same top-level keys as the input CV JSON (meta, professional_summary,
skills, experience_summary, work_experience, education, certifications, projects, etc.).
Preserve every field that exists; rewrite only the text content where relevant.
""",
    input_variables=[
        "domain", "domain_guidance",
        "target_words", "max_roles", "max_skills",
        "max_projects", "max_publications", "max_certs",
        "must_have_missing", "skills_missing", "tools_missing",
        "user_feedback",
        "cv_text", "jd_text", "ats_score", "title_alignment",
    ],
)


# ── Domain-specific rewrite guidance strings ────────────────────────────────────

DOMAIN_REWRITE_GUIDANCE = {
    "tech": (
        "Optimise for ATS keyword scanning. Place exact JD keywords in the skills section. "
        "Lead bullet points with strong verbs (Designed, Built, Deployed, Optimised). "
        "Quantify impact (e.g. 'reduced latency by 40%'). GitHub/portfolio link prominent."
    ),
    "medical": (
        "Lead with licenses and clinical practice — these are the primary screening criteria. "
        "Use standard clinical terminology matching the JD (e.g. ICU, CCU, paediatric). "
        "List specialisations explicitly. Publications are valued for senior roles. "
        "Do NOT add cloud platforms or coding tools unless already in the CV."
    ),
    "education": (
        "Lead with teaching philosophy and subject expertise. "
        "Highlight curriculum design, assessment methods, and student outcomes. "
        "Publications and research outputs are important for academic roles. "
        "Use subject-specific terminology from the JD."
    ),
    "trades": (
        "Lead with trade licenses and certifications — these are mandatory screening criteria. "
        "List specific trade qualifications (BTEB, NVQ, City & Guilds, etc.) prominently. "
        "Emphasise safety certifications and years of hands-on experience. "
        "Keep language direct and practical."
    ),
    "finance": (
        "Emphasise regulatory knowledge (BSEC, IFRS, local standards) and analytical tools. "
        "Quantify portfolio sizes, cost savings, or revenue impact where present. "
        "Professional qualifications (CFA, ACCA, CPA) should be prominently listed. "
        "Use precise financial terminology from the JD."
    ),
    "legal": (
        "Lead with bar membership, practice areas, and jurisdiction. "
        "Reference specific legislation and case types matching the JD. "
        "Publications and academic credentials valued for senior roles. "
        "Precise, formal language expected."
    ),
    "creative": (
        "Portfolio link must be prominent in the header. "
        "Lead with high-impact projects and tools (Figma, Adobe Suite, etc.). "
        "Describe the creative brief, your process, and measurable outcomes. "
        "Match the design/brand language the JD signals."
    ),
    "general": (
        "Match the JD's required experience level and core competencies. "
        "Lead with the most relevant work experience for this role. "
        "Use terminology from the JD where it truthfully applies. "
        "Balanced presentation of skills, experience, and education."
    ),
}


def get_domain_guidance(domain: str) -> str:
    return DOMAIN_REWRITE_GUIDANCE.get(domain, DOMAIN_REWRITE_GUIDANCE["general"])


# ── Cover Letter prompt ─────────────────────────────────────────────────────────

COVER_LETTER_PROMPT = PromptTemplate(
    template="""\
You are an expert cover letter writer. Write a cover letter for the candidate below.

STRICT RULES — follow every rule or the output is unusable:
1. NEVER invent achievements, skills, or claims not present in the CV or tailored CV.
2. Every body paragraph must cite ONE specific achievement from the CV and link it to ONE requirement from the JD.
3. Requirements with no supporting CV evidence are silently skipped — do NOT mention them.
4. Salutation: use the hiring manager's name if detectable in the JD, otherwise "Dear Hiring Manager,".
5. No generic opener like "I am writing to apply for...". Open with a hook tied to the role.
6. Tone: {tone}. Length: {length} (~{word_target} words total body).
7. Sign-off: "Sincerely," for formal tone; "Best regards," for conversational.

CANDIDATE CV (tailored/rewritten):
{cv_text}

JOB DESCRIPTION:
{jd_text}

GAPS (evidence missing — do NOT fill these by invention):
{gaps}

{format_instructions}
""",
    input_variables=["tone", "length", "word_target", "cv_text", "jd_text", "gaps"],
    partial_variables={"format_instructions": parser_cover_letter.get_format_instructions()},
)
