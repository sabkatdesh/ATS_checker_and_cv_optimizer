from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.graph import build_graph
from app.pipeline.hooks import NODE_STAGES, NoopHooks, ProgressEvent
from tests.pipeline.helpers import deps_for, run

HAPPY_PATH = [
    "jd_extract",
    "cv_extract",
    "eligibility",
    "gap_questions",
    "await_answers",
    "ats_score",
    "rewrite",
    "verify_claims",
    "revise_flagged",
    "cover_letter_options",
    "cover_letter",
]


def test_every_graph_node_has_a_stage():
    _, deps = deps_for({})
    nodes = set(build_graph(deps, new_checkpointer()).get_graph().nodes) - {"__start__", "__end__"}
    assert nodes <= set(NODE_STAGES)


def test_snapshot_node_shares_the_extract_stage():
    assert NODE_STAGES["cv_snapshot"] == NODE_STAGES["cv_extract"] == ("analysis", 15)


def test_progress_never_decreases_along_the_happy_path():
    progress = [NODE_STAGES[name][1] for name in HAPPY_PATH]
    assert progress == sorted(progress)
    assert progress[-1] == 100


def test_noop_hooks_accept_events():
    event = ProgressEvent(
        session_id="s", node="jd_extract", stage="analysis", phase="started", progress=10
    )
    run(NoopHooks().before_node(event))
    run(NoopHooks().after_node(event))
