"""In-memory repositories mirroring the Pg adapters' behaviour."""

from datetime import UTC, datetime

from app.ports.repositories import BonusState, JsonDict


class MemoryProfileRepo:
    def __init__(self) -> None:
        self.prefs: dict[str, JsonDict] = {}
        self.bonus: dict[str, dict[str, datetime | None]] = {}

    def get_preferences(self, user_id: str) -> JsonDict:
        return dict(self.prefs.get(user_id, {}))

    def save_preferences(self, user_id: str, prefs: JsonDict) -> None:
        self.prefs[user_id] = {**self.prefs.get(user_id, {}), **prefs}

    def bonus_state(self, user_id: str) -> BonusState:
        b = self.bonus.get(user_id, {})
        return BonusState(b.get("verified"), b.get("granted"), b.get("review"))

    def mark_bonus(self, user_id: str, *, granted: bool) -> None:
        b = self.bonus.setdefault(user_id, {})
        key = "granted" if granted else "review"
        b[key] = b.get(key) or datetime.now(UTC)


class MemoryMasterProfileRepo:
    def __init__(self) -> None:
        self.default: dict[str, JsonDict] = {}

    def get_default(self, user_id: str) -> JsonDict | None:
        if user_id not in self.default:
            return None
        return {**self.default[user_id], "user_id": user_id}

    def upsert_default(self, user_id: str, data: JsonDict) -> None:
        clean = {k: v for k, v in data.items() if k != "user_id"}
        self.default[user_id] = {**self.default.get(user_id, {}), **clean}


class MemoryTemplateRepo:
    def __init__(self) -> None:
        self.rows: list[JsonDict] = []

    def list_active(self) -> list[JsonDict]:
        return list(self.rows)
