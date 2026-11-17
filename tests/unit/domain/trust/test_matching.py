from typing import Any

import pytest

from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.questions.schemas import GapAnswers
from app.domain.trust.claims import build_evidence
from app.domain.trust.matching import find_unsupported
from app.domain.trust.report import SourceCounts, UnsupportedClaim
from tests.pipeline.helpers import persona_cv

PERSONAS = (
    "tech_backend",
    "nurse_icu",
    "electrician_trades",
    "teacher_volunteer",
    "banker_mixed_bn",
    "fresh_graduate_sparse",
)


def _set(data: dict[str, Any], path: str, value: Any) -> None:
    target: Any = data
    *head, last = path.split(".")
    for part in head:
        target = target[int(part)] if part.isdigit() else target[part]
    target[last] = value


def _cv(base: UniversalCVStructured, edit: dict[str, Any]) -> dict[str, Any]:
    data = base.model_dump(mode="json")
    for path, value in edit.items():
        _set(data, path, value)
    return data


def _check(
    source: UniversalCVStructured,
    edit: dict[str, Any] | None = None,
    answers: GapAnswers | None = None,
) -> tuple[list[UnsupportedClaim], SourceCounts]:
    output = RewrittenCV.model_validate(_cv(source, edit or {}))
    return find_unsupported(build_evidence(source, answers), output)


def _edited(base: UniversalCVStructured, edit: dict[str, Any]) -> UniversalCVStructured:
    return UniversalCVStructured.model_validate(_cv(base, edit))


def _kinds(claims: list[UnsupportedClaim]) -> list[tuple[str, str, str]]:
    return [(c.kind, c.reason, c.severity) for c in claims]


@pytest.mark.parametrize("name", PERSONAS)
def test_unchanged_persona_has_no_claims(name: str):
    claims, counts = _check(persona_cv(name))
    assert claims == []
    assert counts.cv > 0 and counts.answers == 0


def test_invented_degree_is_one_hard_claim():
    tech = persona_cv("tech_backend")
    extra = {"degree": "MBA", "institution": "Example University", "graduation_year": 2022}
    claims, _ = _check(tech, {"education": [*tech.model_dump(mode="json")["education"], extra]})
    assert _kinds(claims) == [("degree", "not_in_source", "hard")]
    assert claims[0].section == "education" and claims[0].layer == "deterministic"


def test_invented_employer_is_hard():
    claims, _ = _check(persona_cv("tech_backend"), {"work_experience.0.company_name": "Google"})
    assert _kinds(claims) == [("employer", "not_in_source", "hard")]


def test_changed_percentage_is_hard_number():
    tech = persona_cv("tech_backend")
    source = _edited(tech, {"work_experience.0.achievements": ["Cut processing time by 30%"]})
    claims, _ = _check(source, {"work_experience.0.achievements": ["Cut processing time by 40%"]})
    assert _kinds(claims) == [("number", "number_not_in_source", "hard")]
    assert "40%" in claims[0].text


def test_bangla_digits_match_source_number():
    tech = persona_cv("tech_backend")
    source = _edited(tech, {"work_experience.0.achievements": ["Cut processing time by 30%"]})
    claims, _ = _check(source, {"work_experience.0.achievements": ["প্রসেসিং সময় ৩০% কমিয়েছি"]})
    assert claims == []


def test_skill_alias_is_supported():
    tech = persona_cv("tech_backend")
    source = _edited(tech, {"skills.tools": ["Python", "PostgreSQL", "Docker", "JavaScript"]})
    claims, _ = _check(source, {"skills.tools": ["Python", "Postgres", "Docker", "JS"]})
    assert claims == []


def test_skill_only_in_answers_is_supported_and_counted():
    answers = GapAnswers(free_text="I ran two services on a small Kubernetes cluster.")
    edit = {"skills.tools": ["Python", "PostgreSQL", "Docker", "Kubernetes"]}
    claims, counts = _check(persona_cv("tech_backend"), edit, answers)
    assert claims == []
    assert counts.answers == 1


def test_skill_named_in_a_source_bullet_is_supported():
    edit = {"skills.hard_skills": ["API design", "Database modelling", "REST services"]}
    claims, _ = _check(persona_cv("tech_backend"), edit)
    assert claims == []


def test_invented_skill_is_soft():
    edit = {"skills.tools": ["Python", "PostgreSQL", "Docker", "Terraform"]}
    claims, _ = _check(persona_cv("tech_backend"), edit)
    assert _kinds(claims) == [("skill", "not_in_source", "soft")]


def test_inflated_title_is_hard():
    source = _edited(persona_cv("tech_backend"), {"work_experience.0.job_title": "Engineer"})
    claims, _ = _check(source, {"work_experience.0.job_title": "Senior Engineer"})
    assert _kinds(claims) == [("title", "not_in_source", "hard")]


def test_degree_upgrade_is_hard():
    claims, _ = _check(persona_cv("nurse_icu"), {"education.0.degree": "MSc Nursing"})
    assert _kinds(claims) == [("degree", "not_in_source", "hard")]


def test_moved_start_date_is_hard():
    source = _edited(persona_cv("tech_backend"), {"work_experience.0.start_date": "2019-05-01"})
    claims, _ = _check(source, {"work_experience.0.start_date": "2018-05-01"})
    assert _kinds(claims) == [("date", "date_changed", "hard")]
    assert claims[0].section == "work_experience"
    same_month, _ = _check(source, {"work_experience.0.start_date": "2019-05-20"})
    assert same_month == []


def test_clinical_dates_match_by_institution():
    claims, _ = _check(persona_cv("nurse_icu"), {"clinical_practice.1.end_date": "2019-12-31"})
    assert _kinds(claims) == [("date", "date_changed", "hard")]
    assert claims[0].section == "clinical_practice"


def test_ending_a_current_role_is_a_date_change():
    claims, _ = _check(persona_cv("tech_backend"), {"work_experience.0.end_date": "2024-01-01"})
    assert _kinds(claims) == [("date", "date_changed", "hard")]


def test_paraphrased_bullet_has_no_claim():
    bullets = ["Designed and shipped REST APIs for logistics teams", "Owned the database schema"]
    claims, _ = _check(persona_cv("tech_backend"), {"work_experience.0.responsibilities": bullets})
    assert claims == []


def test_bangla_institution_kept_verbatim_is_supported():
    source = _edited(persona_cv("nurse_icu"), {"education.0.institution": "ঢাকা নার্সিং কলেজ"})
    claims, _ = _check(source, {"education.0.institution": "# ঢাকা নার্সিং কলেজ"})
    assert claims == []


def test_markup_stripped_copy_is_not_flagged():
    edit = {
        "certifications.0.name": "`Cloud Practitioner`",
        "work_experience.0.company_name": "Example Logistics.",
    }
    claims, _ = _check(persona_cv("tech_backend"), edit)
    assert claims == []
