from core.schemas.universal_cv import UniversalCVStructured
from services.profile_builder import ProfileBuilder
from tests.fakes.backend import auth_header

LONG_CV = "Experienced professional with a strong record of delivery. " * 5


def _post(client, text):
    return client.post("/profile/import-cv", json={"cv_text": text}, headers=auth_header())


def test_too_short_400(client):
    r = _post(client, "a" * 99)
    assert r.status_code == 400
    assert r.json() == {"detail": "CV text is too short to parse."}


def test_short_after_strip_is_400(client):
    r = _post(client, "a" * 99 + " " * 50)
    assert r.status_code == 400
    assert r.json() == {"detail": "CV text is too short to parse."}


def test_too_long_400(client):
    r = _post(client, "a" * 15001)
    assert r.status_code == 400
    assert r.json() == {
        "detail": "CV text is too long. Please paste up to 15,000 characters."
    }


def test_llm_error_is_500_with_message(client, backend):
    backend.llm.error = RuntimeError("boom")
    r = _post(client, LONG_CV)
    assert r.status_code == 500
    assert r.json() == {"detail": "CV parsing failed: boom"}


def test_success_keeps_llm_domain(client, backend):
    backend.llm.output = UniversalCVStructured(domain="tech")
    r = _post(client, LONG_CV)
    assert r.status_code == 200
    assert r.json()["profile"]["domain"] == "tech"
    assert "CV TEXT:\n" + LONG_CV.strip() in backend.llm.prompts[0]


def test_success_general_domain_is_detected(client, backend):
    structured = UniversalCVStructured(
        domain="general",
        professional_summary="Registered nurse working in a hospital ward caring for patients.",
    )
    backend.llm.output = structured
    r = _post(client, LONG_CV)
    assert r.status_code == 200
    expected = ProfileBuilder.detect_domain(structured.model_dump()).value
    assert expected == "medical"
    assert r.json()["profile"]["domain"] == expected
