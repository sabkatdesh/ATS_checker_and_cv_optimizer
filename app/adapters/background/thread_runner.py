import threading
from collections.abc import Callable


class ThreadRunner:
    def submit(self, fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()
