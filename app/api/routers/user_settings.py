from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_container, require_user_id
from app.api.schemas.user_settings import UserSettingsRequest
from app.container import Container

router = APIRouter()


@router.get("/settings")
def get_settings(authorization: str = Header(None), c: Container = Depends(get_container)):
    user_id = require_user_id(c, authorization)
    settings = c.store.get_user_settings(user_id)
    return {"settings": settings or {}}


@router.post("/settings")
def update_settings(
    body: UserSettingsRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    user_id = require_user_id(c, authorization)
    data = {k: v for k, v in body.dict().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No settings provided")
    c.store.save_user_settings(user_id, data)
    return {"message": "Settings saved"}
