"""Bonus rejections and history labels."""

from datetime import UTC, datetime

import pytest

from app.ports.repositories import BonusUnavailable
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A


def test_rejected_bonus_claim_is_a_constant_409(client, backend, monkeypatch):
    backend.profiles.bonus[USER_A] = {"verified": datetime(2026, 11, 20, tzinfo=UTC)}

    def reject(*_a, **_k):
        raise BonusUnavailable

    monkeypatch.setattr(backend.guards, "claim", reject)
    r = client.post("/billing/claim-signup-bonus", headers=auth_header())
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "BONUS_UNAVAILABLE"
    assert body["detail"] == "The signup bonus is not available for this account."
    assert backend.credits.ledger_rows == []


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        ("signup_bonus", "Signup bonus"),
        ("purchase", "Credit purchase"),
        ("capture", "CV generation"),
        ("refund_admin", "Refund"),
        ("adjustment", "Adjustment"),
        ("something_new", "Credit change"),
    ],
)
def test_history_description_falls_back_to_a_kind_label(client, backend, kind, label):
    row = {"id": 1, "user_id": USER_A, "kind": kind, "delta_balance": 5, "reason": None}
    row["created_at"] = datetime(2026, 11, 20, tzinfo=UTC)
    backend.credits.ledger_rows.append(row)
    r = client.get("/billing/history", headers=auth_header())
    assert r.json()["transactions"][0]["description"] == label
