"""In-memory stand-in for database.py; method names and args mirror it."""

from datetime import UTC, datetime


class MemoryStore:
    def __init__(self):
        self.profiles: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.settings: dict[str, dict] = {}
        self.balances: dict[str, int] = {}
        self.transactions: list[dict] = []
        self.templates: list[dict] = []
        self.uploads: list[tuple[str, str, bytes]] = []
        self.calls: list[tuple[str, tuple, dict]] = []
        self.raise_on: dict[str, Exception] = {}

    def _enter(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        if name in self.raise_on:
            raise self.raise_on[name]

    def get_cv_profile(self, user_id):
        self._enter("get_cv_profile", (user_id,), {})
        return self.profiles.get(user_id)

    def save_cv_profile(self, user_id, data):
        self._enter("save_cv_profile", (user_id, data), {})
        data["user_id"] = user_id
        self.profiles[user_id] = data
        return [data]

    def create_session(
        self,
        user_id,
        thread_id,
        job_description,
        template_id="classic",
        domain=None,
        cover_letter_requested=False,
        cover_letter_tone=None,
        cover_letter_length=None,
    ):
        self._enter(
            "create_session",
            (user_id, thread_id, job_description),
            {
                "template_id": template_id,
                "domain": domain,
                "cover_letter_requested": cover_letter_requested,
                "cover_letter_tone": cover_letter_tone,
                "cover_letter_length": cover_letter_length,
            },
        )
        row = {
            "thread_id": thread_id,
            "user_id": user_id,
            "job_description": job_description,
            "template_id": template_id,
            "domain": domain,
            "status": "running",
            "cover_letter_requested": cover_letter_requested,
            "cover_letter_tone": cover_letter_tone,
            "cover_letter_length": cover_letter_length,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.sessions[thread_id] = row
        return row

    def update_session(self, thread_id, updates):
        self._enter("update_session", (thread_id, updates), {})
        self.sessions.setdefault(thread_id, {"thread_id": thread_id}).update(updates)

    def get_session(self, thread_id):
        self._enter("get_session", (thread_id,), {})
        return self.sessions.get(thread_id)

    def get_user_sessions(self, user_id):
        self._enter("get_user_sessions", (user_id,), {})
        return [s for s in self.sessions.values() if s.get("user_id") == user_id]

    def upload_pdf_to_storage(self, thread_id, user_id, local_path):
        self._enter("upload_pdf_to_storage", (thread_id, user_id, local_path), {})
        with open(local_path, "rb") as f:
            self.uploads.append((thread_id, user_id, f.read()))
        return f"https://storage.test/{user_id}/{thread_id}.pdf"

    def get_cv_templates(self):
        self._enter("get_cv_templates", (), {})
        return self.templates

    def get_user_settings(self, user_id):
        self._enter("get_user_settings", (user_id,), {})
        return self.settings.get(user_id)

    def save_user_settings(self, user_id, data):
        self._enter("save_user_settings", (user_id, data), {})
        self.settings[user_id] = data
        return [data]

    def get_coin_balance(self, user_id):
        self._enter("get_coin_balance", (user_id,), {})
        return self.balances.get(user_id, 0)

    def deduct_coins(self, user_id, amount, description):
        self._enter("deduct_coins", (user_id, amount, description), {})
        if self.balances.get(user_id, 0) < amount:
            return False
        self.balances[user_id] = self.balances.get(user_id, 0) - amount
        return True

    def add_coins(self, user_id, amount, description):
        self._enter("add_coins", (user_id, amount, description), {})
        self.balances[user_id] = self.balances.get(user_id, 0) + amount

    def get_coin_transactions(self, user_id):
        self._enter("get_coin_transactions", (user_id,), {})
        return self.transactions
