from pathlib import Path

import pytest

from app.config.settings import AppSettings, ConfigError, load_settings

VARS = [
    "ENV",
    "API__CORS_ORIGINS",
    "AUTH__SUPABASE_URL",
    "OBS__LOG_LEVEL",
    "OBS__LOG_FORMAT",
    "OBS__RELEASE",
    "SENTRY_DSN",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_FOUNDRY",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in VARS:
        monkeypatch.delenv(var, raising=False)


def load(**kw: object) -> AppSettings:
    return load_settings(_env_file=None, **kw)


def test_defaults_without_env() -> None:
    s = load()
    assert s.env == "dev"
    assert s.api.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert s.supabase_url is None


def test_bad_env_value_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(ConfigError) as e:
        load()
    assert "env" in str(e.value)
    assert "'dev', 'test', 'staging' or 'prod'" in str(e.value)


def test_error_never_echoes_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API__CORS_ORIGINS", "https://x.example/secret-xyz")
    with pytest.raises(ConfigError) as e:
        load()
    assert "secret-xyz" not in str(e.value)
    assert "api.cors_origins" in str(e.value)


def test_star_origin_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API__CORS_ORIGINS", "*")
    with pytest.raises(ConfigError) as e:
        load()
    assert "use explicit origins, '*' is not allowed" in str(e.value)


def test_comma_separated_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API__CORS_ORIGINS", "https://a.example, https://b.example:8443")
    assert load().api.cors_origins == ["https://a.example", "https://b.example:8443"]


def test_json_list_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API__CORS_ORIGINS", '["https://a.example","https://b.example"]')
    assert load().api.cors_origins == ["https://a.example", "https://b.example"]


def test_localhost_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    with pytest.raises(ConfigError) as e:
        load()
    assert "api.cors_origins" in str(e.value)


def test_prod_with_explicit_origin_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("API__CORS_ORIGINS", "https://app.example.com")
    assert load().api.cors_origins == ["https://app.example.com"]


def test_unknown_dotenv_keys_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("VITE_API_URL=x\nDB__DSN=y\nREDIS__URL=z\n", encoding="utf-8")
    s = load_settings(_env_file=env_file)
    assert s.env == "dev"


def test_legacy_supabase_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://legacy.example")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sk-test-legacy")
    s = load()
    assert s.supabase_url == "https://legacy.example"
    assert s.supabase_secret_key is not None
    assert s.supabase_secret_key.get_secret_value() == "sk-test-legacy"
    monkeypatch.setenv("AUTH__SUPABASE_URL", "https://new.example")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sk-test-new")
    s = load()
    assert s.supabase_url == "https://new.example"
    assert s.supabase_secret_key is not None
    assert s.supabase_secret_key.get_secret_value() == "sk-test-new"


def test_secret_not_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sk-test-1")
    monkeypatch.setenv("SENTRY_DSN", "https://sk-test-2@sentry.example/1")
    monkeypatch.setenv("AZURE_OPENAI_KEY", "sk-test-3")
    assert "sk-test" not in repr(load())


@pytest.mark.parametrize(
    ("env", "expected"), [("dev", True), ("test", True), ("staging", False), ("prod", False)]
)
def test_dev_tools_enabled(monkeypatch: pytest.MonkeyPatch, env: str, expected: bool) -> None:
    monkeypatch.setenv("ENV", env)
    if env in ("staging", "prod"):
        monkeypatch.setenv("API__CORS_ORIGINS", "https://app.example.com")
    assert load().dev_tools_enabled is expected
