"""Delete LangGraph checkpoints of finished, stale or orphaned sessions (ADR-007 sweep).

    uv run python scripts/prune_checkpoints.py                 # says what it would do; no DB
    uv run python scripts/prune_checkpoints.py --yes           # calls public.prune_checkpoints
    uv run python scripts/prune_checkpoints.py --yes --older "3 days"

Runs as app_backend through the container's pool (DB__DSN). The cron arrives in M6.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PRUNE_SQL = "select public.prune_checkpoints(%s::interval) as deleted"
DEFAULT_OLDER = "7 days"


def _build() -> Any:
    from app.container import build_container

    return build_container()


def prune(pool: Any, older: str) -> int:
    with pool.connection() as conn:
        row = conn.execute(PRUNE_SQL, (older,)).fetchone()
    return int(row["deleted"] if row else 0)


def main(argv: Sequence[str] | None = None, *, build: Callable[[], Any] = _build) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="actually delete (touches the DB)")
    parser.add_argument("--older", default=DEFAULT_OLDER, help="age cut-off, a Postgres interval")
    args = parser.parse_args(argv)
    if not args.yes:
        print(
            f"Would call public.prune_checkpoints('{args.older}'): deletes lg checkpoint rows "
            "of terminal, stale or orphaned sessions. Re-run with --yes to do it."
        )
        return 0
    container = build()
    try:
        count = prune(container.pool, args.older)
    finally:
        container.close()
    print(f"deleted {count} checkpoint rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
