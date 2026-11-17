import logging
from collections.abc import Mapping
from typing import Any

import structlog

from app.container import Container
from app.domain.cv.profile_text import ProfileBuilder
from app.pipeline.errors import NotAwaitingInput, PipelineStepFailed
from app.pipeline.state import RunOptions
from app.ports.pipeline import JsonDict
from app.services.finalize import finalize_session

logger = logging.getLogger(__name__)
_log = structlog.get_logger("pipeline")

AWAIT_ANSWERS = "await_answers"
AWAIT_COVER_LETTER = "cover_letter_options"
_TONES = ("formal", "conversational")
_LENGTHS = ("short", "standard")


def _options(c: Container, cover_letter: bool, tone: str | None, length: str | None) -> RunOptions:
    """Unknown tone/length values become None, so the run pauses to ask for them."""
    return RunOptions.model_validate(
        {
            "cover_letter": bool(cover_letter),
            "cover_letter_tone": tone if tone in _TONES else None,
            "cover_letter_length": length if length in _LENGTHS else None,
            "max_passes": c.settings.pipeline.max_passes,
        }
    )


def _step_failed(c: Container, thread_id: str, failure: PipelineStepFailed) -> None:
    """A required step failed: mark the session errored (no render, no coin deduction)."""
    _log.warning("pipeline.failed", step=failure.step, code=failure.code)
    c.store.update_session(thread_id, {"status": "error"})


def _pause_status(c: Container, thread_id: str) -> bool:
    """Record a pause on the session row; False when the run finished."""
    state = c.pipeline.get_state(thread_id)
    next_nodes = state.get("next", [])
    values = state.get("values", {})
    if AWAIT_ANSWERS in next_nodes:
        eligibility = values.get("eligibility")
        c.store.update_session(
            thread_id,
            {
                "status": "awaiting_hitl",
                "gaps": [q.text for q in values.get("questions", [])],
                "eligibility_score": eligibility.score if eligibility else None,
            },
        )
        return True
    if AWAIT_COVER_LETTER in next_nodes:
        c.store.update_session(thread_id, {"status": "awaiting_cover_letter_options"})
        return True
    return False


def run_new_session(
    c: Container,
    *,
    user_id: str,
    thread_id: str,
    profile: JsonDict,
    job_description: str,
    cover_letter: bool,
    cover_letter_tone: str | None,
    cover_letter_length: str | None,
) -> None:
    try:
        # Convert saved profile to resume text using domain-aware builder
        resume_text = ProfileBuilder.from_profile_dict(profile)

        result = c.pipeline.run(
            job_description=job_description,
            user_resume_text=resume_text,
            thread_id=thread_id,
            options=_options(c, cover_letter, cover_letter_tone, cover_letter_length),
        )
        if not _pause_status(c, thread_id):
            finalize_session(c, thread_id, result, user_id, profile=profile)

    except PipelineStepFailed as failure:
        _step_failed(c, thread_id, failure)
    except Exception:
        logger.exception("Pipeline error for thread %s", thread_id)
        c.store.update_session(thread_id, {"status": "error"})


def resume_after_answers(
    c: Container, *, user_id: str, thread_id: str, reply: Mapping[str, Any] | str | None
) -> None:
    try:
        result = c.pipeline.resume(thread_id, reply)
        if not _pause_status(c, thread_id):
            profile = c.store.get_cv_profile(user_id)
            finalize_session(c, thread_id, result, user_id, profile=profile)
    except NotAwaitingInput:
        _log.warning("pipeline.reply_not_awaited")
        c.store.update_session(thread_id, {"status": "error"})
    except PipelineStepFailed as failure:
        _step_failed(c, thread_id, failure)
    except Exception:
        logger.exception("Resume error for thread %s", thread_id)
        c.store.update_session(thread_id, {"status": "error"})


def resume_after_cover_letter_options(
    c: Container, *, user_id: str, thread_id: str, tone: str, length: str
) -> None:
    try:
        result = c.pipeline.resume_cover_letter(thread_id, tone, length)
        profile = c.store.get_cv_profile(user_id)
        finalize_session(c, thread_id, result, user_id, profile=profile)
    except PipelineStepFailed as failure:
        _step_failed(c, thread_id, failure)
    except Exception:
        logger.exception("Cover letter resume error for %s", thread_id)
        c.store.update_session(thread_id, {"status": "error"})
