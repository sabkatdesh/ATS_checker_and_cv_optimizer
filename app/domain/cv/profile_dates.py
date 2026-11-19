"""Lenient dates from a saved profile: ISO forms, month names and Bangla digits."""

import re
from datetime import date, datetime

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_OPEN_ENDED = frozenset({"", "present", "current", "now", "ongoing"})
_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
_ISO = re.compile(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?")
_MONTH_YEAR = re.compile(r"([a-z]+)\.?\s+(\d{4})")


def to_ascii_digits(text: str) -> str:
    return text.translate(_BANGLA_DIGITS)


def _build(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_profile_date(value: object) -> date | None:
    """A profile date, or None when open-ended (Present/Current), empty or unreadable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = to_ascii_digits(value).strip().lower()
    if text in _OPEN_ENDED:
        return None
    if iso := _ISO.fullmatch(text):
        year, month, day = (int(part) if part else 1 for part in iso.groups())
        return _build(year, month, day)
    if (named := _MONTH_YEAR.fullmatch(text)) and named.group(1) in _MONTHS:
        return _build(int(named.group(2)), _MONTHS[named.group(1)], 1)
    return None
