"""Manual Bedrock smoke check, run by the owner: one structured JD extraction (paid).

    uv run python -m app.adapters.llm.bedrock_converse          # prints the cost estimate only
    uv run python -m app.adapters.llm.bedrock_converse --yes    # makes the real call

The router is built directly from settings (the container does not expose it yet) and the
jd_extract route is used with max_tokens capped at 1500 and its fallback disabled. Only a
short parsed summary is printed, never model text.
"""

import argparse
import asyncio
import sys

from app.adapters.llm._bedrock_wire import estimate_tokens
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._structured import json_instruction
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.usage.memory_sink import MemoryUsageSink
from app.config.llm_routes import RouteTable, load_route_table
from app.config.settings import load_settings
from app.domain.jd.schemas import JobDescriptionStructured
from app.ports.llm import CallMeta, LLMRequest, Message, Usage
from app.ports.llm_errors import LLMError

STEP = "jd_extract"
MAX_TOKENS = 1500
SYSTEM = "Extract the job description into the requested JSON structure. Use only the text given."
SAMPLE_JD = """Senior Backend Engineer (Python), Dhaka, full-time.
We build payment software for small merchants across Bangladesh.
You will design and run FastAPI services, own PostgreSQL schemas and mentor two engineers.
Must have: 5+ years of Python, FastAPI or Django, PostgreSQL, Docker, REST API design.
Nice to have: AWS, Redis, experience with mobile financial services such as bKash.
Education: BSc in Computer Science or equivalent experience."""


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")


def _request() -> LLMRequest[JobDescriptionStructured]:
    return LLMRequest[JobDescriptionStructured](
        step=STEP,
        system=SYSTEM,
        messages=[Message(role="user", content=f"<jd>\n{SAMPLE_JD}\n</jd>")],
        output_schema=JobDescriptionStructured,
        metadata=CallMeta(prompt_id="smoke.jd_extract"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bedrock smoke check (one paid call).")
    parser.add_argument("--yes", action="store_true", help="really call Bedrock")
    args = parser.parse_args(argv)

    settings = load_settings()
    prices = PriceTable.from_file(settings.llm.prices_file)
    full = load_route_table(settings.llm, prices)
    primary = full.resolve(STEP)
    route = primary.model_copy(update={"max_tokens": min(primary.max_tokens, MAX_TOKENS)})
    # Only the capped jd_extract route, with no fallback, so the cost bound below holds.
    table = RouteTable({STEP: route}, {STEP: None}, full.embeddings)
    instruction = json_instruction(JobDescriptionStructured.model_json_schema())
    est_in = estimate_tokens(SYSTEM + instruction + SAMPLE_JD) + 50
    one_call = prices.cost(
        route.provider, route.model, Usage(input_tokens=est_in, output_tokens=route.max_tokens)
    )
    _say(f"route: {route.provider}/{route.model} max_tokens={route.max_tokens}")
    _say("fallback: disabled for this run")
    _say(f"estimated cost: ~${one_call} per call, at most ${one_call * 2} with one repair")
    if not args.yes:
        _say("dry run: no call made. Re-run with --yes to call Bedrock.")
        return 0

    sink = MemoryUsageSink()
    providers = ProviderRegistry(settings, prices=prices, breakers=BreakerRegistry())
    router = LLMRouter(table, providers, UsageRecorder(sink, prices))
    try:
        result = asyncio.run(router.complete(_request()))
    except LLMError as err:
        _say(f"call failed: {err.kind} ({err.detail}); attempts={err.attempts}")
        return 1
    jd = result.output
    valid = isinstance(jd, JobDescriptionStructured)
    _say(f"valid={valid} repaired={result.repaired} stop={result.stop_reason}")
    _say(f"tokens in={result.usage.input_tokens} out={result.usage.output_tokens}")
    _say(f"cost=${result.cost_usd} latency_ms={result.latency_ms} attempts={result.attempts}")
    if isinstance(jd, JobDescriptionStructured):
        title = (jd.job_title or "")[:80]
        _say(f"job_title={title!r} must_haves={len(jd.requirements.must_have)}")
    return 0 if valid else 1
