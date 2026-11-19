"""Pipeline tuning knobs (env prefix PIPELINE__)."""

from pydantic import BaseModel, Field


class PipelineSettings(BaseModel, frozen=True):
    eligibility_threshold: int = Field(default=30, ge=0, le=100)
    ats_target: int = Field(default=90, ge=1, le=100)
    max_passes: int = Field(default=2, ge=1, le=3)
    judge_enabled: bool = True
