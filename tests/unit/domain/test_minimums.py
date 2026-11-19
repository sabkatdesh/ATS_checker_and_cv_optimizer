from app.domain.cv.minimums import check_minimums
from app.domain.cv.universal_cv import (
    EducationEntry,
    UniversalCVMeta,
    UniversalCVStructured,
    WorkExperienceEntry,
)


def test_empty_cv_misses_everything():
    assert check_minimums(UniversalCVStructured()) == [
        "NAME",
        "CONTACT",
        "EXPERIENCE_OR_EDUCATION",
    ]


def test_name_email_and_one_education_entry_is_enough():
    cv = UniversalCVStructured(
        meta=UniversalCVMeta(full_name="Mim Example", email="mim@example.com"),
        education=[EducationEntry(degree="BSc")],
    )
    assert check_minimums(cv) == []


def test_phone_counts_as_contact_and_a_job_counts_as_experience():
    cv = UniversalCVStructured(
        meta=UniversalCVMeta(full_name="Mim Example", phone="+880 1700-000006"),
        work_experience=[WorkExperienceEntry(job_title="Clerk")],
    )
    assert check_minimums(cv) == []


def test_name_only():
    cv = UniversalCVStructured(meta=UniversalCVMeta(full_name="Mim Example"))
    assert check_minimums(cv) == ["CONTACT", "EXPERIENCE_OR_EDUCATION"]
