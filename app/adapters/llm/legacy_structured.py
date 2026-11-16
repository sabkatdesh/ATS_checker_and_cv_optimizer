"""StructuredLLM (the legacy sync port) on top of the LLM gateway, used by profile import."""

from typing import Any, TypeVar, cast

import structlog

from app.adapters.llm._sync import run_sync
from app.ports.llm import CallMeta, LLMGateway, LLMRequest, Message
from app.ports.llm_errors import LLMOutputInvalid

T = TypeVar("T")


class GatewayStructuredLLM:
    def __init__(
        self,
        gateway: LLMGateway,
        *,
        step: str = "profile_import",
        prompt_id: str = "legacy.profile_import",
    ) -> None:
        self._gateway = gateway
        self._step = step
        self._prompt_id = prompt_id

    def invoke_structured(self, prompt: str, schema: type[T]) -> T:
        """Invalid output (after the provider's one repair) yields schema(); other errors raise."""
        req = LLMRequest[Any](
            step=self._step,
            messages=[Message(role="user", content=prompt)],
            output_schema=cast(Any, schema),
            metadata=CallMeta(prompt_id=self._prompt_id),
        )
        try:
            result = run_sync(self._gateway.complete(req))
        except LLMOutputInvalid as err:
            structlog.get_logger("llm").warning(
                "llm.structured_default", step=self._step, prompt_id=self._prompt_id, kind=err.kind
            )
            return schema()
        return cast(T, result.output)
