"""Repository ports for user-owned rows. Every method is scoped by user_id."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class BonusState:
    verified_at: datetime | None
    granted_at: datetime | None
    review_at: datetime | None


class ProfileRepo(Protocol):
    def get_preferences(self, user_id: str) -> JsonDict: ...

    def save_preferences(self, user_id: str, prefs: JsonDict) -> None: ...

    def bonus_state(self, user_id: str) -> BonusState: ...

    def mark_bonus(self, user_id: str, *, granted: bool) -> None: ...


class MasterProfileRepo(Protocol):
    def get_default(self, user_id: str) -> JsonDict | None: ...

    def upsert_default(self, user_id: str, data: JsonDict) -> None: ...


class TemplateRepo(Protocol):
    def list_active(self) -> list[JsonDict]: ...
