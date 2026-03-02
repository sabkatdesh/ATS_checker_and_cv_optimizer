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
from profile_builder import profile_to_resume_text
from input_validator import validate_jd
from main_pipeline_hitl_supabase import (
    run_pipeline_for_user,
    get_pipeline_state,
    resume_pipeline_for_user,
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


class StartSessionRequest(BaseModel):
    job_description: str


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
            # Convert saved profile to resume text for pipeline
            resume_text = profile_to_resume_text(profile)

            # Run the pipeline
            result = run_pipeline_for_user(
                job_description=body.job_description,
                user_resume_text=resume_text,
                thread_id=thread_id,
            )

            # Check if pipeline paused at HITL
            pipeline_state = get_pipeline_state(thread_id)

            if pipeline_state.get("is_paused_at_hitl"):
                # Pipeline is waiting for user answers
                gaps = pipeline_state["values"].get("gaps_identified", [])
                eligibility = pipeline_state["values"].get("eligibility_verdict")
                update_session(thread_id, {
                    "status": "awaiting_hitl",
                    "gaps": gaps,
                    "eligibility_score": eligibility.score if eligibility else None,
                })
            else:
                # Pipeline completed — finalize
                _finalize_session(thread_id, result, user_id)

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
            _finalize_session(thread_id, result, user_id)
        except Exception as e:
            print(f"Resume error for thread {thread_id}: {e}")
            update_session(thread_id, {"status": "error"})

    thread = threading.Thread(target=resume_in_background)
    thread.daemon = True
    thread.start()

    return {"status": "resumed", "message": "Pipeline resumed. Keep polling /status"}


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

def _finalize_session(thread_id: str, result: dict, user_id: str):
    """
    Called after pipeline finishes.
    1. Generates PDF
    2. Uploads to Supabase storage
    3. Deducts coins
    4. Updates session as complete
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
        update_session(thread_id, {
            "status": "ineligible",
            "eligibility_score": eligibility_score,
        })
        return

    # Generate PDF
    if result.get("structured_cv"):
        try:
            from generate_pdf import create_cv_pdf

            local_path = os.path.join(tempfile.gettempdir(), f"{thread_id}.pdf")
            create_cv_pdf(result["structured_cv"], local_path)

            # Upload to Supabase storage
            pdf_url = upload_pdf_to_storage(thread_id, user_id, local_path)

            # Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)

        except Exception as e:
            print(f"PDF generation failed for {thread_id}: {e}")

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
    })