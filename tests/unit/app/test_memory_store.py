import pytest

from tests.fakes.memory_store import LEGACY_SESSION_COLUMNS, MemoryStore


def test_update_session_rejects_unknown_column():
    store = MemoryStore()
    store.update_session("t1", {"status": "complete", "ats_score": 80})
    assert store.sessions["t1"]["status"] == "complete"
    with pytest.raises(ValueError, match="jd_title"):
        store.update_session("t1", {"status": "complete", "jd_title": "Engineer"})
    assert "jd_title" not in store.sessions["t1"]


def test_legacy_columns_match_the_schema():
    assert {
        "status",
        "domain",
        "gaps",
        "hitl_question",
        "token_cost_output",
    } <= LEGACY_SESSION_COLUMNS
    assert "trust_report" not in LEGACY_SESSION_COLUMNS
