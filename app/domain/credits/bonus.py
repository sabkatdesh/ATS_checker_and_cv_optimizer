"""Signup bonus decision: pure, no I/O except loading the shipped disposable-domain list."""

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.config.db_settings import BonusSettings

BonusOutcome = Literal["granted", "already_granted", "pending_review", "email_not_verified"]

_DOMAINS_FILE = Path(__file__).resolve().parents[2] / "config" / "disposable_domains.txt"


@dataclass(frozen=True)
class BonusInputs:
    verified_at: datetime | None
    granted_at: datetime | None
    review_at: datetime | None
    email_domain: str
    ip_count_today: int
    device_count: int


@lru_cache(maxsize=1)
def load_disposable_domains() -> frozenset[str]:
    """Lowercased domains, one per line; blank lines and # comments are skipped."""
    lines = _DOMAINS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(d for line in lines if (d := line.strip().lower()) and not d.startswith("#"))


def is_blocked_domain(domain: str, blocklist: frozenset[str]) -> bool:
    """Case-insensitive; a listed domain also blocks every subdomain of it."""
    parts = domain.strip().strip(".").lower().split(".")
    return any(".".join(parts[i:]) in blocklist for i in range(len(parts)))


def decide_bonus(i: BonusInputs, s: BonusSettings, blocklist: frozenset[str]) -> BonusOutcome:
    if i.granted_at is not None:
        return "already_granted"
    if i.verified_at is None:
        return "email_not_verified"
    if i.review_at is not None:
        return "pending_review"
    if (
        is_blocked_domain(i.email_domain, blocklist)
        or i.ip_count_today >= s.ip_daily_max
        or i.device_count >= s.device_max
    ):
        return "pending_review"
    return "granted"
