"""
test_domain_classification.py — Domain detection from structured profile dicts.

detect_domain() was designed for structured DB profile dicts (cv_profiles table),
not raw CV text. Tests use minimal constructed profiles matching real DB shape.
"""
import pytest

from services.profile_builder import ProfileBuilder
from core.schemas.domain_config import Domain


def test_tech_detected_from_skills():
    p = {"skills": {"hard_skills": ["Python", "Django", "React", "Docker"]}}
    assert ProfileBuilder.detect_domain(p) == Domain.TECH


def test_tech_detected_from_job_title():
    p = {"professional_summary": "Senior software engineer specialising in backend API development with Python and PostgreSQL."}
    assert ProfileBuilder.detect_domain(p) == Domain.TECH


def test_tech_detected_from_experience():
    p = {"work_experience": [{"job_title": "Software Developer", "responsibilities": ["Built REST APIs", "Deployed to AWS"]}]}
    assert ProfileBuilder.detect_domain(p) == Domain.TECH


def test_medical_detected_from_license():
    p = {"licenses": ["BMDC Registered Physician"], "professional_summary": "Practising physician."}
    assert ProfileBuilder.detect_domain(p) == Domain.MEDICAL


def test_medical_detected_from_nursing():
    p = {"professional_summary": "Registered nurse with 5 years of clinical experience in hospital wards."}
    assert ProfileBuilder.detect_domain(p) == Domain.MEDICAL


def test_education_detected_from_role():
    p = {"professional_summary": "Secondary school teacher with 8 years experience in curriculum development and classroom instruction."}
    assert ProfileBuilder.detect_domain(p) == Domain.EDUCATION


def test_education_detected_from_publications():
    p = {"publications": [{"title": "Research paper on pedagogy", "journal": "Int. Journal of Education"}]}
    assert ProfileBuilder.detect_domain(p) == Domain.EDUCATION


def test_trades_detected_from_qualification():
    p = {"trade_qualifications": ["Diploma in Electrical Engineering (BTEB)"],
         "professional_summary": "Licensed electrician with BTEB certification."}
    assert ProfileBuilder.detect_domain(p) == Domain.TRADES


def test_trades_detected_from_summary():
    p = {"professional_summary": "Experienced electrician and HVAC technician with NVQ Level 3."}
    assert ProfileBuilder.detect_domain(p) == Domain.TRADES


def test_finance_detected_from_certifications():
    p = {"certifications": ["ACCA Qualified"], "professional_summary": "Financial analyst with expertise in investment banking and equity research."}
    assert ProfileBuilder.detect_domain(p) == Domain.FINANCE


def test_finance_detected_from_summary():
    p = {"professional_summary": "Chartered accountant with 6 years in audit, tax, and financial reporting."}
    assert ProfileBuilder.detect_domain(p) == Domain.FINANCE


def test_legal_detected_from_summary():
    p = {"professional_summary": "Advocate with LLB and LLM, practicing litigation and contract law at a law chamber."}
    assert ProfileBuilder.detect_domain(p) == Domain.LEGAL


def test_creative_detected_from_skills():
    p = {"skills": {"tools": ["Figma", "Photoshop", "Illustrator"]},
         "professional_summary": "UI/UX designer specialising in branding and typography."}
    assert ProfileBuilder.detect_domain(p) == Domain.CREATIVE


def test_general_fallback():
    p = {"professional_summary": "Motivated professional seeking opportunities in a growing organisation."}
    assert ProfileBuilder.detect_domain(p) == Domain.GENERAL


def test_empty_profile_returns_general():
    assert ProfileBuilder.detect_domain({}) == Domain.GENERAL


def test_explicit_domain_field_respected():
    """If the profile already has domain='tech', detect_domain should still work correctly."""
    p = {"domain": "tech", "skills": {"hard_skills": ["Python"]}}
    result = ProfileBuilder.detect_domain(p)
    assert result == Domain.TECH
