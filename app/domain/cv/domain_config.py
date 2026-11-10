"""
Domain classification and per-domain configuration.

- Domain: 8-value enum covering all professions
- DOMAIN_BLOCK_ORDER: which CV sections appear and in what order per domain
- DOMAIN_BUDGET_RULES: word/section limits per domain + seniority tier
"""

from typing import Any

from app.domain.cv.domain_budget_rules import DOMAIN_BUDGET_RULES  # noqa: F401
from app.domain.cv.domain_enum import Domain as Domain

# Which blocks are rendered and in what order for each domain.
# Keys match block names on UniversalCVStructured.
# The PDF renderer uses this list to decide section order and visibility.
DOMAIN_BLOCK_ORDER: dict[str, list[str]] = {
    Domain.TECH: [
        "meta",
        "professional_summary",
        "skills",
        "work_experience",
        "projects",
        "education",
        "certifications",
        "languages",
    ],
    Domain.MEDICAL: [
        "meta",
        "licenses",
        "professional_summary",
        "clinical_practice",
        "work_experience",
        "education",
        "publications",
        "certifications",
        "languages",
    ],
    Domain.EDUCATION: [
        "meta",
        "professional_summary",
        "certifications",
        "work_experience",
        "education",
        "publications",
        "skills",
        "awards",
        "volunteering",
        "languages",
    ],
    Domain.TRADES: [
        "meta",
        "licenses",
        "trade_qualifications",
        "skills",
        "work_experience",
        "education",
        "certifications",
        "languages",
    ],
    Domain.FINANCE: [
        "meta",
        "professional_summary",
        "skills",
        "work_experience",
        "education",
        "certifications",
        "awards",
        "languages",
    ],
    Domain.LEGAL: [
        "meta",
        "licenses",
        "professional_summary",
        "work_experience",
        "education",
        "publications",
        "awards",
        "languages",
    ],
    Domain.CREATIVE: [
        "meta",
        "professional_summary",
        "projects",
        "skills",
        "work_experience",
        "education",
        "certifications",
        "languages",
    ],
    Domain.GENERAL: [
        "meta",
        "professional_summary",
        "skills",
        "work_experience",
        "education",
        "certifications",
        "projects",
        "volunteering",
        "languages",
    ],
}

# Domains where full ATS keyword scoring applies (corporate ATS scanners).
# Other domains skip ATS scoring and get a simplified eligibility check.
ATS_SCORING_DOMAINS: set[str] = {Domain.TECH, Domain.FINANCE, Domain.LEGAL}


def get_budget(domain: Domain | str, total_years: float) -> dict[str, Any]:
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
