"""Supabase-backed LegacyStore: queries and error handling ported unchanged from database.py."""

from typing import Any

from supabase import Client

JsonDict = dict[str, Any]

_SESSION_COLUMNS = (
    "thread_id, status, job_description, "
    "ats_score, semantic_score, improvement_score, eligibility_score, "
    "pdf_url, template_id, domain, cover_letter_requested, "
    "cover_letter_text, cover_letter_pdf_url, created_at"
)


class SupabaseLegacyStore:
    def __init__(self, client: Client) -> None:
        self._sb = client

    # -- CV Profile --

    def get_cv_profile(self, user_id: str) -> JsonDict | None:
        try:
            result = (
                self._sb.table("cv_profiles").select("*").eq("user_id", user_id).single().execute()
            )
            return result.data  # type: ignore[return-value]
        except Exception:
            return None

    def save_cv_profile(self, user_id: str, data: JsonDict) -> Any:
        data["user_id"] = user_id
        result = self._sb.table("cv_profiles").upsert(data, on_conflict="user_id").execute()
        return result.data

    # -- Sessions --

    def create_session(
        self,
        user_id: str,
        thread_id: str,
        job_description: str,
        template_id: str = "classic",
        domain: str | None = None,
        cover_letter_requested: bool = False,
        cover_letter_tone: str | None = None,
        cover_letter_length: str | None = None,
    ) -> JsonDict:
        payload: JsonDict = {
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

        result = self._sb.table("cv_sessions").insert(payload).execute()
        return result.data[0] if result.data else None  # type: ignore[return-value]

    def update_session(self, thread_id: str, updates: JsonDict) -> None:
        self._sb.table("cv_sessions").update(updates).eq("thread_id", thread_id).execute()

    def get_session(self, thread_id: str) -> JsonDict | None:
        try:
            result = (
                self._sb.table("cv_sessions")
                .select("*")
                .eq("thread_id", thread_id)
                .single()
                .execute()
            )
            return result.data  # type: ignore[return-value]
        except Exception:
            return None

    def get_user_sessions(self, user_id: str) -> list[JsonDict]:
        result = (
            self._sb.table("cv_sessions")
            .select(_SESSION_COLUMNS)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []  # type: ignore[return-value]

    # -- Storage --

    def upload_pdf_to_storage(self, thread_id: str, user_id: str, local_path: str) -> str:
        storage_path = f"pdfs/{user_id}/{thread_id}.pdf"
        with open(local_path, "rb") as f:
            self._sb.storage.from_("cv-pdfs").upload(
                storage_path, f, {"content-type": "application/pdf", "upsert": "true"}
            )
        return self._sb.storage.from_("cv-pdfs").get_public_url(storage_path)

    # -- CV Templates --

    def get_cv_templates(self) -> list[JsonDict]:
        result = self._sb.table("cv_templates").select("*").execute()
        return result.data or []  # type: ignore[return-value]

    # -- User Settings --

    def get_user_settings(self, user_id: str) -> JsonDict | None:
        try:
            result = (
                self._sb.table("user_settings")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            return result.data  # type: ignore[return-value]
        except Exception:
            return None

    def save_user_settings(self, user_id: str, data: JsonDict) -> Any:
        data["user_id"] = user_id
        result = self._sb.table("user_settings").upsert(data, on_conflict="user_id").execute()
        return result.data

    # -- Coins --

    def get_coin_balance(self, user_id: str) -> int:
        try:
            result = (
                self._sb.table("coin_balance")
                .select("balance")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            return result.data["balance"] if result.data else 0  # type: ignore[index,call-overload,return-value]
        except Exception:
            return 0

    def deduct_coins(self, user_id: str, amount: int, description: str) -> bool:
        balance = self.get_coin_balance(user_id)
        if balance < amount:
            return False

        self._sb.table("coin_balance").update({"balance": balance - amount}).eq(
            "user_id", user_id
        ).execute()
        self._sb.table("coin_transactions").insert(
            {"user_id": user_id, "amount": -amount, "type": "charge", "description": description}
        ).execute()
        return True

    def add_coins(self, user_id: str, amount: int, description: str) -> None:
        current = self.get_coin_balance(user_id)
        self._sb.table("coin_balance").upsert(
            {"user_id": user_id, "balance": current + amount}, on_conflict="user_id"
        ).execute()
        self._sb.table("coin_transactions").insert(
            {"user_id": user_id, "amount": amount, "type": "purchase", "description": description}
        ).execute()

    def get_coin_transactions(self, user_id: str) -> list[JsonDict]:
        result = (
            self._sb.table("coin_transactions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []  # type: ignore[return-value]
