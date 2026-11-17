"""Deterministic checks every model-written CV draft passes before it enters the state.

Dropped sections come back from the source, then markup and invented contacts are removed.
"""

from app.domain.cv.output_checks import remove_foreign_contacts, strip_markup
from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.sections import restore_dropped
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.questions.reply import answers_block
from app.pipeline.state import PipelineState
from app.pipeline.warnings import PipelineWarning


def check_draft(
    source: UniversalCVStructured, draft: RewrittenCV, step: str
) -> tuple[RewrittenCV, list[PipelineWarning]]:
    cv, restored = restore_dropped(source, draft)
    cv, removed = remove_foreign_contacts(source, strip_markup(cv))
    warnings: list[PipelineWarning] = []
    if restored:
        warnings.append(PipelineWarning(code="SECTION_RESTORED", step=step))
    if removed:
        warnings.append(PipelineWarning(code="FOREIGN_CONTACT_REMOVED", step=step))
    return cv, warnings


def answers_text(state: PipelineState) -> str:
    """The <answers> block text; empty when the user gave none (the block is then left out)."""
    answers = state.get("answers")
    return answers_block(state.get("questions") or [], answers) if answers is not None else ""
