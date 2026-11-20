"""The remote suite's gate and helpers, offline: no DB, no network, no .env."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
import pytest

from app.services.account_purge import PURGE_BUCKETS
from tests.remote import _auth_admin as aa
from tests.remote._env import PAUSED_MESSAGE, SKIP_REASON, load_remote_env, remote_enabled
from tests.remote._gate import REMOTE_DIR, mark_remote_items, preflight
from tests.remote._rest import Rest, denied_or_empty
from tests.remote._seed import BUCKET_TYPES, NO_USER_LINK, USER_LINK
from tests.rls_matrix import MATRIX

BASE = "https://proj.example.test"
ENV_NAMES = (
    "DB__DSN",
    "AUTH__SUPABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_ANON_KEY",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("M4_ENV_FILE", str(tmp_path / "absent.env"))  # never the real .env
    return monkeypatch


@pytest.mark.parametrize(("value", "on"), [("1", True), (" 1 ", True), ("0", False), ("", False)])
def test_remote_enabled_only_for_1(value: str, on: bool) -> None:
    assert remote_enabled({"M4_REMOTE": value}) is on
    assert remote_enabled({}) is False


class _Item:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.markers: list[pytest.Mark] = []

    def add_marker(self, m: pytest.MarkDecorator) -> None:
        self.markers.append(m.mark)


def test_gate_skips_only_remote_items_when_disabled() -> None:
    remote = _Item(REMOTE_DIR / "test_rls_matrix.py")
    other = _Item(REMOTE_DIR.parent / "unit" / "test_x.py")
    assert mark_remote_items([remote, other], enabled=False) == 1
    assert [m.name for m in remote.markers] == ["remote", "skip"]
    assert remote.markers[1].kwargs["reason"] == SKIP_REASON
    assert other.markers == []


def test_gate_marks_but_does_not_skip_when_enabled() -> None:
    remote = _Item(REMOTE_DIR / "test_storage.py")
    assert mark_remote_items([remote], enabled=True) == 0
    assert [m.name for m in remote.markers] == ["remote"]


def test_preflight_disabled_touches_nothing() -> None:
    def boom(*_a: object) -> None:
        raise AssertionError("must not be called")

    assert preflight(False, boom, boom) is None  # type: ignore[arg-type]


def test_preflight_missing_env_exits_with_names(clean_env) -> None:
    with pytest.raises(pytest.exit.Exception) as exc:
        preflight(True, load_remote_env, lambda _e: None)
    msg = str(exc.value)
    assert "DB__DSN" in msg and "SUPABASE_PUBLISHABLE_KEY|SUPABASE_ANON_KEY" in msg


def test_preflight_unreachable_db_exits_paused(clean_env) -> None:
    clean_env.setenv(
        "DB__DSN", "postgresql://app_backend.proj:secret-pw@pooler.example.test/postgres"
    )
    clean_env.setenv("AUTH__SUPABASE_URL", BASE)
    clean_env.setenv("SUPABASE_SECRET_KEY", "sb_secret_x")
    clean_env.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_x")

    def probe(_env: object) -> None:
        raise psycopg.OperationalError("timeout")

    with pytest.raises(pytest.exit.Exception) as exc:
        preflight(True, load_remote_env, probe, ref="proj")
    assert str(exc.value) == PAUSED_MESSAGE
    assert "secret-pw" not in str(exc.value)


def test_load_remote_env_accepts_legacy_names(clean_env) -> None:
    clean_env.setenv("DB__DSN", "postgresql://x")
    clean_env.setenv("SUPABASE_URL", BASE + "/")
    clean_env.setenv("SUPABASE_SERVICE_KEY", "svc")
    clean_env.setenv("SUPABASE_ANON_KEY", "anon")
    env = load_remote_env()
    assert env.base_url == BASE
    assert env.secret_key.get_secret_value() == "svc"
    assert env.publishable_key.get_secret_value() == "anon"


def test_request_builders() -> None:
    req = aa.create_user_request(BASE, "sk", "m4test+1@example.test", "pw", False)
    assert (req.method, str(req.url)) == ("POST", f"{BASE}/auth/v1/admin/users")
    assert req.headers["apikey"] == "sk" and req.headers["authorization"] == "Bearer sk"
    assert b'"email_confirm":false' in req.content.replace(b" ", b"")
    grant = aa.password_grant_request(BASE, "pk", "e@example.test", "pw")
    assert grant.url.path == "/auth/v1/token" and grant.url.params["grant_type"] == "password"
    assert grant.headers["apikey"] == "pk" and "authorization" not in grant.headers
    assert aa.confirm_user_request(BASE, "sk", "u1").method == "PUT"
    assert aa.delete_user_request(BASE, "sk", "u1").url.path == "/auth/v1/admin/users/u1"
    listing = aa.list_users_request(BASE, "sk", 2)
    assert listing.url.params["page"] == "2"


def test_new_test_email_shape() -> None:
    email = aa.new_test_email()
    assert email.startswith("m4test+") and email.endswith("@example.test")
    assert email != aa.new_test_email()


NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("email", "age", "stale"),
    [
        ("m4test+abc@example.test", timedelta(hours=2), True),
        ("M4TEST+abc@EXAMPLE.TEST", timedelta(hours=2), True),
        ("m4test+abc@example.test", timedelta(minutes=30), False),
        ("real.person@gmail.com", timedelta(days=9), False),
        ("m4test+abc@example.com", timedelta(days=9), False),
        ("x-m4test+abc@example.test", timedelta(days=9), False),
    ],
)
def test_sweep_filter(email: str, age: timedelta, stale: bool) -> None:
    user = {"email": email, "created_at": (NOW - age).isoformat().replace("+00:00", "Z")}
    assert aa.is_stale_test_user(user, NOW) is stale


def test_sweep_filter_needs_a_timestamp() -> None:
    assert aa.is_stale_test_user({"email": "m4test+a@example.test"}, NOW) is False
    bad = {"email": "m4test+a@example.test", "created_at": "garbage"}
    assert aa.is_stale_test_user(bad, NOW) is False


def _admin(handler) -> aa.AuthAdmin:
    return aa.AuthAdmin(BASE, "sk", "pk", httpx.Client(transport=httpx.MockTransport(handler)))


def _user() -> aa.TestUser:
    return aa.TestUser(id="u1", email="m4test+1@example.test", password="pw", confirmed=True)


def test_jwt_from_password_grant_is_cached() -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return httpx.Response(200, json={"access_token": "jwt-1"})

    admin, user = _admin(handler), _user()
    assert admin.jwt(user) == "jwt-1" and admin.jwt(user) == "jwt-1"
    assert calls == ["/auth/v1/token"]


def test_jwt_falls_back_to_admin_magic_link() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/auth/v1/token":
            return httpx.Response(400, json={"error_code": "captcha_failed"})
        if req.url.path == "/auth/v1/admin/generate_link":
            return httpx.Response(200, json={"properties": {"hashed_token": "h"}})
        assert req.url.path == "/auth/v1/verify" and b'"token_hash":"h"' in req.content
        return httpx.Response(200, json={"access_token": "jwt-2"})

    assert _admin(handler).jwt(_user()) == "jwt-2"


def test_unconfirmed_user_has_no_jwt() -> None:
    user = _user()
    user.confirmed = False
    with pytest.raises(RuntimeError):
        _admin(lambda r: httpx.Response(200)).jwt(user)


def test_sweep_deletes_only_stale_test_users() -> None:
    old = (NOW - timedelta(hours=3)).isoformat()
    users = [
        {"id": "a", "email": "m4test+a@example.test", "created_at": old},
        {"id": "b", "email": "owner@company.example", "created_at": old},
        {"id": "c", "email": "m4test+c@example.test", "created_at": NOW.isoformat()},
    ]
    deleted: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(200, json={"users": users})
        deleted.append(req.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={})

    assert _admin(handler).sweep_stale(NOW) == 1
    assert deleted == ["a"]


def test_rest_sends_key_jwt_and_eq_filters() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=[])

    api = Rest(BASE, "pk", "user-jwt", httpx.Client(transport=httpx.MockTransport(handler)))
    api.select("cv_sessions", id="s1")
    api.rpc("credits_grant", {"p_user": "u"})
    assert seen[0].url.path == "/rest/v1/cv_sessions" and seen[0].url.params["id"] == "eq.s1"
    assert seen[0].headers["authorization"] == "Bearer user-jwt"
    assert seen[1].url.path == "/rest/v1/rpc/credits_grant"
    anon = Rest(BASE, "pk", None, httpx.Client(transport=httpx.MockTransport(handler)))
    anon.select("templates")
    assert "authorization" not in seen[2].headers


def test_denied_or_empty() -> None:
    assert denied_or_empty(httpx.Response(401))
    assert denied_or_empty(httpx.Response(403))
    assert denied_or_empty(httpx.Response(200, json=[]))
    assert not denied_or_empty(httpx.Response(200, json=[{"id": 1}]))
    assert not denied_or_empty(httpx.Response(500))


def test_every_matrix_table_is_classified_for_the_purge() -> None:
    """A new table must join USER_LINK (purge-checked) or NO_USER_LINK."""
    assert set(USER_LINK) | NO_USER_LINK == set(MATRIX)
    assert not set(USER_LINK) & NO_USER_LINK
    assert set(BUCKET_TYPES) == set(PURGE_BUCKETS)


def test_remote_files_stay_small() -> None:
    for path in REMOTE_DIR.glob("*.py"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 300, path.name
