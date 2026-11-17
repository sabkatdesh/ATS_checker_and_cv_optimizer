"""Checkable claims in a CV (names, skills, dates, numbers) and the evidence a source offers."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.domain.cv.sections import SECTIONS, SectionName
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.questions.schemas import GapAnswers
from app.domain.text.strings import iter_strings
from app.domain.trust.aliases import canonical_skill
from app.domain.trust.normalise import normalise_text, number_key, parse_numbers, word_numbers
from app.domain.trust.report import ClaimKind

__all__ = ["Claim", "ClaimKind", "SourceEvidence", "build_evidence", "extract_claims"]

# Per entry section: field -> kind for name claims (names are never also number claims).
NAME_FIELDS: dict[str, dict[str, ClaimKind]] = {
    "work_experience": {"company_name": "employer", "job_title": "title"},
    "education": {"degree": "degree", "institution": "institution"},
    "certifications": {"name": "certification", "issuer": "institution"},
    "licenses": {"name": "licence", "issuing_body": "institution"},
    "clinical_practice": {"institution": "institution", "role": "title"},
    "trade_qualifications": {"qualification": "certification", "certifying_body": "institution"},
    "volunteering": {"organization": "employer", "role": "title"},
}
SKILL_FIELDS: dict[str, str] = {"work_experience": "tools_used", "projects": "technologies"}
DATED_SECTIONS = ("work_experience", "clinical_practice", "volunteering")
_NO_NUMBERS = {"meta", "skills"}
_PART_OF_NAME = {"education": {"field_of_study"}}  # folded into the degree claim


@dataclass(frozen=True)
class Claim:
    kind: ClaimKind
    text: str
    norm: str
    section: SectionName
    entry_key: str | None


def _name_text(section: str, entry: Any, field: str) -> str:
    value = getattr(entry, field) or ""
    if section == "education" and field == "degree" and entry.field_of_study:
        return f"{value} {entry.field_of_study}".strip()
    return str(value)


def _month(value: date | None, missing: str) -> str:
    return value.strftime("%Y-%m") if value else missing


def _entry_claims(section: SectionName, index: int, entry: Any) -> Iterator[Claim]:
    key = f"{section}[{index}]"
    for field, kind in NAME_FIELDS.get(section, {}).items():
        text = _name_text(section, entry, field)
        yield Claim(kind, text, normalise_text(text), section, key)
    if section in SKILL_FIELDS:
        for skill in getattr(entry, SKILL_FIELDS[section]):
            yield Claim("skill", skill, canonical_skill(skill), section, key)
    if section in DATED_SECTIONS:
        start, end = _month(entry.start_date, "none"), _month(entry.end_date, "present")
        yield Claim("date", f"start {start}", f"start:{start}", section, key)
        yield Claim("date", f"end {end}", f"end:{end}", section, key)


def _free_strings(section: str, value: Any) -> Iterator[str]:
    """Strings that are not name or skill fields: bullets, summaries, descriptions, grades."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, BaseModel):
        skip = {*NAME_FIELDS.get(section, {}), *_PART_OF_NAME.get(section, ())}
        skip.add(SKILL_FIELDS.get(section, ""))
        yield from (text for _, text in iter_strings(value, skip=skip))


def _number_claims(section: SectionName, key: str | None, value: Any) -> Iterator[Claim]:
    for text in _free_strings(section, value):
        for number in parse_numbers(text):
            norm = number_key(number)
            yield Claim("number", f"{norm} in: {text}", norm, section, key)


def _section_claims(cv: UniversalCVStructured, section: SectionName) -> Iterator[Claim]:
    value = getattr(cv, section)
    if section == "skills":
        for _, skill in iter_strings(value):
            yield Claim("skill", skill, canonical_skill(skill), section, None)
        return
    if section in _NO_NUMBERS:
        return
    if not isinstance(value, list):
        yield from _number_claims(section, None, value)
        return
    for index, entry in enumerate(value):
        yield from _entry_claims(section, index, entry)
        yield from _number_claims(section, f"{section}[{index}]", entry)


def extract_claims(cv: UniversalCVStructured) -> list[Claim]:
    """Every checkable claim in reading order, without duplicates or empty names."""
    seen: set[tuple[str, str, str, str | None]] = set()
    claims: list[Claim] = []
    for section in SECTIONS:
        for claim in _section_claims(cv, section):
            ident = (claim.kind, claim.norm, claim.section, claim.entry_key)
            if claim.norm and ident not in seen:
                seen.add(ident)
                claims.append(claim)
    return claims


@dataclass(frozen=True)
class SourceEvidence:
    cv_claims: list[Claim]
    answer_text_norm: str
    cv_text_norm: str
    cv_numbers: frozenset[Decimal] = frozenset()
    answer_numbers: frozenset[Decimal] = frozenset()


def _numeric_fields(value: Any) -> Iterator[Decimal]:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        yield Decimal(str(value)).normalize()
    elif isinstance(value, dict):
        for item in value.values():
            yield from _numeric_fields(item)
    elif isinstance(value, list):
        for item in value:
            yield from _numeric_fields(item)


def _numbers(texts: list[str], text_norm: str) -> frozenset[Decimal]:
    parsed = {n for text in texts for n in parse_numbers(text)}
    return frozenset(parsed | word_numbers(text_norm))


def build_evidence(cv: UniversalCVStructured, answers: GapAnswers | None) -> SourceEvidence:
    """Source claims, normalised source text and every source number (answers kept apart)."""
    cv_texts = [text for _, text in iter_strings(cv, skip=("meta",))]
    cv_norm = normalise_text("\n".join(cv_texts))
    numeric = set(_numeric_fields(cv.model_dump(exclude={"meta"})))
    answer_texts: list[str] = []
    if answers is not None and not answers.skipped:
        answer_texts = [*answers.answers.values(), answers.free_text or ""]
    answer_norm = normalise_text("\n".join(answer_texts))
    return SourceEvidence(
        cv_claims=extract_claims(cv),
        answer_text_norm=answer_norm,
        cv_text_norm=cv_norm,
        cv_numbers=_numbers(cv_texts, cv_norm) | numeric,
        answer_numbers=_numbers(answer_texts, answer_norm),
    )
