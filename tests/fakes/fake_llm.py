from typing import Any, TypeVar

T = TypeVar("T")


class FakeStructuredLLM:
    def __init__(self):
        self.output: Any = None
        self.error: Exception | None = None
        self.prompts: list[str] = []

    def invoke_structured(self, prompt: str, schema: type[T]) -> T:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.output
