"""Cost report for the M3 measurement runs. Holds ids, tokens, costs and flags; never CV/JD text."""

from __future__ import annotations

import dataclasses
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

SPEC_ESTIMATE_PER_CV = Decimal("0.30")  # spec 10 section 7, with a cover letter
TIER_PRICES = (8, 10, 12)  # credits per CV: standard / designed / premium
BONUS_CREDITS = 100
_COVER = "cover_letter"


@dataclass(frozen=True)
class StepUsage:
    step: str
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class CvRun:
    persona: str
    total_usd: Decimal
    calls: int
    repairs: int
    passes: int
    verifier_status: str
    latency_s: float
    steps: list[StepUsage] = field(default_factory=list)


@dataclass(frozen=True)
class ReportMeta:
    cap: Decimal
    spent: Decimal
    cache_read_saving_per_m: Decimal = Decimal("2.70")  # input price minus cache-read price
    cache_covers: str = "the system prompt only (rewrite is the only step that asks for it)"


def percentile(values: Sequence[Decimal], pct: int) -> Decimal:
    """Nearest rank."""
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _money(value: Decimal) -> str:
    return f"${value:.4f}"


def _per_step(runs: Sequence[CvRun]) -> list[StepUsage]:
    acc: dict[str, list[int | Decimal]] = defaultdict(lambda: [0, 0, 0, 0, 0, Decimal(0)])
    for run in runs:
        for s in run.steps:
            row = acc[s.step]
            for i, v in enumerate(
                (
                    s.calls,
                    s.input_tokens,
                    s.output_tokens,
                    s.cache_read_tokens,
                    s.cache_write_tokens,
                )
            ):
                row[i] += v
            row[5] += s.cost_usd
    return [StepUsage(step, *row) for step, row in acc.items()]  # type: ignore[arg-type]


def _step_table(runs: Sequence[CvRun]) -> list[str]:
    lines = [
        "| step | calls | avg in | avg out | avg cache read | avg cache write | avg $ |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in _per_step(runs):
        n = max(s.calls, 1)
        lines.append(
            f"| {s.step} | {s.calls} | {s.input_tokens // n} | {s.output_tokens // n} | "
            f"{s.cache_read_tokens // n} | {s.cache_write_tokens // n} | {_money(s.cost_usd / n)} |"
        )
    return lines


def _cv_table(runs: Sequence[CvRun]) -> list[str]:
    lines = [
        "| persona | total $ | calls | repairs | passes | verifier | latency s |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        lines.append(
            f"| {r.persona} | {_money(r.total_usd)} | {r.calls} | {r.repairs} | {r.passes} | "
            f"{r.verifier_status} | {r.latency_s:.1f} |"
        )
    return lines


def render_report(runs: Sequence[CvRun], meta: ReportMeta) -> str:
    totals = [r.total_usd for r in runs]
    p50, p95 = percentile(totals, 50), percentile(totals, 95)
    mean = sum(totals, Decimal(0)) / len(totals)
    cache_read = sum(s.cache_read_tokens for r in runs for s in r.steps)
    saved = Decimal(cache_read) * meta.cache_read_saving_per_m / Decimal(1_000_000)
    cover = sum((s.cost_usd for r in runs for s in r.steps if s.step == _COVER), Decimal(0))
    share = cover / sum(totals, Decimal(0)) * 100 if sum(totals, Decimal(0)) else Decimal(0)
    note = " With fewer than 20 samples p95 equals the maximum." if len(runs) < 20 else ""
    out = ["# M3 pipeline cost report", ""]
    out += [f"Runs: {len(runs)}. Spent {_money(meta.spent)} of the {_money(meta.cap)} cap.", ""]
    out += ["## Per step", "", *_step_table(runs), ""]
    out += ["## Per CV", "", *_cv_table(runs), ""]
    out += [
        f"Cost per CV: p50 {_money(p50)}, p95 {_money(p95)}, mean {_money(mean)} "
        "(nearest rank)." + note,
        "",
    ]
    out += [
        "## Caching effect",
        "",
        f"Cache-read tokens: {cache_read}; saving versus uncached input: {_money(saved)}. "
        f"The cachePoint covers {meta.cache_covers}.",
        "",
    ]
    out += ["## Cover letter share", "", f"The cover letter is {share:.1f}% of the total.", ""]
    delta = mean - SPEC_ESTIMATE_PER_CV
    out += [
        "## Measured vs Spec 10 estimate",
        "",
        f"Spec 10 section 7 estimates {_money(SPEC_ESTIMATE_PER_CV)} per CV; measured mean "
        f"{_money(mean)} (difference {_money(delta)}).",
        "",
    ]
    out += [
        "## Prices (unverified)",
        "",
        "The Sonnet 4.6 prices are the list prices assumed for the us.* inference profile; "
        "any geo-profile premium is not confirmed.",
        "",
    ]
    out += [f"## Bonus projection ({BONUS_CREDITS} credits)", ""]
    for tier in TIER_PRICES:
        cvs = Decimal(BONUS_CREDITS) / tier
        out.append(
            f"- At {tier} credits per CV: {cvs:.1f} CVs, LLM cost {_money(cvs * p50)} (p50)."
        )
    return "\n".join(out) + "\n"


def runs_to_json(runs: Sequence[CvRun], meta: ReportMeta) -> str:
    def plain(value: object) -> object:
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(type(value).__name__)

    payload = {
        "cap": meta.cap,
        "spent": meta.spent,
        "runs": [dataclasses.asdict(r) for r in runs],
    }
    return json.dumps(payload, default=plain, indent=2)
