"""CV rewrite prompt and domain guidance."""

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.cv.rewrite import RewrittenCV

parser_rewrite: PydanticOutputParser[RewrittenCV] = PydanticOutputParser(
    pydantic_object=RewrittenCV
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
        "domain",
        "domain_guidance",
        "target_words",
        "max_roles",
        "max_skills",
        "max_projects",
        "max_publications",
        "max_certs",
        "must_have_missing",
        "skills_missing",
        "tools_missing",
        "user_feedback",
        "cv_text",
        "jd_text",
        "ats_score",
        "title_alignment",
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
