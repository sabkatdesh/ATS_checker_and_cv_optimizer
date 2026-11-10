"""
Input validation for CV and Job Description text.

Usage (functional — backward compatible):
    from core.parsers.input_validator import validate_jd, validate_cv

Usage (class):
    validator = InputValidator()
    result = validator.validate_jd(text)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

MIN_JD_WORDS = 100
MIN_CV_WORDS = 80
MAX_INPUT_CHARS = 15_000

JD_SIGNALS = [
    "responsibilities", "requirements", "qualifications", "experience",
    "salary", "benefits", "role", "position", "candidate", "job",
    "skills", "apply", "employer", "team", "company", "hiring",
    "full-time", "part-time", "remote", "hybrid", "years of experience",
    "we are looking", "you will", "about the role", "about the job",
]

CV_SIGNALS = [
    "experience", "education", "skills", "summary", "objective",
    "work", "university", "degree", "project", "certification",
    "linkedin", "github", "email", "phone", "graduated",
    "bachelor", "master", "b.sc", "m.sc", "mba", "engineer",
    "developer", "manager", "analyst", "intern",
]


@dataclass
class ValidationResult:
    is_valid: bool
    error_code: Optional[str]   # "TOO_SHORT" | "TOO_LONG" | "NOT_A_JD" | "NOT_A_CV" | "EMPTY"
    user_message: Optional[str]
    word_count: int = 0


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text.strip()))


def _has_signals(text: str, keywords: list, min_hits: int = 2) -> bool:
    lower = text.lower()
    return sum(1 for kw in keywords if kw in lower) >= min_hits


def validate_jd(text: str) -> ValidationResult:
    if not text or not text.strip():
        return ValidationResult(False, "EMPTY", "Please provide a Job Description.")
    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(False, "TOO_LONG",
            f"The Job Description is too long ({len(text):,} characters). "
            f"Please paste only the relevant job posting (max ~10 pages).")
    wc = _count_words(text)
    if wc < MIN_JD_WORDS:
        return ValidationResult(False, "TOO_SHORT",
            f"Your Job Description is too short ({wc} words). "
            f"Please paste the full job posting — we need at least {MIN_JD_WORDS} words.", wc)
    if not _has_signals(text, JD_SIGNALS):
        return ValidationResult(False, "NOT_A_JD",
            "This doesn't look like a Job Description. "
            "Please paste the actual job posting, which should include responsibilities, "
            "requirements, and role details.", wc)
    return ValidationResult(True, None, None, wc)


def validate_cv(text: str) -> ValidationResult:
    if not text or not text.strip():
        return ValidationResult(False, "EMPTY", "Please provide a CV / Resume.")
    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(False, "TOO_LONG",
            f"Your CV is too long ({len(text):,} characters). "
            f"Please paste a clean text version (max ~10 pages).")
    wc = _count_words(text)
    if wc < MIN_CV_WORDS:
        return ValidationResult(False, "TOO_SHORT",
            f"Your CV seems too short ({wc} words). Please paste your full resume.", wc)
    if not _has_signals(text, CV_SIGNALS):
        return ValidationResult(False, "NOT_A_CV",
            "This doesn't look like a CV or Resume. "
            "Please paste your actual resume with experience, skills, and education.", wc)
    return ValidationResult(True, None, None, wc)


class InputValidator:
    """Class wrapper for dependency-injection use cases."""

    def validate_jd(self, text: str) -> ValidationResult:
        return validate_jd(text)

    def validate_cv(self, text: str) -> ValidationResult:
        return validate_cv(text)
