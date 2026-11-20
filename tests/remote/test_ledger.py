"""Ledger immutability and the backend's write surface on credit and serial tables.

service_role keeps Supabase's default table grants, so its writes reach the append-only
trigger and fail with LEDGER_IMMUTABLE. app_backend has SELECT only on the credit tables, so
its writes fail earlier, on the grant (42501), which is stronger; TRUNCATE (which would bypass
the row trigger) is revoked from it explicitly.
"""

import pytest
from psycopg import errors

from tests.remote._helpers import Conn, grant, insert_session, new_key, one, scalar
from tests.remote._rest import Rest


@pytest.fixture
def ledger_row(user_a, backend_conn: Conn) -> tuple[str, int]:
    grant(backend_conn, user_a.id, 10, new_key("ledger"))
    row = one(
        backend_conn,
        "select id from public.credit_ledger where user_id = %s order by id desc limit 1",
        (user_a.id,),
    )
    return user_a.id, int(row["id"])


def _ledger(conn: Conn, row_id: int) -> dict:
    return one(conn, "select * from public.credit_ledger where id = %s", (row_id,))


def test_ledger_immutable_even_for_service_role(
    ledger_row, service_rest: Rest, backend_conn: Conn
) -> None:
    _, row_id = ledger_row
    before = _ledger(backend_conn, row_id)
    resp = service_rest.update("credit_ledger", {"delta_balance": 999}, id=row_id)
    assert resp.status_code >= 400 and "LEDGER_IMMUTABLE" in resp.text
    resp = service_rest.delete("credit_ledger", id=row_id)
    assert resp.status_code >= 400 and "LEDGER_IMMUTABLE" in resp.text
    with pytest.raises(errors.InsufficientPrivilege):
        backend_conn.execute(
            "update public.credit_ledger set delta_balance = 999 where id = %s", (row_id,)
        )
    with pytest.raises(errors.InsufficientPrivilege):
        backend_conn.execute("delete from public.credit_ledger where id = %s", (row_id,))
    assert _ledger(backend_conn, row_id) == before


def test_backend_cannot_truncate_ledger(backend_conn: Conn) -> None:
    with pytest.raises(errors.InsufficientPrivilege):
        backend_conn.execute("truncate public.credit_ledger")
    sql = "select has_table_privilege('app_backend', 'public.credit_ledger', 'TRUNCATE')"
    assert scalar(backend_conn, sql) is False


def test_ledger_allows_only_user_id_nulling(
    ledger_row, user_b, service_rest: Rest, backend_conn: Conn
) -> None:
    _, row_id = ledger_row
    before = _ledger(backend_conn, row_id)
    for patch in ({"user_id": None, "reason": "x"}, {"user_id": user_b.id}, {"reason": "x"}):
        resp = service_rest.update("credit_ledger", patch, id=row_id)
        assert resp.status_code >= 400 and "LEDGER_IMMUTABLE" in resp.text, patch
    assert _ledger(backend_conn, row_id) == before
    resp = service_rest.update("credit_ledger", {"user_id": None}, id=row_id)
    assert resp.status_code == 200
    after = _ledger(backend_conn, row_id)
    assert after["user_id"] is None
    assert {k: v for k, v in after.items() if k != "user_id"} == {
        k: v for k, v in before.items() if k != "user_id"
    }
    # Already anonymised: nulling again is not an anonymisation, so it is refused too.
    resp = service_rest.update("credit_ledger", {"user_id": None}, id=row_id)
    assert resp.status_code >= 400 and "LEDGER_IMMUTABLE" in resp.text


WRITES = {
    "credit_balances-insert": "insert into public.credit_balances (user_id) values (%(uid)s)",
    "credit_balances-update": (
        "update public.credit_balances set balance = balance + 1 where user_id = %(uid)s"
    ),
    "credit_balances-delete": "delete from public.credit_balances where user_id = %(uid)s",
    "credit_reservations-insert": (
        "insert into public.credit_reservations (user_id, amount) values (%(uid)s, 1)"
    ),
    "credit_reservations-update": (
        "update public.credit_reservations set amount = 0 where user_id = %(uid)s"
    ),
    "credit_ledger-insert": (
        "insert into public.credit_ledger (user_id, kind, delta_balance) "
        "values (%(uid)s, 'adjustment', 1)"
    ),
}


@pytest.mark.parametrize("name", list(WRITES))
def test_backend_cannot_write_credit_tables_directly(user_a, backend_conn: Conn, name: str):
    with pytest.raises(errors.InsufficientPrivilege):
        backend_conn.execute(WRITES[name], {"uid": user_a.id})


def test_backend_can_insert_into_serial_tables(user_a, backend_conn: Conn) -> None:
    """bigserial ids need USAGE on the sequences (granted to app_backend in 0700)."""
    sid = insert_session(backend_conn, user_a.id)
    job = scalar(
        backend_conn,
        "insert into public.jobs (session_id, user_id, kind) values (%s, %s, 'render') "
        "returning id::text",
        (sid, user_a.id),
    )
    ev = scalar(
        backend_conn,
        "insert into public.job_events (job_id, seq, type) values (%s, 1, 'm4test') returning id",
        (job,),
    )
    au = scalar(
        backend_conn,
        "insert into public.audit_log (actor, action) values (%s, 'm4test') returning id",
        (user_a.id,),
    )
    pe = scalar(
        backend_conn,
        "insert into public.payment_events (provider, event_id) values ('m4test', %s) returning id",
        (new_key("pe"),),
    )
    assert all(isinstance(v, int) and v > 0 for v in (ev, au, pe))
    backend_conn.execute("delete from public.audit_log where id = %s", (au,))
    backend_conn.execute("delete from public.payment_events where id = %s", (pe,))
