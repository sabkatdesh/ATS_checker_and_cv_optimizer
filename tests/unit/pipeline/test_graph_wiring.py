from langgraph.checkpoint.memory import MemorySaver

from app.pipeline.graph import build_graph
from tests.pipeline.helpers import deps_for

NODES = {
    "jd_extract",
    "cv_extract",
    "eligibility",
    "gap_questions",
    "await_answers",
    "ats_score",
    "rewrite",
    "cover_letter_options",
    "cover_letter",
}
EDGES = {
    ("__start__", "jd_extract", False),
    ("jd_extract", "cv_extract", False),
    ("cv_extract", "eligibility", False),
    ("eligibility", "gap_questions", True),
    ("eligibility", "__end__", True),
    ("gap_questions", "await_answers", False),
    ("await_answers", "ats_score", False),
    ("ats_score", "rewrite", True),
    ("ats_score", "cover_letter_options", True),
    ("rewrite", "ats_score", False),
    ("cover_letter_options", "cover_letter", True),
    ("cover_letter_options", "__end__", True),
    ("cover_letter", "__end__", False),
}


def _graph():
    _, deps = deps_for({})
    return build_graph(deps, MemorySaver()).get_graph()


def test_node_names():
    assert set(_graph().nodes) - {"__start__", "__end__"} == NODES


def test_edges():
    assert {(e.source, e.target, e.conditional) for e in _graph().edges} == EDGES
