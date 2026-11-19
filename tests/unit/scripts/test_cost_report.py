import dataclasses
import json
from decimal import Decimal

from scripts.cost_report import CvRun, ReportMeta, StepUsage, render_report, runs_to_json

COSTS = ["0.20", "0.25", "0.30", "0.35", "0.60"]
RUN_KEYS = {
    "persona",
    "total_usd",
    "calls",
    "repairs",
    "passes",
    "verifier_status",
    "latency_s",
    "steps",
}


def _run(i: int, cost: str) -> CvRun:
    return CvRun(
        persona=f"persona_{i}",
        total_usd=Decimal(cost),
        calls=7,
        repairs=1,
        passes=2,
        verifier_status="pass",
        latency_s=41.5,
        steps=[
            StepUsage("rewrite", 1, 3000, 2500, 0, 0, Decimal(cost) * Decimal("0.7")),
            StepUsage("cover_letter", 1, 900, 400, 0, 0, Decimal(cost) * Decimal("0.3")),
        ],
    )


META = ReportMeta(cap=Decimal("0.50"), spent=Decimal("1.70"))


def test_report_percentiles():
    text = render_report([_run(i, c) for i, c in enumerate(COSTS)], META)
    assert "p50 $0.3000" in text
    assert "p95 $0.6000" in text
    assert "p95 equals the maximum" in text


def test_report_sections_present():
    text = render_report([_run(i, c) for i, c in enumerate(COSTS)], META)
    for heading in ("Per step", "Per CV", "Caching", "Cover letter", "Spec 10", "Prices", "Bonus"):
        assert heading in text
    assert "100 credits" in text


def test_report_has_no_text_fields():
    runs = [_run(i, c) for i, c in enumerate(COSTS)]
    assert {f.name for f in dataclasses.fields(CvRun)} == RUN_KEYS
    payload = json.loads(runs_to_json(runs, META))
    assert set(payload["runs"][0]) == RUN_KEYS
    step_keys = {f.name for f in dataclasses.fields(StepUsage)}
    assert set(payload["runs"][0]["steps"][0]) == step_keys
