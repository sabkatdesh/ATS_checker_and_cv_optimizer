from app.ports.auth import InvalidToken, VerifiedUser

USER_A, USER_B = "user-a", "user-b"
TOKEN_A, TOKEN_B = "token-a", "token-b"


class FakeAuth:
    def __init__(self):
        self.tokens = {TOKEN_A: USER_A, TOKEN_B: USER_B}

    def verify(self, token: str) -> VerifiedUser:
        if token not in self.tokens:
            raise InvalidToken("invalid token")
        uid = self.tokens[token]
        return VerifiedUser(user_id=uid, email=f"{uid}@example.com")
