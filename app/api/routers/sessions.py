from functools import partial
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_container, require_session, require_user_id
from app.api.errors import AppError
from app.api.schemas.sessions import HITLReplyRequest, StartSessionRequest
from app.container import Container
from app.domain.common import uuid7
from app.domain.cv.minimums import check_minimums
from app.domain.cv.profile_to_cv import profile_to_universal_cv
from app.domain.parsing.input_validator import validate_jd
from app.domain.sessions.status import legacy_status
from app.ports.repositories import SessionRow
from app.services.generation import resume_after_answers, run_new_session
from app.services.session_view import list_view, status_view

router = APIRouter()
_log = structlog.get_logger("pipeline")
DEFAULT_TEMPLATE = "classic"
_FINISHED = frozenset({"succeeded", "failed", "cancelled", "expired", "ineligible"})


def _pipeline_summary(c: Container, row: SessionRow) -> dict[str, Any] | None:
    """Live checkpoint summary, else the stored one. The poll must never fail on it.

    A finished session's checkpoints are deleted, so its stored summary is the record.
    """
    if row.status in _FINISHED and row.pipeline_summary is not None:
        return row.pipeline_summary
    try:
        summary = c.pipeline.summary(row.id)
        if summary:
            return summary.model_dump(mode="json")
    except Exception as exc:
        _log.error("pipeline.summary_failed", error_type=type(exc).__name__)
    return row.pipeline_summary


@router.post("/sessions/start")
def start_session(
    body: StartSessionRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    """
    Start a CV generation session.
    1. Validates JD
    2. Checks user has a profile that meets the minimums
    3. Creates the session row (status running) and runs the pipeline in the background
    4. Returns thread_id (the session id) immediately
    """
    user_id = require_user_id(c, authorization)

    jd_check = validate_jd(body.job_description)
    if not jd_check.is_valid:
        raise HTTPException(status_code=400, detail=jd_check.user_message)

    profile = c.master_profiles.get_default(user_id)
    if not profile:
        raise HTTPException(
            status_code=400, detail="Please complete your profile first before generating a CV"
        )

    # The profile must meet the generation minimums (spec 08 H1)
    missing = check_minimums(profile_to_universal_cv(profile).cv)
    if missing:
        raise AppError(
            "PROFILE_INCOMPLETE",
            422,
            "Profile incomplete",
            "Add your name, one contact and at least one job or education entry first.",
            missing=missing,
        )

    thread_id = uuid7()
    c.sessions.create(
        user_id,
        thread_id,
        jd_text=body.job_description,
        source_cv={k: v for k, v in profile.items() if k != "user_id"},
        options={
            "cover_letter": bool(body.cover_letter),
            "cover_letter_tone": body.cover_letter_tone,
            "cover_letter_length": body.cover_letter_length,
        },
        template_id=DEFAULT_TEMPLATE,
    )

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
    session = require_session(c, user_id, thread_id)

    if legacy_status(session.status, session.awaiting_kind) != "awaiting_hitl":
        raise HTTPException(status_code=400, detail="Session is not waiting for your input")

    c.sessions.update(user_id, thread_id, status="running", awaiting_kind=None)

    c.runner.submit(
        partial(
            resume_after_answers,
            c,
            user_id=user_id,
            thread_id=thread_id,
            reply=body.to_reply(),
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
    session = require_session(c, user_id, thread_id)
    return {**status_view(c, user_id, session), "pipeline": _pipeline_summary(c, session)}


@router.get("/sessions")
def list_sessions(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get all past CV generations for the logged-in user"""
    user_id = require_user_id(c, authorization)
    return {"sessions": [list_view(c, user_id, s) for s in c.sessions.list_for_user(user_id)]}
