"""Clean one saved-profile entry before validation: trimmed strings, lenient dates and years."""

from typing import Any

from app.domain.cv.profile_dates import parse_profile_date, to_ascii_digits
from app.domain.cv.universal_cv import EmploymentType
from app.domain.text.invisible import strip_invisible

_DATE_FIELDS = frozenset({"start_date", "end_date"})
_YEAR_FIELDS = frozenset({"graduation_year", "year", "expiry_year"})
# Older profile rows used shorter names in work and education entries.
WORK_ALIASES = {"title": "job_title", "company": "company_name"}
EDUCATION_ALIASES = {"field": "field_of_study"}
_EMPLOYMENT_TYPES = frozenset(t.value for t in EmploymentType)


def clean_text(value: object) -> str | None:
    """A trimmed string without invisible characters; blank or non-string values become None."""
    if not isinstance(value, str):
        return None
    return strip_invisible(value).strip() or None


def clean_value(value: object) -> Any:
    """Trim every string inside a JSON value; blank strings become None, blank list items go."""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [item for item in (clean_value(v) for v in value) if item is not None]
    if isinstance(value, dict):
        return {key: clean_value(item) for key, item in value.items()}
    return value


def text_list(value: object) -> list[str]:
    """A list of strings from a list or a comma-separated string."""
    items = value.split(",") if isinstance(value, str) else value
    if not isinstance(items, list):
        return []
    return [text for text in (clean_text(item) for item in items) if text]


def _year(value: object) -> object:
    if isinstance(value, str):
        digits = to_ascii_digits(value).strip()
        return int(digits) if digits.isdigit() else None
    return value


def _employment_type(value: object) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    normalised = text.lower().replace("-", "_").replace(" ", "_")
    return normalised if normalised in _EMPLOYMENT_TYPES else None


def clean_entry(entry: dict[str, Any], aliases: dict[str, str] | None = None) -> dict[str, Any]:
    """Field values a section model can validate; unreadable dates and years become None."""
    out: dict[str, Any] = {}
    for key, value in entry.items():
        name = (aliases or {}).get(key, key)
        if name != key and name in entry:
            continue  # the canonical field wins over its legacy alias
        if name in _DATE_FIELDS:
            out[name] = parse_profile_date(value)
        elif name in _YEAR_FIELDS:
            out[name] = _year(value)
        elif name == "employment_type":
            out[name] = _employment_type(value)
        else:
            out[name] = clean_value(value)
    return out
