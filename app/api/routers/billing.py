from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_container, require_user_id
from app.api.schemas.billing import AddCoinsRequest
from app.container import Container
from app.domain.credits.legacy import CV_GENERATION_COST

router = APIRouter()
# Mounted by create_app only when settings.dev_tools_enabled.
dev_router = APIRouter()


@router.get("/billing/balance")
def get_balance(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get current coin balance"""
    user_id = require_user_id(c, authorization)
    balance = c.store.get_coin_balance(user_id)
    return {"balance": balance, "cost_per_cv": CV_GENERATION_COST}


@router.get("/billing/history")
def billing_history(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get full transaction history"""
    user_id = require_user_id(c, authorization)
    transactions = c.store.get_coin_transactions(user_id)
    return {"transactions": transactions}


@dev_router.post("/billing/add-coins")
def manual_add_coins(
    body: AddCoinsRequest, authorization: str = Header(None), c: Container = Depends(get_container)
):
    """
    Manually add coins to a user's account.
    This will later be called by bKash/Nagad webhook after payment.
    For now used for testing and manual top-ups.
    """
    user_id = require_user_id(c, authorization)

    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    c.store.add_coins(user_id, body.amount, body.description)
    new_balance = c.store.get_coin_balance(user_id)

    return {"message": f"{body.amount} coins added successfully", "new_balance": new_balance}
