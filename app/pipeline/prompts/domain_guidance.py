"""Domain-specific rewrite guidance strings."""

# ── Domain-specific rewrite guidance strings ────────────────────────────────────

DOMAIN_REWRITE_GUIDANCE = {
    "tech": (
        "Optimise for ATS scanning: use the job's exact terms in the skills section where the CV "
        "supports them. Lead bullet points with strong verbs (Designed, Built, Deployed, "
        "Optimised). Quantify impact only with numbers the CV states. GitHub/portfolio link "
        "prominent."
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
