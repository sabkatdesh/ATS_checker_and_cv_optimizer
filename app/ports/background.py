from collections.abc import Callable
from typing import Protocol


class BackgroundRunner(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...
