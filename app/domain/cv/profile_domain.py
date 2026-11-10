"""Keyword-based domain classification for profile dicts."""

from __future__ import annotations

from app.domain.cv.domain_config import Domain


def detect_domain(text_corpus: str, license_text: str) -> Domain:
    """Classify a profile from its lowercased search corpus and licence text."""
    # Medical — licenses/registrations are the strongest signal
    medical_signals = [
        "bnmc",
        "bmc",
        "bmdc",
        "mbbs",
        " md ",
        "registered nurse",
        " rn ",
        "physician",
        "surgeon",
        "clinical",
        "ward",
        "hospital",
        "patient",
        "diagnosis",
        "nursing",
    ]
    if any(s in license_text or s in text_corpus for s in medical_signals):
        return Domain.MEDICAL

    # Trades — trade qualification keywords
    trades_signals = [
        "electrician",
        "electrical",
        "plumber",
        "plumbing",
        "welder",
        "welding",
        "carpenter",
        "bteb",
        "nc-3",
        "nc3",
        "nvq",
        "construction",
        "mechanic",
        "hvac",
        "refrigeration",
    ]
    if any(s in license_text or s in text_corpus for s in trades_signals):
        return Domain.TRADES

    # Education — academic keywords
    education_signals = [
        "teacher",
        "lecturer",
        "professor",
        "phd",
        "thesis",
        "syllabus",
        "curriculum",
        "pedagogy",
        "instruction",
        "classroom",
        "faculty",
        "publication",
        "journal",
        "research paper",
    ]
    if any(s in text_corpus for s in education_signals):
        return Domain.EDUCATION

    # Legal
    legal_signals = [
        "advocate",
        "attorney",
        "barrister",
        "solicitor",
        "llb",
        "llm",
        "bar council",
        "law chamber",
        "litigation",
        "legal counsel",
    ]
    if any(s in text_corpus for s in legal_signals):
        return Domain.LEGAL

    # Finance
    finance_signals = [
        "cfa",
        "cpa",
        "acca",
        "chartered accountant",
        "financial analyst",
        "investment",
        "banking",
        "audit",
        "tax",
        "balance sheet",
        "ledger",
        "portfolio management",
        "equity",
        "fixed income",
    ]
    if any(s in text_corpus for s in finance_signals):
        return Domain.FINANCE

    # Creative
    creative_signals = [
        "designer",
        "ui/ux",
        "ux designer",
        "ui designer",
        "graphic design",
        "illustrator",
        "photoshop",
        "figma",
        "branding",
        "typography",
        "video editor",
        "motion graphic",
        "art director",
        "copywriter",
    ]
    if any(s in text_corpus for s in creative_signals):
        return Domain.CREATIVE

    # Tech — checked last because tech words appear in many domains
    tech_signals = [
        "python",
        "javascript",
        "typescript",
        "java",
        "golang",
        "rust",
        "react",
        "angular",
        "vue",
        "node.js",
        "django",
        "fastapi",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "devops",
        "machine learning",
        "deep learning",
        "data science",
        "sql",
        "postgresql",
        "mongodb",
        "redis",
        "api",
        "backend",
        "frontend",
        "software engineer",
        "developer",
    ]
    if any(s in text_corpus for s in tech_signals):
        return Domain.TECH

    return Domain.GENERAL
