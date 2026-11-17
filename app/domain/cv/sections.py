"""CV section names and the deterministic restore of sections a rewrite dropped (D2, E3)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, get_args

from pydantic import BaseModel

from app.domain.common import SeniorityLevel
from app.domain.cv.universal_cv import UniversalCVStructured

if TYPE_CHECKING:
    from app.domain.cv.rewrite import RewrittenCV

SectionName = Literal[
    "meta",
    "professional_summary",
    "skills",
    "experience_summary",
    "work_experience",
    "education",
    "certifications",
    "projects",
    "publications",
    "licenses",
    "clinical_practice",
    "trade_qualifications",
    "languages",
    "volunteering",
    "awards",
    "references_available",
]
SECTIONS: tuple[SectionName, ...] = get_args(SectionName)
PROTECTED_SECTIONS: tuple[SectionName, ...] = (
    "education",
    "licenses",
    "certifications",
    "clinical_practice",
    "trade_qualifications",
)
_CONTACT_FIELDS = ("full_name", "location", "email", "phone", "linkedin", "optional_links")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


_ENTRY_KEY: dict[str, Callable[[Any], tuple[str, ...]]] = {
    "education": lambda e: (_norm(e.degree), _norm(e.institution)),
    "licenses": lambda e: (_norm(e.name),),
    "certifications": lambda e: (_norm(e.name),),
    "clinical_practice": lambda e: (_norm(e.setting), _norm(e.institution)),
    "trade_qualifications": lambda e: (_norm(e.qualification),),
}


def _filled(value: Any) -> bool:
    if isinstance(value, SeniorityLevel):
        return value != SeniorityLevel.UNKNOWN
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, BaseModel):
        return any(_filled(getattr(value, f)) for f in type(value).model_fields)
    if isinstance(value, list | dict):
        return bool(value)
    return value is not None and value is not False


def present_sections(cv: UniversalCVStructured) -> frozenset[SectionName]:
    return frozenset(name for name in SECTIONS if _filled(getattr(cv, name)))


def _restore_meta(source: UniversalCVStructured, output: RewrittenCV) -> dict[str, Any]:
    refill = {
        f: copy.deepcopy(getattr(source.meta, f))
        for f in _CONTACT_FIELDS
        if _filled(getattr(source.meta, f)) and not _filled(getattr(output.meta, f))
    }
    return {"meta": output.meta.model_copy(update=refill)} if refill else {}


def _restore_entries(source: list[Any], output: list[Any], section: str) -> list[Any] | None:
    key = _ENTRY_KEY[section]
    kept = {key(e) for e in output}
    missing = [copy.deepcopy(e) for e in source if key(e) not in kept]
    return [*output, *missing] if missing else None


def restore_dropped(
    source: UniversalCVStructured, output: RewrittenCV
) -> tuple[RewrittenCV, list[SectionName]]:
    """Copy back dropped sections and protected entries; return the restored section names."""
    update: dict[str, Any] = {}
    restored: list[SectionName] = []
    for name in SECTIONS:
        if name == "meta":
            meta = _restore_meta(source, output)
            update |= meta
            restored += ["meta"] if meta else []
            continue
        src, out = getattr(source, name), getattr(output, name)
        if not _filled(src):
            continue
        if not _filled(out):
            update[name] = copy.deepcopy(src)
        elif name in PROTECTED_SECTIONS:
            merged = _restore_entries(src, out, name)
            if merged is None:
                continue
            update[name] = merged
        else:
            continue
        restored.append(name)
    return (output.model_copy(update=update) if update else output), restored
