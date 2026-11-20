import hashlib

import pytest

from app.ports.blob_storage import StorageError
from app.services.account_purge import PURGE_BUCKETS, PurgeDeps, PurgeReport, purge_account
from tests.fakes.fake_blob_storage import FakeBlobStorage

UID = "11111111-1111-1111-1111-111111111111"
EMAIL = "someone@example.com"
S1 = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
S2 = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5c"


class _Calls:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.crash_on: str | None = None

    def hit(self, name: str) -> None:
        self.log.append(name)
        if self.crash_on == name:
            raise RuntimeError("crash")


class _Storage(FakeBlobStorage):
    def __init__(self, calls: _Calls) -> None:
        super().__init__()
        self.calls = calls

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        self.calls.hit(f"storage:{bucket}")
        return super().delete_prefix(bucket, prefix)


class _Sessions:
    def __init__(self, calls: _Calls, ids: list[str]) -> None:
        self.calls, self.ids = calls, ids

    def session_ids(self, user_id: str) -> list[str]:
        self.calls.hit("session_ids")
        return list(self.ids) if user_id == UID else []


class _Checkpoints:
    def __init__(self, calls: _Calls) -> None:
        self.calls, self.removed = calls, []

    def delete_thread(self, thread_id: str) -> None:
        self.calls.hit(f"thread:{thread_id}")
        self.removed.append(thread_id)


class _Admin:
    def __init__(self, calls: _Calls, result: bool = True) -> None:
        self.calls, self.result = calls, result

    def delete_user(self, user_id: str) -> bool:
        self.calls.hit("admin")
        return self.result


class _Audit:
    def __init__(self, calls: _Calls) -> None:
        self.calls, self.entries = calls, []

    def write(self, *, actor, action, target, meta) -> None:
        self.calls.hit("audit")
        self.entries.append({"actor": actor, "action": action, "target": target, "meta": meta})


def _deps(*, admin_result: bool = True):
    calls = _Calls()
    storage = _Storage(calls)
    for bucket in PURGE_BUCKETS:
        storage.put(bucket, f"{UID}/a.bin", b"x", "x/y")
        storage.put(bucket, f"{UID}0/other.bin", b"x", "x/y")
    deps = PurgeDeps(
        storage=storage,
        checkpoints=_Checkpoints(calls),
        sessions=_Sessions(calls, [S1, S2]),
        admin=_Admin(calls, admin_result),
        audit=_Audit(calls),
    )
    return deps, calls


def test_purge_order():
    deps, calls = _deps()
    report = purge_account(UID, deps)
    assert calls.log == [
        "session_ids",
        "storage:photos",
        "storage:renders",
        "storage:imports",
        "storage:exports",
        f"thread:{S1}",
        f"thread:{S2}",
        "admin",
        "audit",
    ]
    assert report == PurgeReport(objects_removed=4, threads_removed=2, user_deleted=True)
    assert all(not k[1].startswith(f"{UID}/") for k in deps.storage.objects)
    assert len(deps.storage.objects) == 4  # a similarly-prefixed user is untouched


def test_purge_idempotent_rerun_after_crash_at_step_2():
    deps, calls = _deps()
    calls.crash_on = f"thread:{S2}"
    with pytest.raises(RuntimeError):
        purge_account(UID, deps)
    assert "admin" not in calls.log
    calls.crash_on = None
    calls.log.clear()
    report = purge_account(UID, deps)
    assert "admin" in calls.log and calls.log[-1] == "audit"
    assert report.user_deleted is True
    assert report.objects_removed == 0  # storage already cleared by the first run
    assert report.threads_removed == 2


def test_auth_404_treated_as_done():
    deps, calls = _deps(admin_result=False)
    report = purge_account(UID, deps)
    assert report.user_deleted is False
    assert calls.log[-1] == "audit"  # continues past an already-deleted user


def test_audit_entry_has_no_email_or_raw_id():
    deps, _ = _deps()
    purge_account(UID, deps)
    (entry,) = deps.audit.entries
    assert entry["actor"] is None
    assert entry["action"] == "account.purged"
    assert entry["target"] == hashlib.sha256(UID.encode()).hexdigest()[:16]
    assert entry["meta"] == {"objects_removed": 4, "threads_removed": 2, "user_deleted": True}
    blob = repr(entry)
    assert UID not in blob and EMAIL not in blob


def test_purge_rejects_malformed_user_id():
    deps, calls = _deps()
    for bad in ("", "/", "../x", "not-a-uuid"):
        with pytest.raises(ValueError):
            purge_account(bad, deps)
    assert calls.log == []


def test_fake_delete_prefix_matches_whole_segments():
    fake = FakeBlobStorage()
    fake.put("renders", "u1/s1/cv.pdf", b"x", "a/b")
    fake.put("renders", "u1/s10/cv.pdf", b"x", "a/b")
    assert fake.delete_prefix("renders", "u1/s1") == 1
    assert list(fake.objects) == [("renders", "u1/s10/cv.pdf")]


@pytest.mark.parametrize("prefix", ["", "/", "//", "u1", "u1/s1", f"{UID}/../x", f"{UID}//s"])
def test_real_adapter_rejects_unsafe_prefix(prefix):
    from unittest.mock import MagicMock

    from app.adapters.storage.supabase_storage import SupabaseBlobStorage

    client = MagicMock()
    store = SupabaseBlobStorage(client, sleep=lambda s: None)
    with pytest.raises(StorageError) as err:
        store.delete_prefix("renders", prefix)
    assert str(err.value) == "Storage prefix is not a user prefix"
    client.storage.from_.return_value.list.assert_not_called()
    client.storage.from_.return_value.remove.assert_not_called()


def test_real_adapter_accepts_user_and_session_prefix():
    from unittest.mock import MagicMock

    from app.adapters.storage.supabase_storage import SupabaseBlobStorage

    client = MagicMock()
    client.storage.from_.return_value.list.return_value = []
    store = SupabaseBlobStorage(client, sleep=lambda s: None)
    assert store.delete_prefix("renders", f"{UID}/") == 0
    assert store.delete_prefix("renders", f"{UID}/{S1}") == 0


@pytest.mark.parametrize("prefix", ["", "/", "//"])
def test_fake_rejects_unsafe_prefix(prefix):
    with pytest.raises(StorageError):
        FakeBlobStorage().delete_prefix("renders", prefix)
