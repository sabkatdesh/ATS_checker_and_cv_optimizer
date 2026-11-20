import hashlib
import logging

from app.adapters.db.errors import DbConflict
from app.container import Container
from app.pipeline.summary import ats_score_of
from app.ports.blob_storage import RENDERS_BUCKET, render_path
from app.ports.pipeline import JsonDict
from app.ports.repositories import COVER_LETTER_RENDER
from app.services.terminal import finish_session

logger = logging.getLogger(__name__)
PDF = "application/pdf"


def _store_pdf(
    c: Container, user_id: str, thread_id: str, kind: str, data: bytes, template_id: str
) -> str:
    """Upload to the private bucket and record a renders row; returns the render id."""
    path = render_path(user_id, thread_id, "cv" if kind == "cv" else "cover_letter")
    c.storage.put(RENDERS_BUCKET, path, data, PDF)
    # Salted per session and kind: identical bytes in two sessions are two renders rows.
    digest = hashlib.sha256(f"{thread_id}:{kind}:".encode() + data).hexdigest()
    return c.renders.add(
        user_id, thread_id, pdf_path=path, content_hash=digest, template_id=template_id
    )


def finalize_session(
    c: Container,
    thread_id: str,
    result: JsonDict,
    user_id: str,
    profile: JsonDict | None = None,
) -> None:
    """
    Called after pipeline finishes, with the caller's user_id (never read from the row).
    1. Generates CV PDF (WeasyPrint via PDFGenerator)
    2. Optionally generates cover letter PDF (WeasyPrint via CoverLetterService)
    3. Uploads both PDFs to the private renders bucket and records renders rows
    4. Marks the session succeeded (current_render_id points at the CV render), stores the
       pipeline summary, then deletes the thread's checkpoints
    """
    ats_score = ats_score_of(result.get("ats"))
    eligibility = result.get("eligibility")
    eligibility_score = eligibility.score if eligibility is not None else None
    domain = result.get("domain") or "general"
    scores = {"eligibility_score": eligibility_score}

    # Check if eligible — only generate PDF if eligible
    if not result.get("eligible"):
        finish_session(
            c,
            user_id,
            thread_id,
            status="ineligible",
            awaiting_kind=None,
            jd_domain=domain,
            score_breakdown=scores,
        )
        return

    profile = profile or {}
    template_id = profile.get("preferred_template", "classic")
    render_id = None
    structured_cv = result.get("tailored_cv")
    if not structured_cv:
        logger.info(
            "[PDF] No tailored_cv in pipeline result for %s. Result keys: %s",
            thread_id,
            list(result.keys()),
        )
    if structured_cv:
        try:
            logger.info(
                "[PDF] Generating for %s, template=%s, domain=%s", thread_id, template_id, domain
            )
            pdf_bytes = c.make_pdf_renderer().render(
                cv_data=structured_cv,
                template_id=template_id,
                accent_color=profile.get("accent_color", "#4361ee"),
                bangla=bool(profile.get("bangla_mode", False)),
                domain=domain,
            )
            render_id = _store_pdf(c, user_id, thread_id, "cv", pdf_bytes, template_id)
            logger.info("[PDF] Uploaded successfully for %s", thread_id)
        except DbConflict:
            logger.warning("[PDF] Render row conflict for %s; no PDF link recorded", thread_id)
        except Exception:
            logger.exception("[PDF] Generation failed for %s", thread_id)

    # ── Cover letter PDF (optional) ─────────────────────────────────────────────
    cover_letter_text = None
    cl_result = result.get("cover_letter")
    if cl_result:
        try:
            candidate_name = profile.get("full_name", "")
            options = result.get("options")
            tone = (options.cover_letter_tone if options else None) or "formal"

            cl_service = c.make_cover_letter_renderer()
            cl_pdf_bytes = cl_service.render_to_pdf(
                cl_data=cl_result,
                tone=tone,
                candidate_name=candidate_name,
                bangla=bool(profile.get("bangla_mode", False)),
            )
            # Plain text version — stored so frontend can show editable draft
            cover_letter_text = cl_service.to_plain_text(cl_result, candidate_name)
            _store_pdf(c, user_id, thread_id, "cover_letter", cl_pdf_bytes, COVER_LETTER_RENDER)
        except DbConflict:
            logger.warning("Cover letter render row conflict for %s", thread_id)
        except Exception:
            logger.exception("Cover letter PDF generation failed for %s", thread_id)

    finish_session(
        c,
        user_id,
        thread_id,
        status="succeeded",
        awaiting_kind=None,
        jd_domain=domain,
        template_id=template_id,
        score_after=ats_score,
        score_breakdown=scores,
        current_render_id=render_id,
        cover_letter_text=cover_letter_text,
    )
