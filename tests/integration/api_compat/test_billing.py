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


def _claimed_ip_buckets(backend):
    return {b for b, _ in backend.guards.counts if b.startswith("ip:")}


def _claim_from(backend, headers, **client_kw):
    backend.guards.counts.clear()
    backend.profiles.bonus.clear()
    _verify(backend)
    c = _build_client(backend, **client_kw)
    c.post("/billing/claim-signup-bonus", headers={**auth_header(), **headers})
    return _claimed_ip_buckets(backend)


def _ip(value):
    return {guard_hash("ip", value, PEPPER)}


def test_forwarded_header_ignored_without_trusted_hops(backend):
    got = _claim_from(backend, {"X-Forwarded-For": "7.7.7.7"}, hops=0)
    assert got == _ip("testclient")


def test_forwarded_entry_counted_from_the_right(backend):
    xff = {"X-Forwarded-For": "6.6.6.6 , 7.7.7.7, 10.0.0.1"}  # leftmost is client-spoofable
    assert _claim_from(backend, xff, hops=1) == _ip("10.0.0.1")
    assert _claim_from(backend, xff, hops=2) == _ip("7.7.7.7")
    assert _claim_from(backend, xff, hops=3) == _ip("6.6.6.6")


def test_forwarded_with_too_few_entries_falls_back_to_peer(backend):
    assert _claim_from(backend, {"X-Forwarded-For": "7.7.7.7"}, hops=2) == _ip("testclient")


def test_client_ip_header_takes_precedence(backend):
    hdr = {"CF-Connecting-IP": "8.8.8.8", "X-Forwarded-For": "7.7.7.7, 10.0.0.1"}
    assert _claim_from(backend, hdr, hops=1, ip_header="CF-Connecting-IP") == _ip("8.8.8.8")
    assert _claim_from(backend, {}, hops=0, ip_header="CF-Connecting-IP") == _ip("testclient")


def test_ipv6_is_bucketed_by_slash_64_in_the_route(backend):
    hdr = {"X-Forwarded-For": "2001:db8:1:2:aaaa::1"}
    assert _claim_from(backend, hdr, hops=1) == _ip("2001:db8:1:2::/64")


def test_device_header_validated(client, backend):
    _verify(backend)
    hdr = {**auth_header(), "X-Device-Id": "x" * 65}
    assert client.post("/billing/claim-signup-bonus", headers=hdr).json()["status"] == "granted"
    assert [b.split(":")[0] for b, _ in backend.guards.counts] == ["ip"]
    backend.guards.counts.clear()
    _verify(backend, USER_B)
    hdr = {**auth_header("token-b"), "X-Device-Id": "dev_1.ok-2"}
    client.post("/billing/claim-signup-bonus", headers=hdr)
    assert guard_hash("device", "dev_1.ok-2", PEPPER) in {b for b, _ in backend.guards.counts}
