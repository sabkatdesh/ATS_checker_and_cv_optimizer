import pytest

from app.adapters.auth.jwks_cache import JwksCache
from app.ports.auth import AuthUnavailable, InvalidToken
from tests.unit.adapters.auth.conftest import FakeJwks


def make(clock, fetch):
    return JwksCache("https://x/jwks", 600, fetch, clock)


def test_ttl_expiry_refetches(keys, clock):
    fetch = FakeJwks([keys.jwk("k1")])
    cache = make(clock, fetch)
    cache.key_for("k1")
    clock.now += 599
    cache.key_for("k1")
    assert fetch.calls == 1
    clock.now += 2
    cache.key_for("k1")
    assert fetch.calls == 2


def test_stale_keys_served_when_refresh_fails(keys, clock):
    fetch = FakeJwks([keys.jwk("k1")])
    cache = make(clock, fetch)
    cache.key_for("k1")
    fetch.down = True
    clock.now += 700
    assert cache.key_for("k1") is not None


def test_cold_cache_fetch_failure_is_unavailable(clock):
    fetch = FakeJwks([])
    fetch.down = True
    with pytest.raises(AuthUnavailable):
        make(clock, fetch).key_for("k1")


def test_unknown_kid_is_invalid_not_unavailable(keys, clock):
    cache = make(clock, FakeJwks([keys.jwk("k1")]))
    cache.key_for("k1")
    with pytest.raises(InvalidToken):
        cache.key_for("nope")
