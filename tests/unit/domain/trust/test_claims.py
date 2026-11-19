from app.domain.questions.schemas import GapAnswers
from app.domain.trust.claims import build_evidence, extract_claims
from tests.pipeline.helpers import persona_cv


def test_extracts_names_skills_dates_and_numbers():
    claims = extract_claims(persona_cv("tech_backend"))
    kinds = {(c.kind, c.norm) for c in claims}
    assert ("employer", "example logistics") in kinds
    assert ("title", "software engineer") in kinds
    assert ("degree", "bsc computer science") in kinds
    assert ("institution", "example university") in kinds
    assert ("certification", "cloud practitioner") in kinds
    assert ("skill", "postgresql") in kinds
    assert ("number", "40") in kinds
    assert ("date", "start:2021-03") in kinds
    assert ("date", "end:present") in kinds


def test_claims_carry_section_and_entry_key():
    claims = extract_claims(persona_cv("nurse_icu"))
    licence = next(c for c in claims if c.kind == "licence")
    assert (licence.section, licence.entry_key) == ("licenses", "licenses[0]")
    skill = next(c for c in claims if c.kind == "skill")
    assert skill.entry_key is None


def test_meta_numbers_are_not_claims():
    claims = extract_claims(persona_cv("tech_backend"))
    assert all(c.section != "meta" for c in claims)


def test_evidence_uses_answers_unless_skipped():
    cv = persona_cv("tech_backend")
    answers = GapAnswers(answers={"q1": "Ran ২ services"}, free_text="Kubernetes daily")
    evidence = build_evidence(cv, answers)
    assert "kubernetes daily" in evidence.answer_text_norm
    assert 2 in evidence.answer_numbers
    assert 4 in evidence.cv_numbers  # "four years" and experience_summary.total_years
    skipped = build_evidence(cv, answers.model_copy(update={"skipped": True}))
    assert skipped.answer_text_norm == ""
    assert build_evidence(cv, None).answer_text_norm == ""
