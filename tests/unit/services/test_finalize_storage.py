from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.main import create_app
from app.services.finalize import finalize_session
from tests.fakes.backend import FakeBackend, backend_with_session
from tests.fakes.fake_auth import TOKEN_A, USER_A
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer

TID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a05"
CV_PATH = f"{USER_A}/{TID}/cv.pdf"
CL_PATH = f"{USER_A}/{TID}/cover_letter.pdf"


def _container(backend: FakeBackend | None = None) -> tuple[Container, FakeBackend]:
    backend = backend or backend_with_session(USER_A, TID)
    c = Container(
        AppSettings(_env_file=None, env="test"),
        **backend.repos(),
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )
    return c, backend


def _result(**extra):
    return {
        "eligible": True,
        "eligibility": SimpleNamespace(score=70),
        "tailored_cv": {"full_name": "T"},
        "domain": "tech",
        **extra,
    }


def _with_renders(backend: FakeBackend, cv: str | None = None, cl: str | None = None) -> None:
    if cv:
        rid = backend.renders.add(USER_A, TID, pdf_path=cv, content_hash="cv", template_id="c")
        backend.sessions.update(USER_A, TID, status="succeeded", current_render_id=rid)
    if cl:
        backend.renders.add(USER_A, TID, pdf_path=cl, content_hash="cl", template_id="cover_letter")


def test_finalize_stores_path_not_public_url():
    c, backend = _container()
    finalize_session(c, TID, _result(cover_letter={"body": "x"}), USER_A, {})
    row = c.sessions.get(USER_A, TID)
    assert row is not None
    assert (row.pdf_path, row.cover_letter_pdf_path) == (CV_PATH, CL_PATH)
    assert backend.storage.objects[("renders", CV_PATH)] == (b"%PDF-fake-cv", "application/pdf")
    assert ("renders", CL_PATH) in backend.storage.objects
    assert all("://" not in r["pdf_path"] for r in backend.renders.rows.values())


def test_finalize_upload_failure_still_completes_with_null():
    c, backend = _container()
    backend.storage.fail_put = True
    finalize_session(c, TID, _result(), USER_A, {})
    row = c.sessions.get(USER_A, TID)
    assert row is not None and row.status == "succeeded"
    assert row.current_render_id is None and row.pdf_path is None
    assert backend.renders.rows == {}


def test_finalize_writes_only_the_callers_row():
    c, backend = _container()
    finalize_session(c, TID, _result(), "user-b", {})
    assert backend.sessions.raw(TID)["status"] == "running"


def _client(c):
    return TestClient(create_app(c), raise_server_exceptions=False, follow_redirects=False)


def _hdr():
    return {"Authorization": f"Bearer {TOKEN_A}"}


def test_status_returns_fresh_signed_url():
    c, backend = _container()
    _with_renders(backend, cv=CV_PATH, cl=CL_PATH)
    body = _client(c).get(f"/sessions/{TID}/status", headers=_hdr()).json()
    assert body["pdf_url"] == f"https://signed.test/renders/{CV_PATH}?ttl=600"
    assert body["cover_letter_pdf_url"].endswith("cover_letter.pdf?ttl=600")
    # the stored value stays a path; the URL is derived per request
    assert c.sessions.get(USER_A, TID).pdf_path == CV_PATH  # type: ignore[union-attr]


def test_status_public_url_and_foreign_path_become_null():
    c, backend = _container()
    _with_renders(
        backend,
        cv="https://x.supabase.co/storage/v1/object/public/cv-pdfs/a.pdf",
        cl=f"someone-else/{TID}/cover_letter.pdf",
    )
    body = _client(c).get(f"/sessions/{TID}/status", headers=_hdr()).json()
    assert body["pdf_url"] is None and body["cover_letter_pdf_url"] is None


def test_status_null_when_no_pdf():
    c, _ = _container()
    assert _client(c).get(f"/sessions/{TID}/status", headers=_hdr()).json()["pdf_url"] is None


def test_sessions_list_signs_urls():
    c, backend = _container()
    _with_renders(backend, cv=CV_PATH)
    rows = _client(c).get("/sessions", headers=_hdr()).json()["sessions"]
    assert rows[0]["pdf_url"].startswith("https://signed.test/renders/")


def test_cover_letter_download_redirects_to_signed_url():
    c, backend = _container()
    _with_renders(backend, cl=CL_PATH)
    r = _client(c).get(f"/sessions/{TID}/cover-letter.pdf", headers=_hdr())
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://signed.test/renders/")


TID2 = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a06"


def _new_session(backend: FakeBackend, user: str, sid: str) -> None:
    backend.sessions.create(user, sid, jd_text="jd", source_cv={}, options={}, template_id="c")


def test_identical_pdfs_in_two_sessions_get_their_own_renders():
    c, backend = _container()
    _new_session(backend, USER_A, TID2)
    for sid in (TID, TID2):  # the fake renderers return identical bytes every time
        finalize_session(c, sid, _result(cover_letter={"body": "x"}), USER_A, {})
    assert len(backend.renders.rows) == 4
    assert len({r["content_hash"] for r in backend.renders.rows.values()}) == 4
    for sid in (TID, TID2):
        row = c.sessions.get(USER_A, sid)
        assert row is not None
        assert row.pdf_path == f"{USER_A}/{sid}/cv.pdf"
        assert row.cover_letter_pdf_path == f"{USER_A}/{sid}/cover_letter.pdf"
        assert backend.renders.rows[row.current_render_id]["session_id"] == sid


def test_identical_pdfs_across_users_do_not_conflict_or_link():
    c, backend = _container()
    _new_session(backend, "user-b", TID2)
    finalize_session(c, TID, _result(), USER_A, {})
    finalize_session(c, TID2, _result(), "user-b", {})
    a, b = c.sessions.get(USER_A, TID), c.sessions.get("user-b", TID2)
    assert a is not None and b is not None
    assert a.pdf_path == f"{USER_A}/{TID}/cv.pdf"
    assert b.pdf_path == f"user-b/{TID2}/cv.pdf"
    assert a.current_render_id != b.current_render_id
