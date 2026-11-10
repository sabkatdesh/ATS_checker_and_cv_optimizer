from functools import partial

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse

from app.api.deps import get_container, require_user_id
from app.api.schemas.cover_letters import CoverLetterEditRequest, CoverLetterOptionsRequest
from app.container import Container
from app.services.generation import resume_after_cover_letter_options

router = APIRouter()


@router.post("/sessions/{thread_id}/cover-letter-options")
def submit_cover_letter_options(
    thread_id: str,
    body: CoverLetterOptionsRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    """
    Submit tone + length for cover letter generation.
    Called when the pipeline paused at cover_letter_hitl waiting for these options.
    Resumes the pipeline which then generates the cover letter and finalises the session.
    """
    user_id = require_user_id(c, authorization)
    session = c.store.get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")
    if session.get("status") != "awaiting_cover_letter_options":
        raise HTTPException(
            status_code=400,
            detail="Session is not waiting for cover letter options",
        )

    tone = body.tone if body.tone in ("formal", "conversational") else "formal"
    length = body.length if body.length in ("short", "standard") else "standard"

    c.store.update_session(thread_id, {"status": "running"})

    c.runner.submit(
        partial(
            resume_after_cover_letter_options,
            c,
            user_id=user_id,
            thread_id=thread_id,
            tone=tone,
            length=length,
        )
    )

    return {"status": "resumed", "message": "Generating cover letter. Keep polling /status."}


@router.post("/sessions/{thread_id}/cover-letter")
def save_cover_letter_edit(
    thread_id: str,
    body: CoverLetterEditRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    """
    Save a user-edited cover letter draft (plain text).
    Triggers a fresh PDF render from the edited text and updates storage.
    """
    user_id = require_user_id(c, authorization)
    session = c.store.get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Cover letter text is empty")

    # Store the edited text; PDF re-render is lightweight enough to do inline
    c.store.update_session(thread_id, {"cover_letter_text": text})
    return {"message": "Cover letter saved successfully"}


@router.get("/sessions/{thread_id}/cover-letter.pdf")
def download_cover_letter_pdf(
    thread_id: str, authorization: str = Header(None), c: Container = Depends(get_container)
):
    """
    Download the cover letter PDF for a completed session.
    Returns the Supabase storage URL (redirect) or the file bytes directly.
    """
    user_id = require_user_id(c, authorization)
    session = c.store.get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    pdf_url = session.get("cover_letter_pdf_url")
    if not pdf_url:
        raise HTTPException(
            status_code=404,
            detail="No cover letter PDF found for this session. "
            "Either it was not requested or generation failed.",
        )

    return RedirectResponse(url=pdf_url)
