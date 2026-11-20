"""Remote behaviour suite against the dev Supabase project. Opt-in: M4_REMOTE=1.

Without M4_REMOTE=1 every test here is skipped at collection and no fixture below runs, so
nothing connects anywhere. With it, the preflight checks the env and a 5 s DB connect first and
ends the session with a clear message when the project is paused or unreachable.
"""

from collections.abc import Callable, Iterator

import httpx
import pytest
from psycopg_pool import ConnectionPool

from app.adapters.auth.supabase_admin import SupabaseAdmin
from app.adapters.db.pool import make_pool
from app.adapters.storage.supabase_client import make_supabase_client
from app.adapters.storage.supabase_storage import SupabaseBlobStorage
from app.config.db_settings import DbSettings
from tests.remote._auth_admin import TIMEOUT_S, AuthAdmin, TestUser
from tests.remote._env import SKIP_REASON, RemoteEnv, load_remote_env, remote_enabled
from tests.remote._gate import mark_remote_items, preflight
from tests.remote._helpers import Conn, connect_backend
from tests.remote._rest import Rest, StorageHttp


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mark_remote_items(items, remote_enabled())


def _probe(env: RemoteEnv) -> None:
    with connect_backend(env.db_dsn.get_secret_value(), timeout_s=5) as conn:
        conn.execute("select 1")


@pytest.fixture(scope="session")
def remote_env() -> RemoteEnv:
    env = preflight(remote_enabled(), load_remote_env, _probe)
    if env is None:  # only reachable if a test un-skips itself
        pytest.skip(SKIP_REASON)
    return env


@pytest.fixture(scope="session")
def http() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=TIMEOUT_S) as client:
        yield client


@pytest.fixture(scope="session")
def auth_admin(remote_env: RemoteEnv, http: httpx.Client) -> AuthAdmin:
    admin = AuthAdmin(
        remote_env.base_url,
        remote_env.secret_key.get_secret_value(),
        remote_env.publishable_key.get_secret_value(),
        http,
    )
    admin.sweep_stale()  # leftovers of crashed runs, older than 1 h
    return admin


@pytest.fixture(scope="session", autouse=True)
def _session_start(auth_admin: AuthAdmin) -> None:
    """Preflight + stale-user sweep before the first remote test (never when skipped)."""


class UserFactory:
    """Creates disposable users and guarantees their deletion (even after failures)."""

    def __init__(self, admin: AuthAdmin) -> None:
        self.admin = admin
        self._ids: list[str] = []

    def __call__(self, *, confirmed: bool = True) -> TestUser:
        user = self.admin.create_user(confirmed=confirmed)
        self._ids.append(user.id)
        return user

    def delete_all(self) -> None:
        ids, self._ids = self._ids, []
        errors = 0
        for uid in ids:
            try:
                self.admin.delete(uid)
            except Exception:  # noqa: BLE001 - keep deleting the rest; the sweep catches it
                errors += 1
        if errors:
            raise RuntimeError(f"{errors} test user(s) not deleted; the next run sweeps them")


@pytest.fixture(scope="session")
def session_users(auth_admin: AuthAdmin) -> Iterator[UserFactory]:
    """Session-lifetime users (shared module fixtures); deleted at session end."""
    factory = UserFactory(auth_admin)
    yield factory
    factory.delete_all()


@pytest.fixture
def make_user(auth_admin: AuthAdmin) -> Iterator[UserFactory]:
    """Per-test users: make_user(confirmed=False) etc.; deleted at test teardown."""
    factory = UserFactory(auth_admin)
    yield factory
    factory.delete_all()


@pytest.fixture
def user_a(make_user: UserFactory) -> TestUser:
    return make_user(confirmed=True)


@pytest.fixture
def user_b(make_user: UserFactory) -> TestUser:
    return make_user(confirmed=True)


@pytest.fixture(scope="session")
def service_rest(remote_env: RemoteEnv, http: httpx.Client) -> Rest:
    key = remote_env.secret_key.get_secret_value()
    return Rest(remote_env.base_url, key, key, http)


@pytest.fixture(scope="session")
def anon_rest(remote_env: RemoteEnv, http: httpx.Client) -> Rest:
    return Rest(remote_env.base_url, remote_env.publishable_key.get_secret_value(), None, http)


@pytest.fixture(scope="session")
def rest(
    remote_env: RemoteEnv, http: httpx.Client, auth_admin: AuthAdmin
) -> Callable[[TestUser], Rest]:
    """rest(user): PostgREST with the publishable key and that user's JWT."""
    pub = remote_env.publishable_key.get_secret_value()
    return lambda user: Rest(remote_env.base_url, pub, auth_admin.jwt(user), http)


@pytest.fixture(scope="session")
def storage_http(
    remote_env: RemoteEnv, http: httpx.Client, auth_admin: AuthAdmin
) -> Callable[[TestUser | None], StorageHttp]:
    pub = remote_env.publishable_key.get_secret_value()

    def build(user: TestUser | None) -> StorageHttp:
        return StorageHttp(remote_env.base_url, pub, auth_admin.jwt(user) if user else None, http)

    return build


@pytest.fixture(scope="session")
def blob_storage(remote_env: RemoteEnv) -> SupabaseBlobStorage:
    """The app's Storage adapter with the secret key (the only writer of objects)."""
    return SupabaseBlobStorage(make_supabase_client(remote_env.base_url, remote_env.secret_key))


@pytest.fixture(scope="session")
def service_storage(remote_env: RemoteEnv, http: httpx.Client) -> StorageHttp:
    """Storage REST with the secret key, to observe what really landed (bypasses RLS)."""
    key = remote_env.secret_key.get_secret_value()
    return StorageHttp(remote_env.base_url, key, key, http)


@pytest.fixture(scope="session")
def supabase_admin(remote_env: RemoteEnv) -> SupabaseAdmin:
    return SupabaseAdmin(make_supabase_client(remote_env.base_url, remote_env.secret_key))


@pytest.fixture(scope="session")
def dsn(remote_env: RemoteEnv) -> str:
    return remote_env.db_dsn.get_secret_value()


@pytest.fixture(scope="session")
def backend_conn(dsn: str) -> Iterator[Conn]:
    """psycopg connection as app_backend (autocommit)."""
    with connect_backend(dsn) as conn:
        yield conn


@pytest.fixture(scope="session")
def backend_pool(remote_env: RemoteEnv) -> Iterator[ConnectionPool]:
    """The app's own pool builder, for repos and the checkpointer reader."""
    pool = make_pool(DbSettings(dsn=remote_env.db_dsn, connect_timeout_s=5, pool_max=4))
    pool.open(wait=True, timeout=15)
    yield pool
    pool.close()
