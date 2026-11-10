from types import SimpleNamespace

USER_A, USER_B = "user-a", "user-b"
TOKEN_A, TOKEN_B = "token-a", "token-b"


class FakeAuth:
    def __init__(self):
        self.tokens = {TOKEN_A: USER_A, TOKEN_B: USER_B}

    def user_id_for(self, token: str) -> str:
        if token not in self.tokens:
            raise ValueError("invalid token")
        return self.tokens[token]

    def legacy_get_user(self, token: str):
        return SimpleNamespace(user=SimpleNamespace(id=self.user_id_for(token)))
