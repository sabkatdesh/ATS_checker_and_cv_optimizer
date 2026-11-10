import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"]
)


# ── CV Profile ──────────────────────────────────────────────────

def get_cv_profile(user_id: str):
    try:
        result = supabase.table("cv_profiles") \
            .select("*") \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        return result.data
    except Exception:
        return None


def save_cv_profile(user_id: str, data: dict):
    data["user_id"] = user_id
    result = supabase.table("cv_profiles") \
        .upsert(data, on_conflict="user_id") \
        .execute()
    return result.data


# ── Sessions ─────────────────────────────────────────────────────

def create_session(
    user_id: str,
    thread_id: str,
    job_description: str,
    template_id: str = "classic",
    domain: str | None = None,
    cover_letter_requested: bool = False,
    cover_letter_tone: str | None = None,
    cover_letter_length: str | None = None,
):
    payload = {
        "user_id": user_id,
        "thread_id": thread_id,
        "job_description": job_description,
        "status": "running",
        "template_id": template_id,
        "cover_letter_requested": cover_letter_requested,
    }
    if domain:
        payload["domain"] = domain
    if cover_letter_tone:
        payload["cover_letter_tone"] = cover_letter_tone
    if cover_letter_length:
        payload["cover_letter_length"] = cover_letter_length

    result = supabase.table("cv_sessions").insert(payload).execute()
    return result.data[0] if result.data else None


def update_session(thread_id: str, updates: dict):
    supabase.table("cv_sessions") \
        .update(updates) \
        .eq("thread_id", thread_id) \
        .execute()


def get_session(thread_id: str):
    try:
        result = supabase.table("cv_sessions") \
            .select("*") \
            .eq("thread_id", thread_id) \
            .single() \
            .execute()
        return result.data
    except Exception:
        return None


def get_user_sessions(user_id: str):
    result = supabase.table("cv_sessions") \
        .select(
            "thread_id, status, job_description, "
            "ats_score, semantic_score, improvement_score, eligibility_score, "
            "pdf_url, template_id, domain, cover_letter_requested, "
            "cover_letter_text, cover_letter_pdf_url, created_at"
        ) \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()
    return result.data or []


# ── Storage ──────────────────────────────────────────────────────

def upload_pdf_to_storage(thread_id: str, user_id: str, local_path: str) -> str:
    storage_path = f"pdfs/{user_id}/{thread_id}.pdf"
    with open(local_path, "rb") as f:
        supabase.storage.from_("cv-pdfs").upload(
            storage_path,
            f,
            {"content-type": "application/pdf", "upsert": "true"}
        )
    return supabase.storage.from_("cv-pdfs").get_public_url(storage_path)


# ── CV Templates ─────────────────────────────────────────────────

def get_cv_templates():
    result = supabase.table("cv_templates") \
        .select("*") \
        .execute()
    return result.data or []


def get_cv_template(template_id: str):
    try:
        result = supabase.table("cv_templates") \
            .select("*") \
            .eq("id", template_id) \
            .single() \
            .execute()
        return result.data
    except Exception:
        return None


# ── User Settings ─────────────────────────────────────────────────

def get_user_settings(user_id: str):
    try:
        result = supabase.table("user_settings") \
            .select("*") \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        return result.data
    except Exception:
        return None


def save_user_settings(user_id: str, data: dict):
    data["user_id"] = user_id
    result = supabase.table("user_settings") \
        .upsert(data, on_conflict="user_id") \
        .execute()
    return result.data


# ── Coins ─────────────────────────────────────────────────────────

def get_coin_balance(user_id: str) -> int:
    try:
        result = supabase.table("coin_balance") \
            .select("balance") \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        return result.data["balance"] if result.data else 0
    except Exception:
        return 0


def deduct_coins(user_id: str, amount: int, description: str) -> bool:
    balance = get_coin_balance(user_id)
    if balance < amount:
        return False

    supabase.table("coin_balance") \
        .update({"balance": balance - amount}) \
        .eq("user_id", user_id) \
        .execute()

    supabase.table("coin_transactions").insert({
        "user_id": user_id,
        "amount": -amount,
        "type": "charge",
        "description": description
    }).execute()
    return True


def add_coins(user_id: str, amount: int, description: str):
    current = get_coin_balance(user_id)
    supabase.table("coin_balance") \
        .upsert({"user_id": user_id, "balance": current + amount}, on_conflict="user_id") \
        .execute()

    supabase.table("coin_transactions").insert({
        "user_id": user_id,
        "amount": amount,
        "type": "purchase",
        "description": description
    }).execute()


def get_coin_transactions(user_id: str):
    result = supabase.table("coin_transactions") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()
    return result.data or []
