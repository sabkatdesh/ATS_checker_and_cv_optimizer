"""purge_account on the real stack: every user table and bucket prefix is empty afterwards."""

import hashlib

from app.adapters.db.audit_repo import PgAuditRepo
from app.adapters.db.checkpointer_pg import PostgresCheckpointerFactory
from app.adapters.db.session_repo import PgSessionRepo
from app.services.account_purge import PURGE_BUCKETS, PurgeDeps, purge_account
from tests.remote._helpers import Conn, insert_checkpoint_rows, lg_counts
from tests.remote._rest import StorageHttp, listed_names
from tests.remote._seed import (
    BUCKET_TYPES,
    USER_LINK,
    cleanup_leftovers,
    count_user_rows,
    seed_user_rows,
)


def _objects(service_storage: StorageHttp, uid: str) -> dict[str, list[str]]:
    return {b: listed_names(service_storage.list(b, uid)) for b in PURGE_BUCKETS}


def test_purge_leaves_zero_rows_and_objects(
    make_user,
    auth_admin,
    backend_conn: Conn,
    backend_pool,
    blob_storage,
    service_storage: StorageHttp,
    supabase_admin,
    remote_env,
) -> None:
    user = make_user(confirmed=True)
    uid = user.id
    seeded = seed_user_rows(backend_conn, uid)
    try:
        insert_checkpoint_rows(backend_conn, seeded.session_id)
        for bucket, (ctype, data) in BUCKET_TYPES.items():
            blob_storage.put(bucket, f"{uid}/{seeded.session_id}/m4test", data, ctype)
            blob_storage.put(bucket, f"{uid}/top-level", data, ctype)
        counts = count_user_rows(backend_conn, uid, [seeded.job_id])
        assert all(n >= 1 for n in counts.values()), counts
        assert all(_objects(service_storage, uid).values())

        deps = PurgeDeps(
            storage=blob_storage,
            checkpoints=PostgresCheckpointerFactory(remote_env.db_dsn, backend_pool),
            sessions=PgSessionRepo(backend_pool),
            admin=supabase_admin,
            audit=PgAuditRepo(backend_pool),
        )
        report = purge_account(uid, deps)
        assert report.user_deleted is True
        assert report.threads_removed == 1
        assert report.objects_removed == 2 * len(PURGE_BUCKETS)

        after = count_user_rows(backend_conn, uid, [seeded.job_id])
        assert after == {table: 0 for table in USER_LINK}, after
        assert _objects(service_storage, uid) == {b: [] for b in PURGE_BUCKETS}
        assert lg_counts(backend_conn, seeded.session_id) == {
            "checkpoints": 0,
            "checkpoint_blobs": 0,
            "checkpoint_writes": 0,
        }
        assert auth_admin.exists(uid) is False
        # Accounting rows survive anonymised (ledger, payment intents, llm calls, audit).
        anonymised = backend_conn.execute(
            "select count(*) as n from public.payment_intents where id = %s and user_id is null",
            (seeded.filters["payment_intents"]["id"],),
        ).fetchone()
        assert anonymised is not None and anonymised["n"] == 1

        # Re-running after a crash is safe: nothing left, and Auth reports the user gone.
        again = purge_account(uid, deps)
        assert (again.objects_removed, again.threads_removed, again.user_deleted) == (0, 0, False)
    finally:
        cleanup_leftovers(backend_conn, seeded)
        target = hashlib.sha256(uid.encode()).hexdigest()[:16]
        backend_conn.execute(
            "delete from public.audit_log where action = 'account.purged' and target = %s",
            (target,),
        )
