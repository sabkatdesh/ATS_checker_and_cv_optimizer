import uuid
from functools import partial

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_container, require_user_id
from app.api.schemas.sessions import HITLReplyRequest, StartSessionRequest
from app.container import Container
from app.domain.credits.legacy import CV_GENERATION_COST
from app.domain.parsing.input_validator import validate_jd
from app.services.generation import resume_after_answers, run_new_session

router = APIRouter()


@router.post("/sessions/start")
def start_session(
    body: StartSessionRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    """
    Start a CV generation session.
    1. Validates JD
    2. Checks user has a profile
    3. Checks user has enough coins
    4. Runs pipeline in background
    5. Returns thread_id immediately
    """
    user_id = require_user_id(c, authorization)

    # Step 1 — Validate the job description
    jd_check = validate_jd(body.job_description)
    if not jd_check.is_valid:
        raise HTTPException(status_code=400, detail=jd_check.user_message)

    # Step 2 — Check user has a profile
    profile = c.store.get_cv_profile(user_id)
    if not profile:
        raise HTTPException(
            status_code=400, detail="Please complete your profile first before generating a CV"
        )

    # Step 3 — Check coin balance
    balance = c.store.get_coin_balance(user_id)
    if balance < CV_GENERATION_COST:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough coins. You need {CV_GENERATION_COST} coins. Current balance: {balance}"
            ),
        )

    # Step 4 — Create session record in database
    thread_id = f"thread_{uuid.uuid4().hex}"
    c.store.create_session(
        user_id,
        thread_id,
        body.job_description,
        cover_letter_requested=bool(body.cover_letter),
        cover_letter_tone=body.cover_letter_tone,
        cover_letter_length=body.cover_letter_length,
    )

    # Step 5 — Run pipeline in background thread
    # We use a thread so the API responds immediately
    # User polls /sessions/{thread_id}/status to check progress
    c.runner.submit(
        partial(
            run_new_session,
            c,
            user_id=user_id,
            thread_id=thread_id,
            profile=profile,
            job_description=body.job_description,
            cover_letter=body.cover_letter,
            cover_letter_tone=body.cover_letter_tone,
            cover_letter_length=body.cover_letter_length,
        )
    )

    return {
        "thread_id": thread_id,
        "status": "running",
        "message": "CV generation started. Poll /sessions/{thread_id}/status to check progress.",
    }


@router.post("/sessions/{thread_id}/reply")
def hitl_reply(
    thread_id: str,
    body: HITLReplyRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    """
    User submits answers to HITL gap questions.
    Resumes the pipeline from where it paused.
    """
    user_id = require_user_id(c, authorization)
    session = c.store.get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    if session["status"] != "awaiting_hitl":
        raise HTTPException(status_code=400, detail="Session is not waiting for your input")

    # Update status and resume in background
    c.store.update_session(thread_id, {"status": "running"})

    c.runner.submit(
        partial(
            resume_after_answers,
            c,
            user_id=user_id,
            thread_id=thread_id,
            user_qna=body.user_qna,
        )
    )

    return {"status": "resumed", "message": "Pipeline resumed. Keep polling /status"}


@router.get("/sessions/{thread_id}/status")
def session_status(
    thread_id: str, authorization: str = Header(None), c: Container = Depends(get_container)
):
    """
    Poll this endpoint every few seconds to check progress.
    Returns current status + scores when complete.
    """
    user_id = require_user_id(c, authorization)
    session = c.store.get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Security — only owner can see their session
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    return session


@router.get("/sessions")
def list_sessions(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get all past CV generations for the logged-in user"""
    user_id = require_user_id(c, authorization)
    sessions = c.store.get_user_sessions(user_id)
    return {"sessions": sessions}
