import logging

from app.container import Container
from app.domain.credits.legacy import CV_GENERATION_COST
from app.pipeline.summary import ats_score_of
from app.ports.blob_storage import RENDERS_BUCKET, render_path
from app.ports.pipeline import JsonDict

logger = logging.getLogger(__name__)


def finalize_session(
    c: Container,
    thread_id: str,
    result: JsonDict,
    user_id: str,
    profile: JsonDict | None = None,
) -> None:
    """
    Called after pipeline finishes.
    1. Generates CV PDF (WeasyPrint via PDFGenerator)
    2. Optionally generates cover letter PDF (WeasyPrint via CoverLetterService)
    3. Uploads both PDFs to the private renders bucket (stores the path)
    4. Deducts coins
    5. Updates session as complete
    """
    pdf_url = None
    ats_score = ats_score_of(result.get("ats"))
    eligibility = result.get("eligibility")
    eligibility_score = eligibility.score if eligibility is not None else None
    domain = result.get("domain") or "general"

    # Check if eligible — only generate PDF if eligible
    if not result.get("eligible"):
        c.store.update_session(
            thread_id,
            {
                "status": "ineligible",
                "domain": domain,
                "eligibility_score": eligibility_score,
            },
        )
        return

    # Generate PDF using WeasyPrint + Jinja2 templates
    structured_cv = result.get("tailored_cv")
    if not structured_cv:
        logger.info(
            "[PDF] No tailored_cv in pipeline result for %s. Result keys: %s",
            thread_id,
            list(result.keys()),
        )
    if structured_cv:
        try:
            profile = profile or {}
            logger.info(
                "[PDF] Generating for %s, template=%s, domain=%s",
                thread_id,
                profile.get("preferred_template", "classic"),
                domain,
            )
            generator = c.make_pdf_renderer()
            pdf_bytes = generator.render(
                cv_data=structured_cv,
                template_id=profile.get("preferred_template", "classic"),
                accent_color=profile.get("accent_color", "#4361ee"),
                bangla=bool(profile.get("bangla_mode", False)),
                domain=domain,
            )

            path = render_path(user_id, thread_id, "cv")
            c.storage.put(RENDERS_BUCKET, path, pdf_bytes, "application/pdf")
            pdf_url = path  # a bucket path; the API signs it per request
            logger.info("[PDF] Uploaded successfully for %s", thread_id)

        except Exception:
            logger.exception("[PDF] Generation failed for %s", thread_id)

    # ── Cover letter PDF (optional) ─────────────────────────────────────────────
    cover_letter_pdf_url = None
    cover_letter_text = None
    cl_result = result.get("cover_letter")

    if cl_result:
        try:
            profile = profile or {}
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

            cl_path = render_path(user_id, thread_id, "cover_letter")
            c.storage.put(RENDERS_BUCKET, cl_path, cl_pdf_bytes, "application/pdf")
            cover_letter_pdf_url = cl_path

        except Exception:
            logger.exception("Cover letter PDF generation failed for %s", thread_id)

    # Deduct coins
    c.store.deduct_coins(user_id, CV_GENERATION_COST, f"CV generation - thread {thread_id}")

    # Mark session as complete
    c.store.update_session(
        thread_id,
        {
            "status": "complete",
            "domain": domain,
            "ats_score": ats_score,
            "eligibility_score": eligibility_score,
            "pdf_url": pdf_url,
            "cover_letter_text": cover_letter_text,
            "cover_letter_pdf_url": cover_letter_pdf_url,
        },
    )
