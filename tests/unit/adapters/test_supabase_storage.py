from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.adapters.storage.supabase_storage import SupabaseBlobStorage
from app.ports.blob_storage import StorageError, render_path, signed_url_for_user
from tests.fakes.fake_blob_storage import FakeBlobStorage

ROOT = Path(__file__).resolve().parents[3]
SECRET_URL = "https://abc.supabase.co/storage/v1/object/sign/renders/u/s/cv.pdf?token=SECRETTOKEN"


class _Boom(Exception):
    def __init__(self, status: int | None = None):
        super().__init__(SECRET_URL)
        self.status = status


def _store(**kw):
    client = MagicMock()
    return SupabaseBlobStorage(
        client, sleep=lambda s: None, **kw
    ), client.storage.from_.return_value


def test_render_path_layout():
    assert render_path("u1", "s1", "cv") == "u1/s1/cv.pdf"
    assert render_path("u1", "s1", "cover_letter") == "u1/s1/cover_letter.pdf"


def test_signed_url_uses_ttl():
    store, bucket = _store()
    bucket.create_signed_url.return_value = {"signedURL": "https://x/y?token=t"}
    assert store.signed_url("renders", "u/s/cv.pdf", 600) == "https://x/y?token=t"
    bucket.create_signed_url.assert_called_once_with("u/s/cv.pdf", 600)


def test_signed_url_refuses_foreign_prefix():
    fake = FakeBlobStorage()
    with pytest.raises(StorageError):
        signed_url_for_user(fake, "user_a", "renders", "user_b/s/cv.pdf", 600)
    assert fake.signed == []
    assert signed_url_for_user(fake, "user_a", "renders", "user_a/s/cv.pdf", 600).endswith(
        "ttl=600"
    )


@pytest.mark.parametrize(
    "path",
    [
        "user_a",
        "user_a/",
        "user_ab/s/cv.pdf",
        "user_a/../user_b/s/cv.pdf",
        "user_a/s/../../user_b/cv.pdf",
        "user_a/./../x.pdf",
        "user_a/s/..",
    ],
)
def test_signed_url_refuses_prefix_tricks_and_dot_dot(path):
    fake = FakeBlobStorage()
    with pytest.raises(StorageError):
        signed_url_for_user(fake, "user_a", "renders", path, 600)
    assert fake.signed == []


def test_signed_url_refuses_empty_user():
    with pytest.raises(StorageError):
        signed_url_for_user(FakeBlobStorage(), "", "renders", "/s/cv.pdf", 600)


def test_storage_error_message_has_no_url():
    store, bucket = _store()
    bucket.create_signed_url.side_effect = _Boom(500)
    with pytest.raises(StorageError) as e:
        store.signed_url("renders", "u/s/cv.pdf", 600)
    assert "http" not in str(e.value) and "SECRETTOKEN" not in str(e.value)
    assert e.value.__cause__ is None or "SECRETTOKEN" not in str(e.value.__cause__)


def test_retries_on_5xx_twice_then_succeeds():
    store, bucket = _store()
    bucket.upload.side_effect = [_Boom(502), _Boom(503), {"path": "p"}]
    store.put("renders", "u/s/cv.pdf", b"%PDF", "application/pdf")
    assert bucket.upload.call_count == 3


def test_no_retry_on_4xx():
    store, bucket = _store()
    bucket.upload.side_effect = _Boom(403)
    with pytest.raises(StorageError):
        store.put("renders", "u/s/cv.pdf", b"x", "application/pdf")
    assert bucket.upload.call_count == 1


def test_put_upserts_with_content_type():
    store, bucket = _store()
    store.put("renders", "u/s/cv.pdf", b"x", "application/pdf")
    assert bucket.upload.call_args.args[:2] == ("u/s/cv.pdf", b"x")
    assert bucket.upload.call_args.args[2]["content-type"] == "application/pdf"
    assert bucket.upload.call_args.args[2]["upsert"] == "true"


def test_delete_prefix_removes_listed_objects():
    store, bucket = _store()
    bucket.list.side_effect = [
        [{"name": "s1", "id": None}, {"name": "x.pdf", "id": "1"}],
        [{"name": "cv.pdf", "id": "2"}, {"name": "cl.pdf", "id": "3"}],
        [],
    ]
    bucket.remove.return_value = []
    assert store.delete_prefix("renders", "u1") == 3
    removed = [p for c in bucket.remove.call_args_list for p in c.args[0]]
    assert sorted(removed) == ["u1/s1/cl.pdf", "u1/s1/cv.pdf", "u1/x.pdf"]


def test_buckets_private():
    raw = (ROOT / "supabase/migrations/20261121000900_storage.sql").read_text().lower()
    sql = " ".join(ln for ln in raw.splitlines() if not ln.lstrip().startswith("--"))
    for b in ("photos", "renders", "imports", "exports"):
        assert f"'{b}'" in sql
    assert "true" not in sql.replace("do update", "")
    assert sql.count("false") >= 4
    assert "10485760" in sql
    assert "create policy" not in sql and "storage.objects" not in sql


def test_no_public_url_anywhere_in_app():
    hits = [
        str(p) for p in (ROOT / "app").rglob("*.py") if "get_public_url" in p.read_text("utf-8")
    ]
    assert hits == []
