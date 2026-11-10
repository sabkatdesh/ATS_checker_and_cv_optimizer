# api.py
# ============================================================
# FastAPI Backend — CV Optimizer SaaS
# Connects: Supabase + Pipeline + PDF Generator
# ============================================================

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import os
import threading
import tempfile

from dotenv import load_dotenv
from supabase import create_client

from database import (
    get_cv_profile,
    save_cv_profile,
    create_session,
    update_session,
    get_session,
    get_user_sessions,
    upload_pdf_to_storage,
    get_coin_balance,
    deduct_coins,
    add_coins,
    get_coin_transactions,
)
from services.profile_builder import ProfileBuilder, profile_to_resume_text
from core.parsers.input_validator import validate_jd
from core.pipeline.graph import (
    run_pipeline_for_user,
    get_pipeline_state,
    resume_pipeline_for_user,
    resume_cover_letter_for_user,
    get_cover_letter_result,
)

load_dotenv()

# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(title="CV Optimizer API")

# Allow Streamlit frontend to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this after launch
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client — used only for auth token verification
supabase_client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"]
)

# How many coins one CV generation costs
CV_GENERATION_COST = 0


# ============================================================
# AUTH HELPER
# ============================================================

def get_user_id(authorization: str = Header(None)) -> str:
    """
    Every protected route calls this.
    Reads the token Supabase gave the user,
    verifies it, returns the user's ID.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not logged in")

    token = authorization.replace("Bearer ", "")

    try:
        user = supabase_client.auth.get_user(token)
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class ProfileUpdateRequest(BaseModel):
    # Core fields
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[dict] = None
    experience: Optional[list] = None
    education: Optional[list] = None
    projects: Optional[list] = None
    certifications: Optional[list] = None
    # New universal fields (Phase 3)
    domain: Optional[str] = None
    licenses: Optional[list] = None
    publications: Optional[list] = None
    clinical_practice: Optional[list] = None
    trade_qualifications: Optional[list] = None
    languages: Optional[list] = None
    volunteering: Optional[list] = None
    awards: Optional[list] = None
    references_available: Optional[bool] = None
    preferred_template: Optional[str] = None
    accent_color: Optional[str] = None
    bangla_mode: Optional[bool] = None


class ImportCVRequest(BaseModel):
    cv_text: str


class StartSessionRequest(BaseModel):
    job_description: str
    cover_letter: bool = False
    cover_letter_tone: Optional[str] = None    # "formal" | "conversational"
    cover_letter_length: Optional[str] = None  # "short" | "standard"


class CoverLetterOptionsRequest(BaseModel):
    tone: str       # "formal" | "conversational"
    length: str     # "short" | "standard"


class CoverLetterEditRequest(BaseModel):
    text: str       # user-edited plain-text cover letter draft


class HITLReplyRequest(BaseModel):
    user_qna: str


class AddCoinsRequest(BaseModel):
    amount: int
    description: str = "Manual top-up"


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def health_check():
    """Simple check to confirm API is running"""
    return {"status": "CV Optimizer API is running"}


# ============================================================
# PROFILE ENDPOINTS
# ============================================================

@app.get("/profile")
def get_profile(authorization: str = Header(None)):
    """Get the logged-in user's saved CV profile"""
    user_id = get_user_id(authorization)
    profile = get_cv_profile(user_id)
    return {"profile": profile}


@app.post("/profile")
def update_profile(body: ProfileUpdateRequest, authorization: str = Header(None)):
    """
    Save or update CV profile.
    Safe to call multiple times — updates existing profile.
    """
    user_id = get_user_id(authorization)

    # Only save fields that were actually sent
    data = {k: v for k, v in body.dict().items() if v is not None}

    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    save_cv_profile(user_id, data)
    return {"message": "Profile saved successfully"}


