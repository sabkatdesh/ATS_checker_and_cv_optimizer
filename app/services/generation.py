import logging

from app.container import Container
from app.domain.cv.profile_text import ProfileBuilder
from app.ports.pipeline import JsonDict
from app.services.finalize import finalize_session

logger = logging.getLogger(__name__)


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

        # Run the pipeline
        result = c.pipeline.run(
            job_description=job_description,
            user_resume_text=resume_text,
            thread_id=thread_id,
            cover_letter_requested=bool(cover_letter),
            cover_letter_tone=cover_letter_tone,
            cover_letter_length=cover_letter_length,
        )

        # Check if pipeline paused at a HITL node
        pipeline_state = c.pipeline.get_state(thread_id)
        next_nodes = pipeline_state.get("next", [])
        values = pipeline_state.get("values", {})

        if "hitl_node" in next_nodes:
            gaps = values.get("gaps_identified", [])
            eligibility = values.get("eligibility_verdict")
            c.store.update_session(
                thread_id,
                {
                    "status": "awaiting_hitl",
                    "gaps": gaps,
                    "eligibility_score": eligibility.score if eligibility else None,
                },
            )
        elif "cover_letter_hitl" in next_nodes:
            # Paused waiting for cover letter tone/length
            c.store.update_session(thread_id, {"status": "awaiting_cover_letter_options"})
        else:
            # Pipeline completed — finalize
            finalize_session(c, thread_id, result, user_id, profile=profile)

    except Exception:
        logger.exception("Pipeline error for thread %s", thread_id)
        c.store.update_session(thread_id, {"status": "error"})


def resume_after_answers(c: Container, *, user_id: str, thread_id: str, user_qna: str) -> None:
    try:
        result = c.pipeline.resume(thread_id, user_qna)
        pipeline_state = c.pipeline.get_state(thread_id)
        next_nodes = pipeline_state.get("next", [])

        if "cover_letter_hitl" in next_nodes:
            c.store.update_session(thread_id, {"status": "awaiting_cover_letter_options"})
        else:
            profile = c.store.get_cv_profile(user_id)
            finalize_session(c, thread_id, result, user_id, profile=profile)
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
    except Exception:
        logger.exception("Cover letter resume error for %s", thread_id)
        c.store.update_session(thread_id, {"status": "error"})
