"""Temporary: legacy route bodies moved verbatim from api.py. Split up in Task 7."""

import logging
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.api.deps import get_container, require_user_id
from app.container import Container
from core.parsers.input_validator import validate_jd
from services.profile_builder import ProfileBuilder

logger = logging.getLogger(__name__)
router = APIRouter()

# How many coins one CV generation costs
CV_GENERATION_COST = 0


class StartSessionRequest(BaseModel):
    job_description: str
    cover_letter: bool = False
    cover_letter_tone: str | None = None  # "formal" | "conversational"
    cover_letter_length: str | None = None  # "short" | "standard"


class CoverLetterOptionsRequest(BaseModel):
    tone: str  # "formal" | "conversational"
    length: str  # "short" | "standard"


class CoverLetterEditRequest(BaseModel):
    text: str  # user-edited plain-text cover letter draft


class HITLReplyRequest(BaseModel):
    user_qna: str


class AddCoinsRequest(BaseModel):
    amount: int
    description: str = "Manual top-up"


class UserSettingsRequest(BaseModel):
    default_template: str | None = None
    accent_color: str | None = None
    bangla_mode: bool | None = None
    cover_letter_default_tone: str | None = None


@router.get("/")
def health_check():
    """Simple check to confirm API is running"""
    return {"status": "CV Optimizer API is running"}


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
    def run_in_background():
        try:
            # Convert saved profile to resume text using domain-aware builder
            resume_text = ProfileBuilder.from_profile_dict(profile)

            # Run the pipeline
            result = c.pipeline.run(
                job_description=body.job_description,
                user_resume_text=resume_text,
                thread_id=thread_id,
                cover_letter_requested=bool(body.cover_letter),
                cover_letter_tone=body.cover_letter_tone,
                cover_letter_length=body.cover_letter_length,
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
                _finalize_session(c, thread_id, result, user_id, profile=profile)

        except Exception:
            logger.exception("Pipeline error for thread %s", thread_id)
            c.store.update_session(thread_id, {"status": "error"})

    c.runner.submit(run_in_background)

    return {
        "thread_id": thread_id,
        "status": "running",
        "message": "CV generation started. Poll /sessions/{thread_id}/status to check progress.",
    }


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

    def resume_in_background():
        try:
            result = c.pipeline.resume(thread_id, body.user_qna)
            pipeline_state = c.pipeline.get_state(thread_id)
            next_nodes = pipeline_state.get("next", [])

            if "cover_letter_hitl" in next_nodes:
                c.store.update_session(thread_id, {"status": "awaiting_cover_letter_options"})
            else:
                profile = c.store.get_cv_profile(user_id)
                _finalize_session(c, thread_id, result, user_id, profile=profile)
        except Exception:
            logger.exception("Resume error for thread %s", thread_id)
            c.store.update_session(thread_id, {"status": "error"})

    c.runner.submit(resume_in_background)

    return {"status": "resumed", "message": "Pipeline resumed. Keep polling /status"}


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

    def resume_cl_in_background():
        try:
            result = c.pipeline.resume_cover_letter(thread_id, tone, length)
            profile = c.store.get_cv_profile(user_id)
            _finalize_session(c, thread_id, result, user_id, profile=profile)
        except Exception:
            logger.exception("Cover letter resume error for %s", thread_id)
            c.store.update_session(thread_id, {"status": "error"})

    c.runner.submit(resume_cl_in_background)

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
    from fastapi.responses import RedirectResponse

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


@router.get("/sessions")
def list_sessions(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get all past CV generations for the logged-in user"""
    user_id = require_user_id(c, authorization)
    sessions = c.store.get_user_sessions(user_id)
    return {"sessions": sessions}


@router.get("/settings")
def get_settings(authorization: str = Header(None), c: Container = Depends(get_container)):
    user_id = require_user_id(c, authorization)
    settings = c.store.get_user_settings(user_id)
    return {"settings": settings or {}}


@router.post("/settings")
def update_settings(
    body: UserSettingsRequest,
    authorization: str = Header(None),
    c: Container = Depends(get_container),
):
    user_id = require_user_id(c, authorization)
    data = {k: v for k, v in body.dict().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No settings provided")
    c.store.save_user_settings(user_id, data)
    return {"message": "Settings saved"}


@router.get("/billing/balance")
def get_balance(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get current coin balance"""
    user_id = require_user_id(c, authorization)
    balance = c.store.get_coin_balance(user_id)
    return {"balance": balance, "cost_per_cv": CV_GENERATION_COST}


@router.get("/billing/history")
def billing_history(authorization: str = Header(None), c: Container = Depends(get_container)):
    """Get full transaction history"""
    user_id = require_user_id(c, authorization)
    transactions = c.store.get_coin_transactions(user_id)
    return {"transactions": transactions}


@router.post("/billing/add-coins")
def manual_add_coins(
    body: AddCoinsRequest, authorization: str = Header(None), c: Container = Depends(get_container)
):
    """
    Manually add coins to a user's account.
    This will later be called by bKash/Nagad webhook after payment.
    For now used for testing and manual top-ups.
    """
    user_id = require_user_id(c, authorization)

    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    c.store.add_coins(user_id, body.amount, body.description)
    new_balance = c.store.get_coin_balance(user_id)

    return {"message": f"{body.amount} coins added successfully", "new_balance": new_balance}


def _finalize_session(
    c: Container, thread_id: str, result: dict, user_id: str, profile: dict | None = None
):
    """
    Called after pipeline finishes.
    1. Generates CV PDF (WeasyPrint via PDFGenerator)
    2. Optionally generates cover letter PDF (WeasyPrint via CoverLetterService)
    3. Uploads both PDFs to Supabase storage
    4. Deducts coins
    5. Updates session as complete
    """
    ats_score = None
    eligibility_score = None
    pdf_url = None

    # Get scores
    if result.get("final_match"):
        ats_score = result["final_match"].get("overall_score")

    if result.get("eligibility_verdict"):
        eligibility_score = result["eligibility_verdict"].score

    # Check if eligible — only generate PDF if eligible
    if not result.get("is_eligible"):
        c.store.update_session(
            thread_id,
            {
                "status": "ineligible",
                "eligibility_score": eligibility_score,
            },
        )
        return

    # Generate PDF using WeasyPrint + Jinja2 templates
    structured_cv = result.get("structured_cv")
    if not structured_cv:
        logger.info(
            "[PDF] No structured_cv in pipeline result for %s. Result keys: %s",
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
                result.get("detected_domain", "general"),
            )
            generator = c.make_pdf_renderer()
            pdf_bytes = generator.render(
                cv_data=structured_cv,
                template_id=profile.get("preferred_template", "classic"),
                accent_color=profile.get("accent_color", "#4361ee"),
                bangla=bool(profile.get("bangla_mode", False)),
                domain=result.get("detected_domain", "general"),
            )

            local_path = os.path.join(tempfile.gettempdir(), f"{thread_id}.pdf")
            with open(local_path, "wb") as fh:
                fh.write(pdf_bytes)

            # Upload to Supabase storage
            pdf_url = c.store.upload_pdf_to_storage(thread_id, user_id, local_path)
            logger.info("[PDF] Uploaded successfully for %s", thread_id)

            # Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)

        except Exception:
            logger.exception("[PDF] Generation failed for %s", thread_id)

    # ── Cover letter PDF (optional) ─────────────────────────────────────────────
    cover_letter_pdf_url = None
    cover_letter_text = None
    cl_result = result.get("cover_letter_result")

    if cl_result:
        try:
            profile = profile or {}
            candidate_name = profile.get("full_name", "")
            tone = result.get("cover_letter_tone") or "formal"

            cl_service = c.make_cover_letter_renderer()
            cl_pdf_bytes = cl_service.render_to_pdf(
                cl_data=cl_result,
                tone=tone,
                candidate_name=candidate_name,
                bangla=bool(profile.get("bangla_mode", False)),
            )

            # Plain text version — stored so frontend can show editable draft
            cover_letter_text = cl_service.to_plain_text(cl_result, candidate_name)

            cl_local_path = os.path.join(tempfile.gettempdir(), f"{thread_id}_cl.pdf")
            with open(cl_local_path, "wb") as fh:
                fh.write(cl_pdf_bytes)

            cover_letter_pdf_url = c.store.upload_pdf_to_storage(
                f"{thread_id}_cover_letter", user_id, cl_local_path
            )

            if os.path.exists(cl_local_path):
                os.remove(cl_local_path)

        except Exception:
            logger.exception("Cover letter PDF generation failed for %s", thread_id)

    # Deduct coins
    c.store.deduct_coins(user_id, CV_GENERATION_COST, f"CV generation - thread {thread_id}")

    # Mark session as complete
    c.store.update_session(
        thread_id,
        {
            "status": "complete",
            "ats_score": ats_score,
            "eligibility_score": eligibility_score,
            "pdf_url": pdf_url,
            "cover_letter_text": cover_letter_text,
            "cover_letter_pdf_url": cover_letter_pdf_url,
        },
    )
