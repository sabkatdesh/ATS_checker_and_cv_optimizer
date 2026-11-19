from app.pipeline.nodes.gate import route_after_eligibility


def test_route_after_eligibility():
    assert route_after_eligibility({"eligible": True}) == "questions"
    assert route_after_eligibility({"eligible": False}) == "ineligible"
    assert route_after_eligibility({}) == "ineligible"
