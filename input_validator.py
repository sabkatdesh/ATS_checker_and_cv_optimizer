import re
from dataclasses import dataclass
from typing import Optional

# ── Thresholds ─────────────────────────────────────────────────────────────
MIN_JD_WORDS  = 100       # anything below → "Too short"
MIN_CV_WORDS  = 80        # anything below → "Too short"
MAX_INPUT_CHARS = 15_000  # ~10 pages — prevent token overflow

# ── Signal keywords ────────────────────────────────────────────────────────
# If the input has at least 2 of these, we treat it as a real JD
JD_SIGNALS = [
    "responsibilities", "requirements", "qualifications", "experience",
    "salary", "benefits", "role", "position", "candidate", "job",
    "skills", "apply", "employer", "team", "company", "hiring",
    "full-time", "part-time", "remote", "hybrid", "years of experience",
    "we are looking", "you will", "about the role", "about the job",
]

# If the input has at least 2 of these, we treat it as a real CV
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
    error_code: Optional[str]      # "TOO_SHORT" | "TOO_LONG" | "NOT_A_JD" | "NOT_A_CV" | "EMPTY"
    user_message: Optional[str]    # polite message to show the user
    word_count: int = 0


def _count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text.strip()))


def _has_signals(text: str, keywords: list, min_hits: int = 2) -> bool:
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits >= min_hits


# ── Public API ─────────────────────────────────────────────────────────────

def validate_jd(text: str) -> ValidationResult:
    """
    Returns ValidationResult.
    is_valid=True  → safe to proceed
    is_valid=False → show user_message to the user, do not proceed
    """
    if not text or not text.strip():
        return ValidationResult(False, "EMPTY",
            "Please provide a Job Description.")

    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(False, "TOO_LONG",
            f"The Job Description is too long ({len(text):,} characters). "
            f"Please paste only the relevant job posting (max ~10 pages).")

    word_count = _count_words(text)

    if word_count < MIN_JD_WORDS:
        return ValidationResult(False, "TOO_SHORT",
            f"Your Job Description is too short ({word_count} words). "
            f"Please paste the full job posting — we need at least {MIN_JD_WORDS} words "
            f"to properly analyse it.",
            word_count)

    if not _has_signals(text, JD_SIGNALS, min_hits=2):
        return ValidationResult(False, "NOT_A_JD",
            "This doesn't look like a Job Description. "
            "Please paste the actual job posting, which should include things like "
            "responsibilities, requirements, and the role details.",
            word_count)

    return ValidationResult(True, None, None, word_count)


def validate_cv(text: str) -> ValidationResult:
    """
    Returns ValidationResult.
    is_valid=True  → safe to proceed
    is_valid=False → show user_message to the user, do not proceed
    """
    if not text or not text.strip():
        return ValidationResult(False, "EMPTY",
            "Please provide a CV / Resume.")

    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(False, "TOO_LONG",
            f"Your CV is too long ({len(text):,} characters). "
            f"Please paste a clean text version (max ~10 pages).")

    word_count = _count_words(text)

    if word_count < MIN_CV_WORDS:
        return ValidationResult(False, "TOO_SHORT",
            f"Your CV seems too short ({word_count} words). "
            f"Please paste your full resume.",
            word_count)

    if not _has_signals(text, CV_SIGNALS, min_hits=2):
        return ValidationResult(False, "NOT_A_CV",
            "This doesn't look like a CV or Resume. "
            "Please paste your actual resume, which should include your experience, "
            "skills, and education.",
            word_count)

    return ValidationResult(True, None, None, word_count)