import socket

import pytest

from app.adapters.llm._retry import RetryPolicy

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: object) -> None:
        # asyncio's self-pipe on Windows is a loopback socketpair; anything else is a leak.
        if isinstance(address, tuple) and address and address[0] in _LOOPBACK:
            return real_connect(self, address)  # type: ignore[arg-type]
        raise AssertionError("contract tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", guarded)


async def _no_sleep(_delay: float) -> None:
    return None


@pytest.fixture
def instant_retry() -> RetryPolicy:
    return RetryPolicy(sleep=_no_sleep, rand=lambda: 1.0)
