"""Non-fatal pipeline warnings: a code and a step name, never user text."""

from pydantic import BaseModel

from app.domain.warnings import WarningCode

__all__ = ["PipelineWarning", "WarningCode"]


class PipelineWarning(BaseModel, frozen=True):
    code: WarningCode
    step: str
