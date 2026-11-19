from app.domain.cv.universal_cv import UniversalCVStructured
from app.ports.llm_errors import LLMOutputTruncated, LLMRefused, LLMUnavailable
from tests.fakes.backend import auth_header

_TECH = UniversalCVStructured(domain="tech", professional_summary="Backend engineer.")
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


def test_import_whitespace_only_is_400(client, backend):
    r = _post(client, " ​ " * 60)
    assert r.status_code == 400
    assert r.json() == {"detail": "CV text is too short to parse."}
    assert backend.llm.requests == []


def test_too_long_400(client):
    r = _post(client, "a" * 15001)
    assert r.status_code == 400
    assert r.json() == {"detail": "CV text is too long. Please paste up to 15,000 characters."}


def test_import_valid(client, backend):
    backend.llm.push("profile_import", _TECH)
    r = _post(client, LONG_CV)
    assert r.status_code == 200
    assert r.json()["profile"]["domain"] == "tech"


def test_import_cv_text_in_data_block(client, backend):
    backend.llm.push("profile_import", _TECH)
    _post(client, LONG_CV)
    req = backend.llm.requests[0]
    assert f"<cv>\n{LONG_CV.strip()}\n</cv>" in req.messages[0].content
    assert LONG_CV.strip() not in (req.system or "")


def test_import_truncated_twice_is_422(client, backend):
    backend.llm.push("profile_import", LLMOutputTruncated("truncated"))
    r = _post(client, LONG_CV)
    assert r.status_code == 422
    assert r.json()["code"] == "CV_IMPORT_FAILED"
    assert "profile" not in r.json()
    assert "Experienced professional" not in r.text


def test_import_refused_is_422(client, backend):
    backend.llm.push("profile_import", LLMRefused("refused"))
    r = _post(client, LONG_CV)
    assert r.status_code == 422
    assert r.json()["code"] == "CONTENT_REFUSED"
    assert "Experienced professional" not in r.text


def test_import_unavailable_is_503(client, backend):
    backend.llm.push("profile_import", LLMUnavailable("down"))
    r = _post(client, LONG_CV)
    assert r.status_code == 503
    assert r.json()["code"] == "LLM_UNAVAILABLE"


def test_success_general_domain_is_detected(client, backend):
    backend.llm.push(
        "profile_import",
        UniversalCVStructured(
            domain="general",
            professional_summary="Registered nurse working in a hospital ward caring for patients.",
        ),
    )
    r = _post(client, LONG_CV)
    assert r.status_code == 200
    assert r.json()["profile"]["domain"] == "medical"
