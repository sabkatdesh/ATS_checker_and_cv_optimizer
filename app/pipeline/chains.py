"""LLM chains, built from an injected chat model (nothing is constructed at import time)."""

from collections.abc import Callable
from dataclasses import dataclass, fields

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable

from app.pipeline.prompts import (
    COVER_LETTER_PROMPT,
    DETAILED_CV_PROMPT,
    DETAILED_JD_PROMPT,
    QUICK_CV_PROMPT,
    QUICK_JD_PROMPT,
    REWRITE_PROMPT,
    VERDICT_PROMPT,
)


@dataclass(frozen=True)
class Chains:
    quick_cv: Runnable
    quick_jd: Runnable
    verdict: Runnable
    detailed_jd: Runnable
    detailed_cv: Runnable
    rewrite: Runnable
    cover_letter: Runnable


ModelFor = Callable[[str], BaseChatModel]

_PROMPTS = {
    "quick_cv": QUICK_CV_PROMPT,
    "quick_jd": QUICK_JD_PROMPT,
    "verdict": VERDICT_PROMPT,
    "detailed_jd": DETAILED_JD_PROMPT,
    "detailed_cv": DETAILED_CV_PROMPT,
    "rewrite": REWRITE_PROMPT,
    "cover_letter": COVER_LETTER_PROMPT,
}


def _always(model: BaseChatModel) -> ModelFor:
    return lambda _chain: model


def build_chains(llm: BaseChatModel | ModelFor) -> Chains:
    """One model for every chain, or a factory asked once per chain name (a Chains field)."""
    model_for: ModelFor = _always(llm) if isinstance(llm, BaseChatModel) else llm
    built = {
        f.name: _PROMPTS[f.name] | model_for(f.name) | StrOutputParser() for f in fields(Chains)
    }
    return Chains(**built)