@app.post("/profile/import-cv")
def import_cv(body: ImportCVRequest, authorization: str = Header(None)):
    """
    Parse a pasted CV text using the LLM and return structured profile data.
    The frontend uses this to pre-fill the profile form fields.
    """
    user_id = get_user_id(authorization)

    cv_text = body.cv_text.strip()
    if len(cv_text) < 100:
        raise HTTPException(status_code=400, detail="CV text is too short to parse.")
    if len(cv_text) > 15000:
        raise HTTPException(status_code=400, detail="CV text is too long. Please paste up to 15,000 characters.")

    try:
        from core.llm_client import AzureLLMClient
        from core.schemas.universal_cv import UniversalCVStructured

        client = AzureLLMClient()
        prompt = (
            "Extract all information from the following CV into the structured JSON format. "
            "Fill every field you can find. Use the domain field to classify the profession "
            "(tech/medical/education/trades/finance/legal/creative/general). "
            "Return only the JSON object — no extra text.\n\n"
            f"CV TEXT:\n{cv_text}"
        )
        structured: UniversalCVStructured = client.invoke_structured(prompt, UniversalCVStructured)

        # Detect domain if LLM left it as GENERAL
        raw = structured.model_dump()
        if raw.get("domain") == "general":
            detected = ProfileBuilder.detect_domain(raw).value
            raw["domain"] = detected

        return {"profile": raw}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV parsing failed: {str(e)}")


# ============================================================
# CV GENERATION ENDPOINTS
# ============================================================

@app.post("/sessions/start")
def start_session(
    body: StartSessionRequest,
    background_tasks: BackgroundTasks,
    authorization: str = Header(None)
):
    """
    Start a CV generation session.
    1. Validates JD
    2. Checks user has a profile
    3. Checks user has enough coins
    4. Runs pipeline in background
    5. Returns thread_id immediately
    """
    user_id = get_user_id(authorization)

    # Step 1 — Validate the job description
    jd_check = validate_jd(body.job_description)
    if not jd_check.is_valid:
        raise HTTPException(status_code=400, detail=jd_check.user_message)

    # Step 2 — Check user has a profile
    profile = get_cv_profile(user_id)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="Please complete your profile first before generating a CV"
        )

    # Step 3 — Check coin balance
    balance = get_coin_balance(user_id)
    if balance < CV_GENERATION_COST:
        raise HTTPException(
            status_code=402,
            detail=f"Not enough coins. You need {CV_GENERATION_COST} coins. Current balance: {balance}"
        )

    # Step 4 — Create session record in database
    thread_id = f"thread_{uuid.uuid4().hex}"
    create_session(user_id, thread_id, body.job_description)

    # Step 5 — Run pipeline in background thread
    # We use a thread so the API responds immediately
    # User polls /sessions/{thread_id}/status to check progress
    def run_in_background():
        try:
            # Convert saved profile to resume text using domain-aware builder
            resume_text = ProfileBuilder.from_profile_dict(profile)

            # Run the pipeline
            result = run_pipeline_for_user(
                job_description=body.job_description,
                user_resume_text=resume_text,
                thread_id=thread_id,
                cover_letter_requested=bool(body.cover_letter),
                cover_letter_tone=body.cover_letter_tone,
                cover_letter_length=body.cover_letter_length,
            )

            # Check if pipeline paused at a HITL node
            pipeline_state = get_pipeline_state(thread_id)
            next_nodes = pipeline_state.get("next", [])
            values = pipeline_state.get("values", {})

            if "hitl_node" in next_nodes:
                gaps = values.get("gaps_identified", [])
                eligibility = values.get("eligibility_verdict")
                update_session(thread_id, {
                    "status": "awaiting_hitl",
                    "gaps": gaps,
                    "eligibility_score": eligibility.score if eligibility else None,
                })
            elif "cover_letter_hitl" in next_nodes:
                # Paused waiting for cover letter tone/length
                update_session(thread_id, {"status": "awaiting_cover_letter_options"})
            else:
                # Pipeline completed — finalize
                _finalize_session(thread_id, result, user_id, profile=profile)

        except Exception as e:
            print(f"Pipeline error for thread {thread_id}: {e}")
            update_session(thread_id, {"status": "error"})

    thread = threading.Thread(target=run_in_background)
    thread.daemon = True
    thread.start()

    return {
        "thread_id": thread_id,
        "status": "running",
        "message": "CV generation started. Poll /sessions/{thread_id}/status to check progress."
    }


