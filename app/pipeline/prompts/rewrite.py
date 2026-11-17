"""CV rewrite prompt and domain guidance."""

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.cv.rewrite import RewrittenCV
from app.pipeline.prompts.domain_guidance import DOMAIN_REWRITE_GUIDANCE, get_domain_guidance

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

__all__ = ["DOMAIN_REWRITE_GUIDANCE", "REWRITE_PROMPT", "get_domain_guidance", "parser_rewrite"]
