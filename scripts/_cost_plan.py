"""Offline cost plan for the pipeline measurement: per-call worst case and a rough estimate.

Inputs are sized from the persona fixtures; nothing here touches the network.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.adapters.llm._pricing import PriceTable
from app.config.llm_routes import RouteTable
from app.pipeline.prompts.loader import PromptLibrary
from app.ports.llm import Usage
from scripts._cost_gate import MARGIN, worst_case_usd

STEPS = (
    "jd_extract",
    "eligibility",
    "gap_questions",
    "rewrite",
    "verify_claims",
    "revise_flagged",
    "cover_letter",
)
# Expected calls per CV (rewrite and verify run once or twice, revise 0 or 1 times).
EXPECTED_CALLS = {"rewrite": 1.5, "verify_claims": 1.5, "revise_flagged": 0.5}
# Steps whose input also carries a whole CV draft on top of the profile.
DRAFT_STEPS = {"rewrite", "verify_claims", "revise_flagged"}
SCHEMA_RESERVE = 1500  # tokens for the JSON schema instruction
EXPECTED_OUTPUT_FRACTION = Decimal("0.5")  # of max_tokens, an assumption to be measured


@dataclass(frozen=True)
class PersonaSize:
    name: str
    jd_chars: int
    profile_chars: int


@dataclass(frozen=True)
class StepPlan:
    step: str
    in_tokens: int
    max_tokens: int
    worst: Decimal
    expected: Decimal


def persona_size(root: Path, name: str) -> PersonaSize:
    folder = root / name
    jd = (folder / "jd.txt").read_text(encoding="utf-8")
    profile = (folder / "profile.json").read_text(encoding="utf-8")
    return PersonaSize(name, len(jd), len(profile))


def _tokens(chars: int) -> int:
    return int(chars / 4 * MARGIN)


def plan_persona(
    size: PersonaSize, table: RouteTable, prices: PriceTable, prompts: PromptLibrary
) -> list[StepPlan]:
    plans: list[StepPlan] = []
    for step in STEPS:
        route = table.resolve(step)
        chars = len(prompts.get(step).system) + size.jd_chars + size.profile_chars
        tin = _tokens(chars) + 50 + SCHEMA_RESERVE
        if step in DRAFT_STEPS:
            tin += _tokens(size.profile_chars)
        out = int(route.max_tokens * EXPECTED_OUTPUT_FRACTION)
        expected = prices.cost(
            route.provider, route.model, Usage(input_tokens=tin, output_tokens=out)
        )
        worst = worst_case_usd(route, tin, prices, provider=route.provider)
        plans.append(StepPlan(step, tin, route.max_tokens, worst, expected))
    return plans


def persona_totals(plans: Sequence[StepPlan]) -> tuple[Decimal, Decimal]:
    """(worst case with every call at max_tokens plus a repair, expected)."""
    worst = sum((p.worst for p in plans), Decimal(0))
    expected = sum(
        (p.expected * Decimal(str(EXPECTED_CALLS.get(p.step, 1))) for p in plans), Decimal(0)
    )
    return worst, expected


def render_plan(
    sizes: Sequence[PersonaSize],
    table: RouteTable,
    prices: PriceTable,
    cap: Decimal,
    say: Callable[[str], None],
) -> bool:
    """Print the plan; False when a single call's worst case exceeds the cap."""
    prompts = PromptLibrary()
    all_plans = {s.name: plan_persona(s, table, prices, prompts) for s in sizes}
    biggest = max(all_plans, key=lambda n: persona_totals(all_plans[n])[1])
    say(f"plan: {len(sizes)} persona(s), one at a time; fallback route DISABLED for this run")
    for size in sizes:
        say(f"persona {size.name}: jd {size.jd_chars} chars, profile {size.profile_chars} chars")
    say(f"per-call worst case, from the largest estimate ({biggest}); includes one repair:")
    for p in all_plans[biggest]:
        say(f"  {p.step:15s} in~{p.in_tokens:6d} max_tokens={p.max_tokens:5d} worst ${p.worst:.4f}")
    worst_call = max(p.worst for plans in all_plans.values() for p in plans)
    say(f"worst case per call (max) ${worst_call:.4f} <= cap ${cap:.2f}")
    totals = {n: persona_totals(p) for n, p in all_plans.items()}
    estimate = sum((e for _, e in totals.values()), Decimal(0))
    worst_all = sum((w for w, _ in totals.values()), Decimal(0))
    worst_persona = max(w for w, _ in totals.values())
    say(f"worst case per persona (every call at max_tokens): up to ${worst_persona:.4f}")
    say(f"estimate (half of max_tokens per call, rewrite x1.5): ${estimate:.4f} for all personas")
    say(f"worst case for all personas ${worst_all:.4f}; cap ${cap:.2f}")
    per_persona = estimate / len(sizes)
    fits = int(cap // per_persona) if per_persona else len(sizes)
    say(f"personas that fit under the cap at the estimate: {min(fits, len(sizes))} of {len(sizes)}")
    return worst_call <= cap
