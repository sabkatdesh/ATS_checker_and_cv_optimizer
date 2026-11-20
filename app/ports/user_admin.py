"""Auth user administration port (service key; never exposed to request handlers)."""

from typing import Protocol


class UserAdmin(Protocol):
    def delete_user(self, user_id: str) -> bool:
        """True when the Auth user was deleted, False when it was already gone (404)."""
        ...


class UserAdminError(Exception):
    """Constant message only: never a key, URL or user id."""
