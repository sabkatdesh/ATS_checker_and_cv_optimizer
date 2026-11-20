"""Balance and history read from the credit ledger (credits change only in SQL functions)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Header

from app.api.deps import get_container, require_user_id
from app.container import Container
from app.ports.repositories import JsonDict

router = APIRouter()
# Generation is free until M5 adds pricing with reserve/settle.
COST_PER_CV = 0


def _transaction(row: JsonDict) -> JsonDict:
    created = row.get("created_at")
    return {
        "id": row.get("id"),
        "amount": row.get("delta_balance"),
        "type": row.get("kind"),
        "description": row.get("reason"),
        "created_at": created.isoformat() if isinstance(created, datetime) else created,
    }


@router.get("/billing/balance")
def get_balance(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Available credits (balance minus held)."""
    user_id = require_user_id(c, authorization)
    balance, held = c.credits.balance(user_id)
    return {"balance": balance - held, "cost_per_cv": COST_PER_CV}


@router.get("/billing/history")
def billing_history(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Ledger rows, newest first."""
    user_id = require_user_id(c, authorization)
    return {"transactions": [_transaction(r) for r in c.credits.ledger(user_id)]}
