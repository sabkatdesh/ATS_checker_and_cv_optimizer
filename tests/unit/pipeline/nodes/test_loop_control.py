from app.config.pipeline_settings import PipelineSettings
from app.domain.ats.schemas import AtsMatch
from app.pipeline.nodes.loop_control import route_after_ats
from app.pipeline.state import RunOptions

S = PipelineSettings(ats_target=90)


def _state(passes: int, score: int, domain: str = "tech", max_passes: int = 2) -> dict:
    return {
        "passes": passes,
        "domain": domain,
        "ats": AtsMatch(applies=True, score=score),
        "options": RunOptions(max_passes=max_passes),
    }


def test_route_after_ats_first_pass_always_rewrites():
    assert route_after_ats(_state(0, 99), settings=S) == "rewrite"
    assert route_after_ats(_state(0, 10, domain="medical"), settings=S) == "rewrite"
    assert route_after_ats({}, settings=S) == "rewrite"


def test_route_after_ats_non_ats_domain_done_after_one_pass():
    assert route_after_ats(_state(1, 10, domain="medical"), settings=S) == "done"


def test_route_after_ats_target_reached():
    assert route_after_ats(_state(1, 90), settings=S) == "done"


def test_route_after_ats_cap_reached():
    assert route_after_ats(_state(2, 50, max_passes=2), settings=S) == "done"
    assert route_after_ats(_state(1, 50, max_passes=1), settings=S) == "done"


def test_route_after_ats_below_target_rewrites():
    assert route_after_ats(_state(1, 89), settings=S) == "rewrite"
    assert route_after_ats(_state(2, 50, max_passes=3), settings=S) == "rewrite"
