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


def test_ttl_expired_endpoint_down_one_fetch_per_window_and_stale_served(keys, clock):
    fetch = FakeJwks([keys.jwk("k1")])
    cache = make(clock, fetch)
    cache.key_for("k1")
    fetch.down = True
    clock.now += 700
    for _ in range(20):
        assert cache.key_for("k1") is not None
    assert fetch.calls == 2  # warmup + one failed attempt
    clock.now += 31
    for _ in range(20):
        assert cache.key_for("k1") is not None
    assert fetch.calls == 3


def test_cold_endpoint_down_one_fetch_then_immediate_unavailable(clock):
    fetch = FakeJwks([])
    fetch.down = True
    cache = make(clock, fetch)
    for _ in range(10):
        with pytest.raises(AuthUnavailable):
            cache.key_for("k1")
    assert fetch.calls == 1
    clock.now += 31
    with pytest.raises(AuthUnavailable):
        cache.key_for("k1")
    assert fetch.calls == 2


def test_concurrent_callers_do_not_queue_behind_slow_fetch(keys, clock):
    import threading

    started, release = threading.Event(), threading.Event()
    jwk = keys.jwk("k1")
    state = {"slow": False, "calls": 0}

    def fetch(url):
        state["calls"] += 1
        if state["slow"]:
            started.set()
            release.wait(5)
        return {"keys": [jwk]}

    cache = make(clock, fetch)
    cache.key_for("k1")
    state["slow"] = True
    clock.now += 700
    t = threading.Thread(target=lambda: cache.key_for("k1"))
    t.start()
    assert started.wait(2)
    result: list = []
    t2 = threading.Thread(target=lambda: result.append(cache.key_for("k1")))
    t2.start()
    t2.join(1)
    assert not t2.is_alive() and result  # served stale while refresh in flight
    assert state["calls"] == 2
    release.set()
    t.join(2)


def test_cold_concurrent_caller_fails_fast_during_fetch(keys, clock):
    import threading

    started, release = threading.Event(), threading.Event()

    def fetch(url):
        started.set()
        release.wait(5)
        return {"keys": [keys.jwk("k1")]}

    cache = make(clock, fetch)
    t = threading.Thread(target=lambda: cache.key_for("k1"))
    t.start()
    assert started.wait(2)
    errors: list = []

    def other():
        try:
            cache.key_for("k1")
        except AuthUnavailable as exc:
            errors.append(exc)

    t2 = threading.Thread(target=other)
    t2.start()
    t2.join(1)
    assert not t2.is_alive() and errors
    release.set()
    t.join(2)


def test_malformed_entries_skipped_not_whole_set(keys, clock):
    entries = [None, "junk", {"kty": "EC"}, {"kid": "bad", "kty": "nope"}, keys.jwk("k1")]
    cache = make(clock, FakeJwks(entries))
    assert cache.key_for("k1") is not None


def test_symmetric_and_non_sig_entries_ignored(keys, clock):
    oct_key = {"kty": "oct", "kid": "sym", "k": "c2VjcmV0"}
    enc = dict(keys.jwk("enc"), use="enc")
    cache = make(clock, FakeJwks([oct_key, enc, keys.jwk("k1")]))
    cache.key_for("k1")
    for kid in ("sym", "enc"):
        with pytest.raises(InvalidToken):
            cache.key_for(kid)
