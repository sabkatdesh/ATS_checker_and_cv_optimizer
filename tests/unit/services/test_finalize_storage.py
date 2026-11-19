from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app
from app.services.finalize import finalize_session
from tests.fakes.fake_auth import TOKEN_A, USER_A, FakeAuth
from tests.fakes.fake_blob_storage import FakeBlobStorage
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_store import MemoryStore

TID = "thread_abc"


def _container(store=None, storage=None):
    return Container(
        AppSettings(_env_file=None, env="test"),
        store=store or MemoryStore(),
        storage=storage or FakeBlobStorage(),
        auth=FakeAuth(),
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )


def _result(**extra):
    return {
        "eligible": True,
        "eligibility": SimpleNamespace(score=70),
        "tailored_cv": {"full_name": "T"},
        "domain": "tech",
        **extra,
    }


def test_finalize_stores_path_not_public_url():
    c = _container()
    c.store.create_session(USER_A, TID, "jd")
    finalize_session(c, TID, _result(cover_letter={"body": "x"}), USER_A, {})
    row = c.store.sessions[TID]
    assert row["pdf_url"] == f"{USER_A}/{TID}/cv.pdf"
    assert row["cover_letter_pdf_url"] == f"{USER_A}/{TID}/cover_letter.pdf"
    assert c.storage.objects[("renders", f"{USER_A}/{TID}/cv.pdf")] == (
        b"%PDF-fake-cv",
        "application/pdf",
    )
    assert ("renders", f"{USER_A}/{TID}/cover_letter.pdf") in c.storage.objects
    assert "https" not in row["pdf_url"]


def test_finalize_upload_failure_still_completes_with_null():
    c = _container()
    c.storage.fail_put = True
    c.store.create_session(USER_A, TID, "jd")
    finalize_session(c, TID, _result(), USER_A, {})
    assert c.store.sessions[TID]["status"] == "complete"
    assert c.store.sessions[TID]["pdf_url"] is None


def _client(c):
    return TestClient(create_app(c), raise_server_exceptions=False, follow_redirects=False)


def _hdr():
    return {"Authorization": f"Bearer {TOKEN_A}"}


def test_status_returns_fresh_signed_url():
    c = _container()
    c.store.create_session(USER_A, TID, "jd")
    c.store.update_session(
        TID,
        {
            "status": "complete",
            "pdf_url": f"{USER_A}/{TID}/cv.pdf",
            "cover_letter_pdf_url": f"{USER_A}/{TID}/cover_letter.pdf",
        },
    )
    body = _client(c).get(f"/sessions/{TID}/status", headers=_hdr()).json()
    assert body["pdf_url"] == f"https://signed.test/renders/{USER_A}/{TID}/cv.pdf?ttl=600"
    assert body["cover_letter_pdf_url"].endswith("cover_letter.pdf?ttl=600")
    # stored value is unchanged (the path), the URL is derived per request
    assert c.store.sessions[TID]["pdf_url"] == f"{USER_A}/{TID}/cv.pdf"


def test_status_legacy_public_url_and_foreign_path_become_null():
    c = _container()
    c.store.create_session(USER_A, TID, "jd")
    c.store.update_session(
        TID,
        {
            "pdf_url": "https://x.supabase.co/storage/v1/object/public/cv-pdfs/a.pdf",
            "cover_letter_pdf_url": f"someone-else/{TID}/cover_letter.pdf",
        },
    )
    body = _client(c).get(f"/sessions/{TID}/status", headers=_hdr()).json()
    assert body["pdf_url"] is None and body["cover_letter_pdf_url"] is None


def test_status_null_when_no_pdf():
    c = _container()
    c.store.create_session(USER_A, TID, "jd")
    c.store.update_session(TID, {"pdf_url": None})
    assert _client(c).get(f"/sessions/{TID}/status", headers=_hdr()).json()["pdf_url"] is None


def test_sessions_list_signs_urls():
    c = _container()
    c.store.create_session(USER_A, TID, "jd")
    c.store.update_session(TID, {"pdf_url": f"{USER_A}/{TID}/cv.pdf"})
    rows = _client(c).get("/sessions", headers=_hdr()).json()["sessions"]
    assert rows[0]["pdf_url"].startswith("https://signed.test/renders/")


def test_cover_letter_download_redirects_to_signed_url():
    c = _container()
    c.store.create_session(USER_A, TID, "jd")
    c.store.update_session(TID, {"cover_letter_pdf_url": f"{USER_A}/{TID}/cover_letter.pdf"})
    r = _client(c).get(f"/sessions/{TID}/cover-letter.pdf", headers=_hdr())
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://signed.test/renders/")
