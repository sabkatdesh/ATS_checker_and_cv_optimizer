import pytest
from pydantic import ValidationError

from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.output_checks import remove_foreign_contacts, scrub_contacts, strip_markup
from app.domain.cv.rewrite import ChangeLogEntry, RewrittenCV
from app.domain.cv.universal_cv import UniversalCVMeta, WorkExperienceEntry
from tests.pipeline.helpers import persona_cv


def _output(**update) -> RewrittenCV:
    return RewrittenCV.model_validate(persona_cv().model_dump()).model_copy(update=update)


def _role(*bullets: str) -> list[WorkExperienceEntry]:
    role = persona_cv().work_experience[0]
    return [role.model_copy(update={"responsibilities": list(bullets)})]


def test_invented_url_in_a_bullet_is_removed() -> None:
    out = _output(work_experience=_role("Built REST services, see https://evil.example/apply"))
    cleaned, count = remove_foreign_contacts(persona_cv(), out)
    assert count == 1
    assert cleaned.work_experience[0].responsibilities == ["Built REST services, see"]


def test_source_linkedin_and_contacts_are_kept() -> None:
    bullet = "Profile https://www.linkedin.com/in/rafi-example/ or rafi@example.com, +8801700000001"
    out = _output(professional_summary=bullet)
    cleaned, count = remove_foreign_contacts(persona_cv(), out)
    assert count == 0 and cleaned == out


def test_invented_email_and_phone_are_removed() -> None:
    out = _output(professional_summary="Mail boss@evil.example or call 01999-888777.")
    cleaned, count = remove_foreign_contacts(persona_cv(), out)
    assert count == 2 and cleaned.professional_summary == "Mail or call."


def test_meta_is_reset_to_source_values() -> None:
    meta = UniversalCVMeta(
        full_name="Rafi Example",
        email="attacker@evil.example",
        phone="+880 1700-000001",
        linkedin="https://evil.example/in/x",
        optional_links={"Site": "https://evil.example"},
    )
    cleaned, count = remove_foreign_contacts(persona_cv(), _output(meta=meta))
    source = persona_cv().meta
    assert count == 3
    assert cleaned.meta.email == source.email and cleaned.meta.linkedin == source.linkedin
    assert cleaned.meta.optional_links == source.optional_links
    assert cleaned.meta.phone == "+880 1700-000001"


def test_dates_and_years_are_not_phone_numbers() -> None:
    out = _output(professional_summary="From 2019-2023 and 2021-03-01, 40% faster")
    assert remove_foreign_contacts(persona_cv(), out) == (out, 0)


def test_cover_letter_contacts_are_scrubbed() -> None:
    letter = CoverLetterStructured(body_paragraphs=["Apply at www.evil.example today."])
    cleaned, count = scrub_contacts(letter, persona_cv())
    assert count == 1 and cleaned.body_paragraphs == ["Apply at today."]


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("**bold**", "bold"),
        ("__bold__ and *it* and _it_", "bold and it and it"),
        ("## Summary", "Summary"),
        ("Use `uvicorn` daily", "Use uvicorn daily"),
        ("<b>Led</b> the <a href='x'>team</a>", "Led the team"),
        ("C# and snake_case_name, 5 * 3 * 2", "C# and snake_case_name, 5 * 3 * 2"),
    ],
)
def test_markup_is_stripped(raw: str, clean: str) -> None:
    out = strip_markup(_output(professional_summary=raw, work_experience=_role(raw)))
    assert out.professional_summary == clean
    assert out.work_experience[0].responsibilities == [clean]


def test_string_over_2000_characters_fails_validation() -> None:
    data = persona_cv().model_dump()
    data["work_experience"][0]["responsibilities"] = ["x" * 2001]
    with pytest.raises(ValidationError, match="longer than 2000"):
        RewrittenCV.model_validate(data)
    data["work_experience"][0]["responsibilities"] = ["x" * 2000]
    RewrittenCV.model_validate(data)


def test_summary_over_1200_characters_fails_validation() -> None:
    with pytest.raises(ValidationError, match="longer than 1200"):
        RewrittenCV(professional_summary="x" * 1201)
    RewrittenCV(professional_summary="x" * 1200)


def test_cap_error_never_echoes_the_text_or_dict_keys() -> None:
    with pytest.raises(ValidationError) as exc:
        RewrittenCV(meta=UniversalCVMeta(optional_links={"SECRETKEY": "y" * 2001}))
    message = exc.value.errors(include_input=False)[0]["msg"]
    assert "SECRETKEY" not in message and "yyy" not in message


def test_change_log_is_truncated_not_capped() -> None:
    cv = RewrittenCV(change_log=[ChangeLogEntry(section="skills", reason="r" * 5000)])
    assert len(cv.change_log[0].reason) == 200
