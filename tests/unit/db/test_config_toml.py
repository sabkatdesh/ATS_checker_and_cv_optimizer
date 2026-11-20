import tomllib
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[3] / "supabase" / "config.toml"


@pytest.fixture(scope="module")
def cfg() -> dict:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def test_confirmations_on(cfg):
    email = cfg["auth"]["email"]
    assert email["enable_confirmations"] is True
    assert email["otp_expiry"] == 3600
    assert email["max_frequency"] == "60s"


def test_minimum_password_length(cfg):
    assert cfg["auth"]["minimum_password_length"] >= 8


def test_redirect_urls_include_callback(cfg):
    auth = cfg["auth"]
    assert auth["site_url"].startswith("http")
    assert "http://localhost:5173/auth/callback" in auth["additional_redirect_urls"]


def test_google_disabled_and_env_refs(cfg):
    google = cfg["auth"]["external"]["google"]
    assert google["enabled"] is False
    assert google["client_id"] == "env(SUPABASE_AUTH_GOOGLE_CLIENT_ID)"
    assert google["secret"] == "env(SUPABASE_AUTH_GOOGLE_SECRET)"
    assert google["skip_nonce_check"] is False


def test_captcha_turnstile_env_secret(cfg):
    captcha = cfg["auth"]["captcha"]
    assert captcha["enabled"] is True
    assert captcha["provider"] == "turnstile"
    assert captcha["secret"] == "env(SUPABASE_AUTH_CAPTCHA_SECRET)"


def test_smtp_block_disabled_and_secret_is_env_ref(cfg):
    smtp = cfg["auth"]["email"]["smtp"]
    assert smtp["enabled"] is False
    assert smtp["host"] == "smtp.resend.com"
    assert smtp["port"] == 465
    assert smtp["user"] == "resend"
    assert smtp["pass"] == "env(SUPABASE_AUTH_SMTP_PASS)"
    assert smtp["admin_email"] and smtp["sender_name"]


def _walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else key)
    else:
        yield path, node


def test_no_literal_secrets_in_config(cfg):
    secret_keys = {"secret", "pass", "client_id", "api_key"}
    for path, value in _walk(cfg):
        if path.rsplit(".", 1)[-1] in secret_keys and value != "":
            assert isinstance(value, str) and value.startswith("env("), path
