from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_container, require_user_id
from app.api.errors import AppError
from app.api.schemas.profiles import ImportCVRequest, ProfileUpdateRequest
from app.container import Container
from app.domain.text.invisible import strip_invisible
from app.services.profile_import import ImportErrorCode, ProfileImportFailed, import_profile

router = APIRouter()

# Constant messages only: never the CV text or the provider's error.
_IMPORT_ERRORS: dict[ImportErrorCode, tuple[int, str, str]] = {
    "CV_IMPORT_FAILED": (
        422,
        "CV import failed",
        "We could not read this CV. Please check the text and try again.",
    ),
    "CONTENT_REFUSED": (422, "CV import refused", "This CV text could not be processed."),
    "LLM_UNAVAILABLE": (
        503,
        "CV import unavailable",
        "CV import is temporarily unavailable. Please try again shortly.",
    ),
}


@router.get("/profile")
def get_profile(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get the logged-in user's saved CV profile"""
    user_id = require_user_id(c, authorization)
    profile = c.master_profiles.get_default(user_id)
    return {"profile": profile}


@router.post("/profile")
def update_profile(
    body: ProfileUpdateRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    """
    Save or update CV profile.
    Safe to call multiple times — updates existing profile.
    """
    user_id = require_user_id(c, authorization)

    # Only save fields that were actually sent
    data = {k: v for k, v in body.dict().items() if v is not None}

    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    c.master_profiles.upsert_default(user_id, data)
    return {"message": "Profile saved successfully"}


@router.post("/profile/import-cv")
async def import_cv(
    body: ImportCVRequest, authorization: str = Header(None), c: Container = Depends(get_container)
):
    """
    Parse a pasted CV text using the LLM and return structured profile data.
    The frontend uses this to pre-fill the profile form fields.
    """
    require_user_id(c, authorization)

    cv_text = strip_invisible(body.cv_text).strip()
    if len(cv_text) < 100:
        raise HTTPException(status_code=400, detail="CV text is too short to parse.")
    if len(cv_text) > 15000:
        raise HTTPException(
            status_code=400, detail="CV text is too long. Please paste up to 15,000 characters."
        )

    try:
        structured = await import_profile(c.llm, c.prompts, cv_text)
    except ProfileImportFailed as err:
        status, title, detail = _IMPORT_ERRORS[err.code]
        raise AppError(err.code, status, title, detail) from None
    return {"profile": structured.model_dump(mode="json")}
