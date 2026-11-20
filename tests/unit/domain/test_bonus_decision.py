from datetime import UTC, datetime

import pytest

from app.config.db_settings import BonusSettings
from app.domain.credits.bonus import (
    BonusInputs,
    decide_bonus,
    load_disposable_domains,
    normalize_ip,
)

NOW = datetime(2026, 11, 20, tzinfo=UTC)
S = BonusSettings()
BLOCK = frozenset({"mailinator.com"})


def inp(**kw):
    base = {
        "verified_at": NOW,
        "granted_at": None,
        "review_at": None,
        "email_domain": "example.com",
        "ip_count_today": 0,
        "device_count": 0,
    }
    return BonusInputs(**{**base, **kw})


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({}, "granted"),
        ({"granted_at": NOW}, "already_granted"),
        ({"granted_at": NOW, "verified_at": None}, "already_granted"),
        ({"verified_at": None}, "email_not_verified"),
        ({"verified_at": None, "review_at": NOW}, "email_not_verified"),
        ({"review_at": NOW}, "pending_review"),
        ({"email_domain": "mailinator.com"}, "pending_review"),
        ({"ip_count_today": 2}, "granted"),
        ({"ip_count_today": 3}, "pending_review"),
        ({"device_count": 0}, "granted"),
        ({"device_count": 1}, "pending_review"),
    ],
)
def test_decide_bonus_table(kw, expected):
    assert decide_bonus(inp(**kw), S, BLOCK) == expected


@pytest.mark.parametrize("domain", ["MAILINATOR.com", "Sub.Mailinator.Com", "a.b.mailinator.com"])
def test_disposable_domain_pending(domain):
    assert decide_bonus(inp(email_domain=domain), S, BLOCK) == "pending_review"


@pytest.mark.parametrize("domain", ["", "nodot", "a..b", ".com", "com.", "a b.com", "-.com"])
def test_malformed_domain_pending(domain):
    assert decide_bonus(inp(email_domain=domain), S, BLOCK) == "pending_review"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.2.3.4", "1.2.3.4"),
        ("::ffff:1.2.3.4", "1.2.3.4"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:0db8:0001:0002::1", "2001:db8:1:2::/64"),
        ("not-an-ip", "not-an-ip"),
    ],
)
def test_normalize_ip(raw, expected):
    assert normalize_ip(raw) == expected


def test_lookalike_domain_is_not_blocked():
    assert decide_bonus(inp(email_domain="notmailinator.com"), S, BLOCK) == "granted"


def test_shipped_blocklist_is_lowercase_and_nonempty():
    domains = load_disposable_domains()
    assert len(domains) >= 40
    assert all(d == d.lower().strip() and "." in d for d in domains)
    assert "mailinator.com" in domains
