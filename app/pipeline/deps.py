"""Collaborators injected into pipeline steps."""

from dataclasses import dataclass, field

from app.config.pipeline_settings import PipelineSettings
from app.pipeline.prompts.loader import PromptLibrary
from app.pipeline.runs import RunRegistry
from app.ports.llm import LLMGateway


@dataclass(frozen=True)
class PipelineDeps:
    gateway: LLMGateway
    prompts: PromptLibrary
    settings: PipelineSettings
    runs: RunRegistry = field(default_factory=RunRegistry)
