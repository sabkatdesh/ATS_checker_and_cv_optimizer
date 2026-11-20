"""Container picks the checkpointer: Postgres with a DSN, memory only in dev/test."""

from unittest.mock import MagicMock

import pytest

from app.adapters.db.checkpointer_pg import PostgresCheckpointerFactory
from app.config.settings import AppSettings, ConfigError
from app.container import Container
from app.pipeline.checkpointer import MemoryCheckpointerFactory

DSN = "postgresql://app_backend:pw@db.invalid:5432/postgres"


def _settings(env: str, dsn: str | None = None) -> AppSettings:
    return AppSettings(
        _env_file=None,
        env=env,
        api={"cors_origins": ["https://a.example"]},
        llm={"default_provider": "fake"},
        db={"dsn": dsn},
    )


def test_dsn_gives_postgres_factory_on_the_shared_pool():
    pool = MagicMock()
    c = Container(_settings("prod", DSN), pool=pool)
    factory = c.checkpointer
    assert isinstance(factory, PostgresCheckpointerFactory)
    assert c.checkpointer is factory
    pool.connection.assert_not_called()  # building it touches no database


@pytest.mark.parametrize("env", ["dev", "test"])
def test_no_dsn_in_dev_or_test_uses_memory(env):
    assert isinstance(Container(_settings(env)).checkpointer, MemoryCheckpointerFactory)


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_no_dsn_outside_dev_raises_config_error(env):
    with pytest.raises(ConfigError):
        _ = Container(_settings(env)).checkpointer


def test_injected_factory_is_used_by_the_pipeline():
    factory = MemoryCheckpointerFactory()
    c = Container(_settings("test"), checkpointer=factory)
    assert c.checkpointer is factory
    assert c.pipeline._checkpoints is factory  # type: ignore[attr-defined]
