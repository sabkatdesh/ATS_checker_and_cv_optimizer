"""cv_sessions v2 statuses and the legacy status strings the API still returns (E5)."""

from typing import Literal, get_args

V2Status = Literal[
    "draft",
    "queued",
    "running",
    "awaiting_input",
    "succeeded",
    "failed",
    "cancelled",
    "expired",
    "ineligible",
]
AwaitingKind = Literal["questions", "cover_letter_options"]
V2_STATUSES: tuple[str, ...] = get_args(V2Status)

_AWAITING = {
    "questions": "awaiting_hitl",
    "cover_letter_options": "awaiting_cover_letter_options",
}
# draft/queued have no legacy string; the frontend keeps polling on "running".
_PLAIN = {
    "draft": "running",
    "queued": "running",
    "running": "running",
    "succeeded": "complete",
    "failed": "error",
}


def legacy_status(status: V2Status | str, awaiting_kind: str | None) -> str:
    """Unknown awaiting kinds and other statuses pass through unchanged."""
    if status == "awaiting_input":
        return _AWAITING.get(awaiting_kind or "", status)
    return _PLAIN.get(status, status)
