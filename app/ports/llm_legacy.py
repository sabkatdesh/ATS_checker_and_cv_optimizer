from typing import Protocol, TypeVar

T = TypeVar("T")


class StructuredLLM(Protocol):
    def invoke_structured(self, prompt: str, schema: type[T]) -> T: ...
