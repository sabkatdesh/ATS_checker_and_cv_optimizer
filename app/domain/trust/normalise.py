"""Text and number normalisation shared by claim extraction and matching."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.domain.text.invisible import strip_invisible

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_DROP_CATEGORIES = ("P", "S")  # punctuation and symbols; marks (Bangla vowel signs) stay


def to_ascii_digits(text: str) -> str:
    return text.translate(_BANGLA_DIGITS)


def normalise_text(s: str) -> str:
    """Casefold, Bangla digits to ASCII, punctuation and markup to spaces, collapse whitespace."""
    text = unicodedata.normalize("NFC", to_ascii_digits(strip_invisible(s))).casefold()
    chars = (" " if unicodedata.category(c)[0] in _DROP_CATEGORIES else c for c in text)
    return " ".join("".join(chars).split())


_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|"
    "july|august|september|october|november|december"
)
_DATE_WORDS = rf"(?:{_MONTHS}|in|since|from|until|till|during|year|circa)"
_DATE_FORMS = re.compile(
    r"(?<![\d.])(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}[/.-]\d{1,2}(?:[/.-]\d{1,2})?"
    r"|\d{1,2}[/.-]\d{4}|24/7)(?![\d.])"
)
_CURRENCY_GLUE = re.compile(r"(BDT|Tk\.?|৳|\$)(?=\d)", re.IGNORECASE)
_NUMBER = re.compile(
    r"(?<![\w.])(?P<num>\d{1,3}(?:(?:,| (?=\d{3}(?!\d)))\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<suf>\s?%|[kK](?![\w])|M(?![\w])|)(?![^\W\d_])(?!\d)"
)
_YEAR_BEFORE = re.compile(rf"(?:\b{_DATE_WORDS}\.?|[-–—]|\d{{4}}\s*(?:[-–—]|to))\s*$", re.I)
_YEAR_AFTER = re.compile(r"^\s*(?:[-–—]|to\b)\s*(?:\d{4}|present|current|now|date)", re.I)
_MULTIPLIER = {"k": Decimal(1000), "m": Decimal(1_000_000)}


def _is_date_year(text: str, match: re.Match[str]) -> bool:
    raw = match.group("num")
    if match.group("suf") or not (len(raw) == 4 and raw.isdigit() and 1950 <= int(raw) <= 2100):
        return False
    before = text[max(0, match.start() - 20) : match.start()]
    after = text[match.end() : match.end() + 20]
    return bool(_YEAR_BEFORE.search(before) or _YEAR_AFTER.search(after))


def parse_numbers(text: str) -> list[Decimal]:
    """Numeric values in reading order; date forms and years in date context are left out."""
    text = _CURRENCY_GLUE.sub(r"\1 ", to_ascii_digits(strip_invisible(text)))
    text = _DATE_FORMS.sub(" ", text)
    values: list[Decimal] = []
    for match in _NUMBER.finditer(text):
        if _is_date_year(text, match):
            continue
        try:
            value = Decimal(re.sub(r"[ ,]", "", match.group("num")))
        except InvalidOperation:  # pragma: no cover - the pattern only admits digits
            continue
        suffix = match.group("suf").strip().lower()
        values.append((value * _MULTIPLIER.get(suffix, Decimal(1))).normalize())
    return values


_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "dozen": 12,
    "এক": 1, "দুই": 2, "তিন": 3, "চার": 4, "পাঁচ": 5, "ছয়": 6, "সাত": 7, "আট": 8, "নয়": 9, "দশ": 10,
}  # fmt: skip
_WORD_NUMBERS = {normalise_text(word): Decimal(value) for word, value in _WORDS.items()}


def word_numbers(text_norm: str) -> set[Decimal]:
    """Small spelled-out numbers ("four years", "পাঁচ বছর"), so a source may support "4 years"."""
    return {_WORD_NUMBERS[t] for t in text_norm.split() if t in _WORD_NUMBERS}


def number_key(value: Decimal) -> str:
    """Plain decimal text without exponent: Decimal("4E+1") -> "40"."""
    return format(value.normalize(), "f")
