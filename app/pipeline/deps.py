"""Collaborators injected into pipeline steps."""

from dataclasses import dataclass

from app.config.pipeline_settings import PipelineSettings
from app.pipeline.prompts.loader import PromptLibrary
from app.ports.llm import LLMGateway


@dataclass(frozen=True)
class PipelineDeps:
    gateway: LLMGateway
    prompts: PromptLibrary
    settings: PipelineSettings
