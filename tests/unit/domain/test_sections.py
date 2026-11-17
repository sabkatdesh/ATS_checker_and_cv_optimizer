from typing import Any

import pytest

from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.sections import (
    PROTECTED_SECTIONS,
    SECTIONS,
    present_sections,
    restore_dropped,
)
from app.domain.cv.universal_cv import UniversalCVStructured

ONLY: dict[str, Any] = {
    "meta": {"full_name": "Example Person", "email": "person@example.com"},
    "professional_summary": "Summary text.",
    "skills": {"hard_skills": ["Wiring"]},
    "experience_summary": {"total_years": 3},
    "work_experience": [{"job_title": "Electrician", "company_name": "Example Works"}],
    "education": [{"degree": "Diploma", "institution": "Example Polytechnic"}],
    "certifications": [{"name": "First Aid"}],
    "projects": [{"title": "Solar install"}],
    "publications": [{"title": "A paper"}],
    "licenses": [{"name": "Electrical licence B"}],
    "clinical_practice": [{"setting": "ICU", "institution": "Example Hospital"}],
    "trade_qualifications": [{"qualification": "NC-3 Electrical"}],
    "languages": [{"language": "Bangla"}],
    "volunteering": [{"organization": "Example Trust"}],
    "awards": [{"title": "Best apprentice"}],
    "references_available": True,
}

SECOND: dict[str, dict[str, Any]] = {
    "education": {"degree": "SSC", "institution": "Example School"},
    "certifications": {"name": "Working at heights"},
    "licenses": {"name": "Driving licence"},
    "clinical_practice": {"setting": "Emergency", "institution": "Example Hospital"},
    "trade_qualifications": {"qualification": "NC-2 Electrical"},
}


def test_section_list_covers_the_cv_and_protected_sections():
    assert set(ONLY) == set(SECTIONS)
    assert PROTECTED_SECTIONS == (
        "education",
        "licenses",
        "certifications",
        "clinical_practice",
        "trade_qualifications",
    )


@pytest.mark.parametrize("name", SECTIONS)
def test_restores_dropped_section(name):
    source = UniversalCVStructured.model_validate({name: ONLY[name]})
    assert present_sections(source) == frozenset({name})
    restored, names = restore_dropped(source, RewrittenCV())
    assert names == [name]
    assert getattr(restored, name) == getattr(source, name)
    assert present_sections(restored) == frozenset({name})


@pytest.mark.parametrize("name", PROTECTED_SECTIONS)
def test_restores_dropped_protected_entry(name):
    first, second = ONLY[name][0], SECOND[name]
    source = UniversalCVStructured.model_validate({name: [first, second]})
    output = RewrittenCV.model_validate({name: [_shouted(first)]})
    restored, names = restore_dropped(source, output)
    assert names == [name]
    entries = getattr(restored, name)
    assert len(entries) == 2
    assert entries[0] == getattr(output, name)[0]  # the rewritten entry is kept as written
    assert entries[1] == getattr(source, name)[1]


def test_kept_protected_entries_are_not_duplicated():
    source = UniversalCVStructured.model_validate({"education": [ONLY["education"][0]]})
    output = RewrittenCV.model_validate({"education": [ONLY["education"][0]]})
    restored, names = restore_dropped(source, output)
    assert names == [] and restored == output


def test_trimmed_unprotected_entry_not_restored():
    projects = [{"title": f"Project {i}"} for i in range(4)]
    source = UniversalCVStructured.model_validate({"projects": projects})
    output = RewrittenCV.model_validate({"projects": projects[:3]})
    restored, names = restore_dropped(source, output)
    assert names == [] and len(restored.projects) == 3


def test_meta_contacts_refilled():
    source = UniversalCVStructured.model_validate(
        {"meta": {"full_name": "A", "email": "a@example.com", "phone": "+880 1700-000009"}}
    )
    output = RewrittenCV.model_validate({"meta": {"full_name": "A B", "email": ""}})
    restored, names = restore_dropped(source, output)
    assert names == ["meta"]
    assert restored.meta.full_name == "A B"
    assert restored.meta.email == "a@example.com"
    assert restored.meta.phone == "+880 1700-000009"


def test_references_flag_kept():
    source = UniversalCVStructured(references_available=True)
    restored, names = restore_dropped(source, RewrittenCV(references_available=False))
    assert restored.references_available is True and names == ["references_available"]
    restored, names = restore_dropped(
        UniversalCVStructured(), RewrittenCV(references_available=True)
    )
    assert restored.references_available is True and names == []


def test_change_log_and_gaps_survive_restore():
    source = UniversalCVStructured.model_validate({"awards": ONLY["awards"]})
    output = RewrittenCV.model_validate(
        {
            "gaps_unaddressed": ["Kubernetes"],
            "change_log": [{"section": "awards", "reason": "Trimmed"}],
        }
    )
    restored, _ = restore_dropped(source, output)
    assert restored.gaps_unaddressed == ["Kubernetes"]
    assert restored.change_log[0].section == "awards"


def _shouted(entry: dict[str, Any]) -> dict[str, Any]:
    """Same entry under a differently cased, padded key: still the same normalised key."""
    return {k: f"  {v.upper()} " if isinstance(v, str) else v for k, v in entry.items()}
