"""Claim the one-time signup bonus: decide, grant through the ledger, record the guards."""

import hmac
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from pydantic import SecretStr

from app.config.db_settings import BonusSettings
from app.config.settings import ConfigError
from app.domain.credits.bonus import BonusInputs, BonusOutcome, decide_bonus, normalize_ip
from app.ports.auth import VerifiedUser
from app.ports.repositories import CreditReadRepo, GuardRepo, ProfileRepo

_OUTCOMES: dict[str, BonusOutcome] = {
    "granted": "granted",
    "already_granted": "already_granted",
    "pending_review": "pending_review",
    "email_not_verified": "email_not_verified",
}
_NO_PEPPER = "Signup guards need GUARDS__HASH_PEPPER"


@dataclass(frozen=True)
class BonusDeps:
    profiles: ProfileRepo
    credits: CreditReadRepo
    guards: GuardRepo
    settings: BonusSettings
    blocklist: frozenset[str]


def guard_hash(kind: Literal["ip", "device"], value: str, pepper: SecretStr | None) -> str:
    """'<kind>:' + HMAC-SHA256 hex. Raw IPs and device ids are never stored."""
    if pepper is None or not pepper.get_secret_value():
        raise ConfigError(_NO_PEPPER)
    digest = hmac.new(
        pepper.get_secret_value().encode(), f"{kind}:{value}".encode(), sha256
    ).hexdigest()
    return f"{kind}:{digest}"


def _domain(email: str | None) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if email and "@" in email else ""


def _available(deps: BonusDeps, user_id: str) -> int:
    balance, held = deps.credits.balance(user_id)
    return balance - held


def claim_signup_bonus(
    user: VerifiedUser, ip: str, device_id: str | None, deps: BonusDeps
) -> tuple[BonusOutcome, int]:
    """Returns (outcome, available balance). Safe to repeat and to run concurrently: the
    guards and the grant run in one SQL transaction, and the ledger key
    signup_bonus:<user_id> lets credits_grant add the bonus only once."""
    s = deps.settings
    state = deps.profiles.bonus_state(user.user_id)
    base = BonusInputs(
        state.verified_at, state.granted_at, state.review_at, _domain(user.email), 0, 0
    )
    # Cheap checks that need no lock (counts are enforced inside the SQL function).
    outcome = decide_bonus(base, s, deps.blocklist)
    if outcome == "granted":
        ip_bucket = guard_hash("ip", normalize_ip(ip), s.hash_pepper)
        dev_bucket = guard_hash("device", device_id, s.hash_pepper) if device_id else None
        result = deps.guards.claim(
            user.user_id,
            ip_bucket,
            dev_bucket,
            ip_max=s.ip_daily_max,
            device_max=s.device_max,
            amount=s.amount,
        )
        outcome = _OUTCOMES.get(result, "pending_review")
    elif outcome == "pending_review" and state.review_at is None:
        deps.profiles.mark_bonus(user.user_id, granted=False)
    return outcome, _available(deps, user.user_id)
