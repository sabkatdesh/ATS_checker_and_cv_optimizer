from typing import Protocol


class InvalidToken(Exception):
    """The bearer token could not be verified."""


class TokenVerifier(Protocol):
    def user_id_for(self, token: str) -> str: ...
