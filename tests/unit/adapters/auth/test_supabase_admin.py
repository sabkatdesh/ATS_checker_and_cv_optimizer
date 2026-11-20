from unittest.mock import MagicMock

import httpx
import pytest

from app.adapters.auth.supabase_admin import SupabaseAdmin
from app.ports.user_admin import UserAdminError

UID = "11111111-1111-1111-1111-111111111111"
SECRET = "https://abc.supabase.co/auth/v1/admin/users/x service-key-SECRET"


class _Boom(Exception):
    def __init__(self, status=None, code=None):
        super().__init__(SECRET)
        self.status, self.code = status, code


def _admin():
    client = MagicMock()
    return SupabaseAdmin(client, sleep=lambda s: None), client.auth.admin.delete_user


def test_delete_user_true_on_success():
    admin, call = _admin()
    assert admin.delete_user(UID) is True
    call.assert_called_once_with(UID)


@pytest.mark.parametrize("exc", [_Boom(404), _Boom(422, "user_not_found")])
def test_not_found_means_already_deleted(exc):
    admin, call = _admin()
    call.side_effect = exc
    assert admin.delete_user(UID) is False
    assert call.call_count == 1


def test_retries_5xx_then_succeeds():
    admin, call = _admin()
    call.side_effect = [_Boom(503), httpx.ConnectError("x"), None]
    assert admin.delete_user(UID) is True
    assert call.call_count == 3


def test_gives_up_after_two_retries_with_constant_message():
    admin, call = _admin()
    call.side_effect = _Boom(500)
    with pytest.raises(UserAdminError) as err:
        admin.delete_user(UID)
    assert call.call_count == 3
    assert str(err.value) == "Auth user deletion failed"
    assert err.value.__cause__ is None and "SECRET" not in repr(err.value)


def test_client_error_not_retried():
    admin, call = _admin()
    call.side_effect = _Boom(403)
    with pytest.raises(UserAdminError):
        admin.delete_user(UID)
    assert call.call_count == 1
