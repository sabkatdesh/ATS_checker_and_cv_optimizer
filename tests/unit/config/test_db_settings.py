import pytest

from app.config.settings import AppSettings, ConfigError, load_settings


def test_hs256_secret_rejected_outside_dev():
    with pytest.raises(ConfigError):
        load_settings(env="prod", auth={"hs256_secret": "x"})


def test_hs256_secret_allowed_in_dev():
    s = load_settings(env="dev", auth={"hs256_secret": "x"})
    assert s.auth.hs256_secret is not None


def test_issuer_derived_from_url():
    s = AppSettings(auth={"supabase_url": "https://r.supabase.co"})
    assert s.auth.issuer == "https://r.supabase.co/auth/v1"


def test_explicit_issuer_wins():
    s = AppSettings(auth={"supabase_url": "https://r.supabase.co", "jwt_issuer": "https://i/x"})
    assert s.auth.issuer == "https://i/x"


def test_auth_defaults():
    a = AppSettings().auth
    assert a.jwt_audience == "authenticated"
    assert a.jwks_ttl_s == 600
    assert a.issuer is None


def test_bonus_defaults():
    b = AppSettings().bonus
    assert (b.amount, b.ip_daily_max, b.device_max) == (100, 3, 1)


def test_other_defaults():
    s = AppSettings()
    assert s.storage.signed_url_ttl_s == 600
    assert s.deletion.grace_days == 7
    assert (s.db.pool_max, s.db.connect_timeout_s, s.db.statement_timeout_ms) == (4, 10, 15000)


def test_dsn_never_in_repr():
    s = AppSettings(db={"dsn": "postgresql://u:hunter2@h/db"})
    assert "hunter2" not in repr(s.db)
    assert "hunter2" not in repr(s)


def test_pepper_env_alias(monkeypatch):
    monkeypatch.setenv("GUARDS__HASH_PEPPER", "pp")
    s = AppSettings()
    assert s.bonus.hash_pepper is not None and s.bonus.hash_pepper.get_secret_value() == "pp"
