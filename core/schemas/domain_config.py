"""
Domain classification and per-domain configuration.

- Domain: 8-value enum covering all professions
- DOMAIN_BLOCK_ORDER: which CV sections appear and in what order per domain
- DOMAIN_BUDGET_RULES: word/section limits per domain + seniority tier
"""
from enum import Enum


class Domain(str, Enum):
    TECH = "tech"
    MEDICAL = "medical"
    EDUCATION = "education"
    TRADES = "trades"
    FINANCE = "finance"
    LEGAL = "legal"
    CREATIVE = "creative"
    GENERAL = "general"


# Which blocks are rendered and in what order for each domain.
# Keys match block names on UniversalCVStructured.
# The PDF renderer uses this list to decide section order and visibility.
DOMAIN_BLOCK_ORDER: dict[str, list[str]] = {
    Domain.TECH: [
        "meta", "professional_summary", "skills", "work_experience",
        "projects", "education", "certifications", "languages",
    ],
    Domain.MEDICAL: [
        "meta", "licenses", "professional_summary", "clinical_practice",
        "work_experience", "education", "publications", "certifications", "languages",
    ],
    Domain.EDUCATION: [
        "meta", "professional_summary", "certifications", "work_experience",
        "education", "publications", "skills", "awards", "volunteering", "languages",
    ],
    Domain.TRADES: [
        "meta", "licenses", "trade_qualifications", "skills",
        "work_experience", "education", "certifications", "languages",
    ],
    Domain.FINANCE: [
        "meta", "professional_summary", "skills", "work_experience",
        "education", "certifications", "awards", "languages",
    ],
    Domain.LEGAL: [
        "meta", "licenses", "professional_summary", "work_experience",
        "education", "publications", "awards", "languages",
    ],
    Domain.CREATIVE: [
        "meta", "professional_summary", "projects", "skills",
        "work_experience", "education", "certifications", "languages",
    ],
    Domain.GENERAL: [
        "meta", "professional_summary", "skills", "work_experience",
        "education", "certifications", "projects", "volunteering", "languages",
    ],
}

# Domains where full ATS keyword scoring applies (corporate ATS scanners).
# Other domains skip ATS scoring and get a simplified eligibility check.
ATS_SCORING_DOMAINS: set[str] = {Domain.TECH, Domain.FINANCE, Domain.LEGAL}

