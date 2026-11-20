import threading
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from app.config.db_settings import BonusSettings
from app.config.settings import ConfigError
from app.ports.auth import VerifiedUser
from app.services.signup_bonus import BonusDeps, claim_signup_bonus, guard_hash
from tests.fakes.memory_repos import MemoryCreditRepo, MemoryGuardRepo, MemoryProfileRepo

UID = "11111111-1111-4111-8111-111111111111"
USER = VerifiedUser(user_id=UID, email="Ann@Example.com")
PEPPER = SecretStr("pepper-1")


def make(verified=True, pepper=PEPPER, blocklist=frozenset({"mailinator.com"})):
    profiles, credits, guards = MemoryProfileRepo(), MemoryCreditRepo(), MemoryGuardRepo()
    if verified:
        profiles.bonus[UID] = {"verified": datetime.now(UTC)}
    settings = BonusSettings(hash_pepper=pepper)
    deps = BonusDeps(profiles, credits, guards, settings, blocklist)
    return deps, profiles, credits, guards


def test_grant_marks_profile_bumps_guards_and_returns_balance():
    deps, profiles, credits, guards = make()
    assert claim_signup_bonus(USER, "1.2.3.4", "dev-1", deps) == ("granted", 100)
    assert credits.ledger_rows[0]["kind"] == "signup_bonus"
    assert list(credits._by_key) == [f"signup_bonus:{UID}"]
    assert profiles.bonus_state(UID).granted_at is not None
    assert sorted(b.split(":")[0] for b in guards.counts_by_bucket) == ["device", "ip"]


def test_second_claim_is_noop_already_granted():
    deps, _, credits, guards = make()
    claim_signup_bonus(USER, "1.2.3.4", "dev-1", deps)
    calls = []
    real = credits.grant
    credits.grant = lambda *a: calls.append(a) or real(*a)  # type: ignore[method-assign]
    assert claim_signup_bonus(USER, "1.2.3.4", "dev-1", deps) == ("already_granted", 100)
    assert calls == []
    assert len(credits.ledger_rows) == 1
    assert sum(guards.counts_by_bucket.values()) == 2


def test_unverified_gets_nothing():
    deps, profiles, credits, _ = make(verified=False)
    assert claim_signup_bonus(USER, "1.2.3.4", None, deps)[0] == "email_not_verified"
    assert credits.ledger_rows == []
    assert profiles.bonus_state(UID).review_at is None


def test_ip_over_limit_goes_to_review_without_grant():
    deps, profiles, credits, guards = make()
    guards.counts_by_bucket[guard_hash("ip", "9.9.9.9", PEPPER)] = 3
    assert claim_signup_bonus(USER, "9.9.9.9", None, deps) == ("pending_review", 0)
    assert credits.ledger_rows == []
    assert profiles.bonus_state(UID).review_at is not None
    assert profiles.bonus_state(UID).granted_at is None


def test_known_device_goes_to_review():
    deps, _, credits, guards = make()
    guards.counts_by_bucket[guard_hash("device", "dev-1", PEPPER)] = 1
    assert claim_signup_bonus(USER, "1.2.3.4", "dev-1", deps)[0] == "pending_review"
    assert credits.ledger_rows == []


def test_disposable_email_goes_to_review():
    deps, _, credits, _ = make()
    user = VerifiedUser(user_id=UID, email="x@Sub.Mailinator.com")
    assert claim_signup_bonus(user, "1.2.3.4", None, deps)[0] == "pending_review"
    assert credits.ledger_rows == []


def test_missing_device_id_skips_device_guard():
    deps, _, _, guards = make()
    assert claim_signup_bonus(USER, "1.2.3.4", None, deps)[0] == "granted"
    assert [b.split(":")[0] for b in guards.counts_by_bucket] == ["ip"]


def test_concurrent_claims_one_grant():
    deps, _, credits, _ = make()
    results, barrier = [], threading.Barrier(5)

    def run():
        barrier.wait()
        results.append(claim_signup_bonus(USER, "1.2.3.4", "dev-1", deps))

    threads = [threading.Thread(target=run) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 5
    assert len(credits.ledger_rows) == 1
    assert credits.balance(UID) == (100, 0)
    assert {b for _, b in results} == {100}
    assert {s for s, _ in results} <= {"granted", "already_granted"}


def test_guard_hash_is_peppered_and_stable():
    a = guard_hash("ip", "1.2.3.4", PEPPER)
    assert a == guard_hash("ip", "1.2.3.4", PEPPER)
    assert a.startswith("ip:") and "1.2.3.4" not in a and len(a) == 3 + 64
    assert a != guard_hash("ip", "1.2.3.4", SecretStr("pepper-2"))
    assert a != guard_hash("ip", "1.2.3.5", PEPPER)
    assert guard_hash("device", "1.2.3.4", PEPPER).startswith("device:")


def test_missing_pepper_raises_constant_config_error():
    deps, _, credits, _ = make(pepper=None)
    with pytest.raises(ConfigError) as exc:
        claim_signup_bonus(USER, "1.2.3.4", "dev-1", deps)
    assert "1.2.3.4" not in str(exc.value)
    assert credits.ledger_rows == []
    with pytest.raises(ConfigError):
        guard_hash("ip", "1.2.3.4", None)
