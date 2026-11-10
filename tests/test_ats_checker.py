"""
test_ats_checker.py — Unit tests for the 6 ATS sub-score functions.

Uses minimal stub objects so no LLM calls are needed.
"""
import pytest
from unittest.mock import MagicMock

from core.ats.ats_checker import (
    compute_final_match,
    _match_must_haves,
    _match_skills,
    _match_experience,
    _match_tools,
    _match_education,
    _match_responsibilities,
    _safe_div,
    _flexible_match,
)


# ── Helpers to build stub JD / CV objects ─────────────────────────────────────

def _jd(
    must_have=None, hard_skills=None, tools=None, cloud_platforms=None,
    min_years=None, seniority="mid", fields_of_study=None, responsibilities=None,
):
    j = MagicMock()
    j.requirements.must_have = must_have or []
    j.skills.hard_skills = hard_skills or []
    j.skills.tools = tools or []
    j.skills.cloud_platforms = cloud_platforms or []
    j.experience.min_years = min_years
    j.experience.seniority = seniority
    j.education.fields_of_study = fields_of_study or []
    j.responsibilities.responsibilities = responsibilities or []
    return j


def _cv(
    hard_skills=None, tools=None, frameworks=None, cloud_platforms=None,
    total_years=None, seniority="mid", education=None, responsibilities_per_role=None,
):
    c = MagicMock()
    c.skills.hard_skills = hard_skills or []
    c.skills.tools = tools or []
    c.skills.frameworks = frameworks or []
    c.skills.cloud_platforms = cloud_platforms or []
    c.experience_summary.total_years = total_years
    c.experience_summary.seniority = seniority

    edu_list = education or []
    c.education = [MagicMock(field_of_study=f) for f in edu_list]

    roles = responsibilities_per_role or []
    c.work_experience = [MagicMock(responsibilities=r) for r in roles]
    return c


# ── _safe_div ──────────────────────────────────────────────────────────────────

def test_safe_div_normal():
    assert _safe_div(3, 4) == 75.0

def test_safe_div_zero_denominator():
    assert _safe_div(5, 0) == 0.0

def test_safe_div_full():
    assert _safe_div(10, 10) == 100.0


# ── _flexible_match ────────────────────────────────────────────────────────────

def test_flexible_match_exact():
    assert _flexible_match("Python", "Python") is True

def test_flexible_match_case_insensitive():
    assert _flexible_match("PYTHON", "python developer") is True

def test_flexible_match_token_overlap():
    assert _flexible_match("machine learning", "learning algorithms") is True

def test_flexible_match_no_overlap():
    assert _flexible_match("Java", "Python developer") is False


# ── _match_must_haves ──────────────────────────────────────────────────────────

def test_must_have_all_matched():
    jd = _jd(must_have=["Python", "Django"], hard_skills=["Python", "Django"])
    cv = _cv(hard_skills=["Python", "Django"])
    result = _match_must_haves(jd, cv)
    assert result["score"] == 100.0
    assert result["missing"] == []

def test_must_have_none_matched():
    jd = _jd(must_have=["Cobol", "Fortran"], hard_skills=[])
    cv = _cv(hard_skills=["Python"])
    result = _match_must_haves(jd, cv)
    assert result["score"] == 0.0
    assert len(result["missing"]) == 2

def test_must_have_empty_jd():
    jd = _jd(must_have=[])
    cv = _cv()
    result = _match_must_haves(jd, cv)
    assert result["score"] == 0.0  # safe_div(0, 0) → 0


# ── _match_experience ──────────────────────────────────────────────────────────

def test_experience_meets_requirement():
    jd = _jd(min_years=3, seniority="mid")
    cv = _cv(total_years=5, seniority="mid")
    result = _match_experience(jd, cv)
    assert result["score"] == 100

def test_experience_below_requirement():
    jd = _jd(min_years=5, seniority="senior")
    cv = _cv(total_years=2, seniority="junior")
    result = _match_experience(jd, cv)
    assert result["score"] < 100

def test_experience_score_never_negative():
    jd = _jd(min_years=10, seniority="director")
    cv = _cv(total_years=1, seniority="intern")
    result = _match_experience(jd, cv)
    assert result["score"] >= 0


# ── _match_education ───────────────────────────────────────────────────────────

def test_education_field_matched():
    jd = _jd(fields_of_study=["Computer Science"])
    cv = _cv(education=["Computer Science"])
    result = _match_education(jd, cv)
    assert result["score"] == 100

def test_education_field_not_matched():
    jd = _jd(fields_of_study=["Medicine"])
    cv = _cv(education=["Engineering"])
    result = _match_education(jd, cv)
    assert result["score"] == 50  # partial credit

def test_education_no_jd_requirement():
    jd = _jd(fields_of_study=[])
    cv = _cv(education=["Business"])
    result = _match_education(jd, cv)
    assert result["score"] == 50  # no match possible → partial credit


# ── compute_final_match (integration) ─────────────────────────────────────────

def test_compute_final_match_perfect_candidate():
    jd = _jd(
        must_have=["Python"],
        hard_skills=["Python"],
        min_years=2, seniority="mid",
        fields_of_study=["CS"],
        responsibilities=["build APIs"],
    )
    cv = _cv(
        hard_skills=["Python"],
        total_years=3, seniority="mid",
        education=["CS"],
        responsibilities_per_role=[["build APIs", "REST endpoints"]],
    )
    result = compute_final_match(jd, cv)
    assert result["overall_score"] > 60

def test_compute_final_match_returns_required_keys():
    jd = _jd()
    cv = _cv()
    result = compute_final_match(jd, cv)
    assert "overall_score" in result
    assert "section_scores" in result

def test_compute_final_match_score_in_range():
    jd = _jd(
        must_have=["Java"],
        hard_skills=["Java"],
        min_years=3, seniority="senior",
    )
    cv = _cv(
        hard_skills=["Python"],
        total_years=1, seniority="junior",
    )
    result = compute_final_match(jd, cv)
    assert 0 <= result["overall_score"] <= 100
