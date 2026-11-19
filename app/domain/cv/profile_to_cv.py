"""A saved profile (legacy `cv_profiles` row) to a validated UniversalCVStructured, no LLM.

Entries are validated one by one: an invalid entry is dropped and counted, never fatal.
Keys that are neither CV data nor known row metadata are counted as unknown.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain.cv.domain_config import Domain
from app.domain.cv.profile_entries import (
    EDUCATION_ALIASES,
    WORK_ALIASES,
    clean_entry,
    clean_text,
    clean_value,
    text_list,
)
from app.domain.cv.profile_text import ProfileBuilder
from app.domain.cv.universal_cv import (
    AwardEntry,
    CertificationEntry,
    ClinicalEntry,
    EducationEntry,
    ExperienceSummary,
    LanguageEntry,
    LicenseEntry,
    ProjectEntry,
    PublicationEntry,
    TradeQualificationEntry,
    UniversalCVMeta,
    UniversalCVStructured,
    UniversalSkillBlock,
    VolunteerEntry,
    WorkExperienceEntry,
)

_ROW_METADATA = frozenset(
    {"user_id", "id", "preferred_template", "accent_color", "bangla_mode"}
    | {"created_at", "updated_at"}
)
_META = ("full_name", "email", "phone", "location", "linkedin")
_LINKS = {"github": "GitHub", "portfolio": "Portfolio"}
_SECTIONS: dict[str, type[BaseModel]] = {
    "work_experience": WorkExperienceEntry,
    "education": EducationEntry,
    "certifications": CertificationEntry,
    "projects": ProjectEntry,
    "publications": PublicationEntry,
    "licenses": LicenseEntry,
    "clinical_practice": ClinicalEntry,
    "trade_qualifications": TradeQualificationEntry,
    "languages": LanguageEntry,
    "volunteering": VolunteerEntry,
    "awards": AwardEntry,
}
_ENTRY_ALIASES: dict[type[BaseModel], dict[str, str]] = {
    WorkExperienceEntry: WORK_ALIASES,
    EducationEntry: EDUCATION_ALIASES,
}
_ALIAS_OF = {"professional_summary": "summary", "work_experience": "experience"}
# experience_summary is not a cv_profiles column; it is accepted for profiles stored as CV data.
_KNOWN_KEYS = (
    _ROW_METADATA
    | set(_META)
    | set(_LINKS)
    | set(_SECTIONS)
    | set(_ALIAS_OF)
    | set(_ALIAS_OF.values())
    | {"skills", "domain", "references_available", "experience_summary"}
)
_DOMAINS = frozenset(d.value for d in Domain)


@dataclass(frozen=True)
class ProfileConversion:
    cv: UniversalCVStructured
    dropped_entries: int
    unknown_keys: int


class _Counter:
    def __init__(self) -> None:
        self.dropped = 0

    def validate[M: BaseModel](self, model: type[M], value: object) -> M | None:
        if isinstance(value, dict):
            try:
                return model.model_validate(clean_entry(value, _ENTRY_ALIASES.get(model)))
            except ValidationError:
                pass
        self.dropped += 1
        return None

    def section(self, model: type[BaseModel], value: object) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            self.dropped += 1
            return []
        return [entry for entry in (self.validate(model, v) for v in value) if entry is not None]


def _field(profile: Mapping[str, Any], name: str) -> Any:
    """The canonical key wins over its legacy alias (summary, experience)."""
    if name in profile:
        return profile[name]
    alias = _ALIAS_OF.get(name)
    return profile.get(alias) if alias else None


def _skills(value: object, counter: _Counter) -> UniversalSkillBlock:
    if isinstance(value, dict):
        return UniversalSkillBlock(
            **{name: text_list(value.get(name)) for name in UniversalSkillBlock.model_fields}
        )
    if value is not None and not isinstance(value, list | str):
        counter.dropped += 1
    return UniversalSkillBlock(hard_skills=text_list(value))


def _domain(profile: Mapping[str, Any]) -> Domain:
    stored = profile.get("domain")
    if isinstance(stored, str) and stored in _DOMAINS:
        return Domain(stored)
    return ProfileBuilder.detect_domain(dict(profile))


def _years(work: list[WorkExperienceEntry], today: date) -> float | None:
    """Years covered by the work history, overlapping roles counted once."""
    spans = sorted((w.start_date, w.end_date or today) for w in work if w.start_date)
    if not spans:
        return None
    days, cursor = 0, spans[0][0]
    for start, end in spans:
        start = max(start, cursor)
        if end > start:
            days += (end - start).days
            cursor = end
    return round(days / 365.25, 1)


def _experience_summary(
    value: object, work: list[WorkExperienceEntry], counter: _Counter, today: date
) -> ExperienceSummary:
    if value is not None:
        summary = counter.validate(ExperienceSummary, value)
        if summary is not None:
            return summary
    return ExperienceSummary(total_years=_years(work, today))


def profile_to_universal_cv(
    profile: Mapping[str, Any], *, today: date | None = None
) -> ProfileConversion:
    counter = _Counter()
    links = {label: text for key, label in _LINKS.items() if (text := clean_text(profile.get(key)))}
    meta = UniversalCVMeta(**{k: clean_text(profile.get(k)) for k in _META}, optional_links=links)
    sections = {name: counter.section(m, _field(profile, name)) for name, m in _SECTIONS.items()}
    summary = _experience_summary(
        profile.get("experience_summary"),
        sections["work_experience"],
        counter,
        today or date.today(),
    )
    cv = UniversalCVStructured.model_validate(
        {
            "domain": _domain(profile),
            "meta": meta,
            "professional_summary": clean_text(_field(profile, "professional_summary")),
            "skills": _skills(clean_value(profile.get("skills")), counter),
            "experience_summary": summary,
            "references_available": profile.get("references_available") is True,
            **sections,
        }
    )
    unknown = sum(1 for key in profile if key not in _KNOWN_KEYS)
    return ProfileConversion(cv=cv, dropped_entries=counter.dropped, unknown_keys=unknown)
