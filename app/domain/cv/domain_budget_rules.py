"""Per-domain, per-seniority CV budget rules."""

from __future__ import annotations

from typing import Any

from app.domain.cv.domain_enum import Domain

# Per-domain, per-seniority budget rules.
# target_words: approximate word count for the full CV text
# max_roles: max number of work experience entries to include
# max_skills: max hard_skills list length
# max_projects / max_publications / max_certs: section item limits
DOMAIN_BUDGET_RULES: dict[str, dict[str, dict[str, Any]]] = {
    Domain.TECH: {
        "fresher": {
            "target_words": 650,
            "max_roles": 2,
            "max_skills": 12,
            "max_projects": 2,
            "max_certs": 1,
        },
        "junior_mid": {
            "target_words": 850,
            "max_roles": 3,
            "max_skills": 18,
            "max_projects": 2,
            "max_certs": 2,
        },
        "mid_senior": {
            "target_words": 1000,
            "max_roles": 5,
            "max_skills": 22,
            "max_projects": 2,
            "max_certs": 3,
        },
        "senior": {
            "target_words": 1100,
            "max_roles": 6,
            "max_skills": 25,
            "max_projects": 2,
            "max_certs": 3,
        },
    },
    Domain.MEDICAL: {
        "fresher": {
            "target_words": 700,
            "max_roles": 2,
            "max_skills": 10,
            "max_publications": 0,
            "max_certs": 2,
        },
        "junior_mid": {
            "target_words": 900,
            "max_roles": 3,
            "max_skills": 12,
            "max_publications": 2,
            "max_certs": 3,
        },
        "mid_senior": {
            "target_words": 1200,
            "max_roles": 5,
            "max_skills": 14,
            "max_publications": 5,
            "max_certs": 4,
        },
        "senior": {
            "target_words": 1500,
            "max_roles": 8,
            "max_skills": 15,
            "max_publications": 10,
            "max_certs": 5,
        },
    },
    Domain.EDUCATION: {
        "fresher": {
            "target_words": 700,
            "max_roles": 2,
            "max_skills": 10,
            "max_publications": 0,
            "max_certs": 2,
        },
        "junior_mid": {
            "target_words": 900,
            "max_roles": 3,
            "max_skills": 12,
            "max_publications": 3,
            "max_certs": 3,
        },
        "mid_senior": {
            "target_words": 1200,
            "max_roles": 5,
            "max_skills": 14,
            "max_publications": 8,
            "max_certs": 4,
        },
        "senior": {
            "target_words": 2000,
            "max_roles": 8,
            "max_skills": 15,
            "max_publications": 20,
            "max_certs": 5,
        },
    },
    Domain.TRADES: {
        "fresher": {"target_words": 500, "max_roles": 2, "max_skills": 10, "max_certs": 2},
        "junior_mid": {"target_words": 600, "max_roles": 3, "max_skills": 12, "max_certs": 3},
        "mid_senior": {"target_words": 700, "max_roles": 4, "max_skills": 15, "max_certs": 4},
        "senior": {"target_words": 800, "max_roles": 5, "max_skills": 18, "max_certs": 5},
    },
    Domain.FINANCE: {
        "fresher": {"target_words": 650, "max_roles": 2, "max_skills": 12, "max_certs": 2},
        "junior_mid": {"target_words": 850, "max_roles": 3, "max_skills": 16, "max_certs": 3},
        "mid_senior": {"target_words": 1000, "max_roles": 5, "max_skills": 20, "max_certs": 4},
        "senior": {"target_words": 1100, "max_roles": 6, "max_skills": 22, "max_certs": 4},
    },
    Domain.LEGAL: {
        "fresher": {
            "target_words": 700,
            "max_roles": 2,
            "max_skills": 10,
            "max_publications": 0,
            "max_certs": 2,
        },
        "junior_mid": {
            "target_words": 900,
            "max_roles": 3,
            "max_skills": 12,
            "max_publications": 2,
            "max_certs": 2,
        },
        "mid_senior": {
            "target_words": 1100,
            "max_roles": 5,
            "max_skills": 14,
            "max_publications": 5,
            "max_certs": 3,
        },
        "senior": {
            "target_words": 1300,
            "max_roles": 7,
            "max_skills": 16,
            "max_publications": 10,
            "max_certs": 3,
        },
    },
    Domain.CREATIVE: {
        "fresher": {
            "target_words": 500,
            "max_roles": 2,
            "max_skills": 12,
            "max_projects": 3,
            "max_certs": 1,
        },
        "junior_mid": {
            "target_words": 700,
            "max_roles": 3,
            "max_skills": 16,
            "max_projects": 4,
            "max_certs": 2,
        },
        "mid_senior": {
            "target_words": 850,
            "max_roles": 4,
            "max_skills": 18,
            "max_projects": 5,
            "max_certs": 2,
        },
        "senior": {
            "target_words": 1000,
            "max_roles": 5,
            "max_skills": 20,
            "max_projects": 6,
            "max_certs": 3,
        },
    },
    Domain.GENERAL: {
        "fresher": {
            "target_words": 600,
            "max_roles": 2,
            "max_skills": 12,
            "max_projects": 2,
            "max_certs": 1,
        },
        "junior_mid": {
            "target_words": 800,
            "max_roles": 3,
            "max_skills": 16,
            "max_projects": 2,
            "max_certs": 2,
        },
        "mid_senior": {
            "target_words": 950,
            "max_roles": 5,
            "max_skills": 20,
            "max_projects": 2,
            "max_certs": 3,
        },
        "senior": {
            "target_words": 1100,
            "max_roles": 6,
            "max_skills": 22,
            "max_projects": 2,
            "max_certs": 3,
        },
    },
}
