"""Balance and history read from the credit ledger (credits change only in SQL functions)."""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import get_container, require_user, require_user_id
from app.api.errors import AppError
from app.config.settings import ConfigError
from app.container import Container
from app.domain.credits.bonus import load_disposable_domains
from app.ports.repositories import JsonDict
from app.services.signup_bonus import BonusDeps, claim_signup_bonus

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


_DEVICE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def client_ip(request: Request, trust_proxy: bool) -> str:
    """Leftmost X-Forwarded-For only behind a trusted proxy; otherwise the socket peer."""
    if trust_proxy:
        first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def device_id(raw: str | None) -> str | None:
    return raw if raw and _DEVICE_ID.fullmatch(raw) else None


@router.post("/billing/claim-signup-bonus")
def claim_bonus(
    request: Request,
    authorization: str = Header(None),
    x_device_id: str | None = Header(None),
    c: Container = Depends(get_container),
):
    """One-time signup bonus; repeat calls are no-ops that report the current state."""
    user = require_user(c, authorization)
    deps = BonusDeps(c.profiles, c.credits, c.guards, c.settings.bonus, load_disposable_domains())
    ip = client_ip(request, c.settings.api.trust_proxy)
    try:
        outcome, balance = claim_signup_bonus(user, ip, device_id(x_device_id), deps)
    except ConfigError:
        raise AppError(
            "BONUS_UNAVAILABLE", 503, "Service unavailable", "Please try again shortly."
        ) from None
    if outcome == "email_not_verified":
        raise AppError(
            "EMAIL_NOT_VERIFIED", 403, "Email not verified", "Verify your email to claim credits."
        )
    return {"status": outcome, "balance": balance}
