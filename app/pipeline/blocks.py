"""Untrusted text goes into the user message inside tagged data blocks only."""

from collections.abc import Sequence
from typing import Literal

DataTag = Literal[
    "job_description",
    "job_requirements",
    "cv",
    "answers",
    "gaps",
    "previous_draft",
    "ats_feedback",
    "rewritten_cv",
    "flagged_claims",
]


def data_block(tag: DataTag, content: str) -> str:
    return f"<{tag}>\n{content}\n</{tag}>"


def user_message(blocks: Sequence[tuple[DataTag, str]], task_line: str) -> str:
    parts = [data_block(tag, content) for tag, content in blocks]
    return "\n".join(parts) + "\n\n" + task_line
