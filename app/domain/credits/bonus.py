"""Signup bonus decision: pure, no I/O except loading the shipped disposable-domain list."""

import ipaddress
import re
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


_DOMAIN = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")


def is_valid_domain(domain: str) -> bool:
    return _DOMAIN.fullmatch(domain.strip().lower()) is not None


def normalize_ip(raw: str) -> str:
    """IPv4 as is; IPv4-mapped IPv6 -> the IPv4; other IPv6 -> its /64 network.

    A /64 is one subscriber, so rotating inside it must not mint new guard buckets.
    Anything unparseable is returned unchanged (still hashed, never trusted)."""
    try:
        ip = ipaddress.ip_address(raw.strip())
    except ValueError:
        return raw.strip()
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


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
        not is_valid_domain(i.email_domain)
        or is_blocked_domain(i.email_domain, blocklist)
        or i.ip_count_today >= s.ip_daily_max
        or i.device_count >= s.device_max
    ):
        return "pending_review"
    return "granted"
