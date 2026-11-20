"""Repository ports for user-owned rows. Every method is scoped by user_id."""

import uuid
from dataclasses import dataclass, field
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


# cv_sessions columns that update() may write; anything else is a programming error.
SESSION_UPDATABLE = frozenset(
    {
        "status",
        "awaiting_kind",
        "pipeline_summary",
        "jd_title",
        "jd_company",
        "jd_domain",
        "template_id",
        "score_before",
        "score_after",
        "score_breakdown",
        "tailored_cv",
        "trust_report",
        "cover_letter_text",
        "current_render_id",
    }
)
SESSION_JSON_COLUMNS = frozenset(
    {"pipeline_summary", "score_breakdown", "tailored_cv", "trust_report", "options", "source_cv"}
)
# renders rows for the cover-letter PDF carry this template_id marker.
COVER_LETTER_RENDER = "cover_letter"


@dataclass(frozen=True)
class SessionRow:
    """One cv_sessions row; pdf paths come from its renders rows (never a URL)."""

    id: str
    user_id: str
    status: str
    awaiting_kind: str | None = None
    jd_text: str | None = None
    jd_domain: str | None = None
    template_id: str | None = None
    options: JsonDict = field(default_factory=dict)
    source_cv: JsonDict | None = None
    score_before: int | None = None
    score_after: int | None = None
    score_breakdown: JsonDict | None = None
    tailored_cv: JsonDict | None = None
    cover_letter_text: str | None = None
    current_render_id: str | None = None
    pipeline_summary: JsonDict | None = None
    created_at: datetime | None = None
    pdf_path: str | None = None
    cover_letter_pdf_path: str | None = None


class SessionRepo(Protocol):
    def create(
        self,
        user_id: str,
        session_id: str,
        *,
        jd_text: str,
        source_cv: JsonDict,
        options: JsonDict,
        template_id: str,
    ) -> None: ...

    def get(self, user_id: str, session_id: str) -> SessionRow | None:
        """None for a missing row, another user's row and a malformed id."""
        ...

    def list_for_user(self, user_id: str, limit: int = 50) -> list[SessionRow]: ...

    def session_ids(self, user_id: str) -> list[str]:
        """Every session id of the user (no limit); the checkpoint thread ids for a purge."""
        ...

    def update(self, user_id: str, session_id: str, **fields: Any) -> None:
        """Only SESSION_UPDATABLE columns; raises ValueError for anything else."""
        ...


class RenderRepo(Protocol):
    def add(
        self, user_id: str, session_id: str, *, pdf_path: str, content_hash: str, template_id: str
    ) -> str:
        """Insert a renders row; an existing row with the same hash (same user) is reused."""
        ...


class CreditReadRepo(Protocol):
    def balance(self, user_id: str) -> tuple[int, int]:
        """(balance, held); (0, 0) when the user has no balance row yet."""
        ...

    def ledger(self, user_id: str, limit: int = 50) -> list[JsonDict]: ...

    def grant(self, user_id: str, amount: int, kind: str, idem: str) -> int:
        """credits_grant(): idempotent by key; returns the new (or current) balance."""
        ...


class AuditRepo(Protocol):
    def write(self, *, actor: str | None, action: str, target: str | None, meta: JsonDict) -> None:
        """Insert-only. Never put an email, raw user id or token in target or meta."""
        ...


class GuardRepo(Protocol):
    def claim(
        self,
        user_id: str,
        ip_bucket: str,
        device_bucket: str | None,
        *,
        ip_max: int,
        device_max: int,
        amount: int,
    ) -> str:
        """claim_signup_bonus(): guards + credits_grant in one transaction.

        Returns granted | already_granted | pending_review | email_not_verified. The ip bucket
        is counted per day, the device bucket for life."""
        ...


def is_uuid(value: object) -> bool:
    """Canonical hyphenated form only (what uuid7() and Postgres ::text produce)."""
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False
