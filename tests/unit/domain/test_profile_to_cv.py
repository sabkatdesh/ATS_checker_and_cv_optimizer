import json
from datetime import date

import pytest

from app.domain.cv.domain_config import Domain
from app.domain.cv.profile_text import ProfileBuilder
from app.domain.cv.profile_to_cv import profile_to_universal_cv
from app.domain.cv.universal_cv import UniversalCVStructured
from tests.pipeline.helpers import PERSONAS

NAMES = sorted(p.name for p in PERSONAS.iterdir() if (p / "profile.json").is_file())


def _load(name: str, file: str) -> dict:
    return json.loads((PERSONAS / name / file).read_text(encoding="utf-8"))


def test_every_persona_has_a_profile():
    assert len(NAMES) == len([p for p in PERSONAS.iterdir() if p.is_dir()]) >= 7


@pytest.mark.parametrize("name", NAMES)
def test_persona_profile_converts_to_its_cv(name):
    conversion = profile_to_universal_cv(_load(name, "profile.json"))
    assert conversion.cv == UniversalCVStructured.model_validate(_load(name, "cv.json"))
    assert (conversion.dropped_entries, conversion.unknown_keys) == (0, 0)


def test_unknown_key_is_counted():
    profile = {**_load("tech_backend", "profile.json"), "hobbies": ["chess"]}
    assert profile_to_universal_cv(profile).unknown_keys == 1


def test_work_entry_without_title_is_dropped_and_counted():
    profile = {
        "full_name": "A Example",
        "experience": [{"company_name": "Example Co"}, {"job_title": "Clerk"}],
    }
    conversion = profile_to_universal_cv(profile)
    assert [w.job_title for w in conversion.cv.work_experience] == ["Clerk"]
    assert conversion.dropped_entries == 1


def test_invalid_entries_in_other_sections_are_dropped_one_by_one():
    profile = {
        "certifications": [{"name": "Cert A"}, {"issuer": "nameless"}, "not a dict"],
        "languages": [{"language": "Bangla"}, {"language": "   "}],
    }
    conversion = profile_to_universal_cv(profile)
    assert [c.name for c in conversion.cv.certifications] == ["Cert A"]
    assert [lang.language for lang in conversion.cv.languages] == ["Bangla"]
    assert conversion.dropped_entries == 3


def test_skills_comma_string():
    cv = profile_to_universal_cv({"skills": "Python, SQL"}).cv
    assert cv.skills.hard_skills == ["Python", "SQL"]


def test_skills_list_and_dict_with_string_values():
    assert profile_to_universal_cv({"skills": ["Python", " ", "SQL"]}).cv.skills.hard_skills == [
        "Python",
        "SQL",
    ]
    skills = profile_to_universal_cv({"skills": {"tools": "Excel, Git", "soft_skills": None}}).cv
    assert skills.skills.tools == ["Excel", "Git"]
    assert skills.skills.soft_skills == []


def test_forty_roles_all_convert():
    roles = [
        {"job_title": f"Role {i}", "company_name": f"Example {i}", "start_date": f"{1980 + i}-01"}
        for i in range(40)
    ]
    cv = profile_to_universal_cv({"full_name": "A Example", "experience": roles}).cv
    assert len(cv.work_experience) == 40
    assert cv.work_experience[39].start_date == date(2019, 1, 1)


def test_meta_links_summary_aliases_and_whitespace():
    profile = {
        "full_name": "  ",
        "email": "a@example.com",
        "github": "github.com/a",
        "portfolio": "a.example.com",
        "linkedin": "",
        "professional_summary": "Engineer.",
        "work_experience": [
            {
                "job_title": "Dev",
                "company_name": "  ",
                "start_date": "Mar 2020",
                "end_date": "Present",
            }
        ],
    }
    cv = profile_to_universal_cv(profile).cv
    assert cv.meta.full_name is None and cv.meta.linkedin is None
    assert cv.meta.optional_links == {"GitHub": "github.com/a", "Portfolio": "a.example.com"}
    assert cv.professional_summary == "Engineer."
    job = cv.work_experience[0]
    assert (job.company_name, job.start_date, job.end_date) == (None, date(2020, 3, 1), None)


def test_ignored_keys_do_not_count():
    profile = {
        "id": 7,
        "user_id": "u",
        "preferred_template": "classic",
        "accent_color": "#000",
        "bangla_mode": True,
        "created_at": "x",
        "updated_at": "y",
    }
    assert profile_to_universal_cv(profile).unknown_keys == 0


def test_lenient_values_are_normalised():
    profile = {
        "experience": [{"job_title": "Dev", "employment_type": "Full-time"}],
        "education": [{"degree": "BSc", "graduation_year": "২০২০"}],
        "references_available": None,
    }
    cv = profile_to_universal_cv(profile).cv
    assert cv.work_experience[0].employment_type == "full_time"
    assert cv.education[0].graduation_year == 2020
    assert cv.references_available is False


def test_domain_stored_or_detected():
    assert profile_to_universal_cv({"domain": "medical"}).cv.domain == Domain.MEDICAL
    profile = {"domain": "unknown", "summary": "Python backend developer, Django and AWS."}
    assert profile_to_universal_cv(profile).cv.domain == ProfileBuilder.detect_domain(profile)
    assert profile_to_universal_cv({**profile, "domain": "astrology"}).cv.domain == Domain.TECH


def test_total_years_derived_from_dates_when_no_summary():
    profile = {
        "experience": [
            {"job_title": "A", "start_date": "2010-01", "end_date": "2014-01"},
            {"job_title": "B", "start_date": "2012-01", "end_date": "2016-01"},
            {"job_title": "C", "start_date": "2018-01"},
        ]
    }
    cv = profile_to_universal_cv(profile, today=date(2020, 1, 1)).cv
    assert cv.experience_summary.total_years == 8.0
    assert cv.experience_summary.seniority == "unknown"


def test_non_mapping_profile_sections_are_dropped():
    conversion = profile_to_universal_cv({"education": "BSc", "skills": 5})
    assert conversion.cv.education == [] and conversion.dropped_entries == 2
