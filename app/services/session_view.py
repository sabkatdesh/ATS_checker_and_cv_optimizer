"""Legacy API shape of a cv_sessions row (the frontend reads these field names).

Mapping from the v2 columns:
  thread_id              <- id (UUIDv7 text; also the LangGraph thread_id)
  status                 <- legacy_status(status, awaiting_kind)
  job_description        <- jd_text
  ats_score              <- score_after
  semantic_score         <- score_breakdown.semantic_score (not produced yet: null)
  improvement_score      <- score_breakdown.improvement_score (not produced yet: null)
  eligibility_score      <- score_breakdown.eligibility_score
  gaps                   <- score_breakdown.gaps (question texts while awaiting answers)
  pdf_url                <- signed URL for renders.pdf_path of current_render_id
  template_id            <- template_id
  domain                 <- jd_domain
  cover_letter_requested <- options.cover_letter
  cover_letter_tone      <- options.cover_letter_tone
  cover_letter_length    <- options.cover_letter_length
  cover_letter_text      <- cover_letter_text
  cover_letter_pdf_url   <- signed URL for the session's 'cover_letter' renders row
  created_at             <- created_at (ISO 8601)
"""

from typing import Any

from app.container import Container
from app.domain.sessions.status import legacy_status
from app.ports.repositories import JsonDict, SessionRow
from app.services.pdf_links import signed_pdf_url


def _scores(row: SessionRow) -> JsonDict:
    return dict(row.score_breakdown or {})


def list_view(c: Container, user_id: str, row: SessionRow) -> JsonDict:
    """The /sessions list fields (the legacy list column set)."""
    scores = _scores(row)
    return {
        "thread_id": row.id,
        "status": legacy_status(row.status, row.awaiting_kind),
        "job_description": row.jd_text,
        "ats_score": row.score_after,
        "semantic_score": scores.get("semantic_score"),
        "improvement_score": scores.get("improvement_score"),
        "eligibility_score": scores.get("eligibility_score"),
        "pdf_url": signed_pdf_url(c, user_id, row.pdf_path),
        "template_id": row.template_id,
        "domain": row.jd_domain,
        "cover_letter_requested": bool(row.options.get("cover_letter")),
        "cover_letter_text": row.cover_letter_text,
        "cover_letter_pdf_url": signed_pdf_url(c, user_id, row.cover_letter_pdf_path),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def status_view(c: Container, user_id: str, row: SessionRow) -> JsonDict:
    """The /status fields: the list fields plus the HITL and option fields."""
    extra: dict[str, Any] = {
        "user_id": row.user_id,
        "gaps": list(_scores(row).get("gaps") or []),
        "cover_letter_tone": row.options.get("cover_letter_tone"),
        "cover_letter_length": row.options.get("cover_letter_length"),
    }
    return {**list_view(c, user_id, row), **extra}
