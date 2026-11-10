"""
test_template_rendering.py — Render all 6 CV templates and assert output is valid PDF.

Requires WeasyPrint + GTK (Windows) or pango (Linux).
Skips gracefully if WeasyPrint is not available.
"""

import pytest

try:
    import weasyprint  # noqa: F401

    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not WEASYPRINT_AVAILABLE, reason="WeasyPrint not installed or GTK runtime missing"
)

from app.rendering.cv_pdf import VALID_TEMPLATES, PDFGenerator  # noqa: E402

FIXTURE_CV = {
    "meta": {
        "full_name": "Test User",
        "email": "test@example.com",
        "phone": "+880-1700-000000",
        "location": "Dhaka, Bangladesh",
        "linkedin": "",
        "github": "",
        "portfolio": "",
    },
    "professional_summary": "An experienced software engineer.",
    "skills": {
        "hard_skills": ["Python", "Django"],
        "soft_skills": ["Communication"],
        "tools": ["Git", "Docker"],
        "frameworks": ["FastAPI"],
        "cloud_platforms": ["AWS"],
    },
    "work_experience": [
        {
            "job_title": "Software Engineer",
            "company": "TechCorp",
            "location": "Dhaka",
            "start_date": "2021-01-01",
            "end_date": None,
            "is_current": True,
            "responsibilities": ["Built REST APIs", "Reviewed code"],
            "achievements": ["Reduced latency by 30%"],
        }
    ],
    "education": [
        {
            "degree": "B.Sc.",
            "field_of_study": "Computer Science",
            "institution": "BUET",
            "location": "Dhaka",
            "start_date": "2016-01-01",
            "end_date": "2020-12-01",
            "gpa": "3.8",
        }
    ],
    "projects": [],
    "certifications": [],
    "licenses": [],
    "publications": [],
    "clinical_practice": [],
    "trade_qualifications": [],
    "languages": [{"language": "English", "proficiency": "Fluent"}],
    "volunteering": [],
    "awards": [],
    "references_available": False,
}


@pytest.mark.parametrize("template_id", sorted(VALID_TEMPLATES))
def test_template_renders_to_bytes(template_id):
    generator = PDFGenerator()
    pdf_bytes = generator.render(
        cv_data=FIXTURE_CV,
        template_id=template_id,
        accent_color="#4361ee",
        bangla=False,
        domain="tech",
    )
    assert isinstance(pdf_bytes, bytes), f"{template_id}: render did not return bytes"
    assert len(pdf_bytes) > 500, f"{template_id}: PDF too small ({len(pdf_bytes)} bytes)"


@pytest.mark.parametrize("template_id", sorted(VALID_TEMPLATES))
def test_template_renders_with_bangla(template_id):
    """Bangla mode must not crash any template."""
    generator = PDFGenerator()
    bangla_cv = dict(FIXTURE_CV)
    bangla_cv["professional_summary"] = "একজন অভিজ্ঞ সফটওয়্যার প্রকৌশলী।"
    pdf_bytes = generator.render(
        cv_data=bangla_cv,
        template_id=template_id,
        accent_color="#4361ee",
        bangla=True,
        domain="tech",
    )
    assert len(pdf_bytes) > 500, f"{template_id}: Bangla PDF too small"


def test_unknown_template_falls_back_to_classic():
    generator = PDFGenerator()
    pdf_bytes = generator.render(
        cv_data=FIXTURE_CV,
        template_id="nonexistent_template",
        accent_color="#4361ee",
        bangla=False,
        domain="general",
    )
    assert len(pdf_bytes) > 500


def test_pdf_is_valid_pdf_header():
    """All PDF output must start with the %PDF magic bytes."""
    generator = PDFGenerator()
    for tmpl in VALID_TEMPLATES:
        pdf_bytes = generator.render(FIXTURE_CV, template_id=tmpl)
        assert pdf_bytes[:4] == b"%PDF", f"{tmpl}: output is not a valid PDF"