@app.get("/sessions/{thread_id}/status")
def session_status(thread_id: str, authorization: str = Header(None)):
    """
    Poll this endpoint every few seconds to check progress.
    Returns current status + scores when complete.
    """
    user_id = get_user_id(authorization)
    session = get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Security — only owner can see their session
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    return session


@app.post("/sessions/{thread_id}/reply")
def hitl_reply(
    thread_id: str,
    body: HITLReplyRequest,
    background_tasks: BackgroundTasks,
    authorization: str = Header(None)
):
    """
    User submits answers to HITL gap questions.
    Resumes the pipeline from where it paused.
    """
    user_id = get_user_id(authorization)
    session = get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    if session["status"] != "awaiting_hitl":
        raise HTTPException(status_code=400, detail="Session is not waiting for your input")

    # Update status and resume in background
    update_session(thread_id, {"status": "running"})

    def resume_in_background():
        try:
            result = resume_pipeline_for_user(thread_id, body.user_qna)
            pipeline_state = get_pipeline_state(thread_id)
            next_nodes = pipeline_state.get("next", [])

            if "cover_letter_hitl" in next_nodes:
                update_session(thread_id, {"status": "awaiting_cover_letter_options"})
            else:
                profile = get_cv_profile(user_id)
                _finalize_session(thread_id, result, user_id, profile=profile)
        except Exception as e:
            print(f"Resume error for thread {thread_id}: {e}")
            update_session(thread_id, {"status": "error"})

    thread = threading.Thread(target=resume_in_background)
    thread.daemon = True
    thread.start()

    return {"status": "resumed", "message": "Pipeline resumed. Keep polling /status"}


@app.post("/sessions/{thread_id}/cover-letter-options")
def submit_cover_letter_options(
    thread_id: str,
    body: CoverLetterOptionsRequest,
    background_tasks: BackgroundTasks,
    authorization: str = Header(None),
):
    """
    Submit tone + length for cover letter generation.
    Called when the pipeline paused at cover_letter_hitl waiting for these options.
    Resumes the pipeline which then generates the cover letter and finalises the session.
    """
    user_id = get_user_id(authorization)
    session = get_session(thread_id)

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

    update_session(thread_id, {"status": "running"})

    def resume_cl_in_background():
        try:
            result = resume_cover_letter_for_user(thread_id, tone, length)
            profile = get_cv_profile(user_id)
            _finalize_session(thread_id, result, user_id, profile=profile)
        except Exception as e:
            print(f"Cover letter resume error for {thread_id}: {e}")
            update_session(thread_id, {"status": "error"})

    t = threading.Thread(target=resume_cl_in_background)
    t.daemon = True
    t.start()

    return {"status": "resumed", "message": "Generating cover letter. Keep polling /status."}


