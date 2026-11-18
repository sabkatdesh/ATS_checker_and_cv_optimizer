"""Tenure phrases ("5+ years") and corporate suffixes ("Ltd") in the deterministic check."""

import pytest

from app.domain.cv.universal_cv import UniversalCVStructured
from tests.pipeline.helpers import persona_cv
from tests.unit.domain.trust.test_matching import _check, _edited, _kinds

_SUMMARY = "professional_summary"


def _tenure_source(total: float, start: str, end: str) -> UniversalCVStructured:
    """tech_backend with a closed role and no spelled-out years in the summary."""
    return _edited(
        persona_cv("tech_backend"),
        {
            _SUMMARY: "Backend engineer with Python and REST API experience.",
            "experience_summary.total_years": total,
            "experience_summary.relevant_years": total,
            "work_experience.0.start_date": start,
            "work_experience.0.end_date": end,
        },
    )


def test_years_up_to_the_source_total_are_supported():
    source = _tenure_source(4.5, "2021-03-01", "2024-03-01")
    claims, _ = _check(source, {_SUMMARY: "Backend engineer with 4+ years of Python."})
    assert claims == []


def test_years_beyond_the_source_are_hard():
    source = _tenure_source(4, "2021-03-01", "2024-03-01")
    claims, _ = _check(source, {_SUMMARY: "Backend engineer with 7+ years of Python."})
    assert _kinds(claims) == [("number", "number_not_in_source", "hard")]


def test_years_up_to_the_work_history_span_are_supported():
    source = _tenure_source(2, "2018-01-01", "2024-02-01")
    claims, _ = _check(source, {_SUMMARY: "Backend engineer with over 6 years of Python."})
    assert claims == []
    seven, _ = _check(source, {_SUMMARY: "Backend engineer with over 7 years of Python."})
    assert _kinds(seven) == [("number", "number_not_in_source", "hard")]


def test_bangla_year_word_counts_as_tenure():
    source = _tenure_source(4.5, "2021-03-01", "2024-03-01")
    claims, _ = _check(source, {_SUMMARY: "৩ বছরের অভিজ্ঞতা"})
    assert claims == []


def test_a_fraction_of_years_is_not_a_tenure_bound():
    source = _tenure_source(4.5, "2021-03-01", "2024-03-01")
    claims, _ = _check(source, {_SUMMARY: "Backend engineer with 3.5 years of Python."})
    assert _kinds(claims) == [("number", "number_not_in_source", "hard")]


def test_number_not_next_to_a_year_word_is_still_checked():
    source = _tenure_source(4.5, "2021-03-01", "2024-03-01")
    claims, _ = _check(source, {_SUMMARY: "Backend engineer who shipped 3 services."})
    assert _kinds(claims) == [("number", "number_not_in_source", "hard")]


def test_corporate_suffix_on_the_employer_is_supported():
    claims, _ = _check(
        persona_cv("tech_backend"), {"work_experience.0.company_name": "Example Logistics Ltd"}
    )
    assert claims == []


def test_added_word_in_the_employer_is_still_hard():
    claims, _ = _check(
        persona_cv("tech_backend"), {"work_experience.0.company_name": "Example Global Logistics"}
    )
    assert _kinds(claims) == [("employer", "not_in_source", "hard")]


@pytest.mark.parametrize(
    "summary", ["Backend engineer who managed 4 teams over 4 years.", "4 years leading 4 teams."]
)
def test_same_value_as_tenure_and_count_checks_the_count(summary: str):
    source = _tenure_source(4.5, "2021-03-01", "2024-03-01")
    claims, _ = _check(source, {_SUMMARY: summary})
    assert _kinds(claims) == [("number", "number_not_in_source", "hard")]
    assert "4 teams" in claims[0].text
