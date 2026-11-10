from collections.abc import Callable


class InlineRunner:
    def submit(self, fn: Callable[[], None]) -> None:
        fn()
