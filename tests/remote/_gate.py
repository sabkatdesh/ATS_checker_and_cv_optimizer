"""Skip-by-default gate and preflight for the remote suite (pure; unit-tested offline)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from tests.remote._env import PAUSED_MESSAGE, SKIP_REASON, RemoteEnv

REMOTE_DIR = Path(__file__).resolve().parent


def is_remote_item(item: Any, remote_dir: Path = REMOTE_DIR) -> bool:
    path = Path(str(getattr(item, "path", "") or getattr(item, "fspath", "")))
    return remote_dir in path.parents


def mark_remote_items(items: list[Any], enabled: bool, remote_dir: Path = REMOTE_DIR) -> int:
    """Mark every item under tests/remote as `remote`; skip them unless enabled. Returns the
    number skipped. (A sub-directory conftest hook still sees the whole session's items.)"""
    skipped = 0
    for item in items:
        if not is_remote_item(item, remote_dir):
            continue
        item.add_marker(pytest.mark.remote)
        if not enabled:
            item.add_marker(pytest.mark.skip(reason=SKIP_REASON))
            skipped += 1
    return skipped


def preflight(
    enabled: bool,
    load: Callable[[], RemoteEnv],
    probe: Callable[[RemoteEnv], None],
) -> RemoteEnv | None:
    """None when disabled (nothing is loaded or probed); else the env, or pytest.exit."""
    if not enabled:
        return None
    try:
        env = load()
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)
    try:
        probe(env)
    except (psycopg.OperationalError, httpx.TransportError, TimeoutError, OSError):
        pytest.exit(PAUSED_MESSAGE, returncode=2)
    return env
