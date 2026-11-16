"""LangChain chat model that sends legacy chain prompts through the LLM gateway (text mode).

The route for `step` sets the model, max_tokens and temperature; this class only maps messages.
It depends on langchain-core alone and never imports the pipeline (chains are built by the
container).
"""

from typing import Any

import structlog
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.adapters.llm._sync import run_sync
from app.ports.llm import CallMeta, LLMRequest, Message
from app.ports.llm_errors import LLMBadRequest


def _text(message: BaseMessage) -> str:
    if not isinstance(message.content, str):
        raise LLMBadRequest("only plain-text message content is supported")
    return message.content


def to_request(messages: list[BaseMessage], *, step: str, prompt_id: str) -> LLMRequest[Any]:
    system: list[str] = []
    turns: list[Message] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            system.append(_text(message))
        elif isinstance(message, HumanMessage):
            turns.append(Message(role="user", content=_text(message)))
        elif isinstance(message, AIMessage):
            turns.append(Message(role="assistant", content=_text(message)))
        else:
            raise LLMBadRequest(f"unsupported message type {message.type!r}")
    if not turns or turns[-1].role != "user":
        raise LLMBadRequest("last message must be from the user; assistant prefill is unsupported")
    return LLMRequest[Any](
        step=step,
        system="\n\n".join(system),
        messages=turns,
        output_schema=None,
        metadata=CallMeta(prompt_id=prompt_id),
    )


class GatewayChatModel(BaseChatModel):
    gateway: Any
    step: str
    prompt_id: str

    @property
    def _llm_type(self) -> str:
        return "llm-gateway"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if stop:
            raise LLMBadRequest("stop sequences are not supported")
        req = to_request(messages, step=self.step, prompt_id=self.prompt_id)
        result = run_sync(self.gateway.complete(req))
        if result.stop_reason == "max_tokens":
            structlog.get_logger("llm").warning(
                "llm.truncated", step=self.step, prompt_id=self.prompt_id
            )
        message = AIMessage(content=str(result.output))
        return ChatResult(generations=[ChatGeneration(message=message)])
