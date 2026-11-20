import pytest

from app.adapters.db.errors import DbConflict
from app.domain.common import uuid7
from tests.fakes.memory_repos import MemoryCreditRepo
from tests.fakes.memory_session_repos import MemoryRenderRepo, MemorySessionRepo

A, B = "user-a", "user-b"


def _create(repo, user=A):
    sid = uuid7()
    repo.create(user, sid, jd_text="jd", source_cv={}, options={}, template_id="classic")
    return sid


def test_get_other_users_session_is_none():
    repo = MemorySessionRepo()
    sid = _create(repo, B)
    assert repo.get(A, sid) is None
    assert repo.get(B, sid).status == "running"


def test_malformed_ids_are_none_and_create_refuses_them():
    repo = MemorySessionRepo()
    assert repo.get(A, "thread_x") is None
    with pytest.raises(ValueError):
        repo.create(A, "thread_x", jd_text="", source_cv={}, options={}, template_id="c")


def test_update_rejects_unknown_column():
    repo = MemorySessionRepo()
    sid = _create(repo)
    with pytest.raises(ValueError, match="pdf_url"):
        repo.update(A, sid, pdf_url="x")
    repo.update(B, sid, status="failed")  # someone else's: no-op
    assert repo.get(A, sid).status == "running"


def test_list_newest_first_scoped():
    repo = MemorySessionRepo()
    first, second = _create(repo), _create(repo)
    _create(repo, B)
    assert [s.id for s in repo.list_for_user(A)] == [second, first]


def test_render_paths_join_by_user():
    renders = MemoryRenderRepo()
    repo = MemorySessionRepo(renders)
    sid = _create(repo)
    rid = renders.add(A, sid, pdf_path=f"{A}/{sid}/cv.pdf", content_hash="h1", template_id="c")
    renders.add(A, sid, pdf_path="cl", content_hash="h2", template_id="cover_letter")
    repo.update(A, sid, current_render_id=rid)
    row = repo.get(A, sid)
    assert (row.pdf_path, row.cover_letter_pdf_path) == (f"{A}/{sid}/cv.pdf", "cl")
    assert renders.add(A, sid, pdf_path="x", content_hash="h1", template_id="c") == rid
    with pytest.raises(DbConflict):
        renders.add(B, sid, pdf_path="x", content_hash="h1", template_id="c")


def test_credit_grant_is_idempotent_by_key():
    credits = MemoryCreditRepo()
    assert credits.grant(A, 100, "signup_bonus", "signup_bonus:a") == 100
    assert credits.grant(A, 100, "signup_bonus", "signup_bonus:a") == 100
    assert credits.balance(A) == (100, 0)
    assert len(credits.ledger(A)) == 1
    with pytest.raises(ValueError, match="IDEMPOTENCY_MISMATCH"):
        credits.grant(B, 100, "signup_bonus", "signup_bonus:a")
    with pytest.raises(ValueError, match="INVALID_AMOUNT"):
        credits.grant(A, 0, "purchase", "k")
