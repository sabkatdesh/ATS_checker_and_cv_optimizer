from unittest.mock import MagicMock

import pytest

from app.adapters.db.supabase_token_verifier import SupabaseTokenVerifier
from app.ports.auth import InvalidToken


def test_returns_user_id():
    client = MagicMock()
    client.auth.get_user.return_value.user.id = "u1"
    assert SupabaseTokenVerifier(client).user_id_for("tok") == "u1"
    client.auth.get_user.assert_called_once_with("tok")


def test_any_exception_is_invalid_token():
    client = MagicMock()
    client.auth.get_user.side_effect = RuntimeError("x")
    with pytest.raises(InvalidToken):
        SupabaseTokenVerifier(client).user_id_for("tok")
