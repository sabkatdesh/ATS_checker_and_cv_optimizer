# database.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"]
)


# ── CV Profile ─────────────────────────────────────────────────

def get_cv_profile(user_id: str):
    """Get saved profile for a user. Returns None if not found."""
    try:
        result = supabase.table("cv_profiles")\
            .select("*")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        return result.data
    except Exception:
        return None


def save_cv_profile(user_id: str, data: dict):
    """Create or update profile. Safe to call multiple times."""
    data["user_id"] = user_id
    result = supabase.table("cv_profiles")\
        .upsert(data, on_conflict="user_id")\
        .execute()
    return result.data


# ── Sessions ────────────────────────────────────────────────────

def create_session(user_id: str, thread_id: str, job_description: str):
    """Create a new CV generation session"""
    result = supabase.table("cv_sessions").insert({
        "user_id": user_id,
        "thread_id": thread_id,
        "job_description": job_description,
        "status": "running"
    }).execute()
    return result.data[0] if result.data else None


def update_session(thread_id: str, updates: dict):
    """Update any fields on a session"""
    supabase.table("cv_sessions")\
        .update(updates)\
        .eq("thread_id", thread_id)\
        .execute()


def get_session(thread_id: str):
    """Get one session by thread_id"""
    try:
        result = supabase.table("cv_sessions")\
            .select("*")\
            .eq("thread_id", thread_id)\
            .single()\
            .execute()
        return result.data
    except Exception:
        return None


def get_user_sessions(user_id: str):
    """Get all sessions for a user, newest first"""
    result = supabase.table("cv_sessions")\
        .select("thread_id, status, ats_score, pdf_url, created_at")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()
    return result.data or []


def upload_pdf_to_storage(thread_id: str, user_id: str, local_path: str) -> str:
    """
    Upload PDF to Supabase Storage
    Returns public URL
    """
    storage_path = f"pdfs/{user_id}/{thread_id}.pdf"

    with open(local_path, "rb") as f:
        supabase.storage.from_("cv-pdfs").upload(
            storage_path,
            f,
            {"content-type": "application/pdf", "upsert": "true"}
        )

    url = supabase.storage.from_("cv-pdfs").get_public_url(storage_path)
    return url

# ── Coins ───────────────────────────────────────────────────────

def get_coin_balance(user_id: str) -> int:
    """Get user's current coin balance"""
    try:
        result = supabase.table("coin_balance")\
            .select("balance")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        return result.data["balance"] if result.data else 0
    except Exception:
        return 0


def deduct_coins(user_id: str, amount: int, description: str) -> bool:
    """
    Deduct coins after CV generation.
    Returns True if successful, False if not enough coins.
    """
    balance = get_coin_balance(user_id)

    if balance < amount:
        return False  # not enough coins

    # Deduct from balance
    supabase.table("coin_balance")\
        .update({"balance": balance - amount})\
        .eq("user_id", user_id)\
        .execute()

    # Record transaction
    supabase.table("coin_transactions").insert({
        "user_id": user_id,
        "amount": -amount,
        "type": "charge",
        "description": description
    }).execute()

    return True


def add_coins(user_id: str, amount: int, description: str):
    """Add coins after purchase"""
    try:
        # Try to update existing balance
        current = get_coin_balance(user_id)
        supabase.table("coin_balance")\
            .upsert({
                "user_id": user_id,
                "balance": current + amount
            }, on_conflict="user_id")\
            .execute()
    except Exception:
        # First time — create balance row
        supabase.table("coin_balance").insert({
            "user_id": user_id,
            "balance": amount
        }).execute()

    # Record transaction
    supabase.table("coin_transactions").insert({
        "user_id": user_id,
        "amount": amount,
        "type": "purchase",
        "description": description
    }).execute()


def get_coin_transactions(user_id: str):
    """Get transaction history for billing page"""
    result = supabase.table("coin_transactions")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()
    return result.data or []