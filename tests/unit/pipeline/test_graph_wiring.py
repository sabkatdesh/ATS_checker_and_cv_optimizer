import json
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from app.pipeline.chains import build_chains
from app.pipeline.graph import build_graph
from tests.fakes.fake_chat_model import RoutingFakeChatModel

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "pipeline_edges.json"
LEGACY_NODES = {
    "quick_extract_jd",
    "quick_extract_cv",
    "eligibility_check",
    "hitl_node",
    "start_detailed_phase",
    "detailed_extract_jd",
    "detailed_extract_cv",
    "compute_match",
    "rewrite_cv",
    "cover_letter_hitl",
    "generate_cover_letter",
}


def _graph():
    return build_graph(build_chains(RoutingFakeChatModel()), MemorySaver()).get_graph()


def test_node_names_match_legacy():
    assert set(_graph().nodes) - {"__start__", "__end__"} == LEGACY_NODES


def test_edges_match_legacy():
    expected = [tuple(p) for p in json.loads(FIXTURE.read_text())]
    assert sorted((e.source, e.target) for e in _graph().edges) == expected
