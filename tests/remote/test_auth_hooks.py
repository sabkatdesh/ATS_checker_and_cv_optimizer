"""auth.users triggers: profile + zero balance on signup; verification mirrored to the profile."""

from tests.remote._helpers import Conn, balance, one, scalar


def _profile(conn: Conn, uid: str) -> dict:
    return one(
        conn,
        "select email_verified_at, bonus_granted_at, never_paid from public.profiles "
        "where user_id = %s",
        (uid,),
    )


def test_signup_creates_profile_and_zero_balance(make_user, backend_conn: Conn) -> None:
    user = make_user(confirmed=False)
    prof = _profile(backend_conn, user.id)
    assert prof["email_verified_at"] is None
    assert prof["bonus_granted_at"] is None and prof["never_paid"] is True
    assert balance(backend_conn, user.id) == (0, 0)
    count = scalar(
        backend_conn, "select count(*) from public.credit_balances where user_id = %s", (user.id,)
    )
    assert count == 1


def test_verification_sets_email_verified_at(make_user, auth_admin, backend_conn: Conn) -> None:
    user = make_user(confirmed=False)
    assert _profile(backend_conn, user.id)["email_verified_at"] is None
    auth_admin.confirm(user)  # admin update_user_by_id(email_confirm=True)
    assert _profile(backend_conn, user.id)["email_verified_at"] is not None
    # The backend-only lookup sees the same value.
    verified = scalar(backend_conn, "select public.user_email_verified(%s)", (user.id,))
    assert verified is not None


def test_confirmed_at_creation_is_verified(user_a, backend_conn: Conn) -> None:
    assert _profile(backend_conn, user_a.id)["email_verified_at"] is not None
