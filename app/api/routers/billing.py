"""Balance and history read from the credit ledger (credits change only in SQL functions)."""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import get_container, require_user, require_user_id
from app.api.errors import AppError
from app.config.settings import ConfigError
from app.container import Container
from app.domain.credits.bonus import load_disposable_domains
from app.ports.repositories import BonusUnavailable, JsonDict
from app.services.signup_bonus import BonusDeps, claim_signup_bonus

router = APIRouter()
# Generation is free until M5 adds pricing with reserve/settle.
COST_PER_CV = 0
# History label when a ledger row carries no reason.
KIND_LABELS = {
    "signup_bonus": "Signup bonus",
    "reserve": "Credits reserved",
    "capture": "CV generation",
    "release": "Credits released",
    "tier_upgrade": "Tier upgrade",
    "purchase": "Credit purchase",
    "refund_admin": "Refund",
    "adjustment": "Adjustment",
}
DEFAULT_KIND_LABEL = "Credit change"


def _transaction(row: JsonDict) -> JsonDict:
    created = row.get("created_at")
    kind = row.get("kind")
    return {
        "id": row.get("id"),
        "amount": row.get("delta_balance"),
        "type": kind,
        "description": row.get("reason") or KIND_LABELS.get(str(kind), DEFAULT_KIND_LABEL),
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


def client_ip(request: Request, hops: int, header: str | None) -> str:
    """The configured edge header, else the Nth X-Forwarded-For entry from the right, else
    the socket peer. Entries further left than the trusted hops can be forged by the client."""
    peer = request.client.host if request.client else "unknown"
    if header:
        value = request.headers.get(header, "").split(",")[0].strip()
        if value:
            return value
    if hops > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
        parts = [p for p in parts if p]
        if len(parts) >= hops:
            return parts[-hops]
    return peer


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
    api = c.settings.api
    ip = client_ip(request, api.trusted_proxy_hops, api.client_ip_header)
    try:
        outcome, balance = claim_signup_bonus(user, ip, device_id(x_device_id), deps)
    except ConfigError:
        raise AppError(
            "BONUS_UNAVAILABLE", 503, "Service unavailable", "Please try again shortly."
        ) from None
    except BonusUnavailable:
        raise AppError(
            "BONUS_UNAVAILABLE",
            409,
            "Bonus unavailable",
            "The signup bonus is not available for this account.",
        ) from None
    if outcome == "email_not_verified":
        raise AppError(
            "EMAIL_NOT_VERIFIED", 403, "Email not verified", "Verify your email to claim credits."
        )
    return {"status": outcome, "balance": balance}
