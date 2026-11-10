"""Deterministic chat model: canned reply chosen by a marker substring found in the prompt.

The two quick-extract nodes run in parallel, so an ordered list of replies would be
non-deterministic; routing on prompt content is not.
"""

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class RoutingFakeChatModel(BaseChatModel):
    routes: list[tuple[str, str]] = Field(default_factory=list)
    default: str = "{}"
    prompts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "routing-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = "\n".join(str(m.content) for m in messages)
        self.prompts.append(text)
        reply = next((out for marker, out in self.routes if marker in text), self.default)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])