@app.post("/sessions/{thread_id}/cover-letter")
def save_cover_letter_edit(
    thread_id: str,
    body: CoverLetterEditRequest,
    authorization: str = Header(None),
):
    """
    Save a user-edited cover letter draft (plain text).
    Triggers a fresh PDF render from the edited text and updates storage.
    """
    user_id = get_user_id(authorization)
    session = get_session(thread_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Cover letter text is empty")

    # Store the edited text; PDF re-render is lightweight enough to do inline
    update_session(thread_id, {"cover_letter_text": text})
    return {"message": "Cover letter saved successfully"}


@app.get("/sessions/{thread_id}/cover-letter.pdf")
def download_cover_letter_pdf(thread_id: str, authorization: str = Header(None)):
    """
    Download the cover letter PDF for a completed session.
    Returns the Supabase storage URL (redirect) or the file bytes directly.
    """
    from fastapi.responses import RedirectResponse

    user_id = get_user_id(authorization)
    session = get_session(thread_id)

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


@app.get("/sessions")
def list_sessions(authorization: str = Header(None)):
    """Get all past CV generations for the logged-in user"""
    user_id = get_user_id(authorization)
    sessions = get_user_sessions(user_id)
    return {"sessions": sessions}


# ============================================================
# BILLING ENDPOINTS
# ============================================================

@app.get("/billing/balance")
def get_balance(authorization: str = Header(None)):
    """Get current coin balance"""
    user_id = get_user_id(authorization)
    balance = get_coin_balance(user_id)
    return {
        "balance": balance,
        "cost_per_cv": CV_GENERATION_COST
    }


@app.get("/billing/history")
def billing_history(authorization: str = Header(None)):
    """Get full transaction history"""
    user_id = get_user_id(authorization)
    transactions = get_coin_transactions(user_id)
    return {"transactions": transactions}


@app.post("/billing/add-coins")
def manual_add_coins(body: AddCoinsRequest, authorization: str = Header(None)):
    """
    Manually add coins to a user's account.
    This will later be called by bKash/Nagad webhook after payment.
    For now used for testing and manual top-ups.
    """
    user_id = get_user_id(authorization)

    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    add_coins(user_id, body.amount, body.description)
    new_balance = get_coin_balance(user_id)

    return {
        "message": f"{body.amount} coins added successfully",
        "new_balance": new_balance
    }


# ============================================================
# HELPER — finalize session after pipeline completes
# ============================================================

def _finalize_session(thread_id: str, result: dict, user_id: str, profile: dict | None = None):
    """
    Called after pipeline finishes.
    1. Generates CV PDF (WeasyPrint via PDFGenerator)
    2. Optionally generates cover letter PDF (WeasyPrint via CoverLetterService)
    3. Uploads both PDFs to Supabase storage
    4. Deducts coins
    5. Updates session as complete
    """
    from services.pdf_generator import PDFGenerator
    from services.cover_letter import CoverLetterService

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
        update_session(thread_id, {
            "status": "ineligible",
            "eligibility_score": eligibility_score,
        })
        return

    # Generate PDF using WeasyPrint + Jinja2 templates
    if result.get("structured_cv"):
        try:
            profile = profile or {}
            generator = PDFGenerator()
            pdf_bytes = generator.render(
                cv_data=result["structured_cv"],
                template_id=profile.get("preferred_template", "classic"),
                accent_color=profile.get("accent_color", "#4361ee"),
                bangla=bool(profile.get("bangla_mode", False)),
                domain=result.get("detected_domain", "general"),
            )

            local_path = os.path.join(tempfile.gettempdir(), f"{thread_id}.pdf")
            with open(local_path, "wb") as fh:
                fh.write(pdf_bytes)

            # Upload to Supabase storage
            pdf_url = upload_pdf_to_storage(thread_id, user_id, local_path)

            # Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)

        except Exception as e:
            print(f"PDF generation failed for {thread_id}: {e}")

    # ── Cover letter PDF (optional) ─────────────────────────────────────────────
    cover_letter_pdf_url = None
    cover_letter_text = None
    cl_result = result.get("cover_letter_result")

    if cl_result:
        try:
            profile = profile or {}
            candidate_name = profile.get("full_name", "")
            tone = result.get("cover_letter_tone") or "formal"

            cl_service = CoverLetterService()
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

            cover_letter_pdf_url = upload_pdf_to_storage(
                f"{thread_id}_cover_letter", user_id, cl_local_path
            )

            if os.path.exists(cl_local_path):
                os.remove(cl_local_path)

        except Exception as e:
            print(f"Cover letter PDF generation failed for {thread_id}: {e}")

    # Deduct coins
    deduct_coins(
        user_id,
        CV_GENERATION_COST,
        f"CV generation - thread {thread_id}"
    )

    # Mark session as complete
    update_session(thread_id, {
        "status": "complete",
        "ats_score": ats_score,
        "eligibility_score": eligibility_score,
        "pdf_url": pdf_url,
        "cover_letter_text": cover_letter_text,
        "cover_letter_pdf_url": cover_letter_pdf_url,
    })