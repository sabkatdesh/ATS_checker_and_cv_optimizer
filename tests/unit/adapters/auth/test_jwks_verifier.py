import time

import jwt
import pytest
from pydantic import SecretStr

from app.adapters.auth.jwks_cache import JwksCache
from app.adapters.auth.jwks_verifier import JwksTokenVerifier
from app.ports.auth import AuthUnavailable, InvalidToken
from tests.unit.adapters.auth.conftest import AUD, ISS, FakeJwks, make_claims, sign


def build(clock, fetch, secret=None):
    cache = JwksCache("https://x/jwks", 600, fetch, clock)
    return JwksTokenVerifier(cache, issuer=ISS, audience=AUD, hs256_secret=secret)


def ec_verifier(keys, clock, secret=None):
    fetch = FakeJwks([keys.jwk("k1")])
    return build(clock, fetch, secret), fetch


def test_valid_token_resolves_without_network_after_warmup(keys, clock):
    v, fetch = ec_verifier(keys, clock)
    token = sign(keys.ec, make_claims())
    for _ in range(5):
        assert v.verify(token).user_id == "user-1"
    assert fetch.calls == 1


def test_rs256_valid(keys, clock):
    v = build(clock, FakeJwks([keys.jwk("k1", "rsa")]))
    assert v.verify(sign(keys.rsa, make_claims(), "RS256")).email == "u@example.com"


def test_expired_401(keys, clock):
    v, _ = ec_verifier(keys, clock)
    with pytest.raises(InvalidToken):
        v.verify(sign(keys.ec, make_claims(exp=int(time.time()) - 120)))


def test_expired_within_leeway_ok(keys, clock):
    v, _ = ec_verifier(keys, clock)
    assert v.verify(sign(keys.ec, make_claims(exp=int(time.time()) - 10)))


def test_wrong_audience_401(keys, clock):
    v, _ = ec_verifier(keys, clock)
    with pytest.raises(InvalidToken):
        v.verify(sign(keys.ec, make_claims(aud="other")))


def test_wrong_issuer_401(keys, clock):
    v, _ = ec_verifier(keys, clock)
    with pytest.raises(InvalidToken):
        v.verify(sign(keys.ec, make_claims(iss="https://evil/auth/v1")))


def test_tampered_signature_401(keys, clock):
    v, _ = ec_verifier(keys, clock)
    head, body, sig = sign(keys.ec, make_claims()).split(".")
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(InvalidToken):
        v.verify(f"{head}.{body}.{flipped}")


def test_alg_none_401(keys, clock):
    v, _ = ec_verifier(keys, clock)
    token = jwt.encode(make_claims(), None, algorithm="none", headers={"kid": "k1"})
    with pytest.raises(InvalidToken):
        v.verify(token)


def test_hs256_refused_when_secret_unset(keys, clock):
    v, _ = ec_verifier(keys, clock)
    with pytest.raises(InvalidToken):
        v.verify(jwt.encode(make_claims(), "s" * 40, algorithm="HS256", headers={"kid": "k1"}))


def test_algorithm_confusion_public_key_as_hmac_secret_refused(keys, clock):
    v, _ = ec_verifier(keys, clock)
    token = jwt.encode(make_claims(), str(keys.jwk("k1")), algorithm="HS256", headers={"kid": "k1"})
    with pytest.raises(InvalidToken):
        v.verify(token)


def test_hs256_accepted_only_with_dev_secret(keys, clock):
    secret = "dev-secret-" + "x" * 32
    v, _ = ec_verifier(keys, clock, SecretStr(secret))
    assert v.verify(jwt.encode(make_claims(), secret, algorithm="HS256")).user_id == "user-1"
    with pytest.raises(InvalidToken):
        v.verify(jwt.encode(make_claims(), "w" * 40, algorithm="HS256"))


def test_missing_sub_401(keys, clock):
    v, _ = ec_verifier(keys, clock)
    with pytest.raises(InvalidToken):
        v.verify(sign(keys.ec, make_claims(sub=None)))


def test_missing_kid_401(keys, clock):
    v, _ = ec_verifier(keys, clock)
    with pytest.raises(InvalidToken):
        v.verify(sign(keys.ec, make_claims(), kid=None))


def test_unknown_kid_refetches_once_then_succeeds(keys, clock):
    v, fetch = ec_verifier(keys, clock)
    v.verify(sign(keys.ec, make_claims()))
    fetch.keys = [keys.jwk("k1"), keys.jwk("k2")]
    clock.now += 31
    assert v.verify(sign(keys.ec, make_claims(), kid="k2"))
    assert fetch.calls == 2


def test_unknown_kid_refetch_rate_limited(keys, clock):
    v, fetch = ec_verifier(keys, clock)
    v.verify(sign(keys.ec, make_claims()))
    for i in range(50):
        with pytest.raises(InvalidToken):
            v.verify(sign(keys.ec, make_claims(), kid=f"rand{i}"))
    assert fetch.calls == 1
    clock.now += 31
    with pytest.raises(InvalidToken):
        v.verify(sign(keys.ec, make_claims(), kid="rand-late"))
    assert fetch.calls == 2


def test_jwks_down_warm_cache_still_verifies(keys, clock):
    v, fetch = ec_verifier(keys, clock)
    token = sign(keys.ec, make_claims())
    v.verify(token)
    fetch.down = True
    clock.now += 5000
    assert v.verify(token).user_id == "user-1"


def test_jwks_down_cold_cache_raises_auth_unavailable(keys, clock):
    fetch = FakeJwks([])
    fetch.down = True
    v = build(clock, fetch)
    with pytest.raises(AuthUnavailable):
        v.verify(sign(keys.ec, make_claims()))


def test_admin_from_app_metadata_role(keys, clock):
    v, _ = ec_verifier(keys, clock)
    assert v.verify(sign(keys.ec, make_claims(app_metadata={"role": "admin"}))).is_admin
    assert not v.verify(sign(keys.ec, make_claims(app_metadata={"role": "user"}))).is_admin
    assert not v.verify(sign(keys.ec, make_claims())).is_admin


def test_error_message_constant_no_token_echo(keys, clock):
    v, _ = ec_verifier(keys, clock)
    bad = [
        sign(keys.ec, make_claims(aud="other")),
        sign(keys.ec, make_claims(exp=int(time.time()) - 999)),
        "garbage.token.value",
    ]
    messages = set()
    for token in bad:
        with pytest.raises(InvalidToken) as exc:
            v.verify(token)
        messages.add(str(exc.value))
        assert token not in repr(exc.value)
    assert messages == {"Invalid token"}
