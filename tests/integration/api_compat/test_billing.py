from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A


def test_balance(client, backend):
    backend.store.balances[USER_A] = 7
    r = client.get("/billing/balance", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"balance": 7, "cost_per_cv": 0}


def test_history(client, backend):
    backend.store.transactions = [{"id": 1, "amount": 5, "description": "Manual top-up"}]
    r = client.get("/billing/history", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"transactions": [{"id": 1, "amount": 5, "description": "Manual top-up"}]}


def test_add_coins_non_positive_400(client):
    r = client.post("/billing/add-coins", json={"amount": 0}, headers=auth_header())
    assert r.status_code == 400
    assert r.json() == {"detail": "Amount must be positive"}


def test_add_coins_ok(client, backend):
    backend.store.balances[USER_A] = 10
    r = client.post("/billing/add-coins", json={"amount": 5}, headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"message": "5 coins added successfully", "new_balance": 15}
