import logging
from collections.abc import Mapping
from typing import Any

import structlog

from app.container import Container
from app.pipeline.errors import NotAwaitingInput, PipelineCancelled, PipelineStepFailed
from app.pipeline.state import RunOptions
from app.ports.pipeline import JsonDict
from app.services.finalize import finalize_session
from app.services.terminal import finish_session

logger = logging.getLogger(__name__)
_log = structlog.get_logger("pipeline")

AWAIT_ANSWERS = "await_answers"
AWAIT_COVER_LETTER = "cover_letter_options"
# cv_sessions.awaiting_kind values (E5)
QUESTIONS = "questions"
COVER_LETTER_OPTIONS = "cover_letter_options"
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


def _failed(c: Container, user_id: str, thread_id: str) -> None:
    finish_session(c, user_id, thread_id, status="failed", awaiting_kind=None)


def _step_failed(c: Container, user_id: str, thread_id: str, failure: PipelineStepFailed) -> None:
    """A required step failed: mark the session failed (no render, no charge)."""
    _log.warning("pipeline.failed", step=failure.step, code=failure.code)
    _failed(c, user_id, thread_id)


def _cancelled(c: Container, user_id: str, thread_id: str, cancelled: PipelineCancelled) -> None:
    """The user cancelled: mark the session cancelled (no render, no charge)."""
    _log.info("pipeline.cancelled", node=cancelled.node, stage=cancelled.stage, when=cancelled.when)
    finish_session(c, user_id, thread_id, status="cancelled", awaiting_kind=None)


def _pause_status(c: Container, user_id: str, thread_id: str) -> bool:
    """Record a pause on the session row; False when the run finished."""
    state = c.pipeline.get_state(thread_id)
    next_nodes = state.get("next", [])
    values = state.get("values", {})
    if AWAIT_ANSWERS in next_nodes:
        eligibility = values.get("eligibility")
        c.sessions.update(
            user_id,
            thread_id,
            status="awaiting_input",
            awaiting_kind=QUESTIONS,
            jd_domain=values.get("domain"),
            score_breakdown={
                "eligibility_score": eligibility.score if eligibility else None,
                "gaps": [q.text for q in values.get("questions", [])],
            },
        )
        return True
    if AWAIT_COVER_LETTER in next_nodes:
        c.sessions.update(
            user_id, thread_id, status="awaiting_input", awaiting_kind=COVER_LETTER_OPTIONS
        )
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
        result = c.pipeline.run(
            job_description=job_description,
            profile=profile,
            thread_id=thread_id,
            options=_options(c, cover_letter, cover_letter_tone, cover_letter_length),
        )
        if not _pause_status(c, user_id, thread_id):
            finalize_session(c, thread_id, result, user_id, profile=profile)

    except PipelineCancelled as cancelled:
        _cancelled(c, user_id, thread_id, cancelled)
    except PipelineStepFailed as failure:
        _step_failed(c, user_id, thread_id, failure)
    except Exception:
        logger.exception("Pipeline error for thread %s", thread_id)
        _failed(c, user_id, thread_id)


def resume_after_answers(
    c: Container, *, user_id: str, thread_id: str, reply: Mapping[str, Any] | str | None
) -> None:
    try:
        result = c.pipeline.resume(thread_id, reply)
        if not _pause_status(c, user_id, thread_id):
            profile = c.master_profiles.get_default(user_id)
            finalize_session(c, thread_id, result, user_id, profile=profile)
    except NotAwaitingInput:
        _log.warning("pipeline.reply_not_awaited")
        _failed(c, user_id, thread_id)
    except PipelineCancelled as cancelled:
        _cancelled(c, user_id, thread_id, cancelled)
    except PipelineStepFailed as failure:
        _step_failed(c, user_id, thread_id, failure)
    except Exception:
        logger.exception("Resume error for thread %s", thread_id)
        _failed(c, user_id, thread_id)


def resume_after_cover_letter_options(
    c: Container, *, user_id: str, thread_id: str, tone: str, length: str
) -> None:
    try:
        result = c.pipeline.resume_cover_letter(thread_id, tone, length)
        profile = c.master_profiles.get_default(user_id)
        finalize_session(c, thread_id, result, user_id, profile=profile)
    except PipelineCancelled as cancelled:
        _cancelled(c, user_id, thread_id, cancelled)
    except PipelineStepFailed as failure:
        _step_failed(c, user_id, thread_id, failure)
    except Exception:
        logger.exception("Cover letter resume error for %s", thread_id)
        _failed(c, user_id, thread_id)
