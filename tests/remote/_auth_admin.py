"""GoTrue admin calls for disposable test users (m4test+<uuid7>@example.test).

Request builders are pure (unit-tested with mocks); AuthAdmin sends them. Users are created
with email_confirm set explicitly, so Auth never sends an email. No key, password or token is
ever logged or put in an assertion message.
"""

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.domain.common import uuid7

EMAIL_PREFIX = "m4test+"
EMAIL_DOMAIN = "example.test"
STALE_AFTER = timedelta(hours=1)
TIMEOUT_S = 15.0


def new_test_email() -> str:
    return f"{EMAIL_PREFIX}{uuid7()}@{EMAIL_DOMAIN}"


def new_password() -> str:
    return "M4t-" + secrets.token_urlsafe(24)


def key_headers(key: str) -> dict[str, str]:
    """apikey always; Authorization too, as supabase-py sends it (the gateway accepts a
    secret/publishable key there when it equals apikey, and a legacy JWT key as is)."""
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def create_user_request(
    base: str, secret: str, email: str, pw: str, confirmed: bool
) -> httpx.Request:
    body = {"email": email, "password": pw, "email_confirm": confirmed}
    return httpx.Request(
        "POST", f"{base}/auth/v1/admin/users", headers=key_headers(secret), json=body
    )


def confirm_user_request(base: str, secret: str, user_id: str) -> httpx.Request:
    return httpx.Request(
        "PUT",
        f"{base}/auth/v1/admin/users/{user_id}",
        headers=key_headers(secret),
        json={"email_confirm": True},
    )


def delete_user_request(base: str, secret: str, user_id: str) -> httpx.Request:
    return httpx.Request(
        "DELETE", f"{base}/auth/v1/admin/users/{user_id}", headers=key_headers(secret)
    )


def get_user_request(base: str, secret: str, user_id: str) -> httpx.Request:
    return httpx.Request(
        "GET", f"{base}/auth/v1/admin/users/{user_id}", headers=key_headers(secret)
    )


def list_users_request(base: str, secret: str, page: int, per_page: int = 200) -> httpx.Request:
    return httpx.Request(
        "GET",
        f"{base}/auth/v1/admin/users",
        headers=key_headers(secret),
        params={"page": page, "per_page": per_page},
    )


def password_grant_request(base: str, publishable: str, email: str, pw: str) -> httpx.Request:
    return httpx.Request(
        "POST",
        f"{base}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": publishable},
        json={"email": email, "password": pw},
    )


def magiclink_request(base: str, secret: str, email: str) -> httpx.Request:
    """Admin generate_link: returns a hashed token and sends no email."""
    return httpx.Request(
        "POST",
        f"{base}/auth/v1/admin/generate_link",
        headers=key_headers(secret),
        json={"type": "magiclink", "email": email},
    )


def verify_request(base: str, publishable: str, token_hash: str) -> httpx.Request:
    return httpx.Request(
        "POST",
        f"{base}/auth/v1/verify",
        headers={"apikey": publishable},
        json={"type": "magiclink", "token_hash": token_hash},
    )


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def is_stale_test_user(user: dict[str, Any], now: datetime) -> bool:
    """Only our own disposable users, and only once they are older than an hour."""
    email = str(user.get("email") or "").lower()
    if not (email.startswith(EMAIL_PREFIX) and email.endswith("@" + EMAIL_DOMAIN)):
        return False
    created = _parse_ts(user.get("created_at"))
    return created is not None and now - created > STALE_AFTER


@dataclass
class TestUser:
    __test__ = False  # not a pytest class

    id: str
    email: str
    password: str = field(repr=False)
    confirmed: bool
    _jwt: str | None = field(default=None, repr=False)


class AuthAdmin:
    def __init__(self, base: str, secret: str, publishable: str, client: httpx.Client) -> None:
        self._base = base
        self._secret = secret
        self._pub = publishable
        self._http = client

    def _send(self, req: httpx.Request, what: str, ok: tuple[int, ...] = (200,)) -> httpx.Response:
        resp = self._http.send(req)
        if resp.status_code not in ok:
            raise RuntimeError(f"auth admin {what} failed: HTTP {resp.status_code}")
        return resp

    def create_user(self, *, confirmed: bool) -> TestUser:
        email, pw = new_test_email(), new_password()
        req = create_user_request(self._base, self._secret, email, pw, confirmed)
        data = self._send(req, "create", (200, 201)).json()
        return TestUser(id=str(data["id"]), email=email, password=pw, confirmed=confirmed)

    def confirm(self, user: TestUser) -> None:
        self._send(confirm_user_request(self._base, self._secret, user.id), "confirm")
        user.confirmed = True

    def delete(self, user_id: str) -> bool:
        """True when deleted, False when already gone."""
        resp = self._send(
            delete_user_request(self._base, self._secret, user_id), "delete", (200, 204, 404)
        )
        return resp.status_code != 404

    def exists(self, user_id: str) -> bool:
        resp = self._send(get_user_request(self._base, self._secret, user_id), "get", (200, 404))
        return resp.status_code == 200

    def jwt(self, user: TestUser) -> str:
        """Password grant; if the project enforces CAPTCHA on it, an admin magic link instead."""
        if user._jwt:
            return user._jwt
        if not user.confirmed:
            raise RuntimeError("an unconfirmed test user has no session")
        req = password_grant_request(self._base, self._pub, user.email, user.password)
        resp = self._http.send(req)
        if resp.status_code != 200:
            link = self._send(
                magiclink_request(self._base, self._secret, user.email), "link"
            ).json()
            token_hash = link.get("hashed_token") or (link.get("properties") or {}).get(
                "hashed_token"
            )
            if not token_hash:
                raise RuntimeError("auth admin link failed: no token in response")
            resp = self._send(verify_request(self._base, self._pub, token_hash), "verify")
        token = resp.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("auth session failed: no access token")
        user._jwt = token
        return token

    def sweep_stale(self, now: datetime | None = None) -> int:
        """Delete leftover m4test+ users older than an hour (from crashed runs)."""
        now = now or datetime.now(UTC)
        stale: list[str] = []
        page = 1
        while True:  # list everything first: deleting while paging would shift the pages
            data = self._send(list_users_request(self._base, self._secret, page), "list").json()
            users = data.get("users", []) if isinstance(data, dict) else []
            stale.extend(str(u["id"]) for u in users if is_stale_test_user(u, now))
            if len(users) < 200:
                break
            page += 1
        return sum(1 for uid in stale if self.delete(uid))
