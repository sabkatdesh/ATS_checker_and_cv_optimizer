import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

ISS = "https://proj.supabase.co/auth/v1"
AUD = "authenticated"


class Keys:
    def __init__(self) -> None:
        self.ec = ec.generate_private_key(ec.SECP256R1())
        self.rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwk(self, kid: str, kind: str = "ec") -> dict[str, Any]:
        alg = "ES256" if kind == "ec" else "RS256"
        priv = self.ec if kind == "ec" else self.rsa
        algo = jwt.algorithms.get_default_algorithms()[alg]
        data = json.loads(algo.to_jwk(priv.public_key()))
        data.update(kid=kid, use="sig", alg=alg)
        return data


class FakeJwks:
    def __init__(self, keys: list[dict[str, Any]]) -> None:
        self.keys = keys
        self.calls = 0
        self.down = False

    def __call__(self, url: str) -> dict[str, Any]:
        self.calls += 1
        if self.down:
            raise ConnectionError("down")
        return {"keys": list(self.keys)}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def keys() -> Keys:
    return Keys()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make_claims(**over: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": "user-1",
        "aud": AUD,
        "iss": ISS,
        "iat": now,
        "exp": now + 3600,
        "email": "u@example.com",
    }
    claims.update(over)
    return {k: v for k, v in claims.items() if v is not None}


def sign(
    private_key: Any, claims: dict[str, Any], alg: str = "ES256", kid: str | None = "k1"
) -> str:
    headers = {"kid": kid} if kid else {}
    return jwt.encode(claims, private_key, algorithm=alg, headers=headers)
