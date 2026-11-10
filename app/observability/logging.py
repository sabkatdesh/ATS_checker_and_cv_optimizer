"""structlog + stdlib logging configured so every line is JSON and redacted."""

import logging
import sys
from typing import TextIO

import structlog
from structlog.typing import Processor

from app.config.settings import ObsSettings
from app.observability.redaction import redact_processor, safe_exc_processor

_MARK = "_cv_obs_handler"


def configure_logging(obs: ObsSettings, *, stream: TextIO | None = None) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        safe_exc_processor,
        redact_processor,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    renderer = (
        structlog.processors.JSONRenderer()
        if obs.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    setattr(handler, _MARK, True)
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(obs.log_level)
