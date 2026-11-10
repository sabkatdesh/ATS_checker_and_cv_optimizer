from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_container, require_user_id
from app.api.schemas.profiles import ImportCVRequest, ProfileUpdateRequest
from app.container import Container
from services.profile_builder import ProfileBuilder

router = APIRouter()


@router.get("/profile")
def get_profile(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get the logged-in user's saved CV profile"""
    user_id = require_user_id(c, authorization)
    profile = c.store.get_cv_profile(user_id)
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

    c.store.save_cv_profile(user_id, data)
    return {"message": "Profile saved successfully"}


@router.post("/profile/import-cv")
def import_cv(
    body: ImportCVRequest, authorization: str = Header(None), c: Container = Depends(get_container)
):
    """
    Parse a pasted CV text using the LLM and return structured profile data.
    The frontend uses this to pre-fill the profile form fields.
    """
    require_user_id(c, authorization)

    cv_text = body.cv_text.strip()
    if len(cv_text) < 100:
        raise HTTPException(status_code=400, detail="CV text is too short to parse.")
    if len(cv_text) > 15000:
        raise HTTPException(
            status_code=400, detail="CV text is too long. Please paste up to 15,000 characters."
        )

    try:
        from core.schemas.universal_cv import UniversalCVStructured

        client = c.make_llm_client()
        prompt = (
            "Extract all information from the following CV into the structured JSON format. "
            "Fill every field you can find. Use the domain field to classify the profession "
            "(tech/medical/education/trades/finance/legal/creative/general). "
            "Return only the JSON object — no extra text.\n\n"
            f"CV TEXT:\n{cv_text}"
        )
        structured: UniversalCVStructured = client.invoke_structured(prompt, UniversalCVStructured)

        # Detect domain if LLM left it as GENERAL
        raw = structured.model_dump()
        if raw.get("domain") == "general":
            detected = ProfileBuilder.detect_domain(raw).value
            raw["domain"] = detected

        return {"profile": raw}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV parsing failed: {str(e)}") from None
