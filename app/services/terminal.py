"""Terminal sessions: keep the final pipeline summary on the row, then drop the checkpoints.

Paused sessions never come here; they keep their checkpoints so they can resume.
"""

from typing import Any

import structlog

from app.container import Container

_log = structlog.get_logger("pipeline")


def finish_session(c: Container, user_id: str, thread_id: str, **fields: Any) -> None:
    """Write the terminal row (with `pipeline_summary`) before deleting the checkpoints.

    No summary (the reader failed) means the checkpoints stay for the prune sweep. The row update
    raises as before; a failed delete is only logged.
    """
    archived = True
    try:
        summary = c.pipeline.summary(thread_id)
        if summary is not None:
            fields["pipeline_summary"] = summary.model_dump(mode="json")
    except Exception as exc:
        archived = False
        _log.warning("pipeline.summary_archive_failed", error_type=type(exc).__name__)
    c.sessions.update(user_id, thread_id, **fields)
    if archived:
        drop_checkpoints(c, thread_id)


def drop_checkpoints(c: Container, thread_id: str) -> None:
    try:
        c.checkpointer.delete_thread(thread_id)
    except Exception as exc:
        _log.warning("pipeline.checkpoint_delete_failed", error_type=type(exc).__name__)
