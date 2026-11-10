"""Backward-compatibility shim. New code should import from core.parsers.input_validator."""
from core.parsers.input_validator import (
    validate_jd, validate_cv, InputValidator, ValidationResult,
    MIN_JD_WORDS, MIN_CV_WORDS, MAX_INPUT_CHARS, JD_SIGNALS, CV_SIGNALS,
)

__all__ = [
    "validate_jd", "validate_cv", "InputValidator", "ValidationResult",
    "MIN_JD_WORDS", "MIN_CV_WORDS", "MAX_INPUT_CHARS", "JD_SIGNALS", "CV_SIGNALS",
]
