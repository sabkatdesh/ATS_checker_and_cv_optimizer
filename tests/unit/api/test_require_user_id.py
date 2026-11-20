import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.deps import require_user_id
from app.api.errors import AppError, _handle_app_error
from app.config.settings import ConfigError
from app.ports.auth import AuthUnavailable, InvalidToken, VerifiedUser


class _Auth:
    def __init__(self, exc=None):
        self.exc = exc

    def verify(self, token):
        if self.exc:
            raise self.exc
        return VerifiedUser(user_id="u1")


def _container(exc=None):
    return SimpleNamespace(auth=_Auth(exc))


def test_valid_returns_user_id():
    assert require_user_id(_container(), "Bearer t") == "u1"


def test_invalid_token_keeps_401_body():
    with pytest.raises(HTTPException) as exc:
        require_user_id(_container(InvalidToken("Invalid token")), "Bearer t")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired session. Please log in again."


@pytest.mark.parametrize("err", [AuthUnavailable("x"), ConfigError("x")])
def test_auth_unavailable_and_config_error_are_503_problem_json(err):
    with pytest.raises(AppError) as exc:
        require_user_id(_container(err), "Bearer t")
    request = SimpleNamespace(state=SimpleNamespace(request_id="r1"))
    response = asyncio.run(_handle_app_error(request, exc.value))
    assert response.status_code == 503
    assert response.media_type == "application/problem+json"
    assert b'"code":"AUTH_UNAVAILABLE"' in response.body.replace(b" ", b"")