# Per-domain, per-seniority budget rules.
# target_words: approximate word count for the full CV text
# max_roles: max number of work experience entries to include
# max_skills: max hard_skills list length
# max_projects / max_publications / max_certs: section item limits
DOMAIN_BUDGET_RULES: dict[str, dict[str, dict]] = {
    Domain.TECH: {
        "fresher":    {"target_words": 650,  "max_roles": 2, "max_skills": 12, "max_projects": 2, "max_certs": 1},
        "junior_mid": {"target_words": 850,  "max_roles": 3, "max_skills": 18, "max_projects": 2, "max_certs": 2},
        "mid_senior": {"target_words": 1000, "max_roles": 5, "max_skills": 22, "max_projects": 2, "max_certs": 3},
        "senior":     {"target_words": 1100, "max_roles": 6, "max_skills": 25, "max_projects": 2, "max_certs": 3},
    },
    Domain.MEDICAL: {
        "fresher":    {"target_words": 700,  "max_roles": 2, "max_skills": 10, "max_publications": 0, "max_certs": 2},
        "junior_mid": {"target_words": 900,  "max_roles": 3, "max_skills": 12, "max_publications": 2, "max_certs": 3},
        "mid_senior": {"target_words": 1200, "max_roles": 5, "max_skills": 14, "max_publications": 5, "max_certs": 4},
        "senior":     {"target_words": 1500, "max_roles": 8, "max_skills": 15, "max_publications": 10, "max_certs": 5},
    },
    Domain.EDUCATION: {
        "fresher":    {"target_words": 700,  "max_roles": 2, "max_skills": 10, "max_publications": 0, "max_certs": 2},
        "junior_mid": {"target_words": 900,  "max_roles": 3, "max_skills": 12, "max_publications": 3, "max_certs": 3},
        "mid_senior": {"target_words": 1200, "max_roles": 5, "max_skills": 14, "max_publications": 8, "max_certs": 4},
        "senior":     {"target_words": 2000, "max_roles": 8, "max_skills": 15, "max_publications": 20, "max_certs": 5},
    },
    Domain.TRADES: {
        "fresher":    {"target_words": 500,  "max_roles": 2, "max_skills": 10, "max_certs": 2},
        "junior_mid": {"target_words": 600,  "max_roles": 3, "max_skills": 12, "max_certs": 3},
        "mid_senior": {"target_words": 700,  "max_roles": 4, "max_skills": 15, "max_certs": 4},
        "senior":     {"target_words": 800,  "max_roles": 5, "max_skills": 18, "max_certs": 5},
    },
    Domain.FINANCE: {
        "fresher":    {"target_words": 650,  "max_roles": 2, "max_skills": 12, "max_certs": 2},
        "junior_mid": {"target_words": 850,  "max_roles": 3, "max_skills": 16, "max_certs": 3},
        "mid_senior": {"target_words": 1000, "max_roles": 5, "max_skills": 20, "max_certs": 4},
        "senior":     {"target_words": 1100, "max_roles": 6, "max_skills": 22, "max_certs": 4},
    },
    Domain.LEGAL: {
        "fresher":    {"target_words": 700,  "max_roles": 2, "max_skills": 10, "max_publications": 0, "max_certs": 2},
        "junior_mid": {"target_words": 900,  "max_roles": 3, "max_skills": 12, "max_publications": 2, "max_certs": 2},
        "mid_senior": {"target_words": 1100, "max_roles": 5, "max_skills": 14, "max_publications": 5, "max_certs": 3},
        "senior":     {"target_words": 1300, "max_roles": 7, "max_skills": 16, "max_publications": 10, "max_certs": 3},
    },
    Domain.CREATIVE: {
        "fresher":    {"target_words": 500,  "max_roles": 2, "max_skills": 12, "max_projects": 3, "max_certs": 1},
        "junior_mid": {"target_words": 700,  "max_roles": 3, "max_skills": 16, "max_projects": 4, "max_certs": 2},
        "mid_senior": {"target_words": 850,  "max_roles": 4, "max_skills": 18, "max_projects": 5, "max_certs": 2},
        "senior":     {"target_words": 1000, "max_roles": 5, "max_skills": 20, "max_projects": 6, "max_certs": 3},
    },
    Domain.GENERAL: {
        "fresher":    {"target_words": 600,  "max_roles": 2, "max_skills": 12, "max_projects": 2, "max_certs": 1},
        "junior_mid": {"target_words": 800,  "max_roles": 3, "max_skills": 16, "max_projects": 2, "max_certs": 2},
        "mid_senior": {"target_words": 950,  "max_roles": 5, "max_skills": 20, "max_projects": 2, "max_certs": 3},
        "senior":     {"target_words": 1100, "max_roles": 6, "max_skills": 22, "max_projects": 2, "max_certs": 3},
    },
}


def get_budget(domain: Domain | str, total_years: float) -> dict:
    """Return the budget rules for a given domain and experience level."""
    d = Domain(domain) if isinstance(domain, str) else domain
    rules = DOMAIN_BUDGET_RULES.get(d, DOMAIN_BUDGET_RULES[Domain.GENERAL])
    if total_years <= 1:
        tier = "fresher"
    elif total_years <= 3:
        tier = "junior_mid"
    elif total_years <= 5:
        tier = "mid_senior"
    else:
        tier = "senior"
    return rules.get(tier, rules["senior"])


def get_block_order(domain: Domain | str) -> list[str]:
    """Return the ordered list of CV section names for a given domain."""
    d = Domain(domain) if isinstance(domain, str) else domain
    return DOMAIN_BLOCK_ORDER.get(d, DOMAIN_BLOCK_ORDER[Domain.GENERAL])


def should_run_ats(domain: Domain | str) -> bool:
    """Return True if full ATS keyword scoring should run for this domain."""
    d = Domain(domain) if isinstance(domain, str) else domain
    return d in ATS_SCORING_DOMAINS
