from datetime import UTC, datetime

from app.services.signup_bonus import guard_hash
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B
from tests.integration.api_compat.conftest import PEPPER, _build_client


def test_balance_is_available_credits(client, backend):
    backend.credits.balances[USER_A] = (7, 2)
    r = client.get("/billing/balance", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"balance": 5, "cost_per_cv": 0}


def test_balance_without_a_row_is_zero(client):
    assert client.get("/billing/balance", headers=auth_header()).json() == {
        "balance": 0,
        "cost_per_cv": 0,
    }


def test_history_maps_ledger_rows(client, backend):
    backend.credits.grant(USER_A, 100, "signup_bonus", f"signup_bonus:{USER_A}")
    backend.credits.grant(USER_B, 5, "purchase", "other")
    row = backend.credits.ledger_rows[0]
    row["reason"] = "Welcome bonus"
    row["created_at"] = datetime(2026, 11, 20, tzinfo=UTC)
    r = client.get("/billing/history", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {
        "transactions": [
            {
                "id": 1,
                "amount": 100,
                "type": "signup_bonus",
                "description": "Welcome bonus",
                "created_at": "2026-11-20T00:00:00+00:00",
            }
        ]
    }


def test_add_coins_route_is_gone(client):
    r = client.post("/billing/add-coins", json={"amount": 5}, headers=auth_header())
    assert r.status_code in (404, 405)


def _verify(backend, user_id=USER_A):
    backend.profiles.bonus[user_id] = {"verified": datetime(2026, 11, 20, tzinfo=UTC)}


def test_claim_grants_once_then_is_a_noop(client, backend):
    _verify(backend)
    r = client.post("/billing/claim-signup-bonus", headers=auth_header())
    assert (r.status_code, r.json()) == (200, {"status": "granted", "balance": 100})
    r = client.post("/billing/claim-signup-bonus", headers=auth_header())
    assert (r.status_code, r.json()) == (200, {"status": "already_granted", "balance": 100})
    assert len(backend.credits.ledger_rows) == 1


def test_unverified_403(client, backend):
    r = client.post("/billing/claim-signup-bonus", headers=auth_header())
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert backend.credits.ledger_rows == []


def test_claim_requires_login(client):
    assert client.post("/billing/claim-signup-bonus").status_code == 401


def test_claim_without_pepper_is_503_and_grants_nothing(backend):
    _verify(backend)
    c = _build_client(backend, pepper=None)
    r = c.post("/billing/claim-signup-bonus", headers=auth_header())
    assert r.status_code == 503
    assert backend.credits.ledger_rows == []


def test_ip_from_forwarded_only_when_trusted(backend):
    for trust, seen in ((False, "testclient"), (True, "7.7.7.7")):
        backend.guards.counts_by_bucket.clear()
        backend.profiles.bonus.clear()
        _verify(backend)
        c = _build_client(backend, trust_proxy=trust)
        hdr = {**auth_header(), "X-Forwarded-For": "7.7.7.7, 10.0.0.1"}
        c.post("/billing/claim-signup-bonus", headers=hdr)
        assert guard_hash("ip", seen, PEPPER) in backend.guards.counts_by_bucket, trust
        assert guard_hash("ip", "10.0.0.1", PEPPER) not in backend.guards.counts_by_bucket


def test_device_header_validated(client, backend):
    _verify(backend)
    hdr = {**auth_header(), "X-Device-Id": "x" * 65}
    assert client.post("/billing/claim-signup-bonus", headers=hdr).json()["status"] == "granted"
    assert [b.split(":")[0] for b in backend.guards.counts_by_bucket] == ["ip"]
    backend.guards.counts_by_bucket.clear()
    _verify(backend, USER_B)
    hdr = {**auth_header("token-b"), "X-Device-Id": "dev_1.ok-2"}
    client.post("/billing/claim-signup-bonus", headers=hdr)
    assert guard_hash("device", "dev_1.ok-2", PEPPER) in backend.guards.counts_by_bucket
