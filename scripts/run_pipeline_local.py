"""Run the whole pipeline offline on a persona fixture and print the summary as JSON.

The fake provider answers every step from tests/fixtures/personas/<name>/replies/<step>.json,
so no model is called and nothing leaves the machine.

    uv run python -m scripts.run_pipeline_local --fixture nurse_icu [--cover-letter]

Logs go to stderr; the JSON result is the only thing on stdout.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm.fake import FakeTransport
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.usage.memory_sink import MemoryUsageSink
from app.config.llm_routes import load_route_table
from app.config.settings import AppSettings
from app.observability.logging import configure_logging
from app.pipeline.checkpointer import MemoryCheckpointerFactory
from app.pipeline.deps import PipelineDeps
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.graph import build_state_graph
from app.pipeline.prompts.loader import PromptLibrary
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions

PERSONAS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "personas"
THREAD = "local-run"


def _router(settings: AppSettings, replies: Path, sink: MemoryUsageSink) -> LLMRouter:
    prices = PriceTable.from_file(settings.llm.prices_file)
    transport = FakeTransport(defaults_dir=replies)  # each call answers with <step>.json
    registry = ProviderRegistry(
        settings,
        prices=prices,
        breakers=BreakerRegistry(),
        factories={"fake": lambda _s: transport},
    )
    table = load_route_table(settings.llm, prices)
    return LLMRouter(table, registry, UsageRecorder(sink, prices))


def run_fixture(name: str, settings: AppSettings, *, cover_letter: bool) -> dict[str, Any]:
    folder = PERSONAS / name
    sink = MemoryUsageSink()
    deps = PipelineDeps(
        gateway=_router(settings, folder / "replies", sink),
        prompts=PromptLibrary(),
        settings=settings.pipeline,
    )
    svc = PipelineService(build_state_graph(deps), deps.runs, MemoryCheckpointerFactory())
    options = RunOptions(
        cover_letter=cover_letter,
        cover_letter_tone="formal" if cover_letter else None,
        cover_letter_length="short" if cover_letter else None,
    )
    svc.run(
        job_description=(folder / "jd.txt").read_text(encoding="utf-8"),
        profile=json.loads((folder / "profile.json").read_text(encoding="utf-8")),
        thread_id=THREAD,
        options=options,
    )
    if "await_answers" in svc.get_state(THREAD)["next"]:
        svc.resume(THREAD, json.loads((folder / "answers.json").read_text(encoding="utf-8")))
    summary = svc.summary(THREAD)
    return {
        "fixture": name,
        "steps": [record.step for record in sink.records()],
        "summary": None if summary is None else summary.model_dump(mode="json"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the pipeline offline on a persona fixture.")
    parser.add_argument("--fixture", required=True, help="persona folder name")
    parser.add_argument("--cover-letter", action="store_true", help="also write a cover letter")
    args = parser.parse_args(argv)
    if not (PERSONAS / args.fixture / "replies").is_dir():
        print(f"unknown fixture: {args.fixture}", file=sys.stderr)
        return 2
    settings = AppSettings(_env_file=None, env="test", llm={"default_provider": "fake"})
    configure_logging(settings.obs, stream=sys.stderr)
    try:
        result = run_fixture(args.fixture, settings, cover_letter=args.cover_letter)
    except PipelineStepFailed as failure:
        print(f"pipeline failed: {failure.step} {failure.code}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
