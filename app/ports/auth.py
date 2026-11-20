from dataclasses import dataclass
from typing import Protocol


class InvalidToken(Exception):
    """The bearer token could not be verified."""


class AuthUnavailable(Exception):
    """Signing keys could not be obtained, so no token can be judged."""


@dataclass(frozen=True)
class VerifiedUser:
    user_id: str
    email: str | None = None
    is_admin: bool = False
    auth_time: int | None = None
    aal: str | None = None


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedUser: ...
