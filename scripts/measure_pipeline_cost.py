"""Measure the real LLM cost of the pipeline on the synthetic personas (budget-gated).

    uv run python scripts/measure_pipeline_cost.py --dry-run     # default: no network
    uv run python scripts/measure_pipeline_cost.py --yes         # paid: needs the owner's yes

The cap defaults to $0.50 (the owner's hard total) and a larger cap is refused. Every call goes
through BudgetedGateway, so no call starts if spent + its worst case would exceed the cap.
Personas run one at a time. Outputs hold ids, tokens, costs and flags, never CV or JD text.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.adapters.llm._breaker import BreakerRegistry  # noqa: E402
from app.adapters.llm._pricing import PriceTable  # noqa: E402
from app.adapters.llm.registry import ProviderRegistry  # noqa: E402
from app.adapters.llm.router import LLMRouter  # noqa: E402
from app.adapters.usage.memory_sink import MemoryUsageSink  # noqa: E402
from app.config.llm_routes import RouteTable  # noqa: E402
from app.config.pipeline_settings import PipelineSettings  # noqa: E402
from app.config.settings import AppSettings, load_settings  # noqa: E402
from app.container import Container  # noqa: E402
from app.pipeline.checkpoint_types import new_checkpointer  # noqa: E402
from app.pipeline.deps import PipelineDeps  # noqa: E402
from app.pipeline.graph import build_graph  # noqa: E402
from app.pipeline.prompts.loader import PromptLibrary  # noqa: E402
from app.pipeline.service import PipelineService  # noqa: E402
from app.pipeline.state import RunOptions  # noqa: E402
from app.ports.llm import LLMGateway, LLMRequest, Usage  # noqa: E402
from scripts._cost_gate import (  # noqa: E402
    BudgetedGateway,
    BudgetExceeded,
    est_input_tokens,
    worst_case_usd,
)
from scripts._cost_plan import STEPS, persona_size, render_plan  # noqa: E402
from scripts.cost_report import (  # noqa: E402
    CvRun,
    ReportMeta,
    StepUsage,
    render_report,
    runs_to_json,
)

PERSONAS_DIR = ROOT / "tests" / "fixtures" / "personas"
DEFAULT_PERSONAS = (
    "tech_backend",
    "nurse_icu",
    "electrician_trades",
    "banker_mixed_bn",
    "teacher_long",
)
MAX_CAP = Decimal("0.50")
OUT_DIR = ROOT / ".local-docs" / "progress"


def say(line: str) -> None:
    sys.stdout.write(line + "\n")


def fail(line: str) -> int:
    sys.stderr.write(line + "\n")
    return 2


def run_persona(
    name: str, gateway: LLMGateway, sink: MemoryUsageSink, settings: PipelineSettings
) -> CvRun:
    """One full run: questions answered from answers.json, cover letter formal / standard."""
    folder = PERSONAS_DIR / name
    deps = PipelineDeps(gateway=gateway, prompts=PromptLibrary(), settings=settings)
    svc = PipelineService(build_graph(deps, new_checkpointer()), deps.runs)
    options = RunOptions(
        cover_letter=True, cover_letter_tone="formal", cover_letter_length="standard"
    )
    started = time.perf_counter()
    svc.run(
        job_description=(folder / "jd.txt").read_text(encoding="utf-8"),
        profile=json.loads((folder / "profile.json").read_text(encoding="utf-8")),
        thread_id=name,
        options=options,
    )
    if "await_answers" in svc.get_state(name)["next"]:
        svc.resume(name, json.loads((folder / "answers.json").read_text(encoding="utf-8")))
    latency = time.perf_counter() - started
    records = [r for r in sink.records() if r.session_id == name]
    summary = svc.summary(name)
    values = svc.get_state(name)["values"]
    trust = None if summary is None else summary.trust_report
    steps = [_step_usage(step, records) for step in STEPS if any(r.step == step for r in records)]
    return CvRun(
        persona=name,
        total_usd=sum((r.cost_usd for r in records), Decimal(0)),
        calls=len(records),
        repairs=sum(1 for r in records if r.repaired),
        passes=int(values.get("passes", 0)),
        verifier_status="none" if trust is None else trust.status,
        latency_s=latency,
        steps=steps,
    )


def _step_usage(step: str, records: Sequence[Any]) -> StepUsage:
    rows = [r for r in records if r.step == step]
    usage = sum((r.usage for r in rows), Usage())
    return StepUsage(
        step,
        len(rows),
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
        sum((r.cost_usd for r in rows), Decimal(0)),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="no network (the default)")
    parser.add_argument("--no-dry-run", action="store_true", help="paid mode; also needs --yes")
    parser.add_argument("--yes", action="store_true", help="the owner approved the paid run")
    parser.add_argument("--cap", default=str(MAX_CAP), help="total USD ceiling (max 0.50)")
    parser.add_argument("--personas", nargs="+", default=list(DEFAULT_PERSONAS))
    return parser


def _paid(settings: AppSettings, personas: Sequence[str], cap: Decimal) -> int:
    sink = MemoryUsageSink()
    container = Container(settings, usage_sink=sink)
    full = container.validate_llm_config()
    prices = PriceTable.from_file(settings.llm.prices_file)
    table = RouteTable({s: full.resolve(s) for s in STEPS}, dict.fromkeys(STEPS), full.embeddings)
    providers = ProviderRegistry(settings, prices=prices, breakers=BreakerRegistry())
    router = LLMRouter(table, providers, container.usage)

    def worst(req: LLMRequest[Any]) -> Decimal:
        route = table.resolve(req.step)
        return worst_case_usd(route, est_input_tokens(req), prices, provider=route.provider)

    def usage_cost(req: LLMRequest[Any], usage: Usage) -> Decimal:
        route = table.resolve(req.step)
        return prices.cost(route.provider, route.model, usage)

    gate = BudgetedGateway(router, cap, worst, usage_cost)
    runs: list[CvRun] = []
    for name in personas:
        try:
            run = run_persona(name, gate, sink, settings.pipeline)
        except BudgetExceeded:
            say(f"{name}: stopped, the next call would exceed the cap")
            break
        except Exception as exc:  # noqa: BLE001 - report the type only, never message text
            say(f"{name}: failed {type(exc).__name__}; spent ${gate.spent:.4f}")
            break
        runs.append(run)
        say(f"{name}: ${run.total_usd:.4f} calls={run.calls} total spent ${gate.spent:.4f}")
    if runs:
        meta = ReportMeta(cap=cap, spent=gate.spent)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "M3-cost-report.md").write_text(render_report(runs, meta), encoding="utf-8")
        (OUT_DIR / "M3-cost-runs.json").write_text(runs_to_json(runs, meta), encoding="utf-8")
    say(f"personas completed: {len(runs)} of {len(personas)}; total spent ${gate.spent:.4f}")
    return 0 if len(runs) == len(personas) else 1


def main(argv: Sequence[str] | None = None, *, settings: AppSettings | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cap = Decimal(args.cap)
    except InvalidOperation:
        return fail(f"invalid --cap {args.cap!r}")
    if cap > MAX_CAP:
        return fail(f"refused: --cap {cap} is above the hard total budget of {MAX_CAP}")
    if cap <= 0:
        return fail("refused: --cap must be positive")
    unknown = [p for p in args.personas if not (PERSONAS_DIR / p / "profile.json").is_file()]
    if unknown:
        return fail(f"unknown persona: {', '.join(unknown)}")
    paid = (args.yes or args.no_dry_run) and not args.dry_run
    if paid and not args.yes:
        return fail("refused: a paid run needs --yes (the owner's explicit approval)")
    settings = settings if settings is not None else load_settings()
    if paid:
        return _paid(settings, args.personas, cap)
    container = Container(settings)
    prices = PriceTable.from_file(settings.llm.prices_file)
    full = container.validate_llm_config()
    table = RouteTable({s: full.resolve(s) for s in STEPS}, dict.fromkeys(STEPS), full.embeddings)
    sizes = [persona_size(PERSONAS_DIR, p) for p in args.personas]
    if not render_plan(sizes, table, prices, cap, say):
        say("ABORT: a single call's worst case exceeds the cap")
        return 2
    say("dry run: no network call made")
    return 0


if __name__ == "__main__":
    sys.exit(main())
