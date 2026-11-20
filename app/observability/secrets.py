"""Scrub credentials from free text: bearer tokens, JWTs, API keys, DSN passwords, URL tokens."""

import base64
import re

_BEARER = re.compile(r"(?i)\bBearer\s+[\w.~+/=-]+")
_JWT = re.compile(r"\beyJ[\w-]+\.([\w-]+)\.[\w-]+")
_KEY = re.compile(r"\bsb_(?:secret|publishable)_[\w-]+")
_URL_DSN = re.compile(r"(\bpostgres(?:ql)?(?:\+\w+)?://[^:/\s@]+:)[^@\s]*(@)", re.I)
_CONNINFO_PW = re.compile(r"(\bpassword\s*=\s*)(?:'[^']*'|\S+)", re.I)
_URL_TOKEN = re.compile(r"([?&])token=[^&\s\"'#]*", re.I)


def _jwt_sub(match: re.Match[str]) -> str:
    payload = match.group(1)
    try:
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
    except ValueError:
        return "[jwt]"
    return "[key]" if "service_role" in decoded else "[jwt]"


def scrub_secrets(value: str) -> str:
    value = _URL_DSN.sub(r"\1***\2", value)
    value = _CONNINFO_PW.sub(r"\1***", value)
    value = _BEARER.sub("Bearer [redacted]", value)
    value = _JWT.sub(_jwt_sub, value)
    value = _KEY.sub("[key]", value)
    return _URL_TOKEN.sub(r"\1token=[redacted]", value)
