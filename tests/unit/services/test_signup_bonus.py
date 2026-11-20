import threading
from datetime import UTC, date, datetime

import pytest
from pydantic import SecretStr

from app.config.db_settings import BonusSettings
from app.config.settings import ConfigError
from app.domain.credits.bonus import normalize_ip
from app.ports.auth import VerifiedUser
from app.services.signup_bonus import BonusDeps, claim_signup_bonus, guard_hash
from tests.fakes.memory_repos import MemoryCreditRepo, MemoryGuardRepo, MemoryProfileRepo

UID = "11111111-1111-4111-8111-111111111111"
PEPPER = SecretStr("pepper-1")
DAY1, DAY2 = date(2026, 11, 20), date(2026, 11, 21)
LIFETIME = date(1970, 1, 1)


class Env:
    def __init__(self, pepper=PEPPER, blocklist=frozenset({"mailinator.com"})):
        self.day = DAY1
        self.profiles, self.credits = MemoryProfileRepo(), MemoryCreditRepo()
        self.guards = MemoryGuardRepo(self.profiles, self.credits, today=lambda: self.day)
        self.deps = BonusDeps(
            self.profiles, self.credits, self.guards, BonusSettings(hash_pepper=pepper), blocklist
        )

    def verify(self, uid=UID):
        self.profiles.bonus.setdefault(uid, {})["verified"] = datetime.now(UTC)

    def claim(self, uid=UID, ip="1.2.3.4", dev="dev-1", email="a@example.com"):
        return claim_signup_bonus(VerifiedUser(uid, email), ip, dev, self.deps)


def make(verified=True, **kw):
    env = Env(**kw)
    if verified:
        env.verify()
    return env


def test_grant_sets_profile_and_counts_both_buckets():
    env = make()
    assert env.claim() == ("granted", 100)
    assert env.credits.ledger_rows[0]["kind"] == "signup_bonus"
    assert list(env.credits._by_key) == [f"signup_bonus:{UID}"]
    assert env.profiles.bonus_state(UID).granted_at is not None
    assert env.guards.counts[(guard_hash("ip", "1.2.3.4", PEPPER), DAY1)] == 1
    assert env.guards.counts[(guard_hash("device", "dev-1", PEPPER), LIFETIME)] == 1


def test_second_claim_is_noop_already_granted():
    env = make()
    env.claim()
    before = dict(env.guards.counts)
    assert env.claim() == ("already_granted", 100)
    assert len(env.credits.ledger_rows) == 1
    assert env.guards.counts == before


def test_unverified_gets_nothing():
    env = make(verified=False)
    assert env.claim()[0] == "email_not_verified"
    assert env.credits.ledger_rows == [] and env.guards.counts == {}
    assert env.profiles.bonus_state(UID).review_at is None


def test_ip_limit_is_per_day():
    env = make()
    for i in range(3):
        env.verify(f"u{i}")
        assert env.claim(f"u{i}", dev=None)[0] == "granted"
    env.verify("u3")
    assert env.claim("u3", dev=None)[0] == "pending_review"
    env.day = DAY2
    env.verify("u4")
    assert env.claim("u4", dev=None)[0] == "granted"


def test_device_limit_is_lifetime():
    env = make()
    assert env.claim()[0] == "granted"
    env.day = DAY2
    env.verify("u2")
    assert env.claim("u2", ip="5.5.5.5")[0] == "pending_review"
    assert env.credits.balance("u2") == (0, 0)
    assert env.profiles.bonus_state("u2").review_at is not None


def test_pending_user_repeat_claim_leaves_counters_unchanged():
    env = make()
    env.verify("u2")
    env.claim()
    assert env.claim("u2", ip="5.5.5.5")[0] == "pending_review"
    before = dict(env.guards.counts)
    assert env.claim("u2", ip="6.6.6.6", dev="other")[0] == "pending_review"
    assert env.guards.counts == before


@pytest.mark.parametrize("email", ["x@Sub.Mailinator.com", "x@", "x", None, "x@nodot", "x@a..b"])
def test_blocked_or_malformed_email_goes_to_review_without_guard_use(email):
    env = make()
    assert env.claim(email=email)[0] == "pending_review"
    assert env.credits.ledger_rows == [] and env.guards.counts == {}
    assert env.profiles.bonus_state(UID).review_at is not None


def test_missing_device_id_skips_device_guard():
    env = make()
    assert env.claim(dev=None)[0] == "granted"
    assert [b.split(":")[0] for b, _ in env.guards.counts] == ["ip"]


def _run_threads(fn, n):
    barrier, out = threading.Barrier(n), []

    def run(i):
        barrier.wait()
        out.append(fn(i))

    ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def test_duplicate_concurrent_claims_of_one_user_grant_once():
    env = make()
    out = _run_threads(lambda i: env.claim(), 5)
    assert {s for s, _ in out} <= {"granted", "already_granted"}
    assert [s for s, _ in out].count("granted") == 1
    assert len(env.credits.ledger_rows) == 1
    assert env.credits.balance(UID) == (100, 0)
    assert set(env.guards.counts.values()) == {1}


def test_concurrent_different_users_same_ip_stop_at_ip_max():
    env = make()
    for i in range(6):
        env.verify(f"u{i}")
    out = _run_threads(lambda i: env.claim(f"u{i}", dev=None)[0], 6)
    assert out.count("granted") == 3 and out.count("pending_review") == 3
    assert len(env.credits.ledger_rows) == 3


def test_concurrent_different_users_same_device_stop_at_device_max():
    env = make()
    for i in range(5):
        env.verify(f"u{i}")
    out = _run_threads(lambda i: env.claim(f"u{i}", ip=f"9.9.9.{i}")[0], 5)
    assert out.count("granted") == 1 and out.count("pending_review") == 4
    assert len(env.credits.ledger_rows) == 1


def test_guard_hash_is_peppered_and_stable():
    a = guard_hash("ip", "1.2.3.4", PEPPER)
    assert a == guard_hash("ip", "1.2.3.4", PEPPER)
    assert a.startswith("ip:") and "1.2.3.4" not in a and len(a) == 3 + 64
    assert a != guard_hash("ip", "1.2.3.4", SecretStr("pepper-2"))
    assert a != guard_hash("ip", "1.2.3.5", PEPPER)
    assert guard_hash("device", "1.2.3.4", PEPPER).startswith("device:")


def test_missing_pepper_raises_constant_config_error():
    env = make(pepper=None)
    with pytest.raises(ConfigError) as exc:
        env.claim()
    assert "1.2.3.4" not in str(exc.value)
    assert env.credits.ledger_rows == []
    with pytest.raises(ConfigError):
        guard_hash("ip", "1.2.3.4", None)


def test_ipv6_is_bucketed_by_slash_64():
    env = make()
    assert env.claim(ip="2001:db8:1:2::1", dev=None)[0] == "granted"
    bucket = guard_hash("ip", normalize_ip("2001:db8:1:2:ffff::9"), PEPPER)
    assert env.guards.counts[(bucket, DAY1)] == 1
