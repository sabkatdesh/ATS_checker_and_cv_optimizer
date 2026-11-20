"""Claim the one-time signup bonus: decide, grant through the ledger, record the guards."""

import hmac
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Literal

from pydantic import SecretStr

from app.config.db_settings import BonusSettings
from app.config.settings import ConfigError
from app.domain.credits.bonus import BonusInputs, BonusOutcome, decide_bonus
from app.ports.auth import VerifiedUser
from app.ports.repositories import CreditReadRepo, GuardRepo, ProfileRepo

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
    """Returns (outcome, available balance). Safe to call repeatedly and concurrently:
    the ledger key signup_bonus:<user_id> lets credits_grant add the bonus only once."""
    s = deps.settings
    state = deps.profiles.bonus_state(user.user_id)
    base = BonusInputs(
        state.verified_at, state.granted_at, state.review_at, _domain(user.email), 0, 0
    )
    outcome = decide_bonus(base, s, deps.blocklist)
    day: date = datetime.now(UTC).date()
    buckets: list[str] = []
    if outcome == "granted":
        # Counts only matter once the cheap checks pass (so the pepper is needed only here).
        ip_bucket = guard_hash("ip", ip, s.hash_pepper)
        dev_bucket = guard_hash("device", device_id, s.hash_pepper) if device_id else None
        buckets = [ip_bucket] + ([dev_bucket] if dev_bucket else [])
        ip_n, dev_n = deps.guards.counts(ip_bucket, dev_bucket, day)
        outcome = decide_bonus(
            BonusInputs(*(base.verified_at, None, None, base.email_domain), ip_n, dev_n),
            s,
            deps.blocklist,
        )
    if outcome == "granted":
        deps.credits.grant(user.user_id, s.amount, "signup_bonus", f"signup_bonus:{user.user_id}")
        deps.profiles.mark_bonus(user.user_id, granted=True)
        deps.guards.bump(buckets, day)
    elif outcome == "pending_review" and state.review_at is None:
        deps.profiles.mark_bonus(user.user_id, granted=False)
    return outcome, _available(deps, user.user_id)
