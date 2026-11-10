"""LLM chains, built from an injected chat model (nothing is constructed at import time)."""

from dataclasses import dataclass

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


def build_chains(llm: BaseChatModel) -> Chains:
    return Chains(
        quick_cv=QUICK_CV_PROMPT | llm | StrOutputParser(),
        quick_jd=QUICK_JD_PROMPT | llm | StrOutputParser(),
        verdict=VERDICT_PROMPT | llm | StrOutputParser(),
        detailed_jd=DETAILED_JD_PROMPT | llm | StrOutputParser(),
        detailed_cv=DETAILED_CV_PROMPT | llm | StrOutputParser(),
        rewrite=REWRITE_PROMPT | llm | StrOutputParser(),
        cover_letter=COVER_LETTER_PROMPT | llm | StrOutputParser(),
    )
