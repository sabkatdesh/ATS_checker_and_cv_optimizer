"""
Input validation for CV and Job Description text.

Usage (functional):
    from app.domain.parsing.input_validator import validate_jd, validate_cv

Usage (class):
    validator = InputValidator()
    result = validator.validate_jd(text)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_JD_WORDS = 100
MIN_CV_WORDS = 80
MAX_INPUT_CHARS = 15_000
MIN_UNIQUE_WORDS = 8  # gibberish gate

JD_SIGNALS = [
    # English
    "responsibilities",
    "requirements",
    "qualifications",
    "experience",
    "salary",
    "benefits",
    "role",
    "position",
    "candidate",
    "job",
    "skills",
    "apply",
    "employer",
    "team",
    "company",
    "hiring",
    "full-time",
    "part-time",
    "remote",
    "hybrid",
    "years of experience",
    "we are looking",
    "you will",
    "about the role",
    "about the job",
    # Bangla transliterations (common in BD job postings)
    "দায়িত্ব",
    "যোগ্যতা",
    "অভিজ্ঞতা",
    "বেতন",
    "পদ",
    "প্রার্থী",
    "চাকরি",
    "আবেদন",
    "দক্ষতা",
    "নিয়োগ",
    "প্রতিষ্ঠান",
]

CV_SIGNALS = [
    "experience",
    "education",
    "skills",
    "summary",
    "objective",
    "work",
    "university",
    "degree",
    "project",
    "certification",
    "linkedin",
    "github",
    "email",
    "phone",
    "graduated",
    "bachelor",
    "master",
    "b.sc",
    "m.sc",
    "mba",
    "engineer",
    "developer",
    "manager",
    "analyst",
    "intern",
    # Bangla CV signals
    "শিক্ষা",
    "দক্ষতা",
    "অভিজ্ঞতা",
    "প্রকল্প",
    "সনদ",
]

_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f1e0-\U0001f1ff"
    "\U00002500-\U00002bef"
    "\U00002702-\U000027b0"
    "\U000024c2-\U0001f251"
    "]+",
    flags=re.UNICODE,
)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-z]{2,}", re.IGNORECASE)


@dataclass
class ValidationResult:
    is_valid: bool
    error_code: str | None  # TOO_SHORT | TOO_LONG | NOT_A_JD | NOT_A_CV | EMPTY | GIBBERISH
    user_message: str | None
    word_count: int = 0
    application_email: str | None = None  # extracted from JD when present


def _strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub(" ", text)


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text.strip()))


def _count_unique_words(text: str) -> int:
    return len(set(re.findall(r"\b\w+\b", text.lower().strip())))


def _has_signals(text: str, keywords: list[str], min_hits: int = 2) -> bool:
    lower = text.lower()
    return sum(1 for kw in keywords if kw in lower) >= min_hits


def _extract_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    return match.group(0).lower() if match else None


def validate_jd(text: str) -> ValidationResult:
    if not text or not text.strip():
        return ValidationResult(False, "EMPTY", "Please provide a Job Description.")

    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(
            False,
            "TOO_LONG",
            f"The Job Description is too long ({len(text):,} characters). "
            "Please paste only the relevant job posting (max ~10 pages).",
        )

    # Gibberish check before stripping — must have enough unique words
    if _count_unique_words(text) < MIN_UNIQUE_WORDS:
        return ValidationResult(
            False,
            "GIBBERISH",
            "This doesn't look like a real Job Description. Please paste the actual job posting.",
        )

    clean = _strip_emojis(text)
    wc = _count_words(clean)

    if wc < MIN_JD_WORDS:
        return ValidationResult(
            False,
            "TOO_SHORT",
            f"Your Job Description is too short ({wc} words). "
            f"Please paste the full job posting — we need at least {MIN_JD_WORDS} words.",
            wc,
        )

    if not _has_signals(clean, JD_SIGNALS):
        return ValidationResult(
            False,
            "NOT_A_JD",
            "This doesn't look like a Job Description. "
            "Please paste the actual job posting, which should include responsibilities, "
            "requirements, and role details.",
            wc,
        )

    return ValidationResult(True, None, None, wc, application_email=_extract_email(text))


def validate_cv(text: str) -> ValidationResult:
    if not text or not text.strip():
        return ValidationResult(False, "EMPTY", "Please provide a CV / Resume.")

    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(
            False,
            "TOO_LONG",
            f"Your CV is too long ({len(text):,} characters). "
            "Please paste a clean text version (max ~10 pages).",
        )

    if _count_unique_words(text) < MIN_UNIQUE_WORDS:
        return ValidationResult(
            False, "GIBBERISH", "This doesn't look like a real CV. Please paste your actual resume."
        )

    clean = _strip_emojis(text)
    wc = _count_words(clean)

    if wc < MIN_CV_WORDS:
        return ValidationResult(
            False,
            "TOO_SHORT",
            f"Your CV seems too short ({wc} words). Please paste your full resume.",
            wc,
        )

    if not _has_signals(clean, CV_SIGNALS):
        return ValidationResult(
            False,
            "NOT_A_CV",
            "This doesn't look like a CV or Resume. "
            "Please paste your actual resume with experience, skills, and education.",
            wc,
        )

    return ValidationResult(True, None, None, wc)


class InputValidator:
    """Class wrapper for dependency-injection use cases."""

    def validate_jd(self, text: str) -> ValidationResult:
        return validate_jd(text)

    def validate_cv(self, text: str) -> ValidationResult:
        return validate_cv(text)
