from fastapi import HTTPException, Request

from app.container import Container


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
