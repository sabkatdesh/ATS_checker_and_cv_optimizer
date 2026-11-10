from app.ports.auth import InvalidToken
from supabase import Client


class SupabaseTokenVerifier:
    def __init__(self, client: Client) -> None:
        self._client = client

    def user_id_for(self, token: str) -> str:
        try:
            response = self._client.auth.get_user(token)
            return str(response.user.id)  # type: ignore[union-attr]
        except Exception as exc:
            raise InvalidToken("invalid token") from exc
