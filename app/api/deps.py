from fastapi import HTTPException, Request

from app.container import Container
from app.ports.repositories import SessionRow


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def require_user_id(container: Container, authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not logged in")
    token = authorization.replace("Bearer ", "")
    try:
        return container.auth.user_id_for(token)
    except Exception:
        raise HTTPException(
            status_code=401, detail="Invalid or expired session. Please log in again."
        ) from None


def require_session(container: Container, user_id: str, session_id: str) -> SessionRow:
    """404 for a missing row, another user's row and a malformed id alike (no 403 oracle)."""
    row = container.sessions.get(user_id, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row
