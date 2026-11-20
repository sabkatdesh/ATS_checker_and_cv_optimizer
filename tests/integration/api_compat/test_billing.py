from datetime import UTC, datetime

from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B


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
