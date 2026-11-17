"""Semantic checks on model output (spec 10 section 5.5): no foreign contacts, no markup.

A URL, email or phone number is foreign when the normalised source CV does not contain it.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.text.strings import iter_strings, map_strings

_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'`()\[\]]+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w+])\+?\d[\d ().-]{7,}\d(?!\w)")
_MIN_PHONE_DIGITS = 10
_TRAILING = ".,;:!?"
_META_FIELDS = ("full_name", "location", "email", "phone", "linkedin")

_HTML_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_HEADER = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_STAR = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])")
_UNDERSCORE = re.compile(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])")


def _bare_url(url: str) -> str:
    url = re.sub(r"^(?:https?://)?(?:www\.)?", "", url.lower())
    return url.rstrip("/")


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)[-_MIN_PHONE_DIGITS:]


@dataclass(frozen=True)
class _Allowed:
    blob: str
    phones: frozenset[str]

    @classmethod
    def of(cls, source: UniversalCVStructured) -> "_Allowed":
        texts = [text for _, text in iter_strings(source)]
        blob = "\n".join(_bare_url(t) for t in texts)
        phones = frozenset(
            _digits(m.group()) for t in texts for m in _PHONE.finditer(t) if _is_phone(m.group())
        )
        return cls(blob, phones)

    def url(self, url: str) -> bool:
        return _bare_url(url) in self.blob

    def email(self, email: str) -> bool:
        return email.lower() in self.blob

    def phone(self, phone: str) -> bool:
        return _digits(phone) in self.phones


def _is_phone(text: str) -> bool:
    return len(re.sub(r"\D", "", text)) >= _MIN_PHONE_DIGITS


def _foreign_spans(text: str, allowed: _Allowed) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    taken: list[tuple[int, int]] = []  # every URL and email, kept or not: no phones inside them
    for m in _EMAIL.finditer(text):
        taken.append(m.span())
        if not allowed.email(m.group()):
            spans.append(m.span())
    for m in _URL.finditer(text):
        url = m.group().rstrip(_TRAILING)
        taken.append(m.span())
        if not allowed.url(url):
            spans.append((m.start(), m.start() + len(url)))
    for m in _PHONE.finditer(text):
        inside = any(s < m.end() and m.start() < e for s, e in taken)
        if not inside and _is_phone(m.group()) and not allowed.phone(m.group()):
            spans.append(m.span())
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return text.strip(" \t,;:-|")


class _Scrubber:
    def __init__(self, allowed: _Allowed) -> None:
        self.allowed = allowed
        self.count = 0

    def __call__(self, text: str) -> str:
        spans = _foreign_spans(text, self.allowed)
        if not spans:
            return text
        self.count += len(spans)
        for start, end in reversed(spans):
            text = text[:start] + text[end:]
        return _tidy(text)


def scrub_contacts[M: BaseModel](
    output: M, source: UniversalCVStructured, skip: tuple[str, ...] = ()
) -> tuple[M, int]:
    """Remove foreign URLs, emails and phone numbers from every string; return the count."""
    scrub = _Scrubber(_Allowed.of(source))
    cleaned = map_strings(output, scrub, skip=skip)
    return cleaned, scrub.count


def _has_foreign(value: object, allowed: _Allowed) -> bool:
    if isinstance(value, str):
        return bool(_foreign_spans(value, allowed))
    if isinstance(value, dict):
        return any(_has_foreign(k, allowed) or _has_foreign(v, allowed) for k, v in value.items())
    return False


def remove_foreign_contacts(
    source: UniversalCVStructured, output: RewrittenCV
) -> tuple[RewrittenCV, int]:
    """Meta fields holding a foreign contact go back to the source; elsewhere the contact goes."""
    allowed = _Allowed.of(source)
    reset = {
        name: getattr(source.meta, name)
        for name in (*_META_FIELDS, "optional_links")
        if _has_foreign(getattr(output.meta, name), allowed)
    }
    cleaned, count = scrub_contacts(output, source, skip=("meta",))
    if reset:
        cleaned = cleaned.model_copy(update={"meta": output.meta.model_copy(update=reset)})
    return cleaned, count + len(reset)


def _strip_markup_text(text: str) -> str:
    text = _HTML_TAG.sub("", text)
    text = _HEADER.sub("", text)
    text = _BOLD.sub(lambda m: m.group(1) or m.group(2), text)
    text = _STAR.sub(r"\1", text)
    text = _UNDERSCORE.sub(r"\1", text)
    return text.replace("`", "")


def strip_markup[M: BaseModel](output: M) -> M:
    """Drop HTML tags and markdown emphasis, headers and backticks from every string field."""
    return map_strings(output, _strip_markup_text)
