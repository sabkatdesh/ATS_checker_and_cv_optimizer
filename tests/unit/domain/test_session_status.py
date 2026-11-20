import pytest

from app.domain.sessions.status import V2_STATUSES, legacy_status

TABLE = [
    ("draft", None, "running"),
    ("queued", None, "running"),
    ("running", None, "running"),
    ("awaiting_input", "questions", "awaiting_hitl"),
    ("awaiting_input", "cover_letter_options", "awaiting_cover_letter_options"),
    ("awaiting_input", None, "awaiting_input"),
    ("succeeded", None, "complete"),
    ("failed", None, "error"),
    ("cancelled", None, "cancelled"),
    ("expired", None, "expired"),
    ("ineligible", None, "ineligible"),
]


@pytest.mark.parametrize(("status", "kind", "expected"), TABLE)
def test_legacy_status_table(status, kind, expected):
    assert legacy_status(status, kind) == expected


def test_table_covers_every_v2_status():
    assert {row[0] for row in TABLE} == set(V2_STATUSES)
    assert len(V2_STATUSES) == 9


def test_awaiting_kind_is_ignored_outside_awaiting_input():
    assert legacy_status("running", "questions") == "running"


def test_terminal_statuses_single_source():
    from app.api.routers import sessions
    from app.domain.sessions.status import TERMINAL_STATUSES, V2_STATUSES

    assert TERMINAL_STATUSES == {"succeeded", "failed", "cancelled", "expired", "ineligible"}
    assert TERMINAL_STATUSES <= set(V2_STATUSES)
    assert sessions.TERMINAL_STATUSES is TERMINAL_STATUSES
